"""`/api/v1` JSON routes — legacy stable contract (superseded by `/api/v2` for new integrations)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from repave_engine.audit_history import (
    AuditHistoryEntry,
    audit_filters_from_mapping,
    query_audit_entries,
)
from repave_engine.auth import (
    ROLE_ADMIN,
    ROLE_GENERATOR,
    ROLE_VIEWER,
    AuthConfig,
    authenticated_user,
    require_role,
    session_user,
)
from repave_engine.auth_context import current_acting_user
from repave_engine.blueprint import blueprint_dir, load_blueprint
from repave_engine.catalog_cost import enrich_catalog_entities_with_cost
from repave_engine.cost_actuals import cost_reader_configured, fetch_entity_cost_actuals_for_portal
from repave_engine.deployment_status import fetch_entity_deployment_status_for_portal
from repave_engine.entity_catalog import find_catalog_entity, observability_embed_url
from repave_engine.estate_map import build_estate_tiles
from repave_engine.execution_mode import (
    SYNC_GENERATE_UNAVAILABLE_DETAIL,
    worker_execution_mode_active,
)
from repave_engine.fleet import (
    FleetEntry,
    FleetError,
    normalize_repo_url,
    pins_from_repave_file,
    read_fleet,
    register_repo,
    unregister_repo,
)
from repave_engine.fleet_operator_status import load_operator_status_file
from repave_engine.fleet_view import build_fleet_rows
from repave_engine.generate_api import run_bundle_api, run_generate_api
from repave_engine.github_auth import resolve_github_access_token
from repave_engine.governance_annotations import build_governance_previews
from repave_engine.observability_slo import fetch_entity_slo_summary
from repave_engine.policy_catalog import enabled_rule_ids_for_profile, load_policy_catalog
from repave_engine.policy_selection import policy_input_defaults
from repave_engine.portal_context import (
    audit_file_or_http404,
    audit_portal_enabled,
    build_portal_catalog_entities,
    fleet_registry_path_or_http404,
    portal_fleet_context,
    portal_recent_activity,
)
from repave_engine.run_events import TERMINAL_EVENT_KINDS
from repave_engine.run_queue import RunQueue, RunQueueFullError, RunQueueShuttingDownError
from repave_engine.run_store import RunStatus
from repave_engine.run_submit import parse_run_target, submit_async_run
from repave_engine.settings import OutputConfig, load_fleet_config, load_portal_config
from repave_engine.standards_diff import standards_diff_for_pin
from repave_engine.verify import VerifyError, verify_target


def _require_roles(request: Request, auth_config: AuthConfig | None, *roles: str) -> None:
    if auth_config is None or not auth_config.service_enabled:
        return
    require_role(authenticated_user(request, auth_config), *roles)


def _run_queue(request: Request) -> RunQueue | None:
    return getattr(request.app.state, "run_queue", None)


def build_api_v1_router(
    *,
    repo_root: Path,
    output_config: OutputConfig,
    auth_config: AuthConfig | None,
) -> APIRouter:
    """Return the legacy v1 JSON router (mounted at ``/api/v1``)."""
    router = APIRouter(prefix="/api/v1", tags=["api-v1"])
    portal_config = load_portal_config(repo_root)

    @router.get("/estate")
    async def api_estate_map(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        enabled, fleet_repos, _namespace = portal_fleet_context(repo_root)
        if not enabled:
            raise HTTPException(
                status_code=404,
                detail="Fleet registry is not configured (set fleet.file or REPAVE_FLEET_FILE)",
            )
        audit_entries: tuple[AuditHistoryEntry, ...] = ()
        if audit_portal_enabled(repo_root):
            audit_entries = portal_recent_activity(repo_root, limit=80)
        tiles = build_estate_tiles(fleet_repos, audit_entries=audit_entries)
        return JSONResponse(
            {
                "count": len(tiles),
                "tiles": [tile.to_public_dict() for tile in tiles],
            }
        )

    @router.get("/governance/annotations/{blueprint_name}")
    async def api_governance_annotations(blueprint_name: str, request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        blueprint = load_blueprint(blueprint_dir(repo_root, blueprint_name), repo_root=repo_root)
        standards = standards_diff_for_pin(
            repo_root,
            standard_source=blueprint.standard_source,
            pinned_version=blueprint.standard_version,
        )
        try:
            catalog = load_policy_catalog(repo_root)
        except FileNotFoundError:
            catalog = None
        policy_defaults = policy_input_defaults(blueprint)
        profile = policy_defaults.get("policy_profile", "estate-default")
        enabled_ids = (
            enabled_rule_ids_for_profile(
                catalog,
                profile=profile,
                artifact_type=blueprint.artifact_type,
            )
            if catalog is not None
            else frozenset()
        )
        policy_rules = (
            tuple(rule for rule in catalog.rules if rule.id in enabled_ids)
            if catalog is not None
            else ()
        )
        previews = build_governance_previews(repo_root, standards, policy_rules)
        return JSONResponse(
            {
                "blueprint": blueprint_name,
                "standard": standards.standard_source,
                "pinned_version": standards.pinned_version,
                "previews": [item.to_public_dict() for item in previews],
            }
        )

    @router.post("/generate")
    async def api_generate(request: Request) -> JSONResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_GENERATOR, ROLE_ADMIN)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Expected JSON object")
        try:
            blueprint_name, bundle_name = parse_run_target(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        dry_run = bool(payload.get("dry_run", True))
        inputs_raw = payload.get("inputs", {})
        if not isinstance(inputs_raw, dict):
            raise HTTPException(status_code=400, detail="inputs must be an object")

        use_async = bool(payload.get("async", False))
        queue = _run_queue(request)
        if use_async:
            if queue is None:
                raise HTTPException(
                    status_code=503,
                    detail="Async generation is not enabled (durability.async_generation)",
                )
            client_request_id = str(payload.get("client_request_id", "")).strip() or None
            idempotency = request.headers.get("Idempotency-Key", "").strip() or None
            key = client_request_id or idempotency
            acting = user.subject if user else current_acting_user()
            try:
                record = submit_async_run(
                    queue,
                    payload=payload,
                    acting_user=acting,
                    client_request_id=key,
                )
            except RunQueueFullError as exc:
                raise HTTPException(status_code=429, detail=str(exc)) from exc
            except RunQueueShuttingDownError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            return JSONResponse(
                record.to_public_dict(),
                status_code=202 if record.status.value == "queued" else 200,
            )

        if worker_execution_mode_active(repo_root):
            raise HTTPException(status_code=409, detail=SYNC_GENERATE_UNAVAILABLE_DETAIL)

        github_token = None if dry_run else resolve_github_access_token()
        try:
            if bundle_name:
                body = run_bundle_api(
                    repo_root=repo_root,
                    output_config=output_config,
                    bundle_name=bundle_name,
                    inputs=inputs_raw,
                    dry_run=dry_run,
                    github_token=github_token,
                )
            else:
                body = run_generate_api(
                    repo_root=repo_root,
                    output_config=output_config,
                    blueprint_name=blueprint_name or "",
                    inputs=inputs_raw,
                    dry_run=dry_run,
                    github_token=github_token,
                )
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(body)

    @router.post("/runs")
    async def api_runs_submit(request: Request) -> JSONResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_GENERATOR, ROLE_ADMIN)
        queue = _run_queue(request)
        if queue is None:
            raise HTTPException(
                status_code=503,
                detail="Async runs require durability.async_generation",
            )
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Expected JSON object")
        kind = str(payload.get("kind", "")).strip()
        if kind != "live_plan" and kind != "environment_vend":
            try:
                parse_run_target(payload)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            inputs_raw = payload.get("inputs", {})
            if not isinstance(inputs_raw, dict):
                raise HTTPException(status_code=400, detail="inputs must be an object")
        client_request_id = str(payload.get("client_request_id", "")).strip() or None
        idempotency = request.headers.get("Idempotency-Key", "").strip() or None
        acting = user.subject if user else current_acting_user()
        try:
            record = submit_async_run(
                queue,
                payload=payload,
                acting_user=acting,
                client_request_id=client_request_id or idempotency,
                repo_root=repo_root,
            )
        except RunQueueFullError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except RunQueueShuttingDownError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(record.to_public_dict(), status_code=202)

    @router.get("/runs")
    async def api_runs_list(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        queue = _run_queue(request)
        if queue is None:
            raise HTTPException(status_code=503, detail="Async runs are not enabled")
        status_raw = request.query_params.get("status", "").strip().lower()
        limit_raw = request.query_params.get("limit", "50").strip()
        try:
            limit = int(limit_raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="limit must be an integer") from exc
        status_filter: RunStatus | None = None
        if status_raw:
            try:
                status_filter = RunStatus(status_raw)
            except ValueError as exc:
                valid = ", ".join(item.value for item in RunStatus)
                raise HTTPException(
                    status_code=400,
                    detail=f"status must be one of: {valid}",
                ) from exc
        records = queue.list_runs(status=status_filter, limit=limit)
        return JSONResponse(
            {
                "count": len(records),
                "runs": [record.to_public_dict() for record in records],
            }
        )

    @router.get("/runs/{run_id}")
    async def api_runs_get(run_id: str, request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        queue = _run_queue(request)
        if queue is None:
            raise HTTPException(status_code=503, detail="Async runs are not enabled")
        record = queue.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return JSONResponse(record.to_public_dict())

    @router.post("/runs/{run_id}/replay")
    async def api_runs_replay(run_id: str, request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_ADMIN)
        queue = _run_queue(request)
        if queue is None:
            raise HTTPException(status_code=503, detail="Async runs are not enabled")
        try:
            record = queue.replay(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(record.to_public_dict(), status_code=202)

    @router.get("/runs/{run_id}/events")
    async def api_run_events(run_id: str, request: Request) -> StreamingResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        queue = _run_queue(request)
        if queue is None or queue.event_store is None:
            raise HTTPException(status_code=503, detail="Run events are not enabled")
        record = queue.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Run not found")

        last_event_id = request.headers.get("Last-Event-ID", "").strip()
        after_seq = int(last_event_id) if last_event_id.isdigit() else 0
        event_store = queue.event_store

        async def event_stream() -> AsyncIterator[str]:
            nonlocal after_seq
            while True:
                events = await asyncio.to_thread(
                    event_store.list_from,
                    run_id,
                    after_seq=after_seq,
                )
                if not events:
                    events = await asyncio.to_thread(
                        event_store.wait_for_events,
                        run_id,
                        after_seq=after_seq,
                        timeout_seconds=15.0,
                    )
                if not events:
                    yield ": heartbeat\n\n"
                    current = queue.get(run_id)
                    if current is not None and current.status.value in {
                        "succeeded",
                        "failed",
                        "dead_letter",
                    }:
                        return
                    continue
                for event in events:
                    after_seq = event.seq
                    payload = json.dumps(event.to_sse_data(), separators=(",", ":"))
                    yield f"id: {event.seq}\ndata: {payload}\n\n"
                    if event.kind in TERMINAL_EVENT_KINDS:
                        return

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @router.post("/verify")
    async def api_verify(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="JSON body required") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="JSON object required")

        path_raw = str(body.get("path") or body.get("repo_url") or "").strip()
        if not path_raw:
            raise HTTPException(status_code=400, detail="path or repo_url is required")

        blueprint_override = str(body.get("blueprint", "")).strip() or None
        require_run = bool(body.get("require_run", False))
        ref = str(body.get("ref", "")).strip() or None
        try:
            outcome = verify_target(
                path_raw,
                repo_root,
                blueprint_name=blueprint_override,
                require_run=require_run,
                ref=ref,
            )
        except VerifyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        payload: dict[str, Any] = outcome.to_json_dict()
        status = 200 if outcome.ok else 422
        return JSONResponse(payload, status_code=status)

    @router.get("/catalog/entities")
    async def api_catalog_entities(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        cost_configured = cost_reader_configured(
            cost_reader=portal_config.cost_reader,
            cost_actuals_url=portal_config.cost_actuals_url,
        )
        entities = list(
            enrich_catalog_entities_with_cost(
                build_portal_catalog_entities(
                    repo_root,
                    output_config,
                    cost_actuals_configured=cost_configured,
                ),
                portal_config,
            )
        )
        return JSONResponse(
            {
                "count": len(entities),
                "entities": [item.to_public_dict() for item in entities],
            }
        )

    @router.get("/catalog/entities/{entity_id}")
    async def api_catalog_entity(request: Request, entity_id: str) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        cost_configured = cost_reader_configured(
            cost_reader=portal_config.cost_reader,
            cost_actuals_url=portal_config.cost_actuals_url,
        )
        entities = build_portal_catalog_entities(
            repo_root,
            output_config,
            cost_actuals_configured=cost_configured,
        )
        entity = find_catalog_entity(entities, entity_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="Entity not found")
        body = entity.to_public_dict()
        obs_url = observability_embed_url(portal_config.observability_dashboard_url, entity)
        if obs_url:
            body["observability_url"] = obs_url
        slo = fetch_entity_slo_summary(portal_config.observability_slo_url, entity)
        if slo is not None:
            body["slo_summary"] = slo.to_public_dict()
        cost = fetch_entity_cost_actuals_for_portal(portal_config, entity)
        if cost is not None:
            body["cost_actuals"] = cost.to_public_dict()
        deployment = fetch_entity_deployment_status_for_portal(portal_config, entity)
        if deployment is not None:
            body["deployment_status"] = deployment.to_public_dict()
        return JSONResponse(body)

    @router.get("/audit")
    async def api_audit_query(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        audit_path = audit_file_or_http404(repo_root)
        raw_filters = {key: str(value) for key, value in request.query_params.items()}
        filters = audit_filters_from_mapping(raw_filters)
        result = query_audit_entries(audit_path, filters, repo_root=repo_root)
        return JSONResponse(
            {
                "total": result.total,
                "limit": result.limit,
                "offset": result.offset,
                "entries": [entry.to_public_dict() for entry in result.entries],
            }
        )

    @router.get("/fleet")
    async def api_fleet_list(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        fleet_cfg = load_fleet_config(repo_root)
        if fleet_cfg is None or not fleet_cfg.enabled:
            raise HTTPException(
                status_code=404,
                detail="Fleet registry is not configured (set fleet.file or REPAVE_FLEET_FILE)",
            )
        entries = read_fleet(fleet_cfg.file, repo_root=repo_root)
        operator_by = (
            load_operator_status_file(fleet_cfg.operator_status_file)
            if fleet_cfg.operator_status_file is not None
            else {}
        )
        repos = build_fleet_rows(
            entries,
            operator_by_url=operator_by,
            namespace=fleet_cfg.gitops_namespace,
        )
        return JSONResponse({"count": len(repos), "repos": repos})

    @router.post("/fleet")
    async def api_fleet_register(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_ADMIN)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Expected JSON object")

        repo_url = str(payload.get("repo_url", "")).strip()
        if not repo_url:
            raise HTTPException(status_code=400, detail="repo_url is required")

        pins = {
            "blueprint_name": str(payload.get("blueprint_name", "")).strip(),
            "blueprint_version": str(payload.get("blueprint_version", "")).strip(),
            "standard_source": str(payload.get("standard_source", "")).strip(),
            "standard_version": str(payload.get("standard_version", "")).strip(),
        }
        local_path = str(payload.get("path", "")).strip()
        try:
            if local_path:
                pins.update(pins_from_repave_file(Path(local_path).expanduser().resolve()))
            if not pins["blueprint_name"]:
                raise FleetError("blueprint_name is required when path is not supplied")
            entry = register_repo(
                fleet_registry_path_or_http404(repo_root),
                FleetEntry(
                    repo_url=repo_url,
                    blueprint_name=pins["blueprint_name"],
                    blueprint_version=pins["blueprint_version"],
                    standard_source=pins["standard_source"],
                    standard_version=pins["standard_version"],
                    owner=str(payload.get("owner", "")).strip(),
                    registered_by=current_acting_user(),
                ),
                repo_root=repo_root,
            )
        except FleetError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"registered": entry.to_dict()}, status_code=201)

    @router.delete("/fleet")
    async def api_fleet_unregister(request: Request, repo_url: str = "") -> JSONResponse:
        _require_roles(request, auth_config, ROLE_ADMIN)
        if not repo_url.strip():
            raise HTTPException(status_code=400, detail="repo_url query parameter is required")
        try:
            removed = unregister_repo(
                fleet_registry_path_or_http404(repo_root),
                repo_url,
                repo_root=repo_root,
            )
        except FleetError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not removed:
            raise HTTPException(status_code=404, detail=f"{repo_url} is not registered")
        return JSONResponse({"unregistered": normalize_repo_url(repo_url)})

    return router
