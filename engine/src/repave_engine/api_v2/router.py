"""`/api/v2` routes — stable JSON contract for portal, operator, and integrations."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from repave_engine import __version__
from repave_engine.api_read_models import (
    FleetRegistryUnavailableError,
    build_estate_read_model,
    build_governance_annotations_read_model,
)
from repave_engine.audit_history import audit_filters_from_mapping, query_audit_entries
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
from repave_engine.catalog_cost import enrich_catalog_entities_with_cost
from repave_engine.cost_actuals import cost_reader_configured, fetch_entity_cost_actuals_for_portal
from repave_engine.deployment_status import fetch_entity_deployment_status_for_portal
from repave_engine.entity_catalog import find_catalog_entity, observability_embed_url
from repave_engine.environment_reclaim import EnvironmentReclaimError, reclaim_expired_environments
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
from repave_engine.github_client import GitHubError
from repave_engine.import_rules import parse_path_overrides
from repave_engine.observability_slo import fetch_entity_slo_summary
from repave_engine.portal_context import (
    audit_file_or_http404,
    build_portal_catalog_entities,
    fleet_registry_path_or_http404,
)
from repave_engine.pr_conventions import add_pull_request_title, load_pull_request_conventions
from repave_engine.repo_add import (
    NotGovernedError,
    RepoAddError,
    apply_add,
    plan_add,
    record_add,
    suggested_add_branch,
)
from repave_engine.repo_import import (
    AlreadyGovernedError,
    RepoImportError,
    import_repository,
    import_repository_batch,
    plan_import,
    plan_import_batch,
    record_import,
)
from repave_engine.run_events import TERMINAL_EVENT_KINDS
from repave_engine.run_queue import RunQueue, RunQueueFullError, RunQueueShuttingDownError
from repave_engine.run_store import RunStatus
from repave_engine.run_submit import parse_run_target, submit_async_run
from repave_engine.settings import (
    OutputConfig,
    load_environment_vending_config,
    load_fleet_config,
    load_portal_config,
)
from repave_engine.upgrade_api import (
    UpgradeTargetError,
    resolve_upgrade_target,
    run_apply_upgrade,
    run_plan_upgrade,
)
from repave_engine.verify import VerifyError, verify_target

V2_ENDPOINTS: tuple[str, ...] = (
    "GET /api/v2",
    "POST /api/v2/generate",
    "POST /api/v2/runs",
    "GET /api/v2/runs",
    "GET /api/v2/runs/{run_id}",
    "POST /api/v2/runs/{run_id}/replay",
    "GET /api/v2/runs/{run_id}/events",
    "POST /api/v2/upgrades/plan",
    "POST /api/v2/upgrades/apply",
    "POST /api/v2/imports/plan",
    "POST /api/v2/imports/apply",
    "POST /api/v2/imports/batch/plan",
    "POST /api/v2/imports/batch/apply",
    "POST /api/v2/components/plan",
    "POST /api/v2/components/apply",
    "POST /api/v2/verify",
    "GET /api/v2/catalog/entities",
    "GET /api/v2/catalog/entities/{entity_id}",
    "GET /api/v2/audit",
    "GET /api/v2/estate",
    "GET /api/v2/governance/annotations/{blueprint_name}",
    "GET /api/v2/fleet",
    "POST /api/v2/fleet",
    "DELETE /api/v2/fleet",
    "POST /api/v2/environments/reclaim",
)


def _require_roles(request: Request, auth_config: AuthConfig | None, *roles: str) -> None:
    if auth_config is None or not auth_config.service_enabled:
        return
    require_role(authenticated_user(request, auth_config), *roles)


def _run_queue(request: Request) -> RunQueue | None:
    return getattr(request.app.state, "run_queue", None)


def _acting_user(request: Request) -> str:
    user = session_user(request)
    return user.subject if user is not None else current_acting_user()


async def _parse_json_object(request: Request) -> dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Expected JSON object")
    return payload


def build_api_v2_router(
    *,
    repo_root: Path,
    output_config: OutputConfig,
    auth_config: AuthConfig | None,
) -> APIRouter:
    """Return the Phase 3 v2 router (mounted at ``/api/v2``)."""
    router = APIRouter(prefix="/api/v2", tags=["api-v2"])
    portal_config = load_portal_config(repo_root)

    @router.get("")
    async def api_v2_metadata() -> JSONResponse:
        return JSONResponse(
            {
                "api_version": "v2",
                "engine_version": __version__,
                "endpoints": list(V2_ENDPOINTS),
            }
        )

    @router.get("/estate")
    async def api_v2_estate(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        try:
            body = build_estate_read_model(repo_root)
        except FleetRegistryUnavailableError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return JSONResponse(body)

    @router.get("/governance/annotations/{blueprint_name}")
    async def api_v2_governance_annotations(
        blueprint_name: str,
        request: Request,
    ) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        return JSONResponse(build_governance_annotations_read_model(repo_root, blueprint_name))

    @router.post("/generate")
    async def api_v2_generate(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_GENERATOR, ROLE_ADMIN)
        payload = await _parse_json_object(request)
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
            try:
                record = submit_async_run(
                    queue,
                    payload=payload,
                    acting_user=_acting_user(request),
                    client_request_id=client_request_id or idempotency,
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
    async def api_v2_runs_submit(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_GENERATOR, ROLE_ADMIN)
        queue = _run_queue(request)
        if queue is None:
            raise HTTPException(
                status_code=503,
                detail="Async runs require durability.async_generation",
            )
        payload = await _parse_json_object(request)
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
        try:
            record = submit_async_run(
                queue,
                payload=payload,
                acting_user=_acting_user(request),
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
    async def api_v2_runs_list(request: Request) -> JSONResponse:
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
    async def api_v2_runs_get(run_id: str, request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        queue = _run_queue(request)
        if queue is None:
            raise HTTPException(status_code=503, detail="Async runs are not enabled")
        record = queue.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return JSONResponse(record.to_public_dict())

    @router.post("/runs/{run_id}/replay")
    async def api_v2_runs_replay(run_id: str, request: Request) -> JSONResponse:
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
    async def api_v2_run_events(run_id: str, request: Request) -> StreamingResponse:
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

    @router.post("/upgrades/plan")
    async def api_v2_upgrades_plan(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_GENERATOR, ROLE_ADMIN)
        payload = await _parse_json_object(request)
        try:
            target = resolve_upgrade_target(
                target_repo=str(payload.get("target_repo", "")),
                repo_url=str(payload.get("repo_url", "")).strip() or None,
            )
        except UpgradeTargetError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        blueprint_name = str(payload.get("blueprint", "")).strip() or None
        staging_root_raw = str(payload.get("staging_root", "")).strip()
        staging_root = Path(staging_root_raw) if staging_root_raw else None
        try:
            result = run_plan_upgrade(
                repo_root=repo_root,
                target=target,
                blueprint_name=blueprint_name,
                staging_root=staging_root,
            )
        except (ValueError, FileNotFoundError, OSError, UpgradeTargetError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(result.to_json_dict())

    @router.post("/upgrades/apply")
    async def api_v2_upgrades_apply(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_GENERATOR, ROLE_ADMIN)
        payload = await _parse_json_object(request)
        try:
            target = resolve_upgrade_target(
                target_repo=str(payload.get("target_repo", "")),
                repo_url=str(payload.get("repo_url", "")).strip() or None,
            )
        except UpgradeTargetError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        git_branch = str(payload.get("git_branch", "")).strip()
        commit_message = str(payload.get("commit_message", "")).strip()
        if not git_branch:
            raise HTTPException(status_code=400, detail="git_branch is required")
        if not commit_message:
            raise HTTPException(status_code=400, detail="commit_message is required")
        blueprint_name = str(payload.get("blueprint", "")).strip() or None
        preserve_local = bool(payload.get("preserve_local", False))
        push = bool(payload.get("push", False))
        staging_root_raw = str(payload.get("staging_root", "")).strip()
        staging_root = Path(staging_root_raw) if staging_root_raw else None
        try:
            result, pushed = run_apply_upgrade(
                repo_root=repo_root,
                target=target,
                blueprint_name=blueprint_name,
                staging_root=staging_root,
                git_branch=git_branch,
                commit_message=commit_message,
                preserve_local=preserve_local,
                push=push,
            )
        except (ValueError, FileNotFoundError, OSError, UpgradeTargetError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        body = result.to_json_dict()
        if pushed:
            body["pushed"] = True
        return JSONResponse(body)

    def _import_request(
        payload: dict[str, Any],
    ) -> tuple[str, str | None, str | None, bool, dict[str, str], bool]:
        target = str(payload.get("target_repo", "")).strip()
        if not target:
            raise HTTPException(status_code=400, detail="target_repo is required")
        blueprint_name = str(payload.get("blueprint", "")).strip() or None
        ref = str(payload.get("ref", "")).strip() or None
        with_gates = bool(payload.get("with_gates", True))
        force_clone = bool(payload.get("force_clone", False))
        overrides = parse_path_overrides(payload.get("overrides"))
        return target, blueprint_name, ref, with_gates, overrides, force_clone

    @router.post("/imports/plan")
    async def api_v2_imports_plan(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_GENERATOR, ROLE_ADMIN)
        payload = await _parse_json_object(request)
        target, blueprint_name, ref, with_gates, overrides, force_clone = _import_request(payload)
        try:
            plan = plan_import(
                target,
                repo_root,
                blueprint_name=blueprint_name,
                values=payload.get("inputs") if isinstance(payload.get("inputs"), dict) else None,
                path_overrides=overrides,
                ref=ref,
                with_gates=with_gates,
                force_clone=force_clone,
            )
        except AlreadyGovernedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (RepoImportError, FileNotFoundError, OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(plan.to_json_dict())

    @router.post("/imports/apply")
    async def api_v2_imports_apply(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_GENERATOR, ROLE_ADMIN)
        payload = await _parse_json_object(request)
        target, blueprint_name, ref, with_gates, overrides, _force_clone = _import_request(payload)
        token = resolve_github_access_token(str(payload.get("github_token", "")).strip() or None)
        if not token:
            raise HTTPException(
                status_code=400,
                detail="a GitHub token is required to open an import pull request",
            )
        try:
            result = import_repository(
                target,
                repo_root,
                github_token=token,
                blueprint_name=blueprint_name,
                values=payload.get("inputs") if isinstance(payload.get("inputs"), dict) else None,
                path_overrides=overrides,
                ref=ref,
                git_branch=str(payload.get("git_branch", "")).strip(),
                base_branch=str(payload.get("base_branch", "")).strip(),
                with_gates=with_gates,
            )
        except AlreadyGovernedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (RepoImportError, GitHubError, FileNotFoundError, OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        body = result.to_json_dict()
        body["fleet_registered"] = record_import(
            repo_root,
            result,
            acting_user=_acting_user(request),
        )
        return JSONResponse(body)

    @router.post("/imports/batch/plan")
    async def api_v2_imports_batch_plan(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_GENERATOR, ROLE_ADMIN)
        payload = await _parse_json_object(request)
        targets_raw = payload.get("targets")
        targets = (
            [str(item).strip() for item in targets_raw if str(item).strip()]
            if isinstance(targets_raw, list)
            else [line.strip() for line in str(targets_raw or "").splitlines() if line.strip()]
        )
        org = str(payload.get("org", "")).strip()
        topic = str(payload.get("topic", "")).strip()
        blueprint_name = str(payload.get("blueprint", "")).strip() or None
        with_gates = bool(payload.get("with_gates", True))
        try:
            batch = plan_import_batch(
                targets,
                repo_root,
                blueprint_name=blueprint_name,
                values=payload.get("inputs") if isinstance(payload.get("inputs"), dict) else None,
                path_overrides=parse_path_overrides(payload.get("overrides")),
                git_token=resolve_github_access_token(
                    str(payload.get("github_token", "")).strip() or None
                ),
                org=org,
                topic=topic,
                with_gates=with_gates,
            )
        except RepoImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(batch.to_json_dict())

    @router.post("/imports/batch/apply")
    async def api_v2_imports_batch_apply(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_GENERATOR, ROLE_ADMIN)
        payload = await _parse_json_object(request)
        targets_raw = payload.get("targets")
        targets = (
            [str(item).strip() for item in targets_raw if str(item).strip()]
            if isinstance(targets_raw, list)
            else [line.strip() for line in str(targets_raw or "").splitlines() if line.strip()]
        )
        token = resolve_github_access_token(str(payload.get("github_token", "")).strip() or None)
        if not token:
            raise HTTPException(
                status_code=400, detail="a GitHub token is required for batch apply"
            )
        try:
            batch_result = import_repository_batch(
                targets,
                repo_root,
                github_token=token,
                blueprint_name=str(payload.get("blueprint", "")).strip() or None,
                values=payload.get("inputs") if isinstance(payload.get("inputs"), dict) else None,
                org=str(payload.get("org", "")).strip(),
                topic=str(payload.get("topic", "")).strip(),
                with_gates=bool(payload.get("with_gates", True)),
            )
        except RepoImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        body = batch_result.to_json_dict()
        body["fleet_registered"] = [
            record_import(repo_root, item, acting_user=_acting_user(request))
            for item in batch_result.items
        ]
        return JSONResponse(body)

    @router.post("/components/plan")
    async def api_v2_components_plan(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_GENERATOR, ROLE_ADMIN)
        payload = await _parse_json_object(request)
        target = str(payload.get("target_repo", "")).strip()
        blueprint_name = str(payload.get("blueprint", "")).strip()
        if not target:
            raise HTTPException(status_code=400, detail="target_repo is required")
        if not blueprint_name:
            raise HTTPException(status_code=400, detail="blueprint is required")
        try:
            plan = plan_add(
                target,
                repo_root,
                blueprint_name=blueprint_name,
                values=payload.get("inputs") if isinstance(payload.get("inputs"), dict) else None,
                component_id=str(payload.get("component_id", "")).strip() or None,
                force=bool(payload.get("force", False)),
            )
        except NotGovernedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RepoAddError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(plan.to_json_dict())

    @router.post("/components/apply")
    async def api_v2_components_apply(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_GENERATOR, ROLE_ADMIN)
        payload = await _parse_json_object(request)
        target = str(payload.get("target_repo", "")).strip()
        blueprint_name = str(payload.get("blueprint", "")).strip()
        if not target:
            raise HTTPException(status_code=400, detail="target_repo is required")
        if not blueprint_name:
            raise HTTPException(status_code=400, detail="blueprint is required")
        try:
            plan = plan_add(
                target,
                repo_root,
                blueprint_name=blueprint_name,
                values=payload.get("inputs") if isinstance(payload.get("inputs"), dict) else None,
                component_id=str(payload.get("component_id", "")).strip() or None,
                force=bool(payload.get("force", False)),
            )
        except NotGovernedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RepoAddError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not plan.ok:
            raise HTTPException(status_code=409, detail={"conflicts": list(plan.conflicts)})
        conventions = load_pull_request_conventions(repo_root)
        git_branch = str(payload.get("git_branch", "")).strip() or suggested_add_branch(
            plan, conventions_prefix=conventions.branch_prefix_add
        )
        commit_message = add_pull_request_title(plan.blueprint_name, plan.component_id)
        import tempfile

        with tempfile.TemporaryDirectory(prefix="repave-add-apply-") as temp_name:
            try:
                result = apply_add(
                    Path(target).expanduser().resolve(),
                    repo_root,
                    plan,
                    staging_dir=Path(temp_name),
                    git_branch=git_branch,
                    commit_message=commit_message,
                )
            except RepoAddError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        body = {
            "git_branch": result.git_branch,
            "commit_sha": result.commit_sha,
            "plan": plan.to_json_dict(),
        }
        record_add(repo_root, result, acting_user=_acting_user(request))
        return JSONResponse(body)

    @router.post("/verify")
    async def api_v2_verify(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        payload = await _parse_json_object(request)
        path_raw = str(payload.get("path") or payload.get("repo_url") or "").strip()
        if not path_raw:
            raise HTTPException(status_code=400, detail="path or repo_url is required")
        blueprint_override = str(payload.get("blueprint", "")).strip() or None
        require_run = bool(payload.get("require_run", False))
        ref = str(payload.get("ref", "")).strip() or None
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
        body: dict[str, Any] = outcome.to_json_dict()
        status = 200 if outcome.ok else 422
        return JSONResponse(body, status_code=status)

    @router.get("/catalog/entities")
    async def api_v2_catalog_entities(request: Request) -> JSONResponse:
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
    async def api_v2_catalog_entity(request: Request, entity_id: str) -> JSONResponse:
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
    async def api_v2_audit_query(request: Request) -> JSONResponse:
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
    async def api_v2_fleet_list(request: Request) -> JSONResponse:
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
    async def api_v2_fleet_register(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_ADMIN)
        payload = await _parse_json_object(request)
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
    async def api_v2_fleet_unregister(request: Request, repo_url: str = "") -> JSONResponse:
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

    @router.post("/environments/reclaim")
    async def api_v2_environments_reclaim(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_ADMIN)
        vend_cfg = load_environment_vending_config(repo_root)
        if vend_cfg is None:
            raise HTTPException(
                status_code=503,
                detail="environment_vending is not enabled",
            )
        payload = await _parse_json_object(request)
        dry_run = bool(payload.get("dry_run", False))
        stack_name = str(payload.get("stack_name", "")).strip() or None
        github_token = resolve_github_access_token(None) if not dry_run else None
        if not dry_run and not github_token:
            raise HTTPException(
                status_code=503,
                detail="GITHUB_TOKEN is required unless dry_run is true",
            )
        try:
            summary = reclaim_expired_environments(
                repo_root=repo_root,
                config=vend_cfg,
                github_token=github_token,
                dry_run=dry_run,
                stack_name=stack_name,
            )
        except EnvironmentReclaimError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(summary.to_public_dict())

    return router
