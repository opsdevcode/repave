"""`/api/v2` routes — stable JSON contract for portal, operator, and integrations."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from repave_engine import __version__
from repave_engine.api_read_models import (
    FleetRegistryUnavailableError,
    build_estate_read_model,
    build_governance_annotations_read_model,
)
from repave_engine.assistant import (
    is_assistant_enabled,
    match_confirmed_blueprint,
    resolve_catalog_intent,
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
from repave_engine.blueprint import (
    group_blueprints_by_artifact,
    list_catalog_blueprints,
    resolve_bundle_dir,
)
from repave_engine.bundle import list_bundles, load_bundle
from repave_engine.bundle_topology import build_bundle_topology, topology_public
from repave_engine.catalog_cost import enrich_entity_cost
from repave_engine.catalog_deployment import (
    deployment_scorecard_for_entity,
)
from repave_engine.component_kinds import ComponentVendError, load_component_kinds
from repave_engine.component_reclaim import ComponentReclaimError, reclaim_expired_components
from repave_engine.component_vend import resolve_component_vend_fields
from repave_engine.cost_actuals import cost_reader_configured
from repave_engine.developer_lab import is_developer_lab_enabled
from repave_engine.entity_catalog import (
    find_catalog_entity,
    observability_embed_url,
)
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
from repave_engine.github_auth import github_credentials_configured, resolve_github_access_token
from repave_engine.github_client import GitHubError
from repave_engine.github_inventory import GitHubInventoryError
from repave_engine.github_repo_provision import list_org_teams, list_team_members
from repave_engine.import_rules import parse_path_overrides
from repave_engine.observability_slo import fetch_entity_slo_summary
from repave_engine.org_import_scan import DEFAULT_SCAN_LIMIT, scan_github_org
from repave_engine.portal_context import (
    audit_file_or_http404,
    build_enriched_portal_catalog_entities,
    build_library_catalog_payload,
    build_portal_catalog_entities,
    fleet_registry_path_or_http404,
)
from repave_engine.portal_generate import public_run_dict_with_preview_files
from repave_engine.portal_platform import (
    build_platform_initiatives_page,
    build_platform_maturity_page,
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
    parse_target_blueprints,
    plan_import,
    plan_import_batch,
    record_import,
    resolve_batch_import_blueprint_options,
)
from repave_engine.run_events import TERMINAL_EVENT_KINDS
from repave_engine.run_queue import RunQueue, RunQueueFullError, RunQueueShuttingDownError
from repave_engine.run_store import RunStatus
from repave_engine.run_submit import parse_run_target, submit_async_run
from repave_engine.safe_paths import trusted_path
from repave_engine.service_catalog_overlay import (
    entity_initiative_statuses,
    filter_entities_by_team,
    filter_entities_for_user,
)
from repave_engine.settings import (
    OutputConfig,
    load_component_vending_config,
    load_environment_vending_config,
    load_fleet_config,
    load_portal_config,
    load_service_catalog_config,
)
from repave_engine.upgrade_api import (
    UpgradeTargetError,
    resolve_upgrade_target,
    run_apply_upgrade,
    run_plan_upgrade,
)
from repave_engine.verify import VerifyError, verify_target
from repave_engine.workload_profiles import (
    SandboxVendError,
    load_deployment_sets,
    load_workload_profiles,
    resolve_sandbox_vend_payload,
)

logger = logging.getLogger(__name__)

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
    "GET /api/v2/component-kinds",
    "POST /api/v2/components/vend",
    "POST /api/v2/components/reclaim",
    "POST /api/v2/verify",
    "GET /api/v2/catalog/entities",
    "GET /api/v2/catalog/entities/{entity_id}",
    "GET /api/v2/catalog/blueprints",
    "POST /api/v2/assistant/resolve",
    "POST /api/v2/assistant/confirm",
    "GET /api/v2/bundles",
    "GET /api/v2/bundles/{name}",
    "GET /api/v2/library",
    "GET /api/v2/audit",
    "GET /api/v2/estate",
    "GET /api/v2/governance/annotations/{blueprint_name}",
    "GET /api/v2/github/teams",
    "GET /api/v2/github/teams/{slug}/members",
    "POST /api/v2/github/org-scan",
    "GET /api/v2/fleet",
    "POST /api/v2/fleet",
    "DELETE /api/v2/fleet",
    "GET /api/v2/deployment-sets",
    "POST /api/v2/environments/vend",
    "POST /api/v2/environments/reclaim",
    "GET /api/v2/platform/metrics",
    "GET /api/v2/platform/compliance",
    "GET /api/v2/platform/value-stream",
    "GET /api/v2/platform/roadmap-evidence",
    "GET /api/v2/platform/maturity",
    "GET /api/v2/platform/initiatives",
    "POST /api/v2/platform/initiatives",
    "PATCH /api/v2/platform/initiatives/{initiative_id}",
    "DELETE /api/v2/platform/initiatives/{initiative_id}",
    "GET /api/v2/platform/feedback",
    "POST /api/v2/platform/feedback",
    "GET /api/v2/platform/finops/export",
    "GET /api/v2/platform/ops",
    "GET /api/v2/platform/standards",
    "GET /api/v2/platform/campaigns",
    "POST /api/v2/platform/campaigns/{namespace}/{name}/paused",
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

    @router.get("/github/teams")
    async def api_v2_github_teams(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        org = output_config.github_org.strip()
        if not org:
            raise HTTPException(
                status_code=400,
                detail="github_org is not configured; set output.github_org or REPAVE_GITHUB_ORG",
            )
        token = resolve_github_access_token()
        if not token:
            raise HTTPException(
                status_code=503,
                detail=(
                    "GitHub credentials are not configured; set GITHUB_TOKEN or "
                    "GitHub App env vars to list org teams"
                ),
            )
        try:
            teams = list_org_teams(org, token)
        except GitHubError as exc:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Failed to list teams for org {org}: HTTP {exc.status}. "
                    "Ensure the token can read organization teams."
                ),
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(
            {
                "org": org,
                "teams": [
                    {
                        "slug": team.slug,
                        "name": team.name,
                        "description": team.description,
                    }
                    for team in teams
                ],
            }
        )

    @router.get("/github/teams/{slug}/members")
    async def api_v2_github_team_members(request: Request, slug: str) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        org = output_config.github_org.strip()
        if not org:
            raise HTTPException(
                status_code=400,
                detail="github_org is not configured; set output.github_org or REPAVE_GITHUB_ORG",
            )
        team_slug = slug.strip()
        if not team_slug:
            raise HTTPException(status_code=400, detail="team slug is required")
        token = resolve_github_access_token()
        if not token:
            raise HTTPException(
                status_code=503,
                detail=(
                    "GitHub credentials are not configured; set GITHUB_TOKEN or "
                    "GitHub App env vars to list team members"
                ),
            )
        try:
            members = list_team_members(org, team_slug, token)
        except GitHubError as exc:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Failed to list members of team {team_slug!r} in org {org}: "
                    f"HTTP {exc.status}. Ensure the token can read organization teams."
                ),
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(
            {
                "org": org,
                "team": team_slug,
                "members": list(members),
                "count": len(members),
            }
        )

    @router.post("/github/org-scan")
    async def api_v2_github_org_scan(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_GENERATOR, ROLE_ADMIN)
        payload = await _parse_json_object(request)
        org = str(payload.get("org", "")).strip()
        if not org:
            raise HTTPException(status_code=400, detail="org is required")
        token = resolve_github_access_token(str(payload.get("github_token", "")).strip() or None)
        if not token:
            raise HTTPException(
                status_code=503,
                detail=(
                    "GitHub credentials are not configured; set GITHUB_TOKEN or "
                    "GitHub App env vars to scan organization repositories"
                ),
            )
        families_raw = payload.get("families")
        families: list[str] | None = None
        if isinstance(families_raw, list):
            families = [str(item).strip() for item in families_raw if str(item).strip()]
        skip_governed = bool(payload.get("skip_governed", True))
        min_confidence_raw = payload.get("min_confidence", 0)
        try:
            min_confidence = float(min_confidence_raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="min_confidence must be a number") from None
        limit_raw = payload.get("limit", DEFAULT_SCAN_LIMIT)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="limit must be an integer") from None
        if limit <= 0:
            raise HTTPException(status_code=400, detail="limit must be positive")
        topic = str(payload.get("topic", "")).strip()
        language = str(payload.get("language", "")).strip()
        pushed_since = str(payload.get("pushed_since", "")).strip()
        exclude_archived = bool(payload.get("exclude_archived", True))
        exclude_forks = bool(payload.get("exclude_forks", True))
        use_async = bool(payload.get("async", False))
        queue = _run_queue(request)
        if use_async:
            if queue is None:
                raise HTTPException(
                    status_code=503,
                    detail="Async org scan requires durability.async_generation",
                )
            scan_inputs: dict[str, Any] = {
                "org": org,
                "families": families or [],
                "skip_governed": skip_governed,
                "min_confidence": min_confidence,
                "limit": limit,
                "topic": topic,
                "language": language,
                "pushed_since": pushed_since,
                "exclude_archived": exclude_archived,
                "exclude_forks": exclude_forks,
            }
            try:
                record = submit_async_run(
                    queue,
                    payload={"kind": "org_scan", "inputs": scan_inputs},
                    acting_user=_acting_user(request),
                    repo_root=repo_root,
                )
            except RunQueueFullError as exc:
                raise HTTPException(status_code=429, detail=str(exc)) from exc
            except RunQueueShuttingDownError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return JSONResponse(record.to_public_dict(), status_code=202)
        try:
            result = scan_github_org(
                org,
                repo_root,
                token,
                families=frozenset(families or ()),
                skip_governed=skip_governed,
                min_confidence=min_confidence,
                limit=limit,
                topic=topic,
                language=language,
                pushed_since=pushed_since,
                exclude_archived=exclude_archived,
                exclude_forks=exclude_forks,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except GitHubInventoryError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return JSONResponse(result.to_json_dict())

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
        platform_kinds = (
            "live_plan",
            "environment_vend",
            "environment_reclaim",
            "fleet_drift_confirm",
            "org_scan",
        )
        if kind not in platform_kinds:
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
        return JSONResponse(public_run_dict_with_preview_files(record, repo_root=repo_root))

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
        blueprint_raw = str(payload.get("blueprint", "")).strip() or None
        use_family_blueprints = bool(payload.get("use_family_blueprints", False))
        blueprint_name, family_blueprints = resolve_batch_import_blueprint_options(
            repo_root,
            blueprint=blueprint_raw,
            family_blueprints_raw=payload.get("family_blueprints"),
            use_family_blueprints=use_family_blueprints,
        )
        target_blueprints = parse_target_blueprints(payload.get("target_blueprints"))
        with_gates = bool(payload.get("with_gates", True))
        try:
            batch = plan_import_batch(
                targets,
                repo_root,
                blueprint_name=blueprint_name,
                family_blueprints=family_blueprints,
                target_blueprints=target_blueprints or None,
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
            blueprint_raw = str(payload.get("blueprint", "")).strip() or None
            use_family_blueprints = bool(payload.get("use_family_blueprints", False))
            blueprint_name, family_blueprints = resolve_batch_import_blueprint_options(
                repo_root,
                blueprint=blueprint_raw,
                family_blueprints_raw=payload.get("family_blueprints"),
                use_family_blueprints=use_family_blueprints,
            )
            target_blueprints = parse_target_blueprints(payload.get("target_blueprints"))
            batch_result = import_repository_batch(
                targets,
                repo_root,
                github_token=token,
                blueprint_name=blueprint_name,
                family_blueprints=family_blueprints,
                target_blueprints=target_blueprints or None,
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
            cost_focus_file=portal_config.cost_focus.file,
        )
        entities = build_enriched_portal_catalog_entities(
            repo_root,
            output_config,
            portal_config,
            cost_actuals_configured=cost_configured,
        )
        team = str(request.query_params.get("team", "")).strip()
        owner = str(request.query_params.get("owner", "")).strip()
        try:
            catalog_cfg = load_service_catalog_config(repo_root)
        except ValueError:
            catalog_cfg = None
        if team and catalog_cfg is not None:
            entities = filter_entities_by_team(
                entities,
                team,
                default_team=catalog_cfg.default_team,
            )
        elif owner:
            entities = filter_entities_for_user(
                entities,
                owner_filter=owner,
                default_team=catalog_cfg.default_team if catalog_cfg else "platform",
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
            cost_focus_file=portal_config.cost_focus.file,
        )
        entities = build_enriched_portal_catalog_entities(
            repo_root,
            output_config,
            portal_config,
            cost_actuals_configured=cost_configured,
        )
        entity = find_catalog_entity(entities, entity_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="Entity not found")
        entity, cost, cost_estimate = enrich_entity_cost(entity, portal_config)
        entity, deployment = deployment_scorecard_for_entity(entity, portal_config)
        body = entity.to_public_dict()
        try:
            catalog_cfg = load_service_catalog_config(repo_root)
        except ValueError:
            catalog_cfg = None
        statuses = entity_initiative_statuses(entity, catalog_cfg)
        if statuses:
            body["initiatives"] = [item.to_public_dict() for item in statuses]
        obs_url = observability_embed_url(portal_config.observability_dashboard_url, entity)
        if obs_url:
            body["observability_url"] = obs_url
        slo = fetch_entity_slo_summary(portal_config.observability_slo_url, entity)
        if slo is not None:
            body["slo_summary"] = slo.to_public_dict()
        if cost is not None:
            body["cost_actuals"] = cost.to_public_dict()
        if cost_estimate is not None:
            body["cost_estimate"] = cost_estimate.to_public_dict()
        if deployment is not None:
            body["deployment_status"] = deployment.to_public_dict()
        return JSONResponse(body)

    @router.get("/catalog/blueprints")
    async def api_v2_catalog_blueprints(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        blueprints = list_catalog_blueprints(repo_root)
        groups = group_blueprints_by_artifact(blueprints)
        return JSONResponse(
            {
                "count": len(blueprints),
                "groups": [item.to_public_dict() for item in groups],
            }
        )

    @router.post("/assistant/resolve")
    async def api_v2_assistant_resolve(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_GENERATOR, ROLE_ADMIN)
        if not is_assistant_enabled(repo_root):
            raise HTTPException(
                status_code=404,
                detail="Assistant is not enabled (set v3.enabled and v3.assistant.enabled)",
            )
        payload = await _parse_json_object(request)
        intent = str(payload.get("intent", "")).strip()
        user = authenticated_user(request, auth_config)
        resolution = resolve_catalog_intent(
            repo_root,
            intent=intent,
            role=user.role if user else None,
            auth_enabled=bool(auth_config and auth_config.service_enabled),
        )
        return JSONResponse(resolution.to_public_dict())

    @router.post("/assistant/confirm")
    async def api_v2_assistant_confirm(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_GENERATOR, ROLE_ADMIN)
        if not is_assistant_enabled(repo_root):
            raise HTTPException(
                status_code=404,
                detail="Assistant is not enabled (set v3.enabled and v3.assistant.enabled)",
            )
        payload = await _parse_json_object(request)
        intent = str(payload.get("intent", "")).strip()
        blueprint = str(payload.get("blueprint", "")).strip()
        user = authenticated_user(request, auth_config)
        resolution = resolve_catalog_intent(
            repo_root,
            intent=intent,
            role=user.role if user else None,
            auth_enabled=bool(auth_config and auth_config.service_enabled),
        )
        match = match_confirmed_blueprint(resolution, blueprint=blueprint)
        if match is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "blueprint is not in the resolved matches; "
                    "POST /api/v2/assistant/resolve first and confirm a suggested name"
                ),
            )
        return JSONResponse(
            {
                "confirmed": True,
                "blueprint": match.blueprint,
                "inputs": match.plan_inputs(),
                "plan": {"method": "POST", "path": "/generate", "dry_run": True},
            }
        )

    @router.get("/bundles")
    async def api_v2_bundles(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        bundles = list_bundles(repo_root)
        return JSONResponse(
            {
                "count": len(bundles),
                "bundles": [item.to_public_dict() for item in bundles],
            }
        )

    @router.get("/bundles/{name}")
    async def api_v2_bundle(request: Request, name: str) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        try:
            bundle = load_bundle(resolve_bundle_dir(repo_root, name), repo_root=repo_root)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"bundle not found: {name}") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        nodes, edges = build_bundle_topology(bundle, ())
        body = bundle.to_public_dict()
        body["topology"] = topology_public(nodes, edges)
        return JSONResponse(body)

    @router.get("/library")
    async def api_v2_library(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        owner = str(request.query_params.get("owner", "")).strip()
        family = str(request.query_params.get("family", "")).strip()
        try:
            payload = build_library_catalog_payload(
                repo_root,
                output_config,
                portal_config,
                owner=owner,
                family=family,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return JSONResponse(payload)

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
                pins.update(pins_from_repave_file(trusted_path(local_path)))
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

    @router.get("/deployment-sets")
    async def api_v2_deployment_sets(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        try:
            catalog_cfg = load_service_catalog_config(repo_root)
        except ValueError:
            catalog_cfg = None
        sets = load_deployment_sets(catalog_cfg.deployment_sets) if catalog_cfg else ()
        profiles = load_workload_profiles(catalog_cfg.workload_profiles) if catalog_cfg else ()
        vend_cfg = load_environment_vending_config(repo_root)
        queue = _run_queue(request)
        default_team = catalog_cfg.default_team if catalog_cfg is not None else "platform"
        auth_user = session_user(request)
        default_owner = (
            auth_user.email
            if auth_user is not None and auth_user.email
            else f"group:{default_team}"
        )
        try:
            developer_lab = is_developer_lab_enabled(repo_root)
        except ValueError:
            developer_lab = False
        return JSONResponse(
            {
                "count": len(sets),
                "vend_available": bool(queue is not None and vend_cfg is not None),
                "developer_lab": developer_lab,
                "default_owner": default_owner,
                "deployment_sets": [item.to_public_dict() for item in sets],
                "workload_profiles": [item.to_public_dict() for item in profiles],
            }
        )

    @router.post("/environments/vend")
    async def api_v2_environments_vend(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_GENERATOR, ROLE_ADMIN)
        queue = _run_queue(request)
        if queue is None:
            raise HTTPException(
                status_code=503,
                detail="Async runs require durability.async_generation",
            )
        try:
            catalog_cfg = load_service_catalog_config(repo_root)
        except ValueError:
            catalog_cfg = None
        if catalog_cfg is None:
            raise HTTPException(
                status_code=404,
                detail="Service catalog is not enabled (set service_catalog.enabled)",
            )
        payload_in = await _parse_json_object(request)
        sets = load_deployment_sets(catalog_cfg.deployment_sets)
        profiles = load_workload_profiles(catalog_cfg.workload_profiles)
        vend_cfg = load_environment_vending_config(repo_root)
        gitops_repo = vend_cfg.gitops_repo if vend_cfg is not None else ""
        try:
            payload = resolve_sandbox_vend_payload(
                sets=sets,
                profiles=profiles,
                deployment_set_id=str(payload_in.get("deployment_set", "")),
                stack_name=str(payload_in.get("stack_name", "")),
                owner=str(payload_in.get("owner", "")),
                gitops_repo=gitops_repo,
                dry_run=bool(payload_in.get("dry_run", True)),
            )
        except SandboxVendError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            record = submit_async_run(
                queue,
                payload=payload,
                acting_user=_acting_user(request),
                repo_root=repo_root,
            )
        except RunQueueFullError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except RunQueueShuttingDownError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(record.to_public_dict(), status_code=202)

    @router.get("/component-kinds")
    async def api_v2_component_kinds(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        vend_cfg = load_component_vending_config(repo_root)
        kinds = load_component_kinds(vend_cfg.kinds_file if vend_cfg is not None else None)
        queue = _run_queue(request)
        return JSONResponse(
            {
                "count": len(kinds),
                "vend_available": bool(queue is not None and vend_cfg is not None),
                "kinds": [item.to_public_dict() for item in kinds],
            }
        )

    @router.post("/components/vend")
    async def api_v2_components_vend(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_GENERATOR, ROLE_ADMIN)
        queue = _run_queue(request)
        if queue is None:
            raise HTTPException(
                status_code=503,
                detail="Async runs require durability.async_generation",
            )
        vend_cfg = load_component_vending_config(repo_root)
        if vend_cfg is None:
            raise HTTPException(
                status_code=503,
                detail="component_vending is not enabled; set component_vending.enabled "
                "in repave.config.yaml or REPAVE_COMPONENT_VENDING=1",
            )
        payload_in = await _parse_json_object(request)
        kinds = load_component_kinds(vend_cfg.kinds_file)
        try:
            resolve_component_vend_fields(payload_in, vend_cfg, kinds)
        except ComponentVendError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        payload = dict(payload_in)
        payload["kind"] = "component_vend"
        if "component_kind" not in payload and payload_in.get("kind") not in (
            None,
            "",
            "component_vend",
        ):
            payload["component_kind"] = str(payload_in.get("kind", "")).strip()
        try:
            record = submit_async_run(
                queue,
                payload=payload,
                acting_user=_acting_user(request),
                repo_root=repo_root,
            )
        except RunQueueFullError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except RunQueueShuttingDownError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(record.to_public_dict(), status_code=202)

    @router.post("/components/reclaim")
    async def api_v2_components_reclaim(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_ADMIN)
        vend_cfg = load_component_vending_config(repo_root)
        if vend_cfg is None:
            raise HTTPException(
                status_code=503,
                detail="component_vending is not enabled; set component_vending.enabled "
                "in repave.config.yaml or REPAVE_COMPONENT_VENDING=1",
            )
        payload = await _parse_json_object(request)
        dry_run = bool(payload.get("dry_run", False))
        name = str(payload.get("name", "")).strip() or None
        kind = str(payload.get("kind", "")).strip() or None
        github_token = resolve_github_access_token(None) if not dry_run else None
        if not dry_run and not github_token:
            raise HTTPException(
                status_code=503,
                detail="GITHUB_TOKEN is required unless dry_run is true",
            )
        try:
            summary = reclaim_expired_components(
                repo_root=repo_root,
                config=vend_cfg,
                github_token=github_token,
                dry_run=dry_run,
                name=name,
                kind=kind,
            )
        except ComponentReclaimError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(summary.to_public_dict())

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

    @router.get("/platform/metrics")
    async def api_v2_platform_metrics(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_ADMIN)
        from repave_engine.dx_metrics_store import capture_dx_metrics, read_dx_metrics_snapshots
        from repave_engine.settings import load_platform_metrics_config

        metrics_cfg = load_platform_metrics_config(repo_root)
        if metrics_cfg is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "platform_metrics is not configured "
                    "(set platform_metrics.enabled or REPAVE_PLATFORM_METRICS=1)"
                ),
            )
        persist = str(request.query_params.get("persist", "")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        history_raw = str(request.query_params.get("history", "0")).strip() or "0"
        try:
            history_limit = max(0, min(int(history_raw), 100))
        except ValueError:
            history_limit = 0
        token = resolve_github_access_token(None)
        snapshot = capture_dx_metrics(
            repo_root,
            github_token=token,
            persist=persist,
        )
        payload: dict[str, Any] = snapshot.to_public_dict()
        if history_limit:
            history = read_dx_metrics_snapshots(
                metrics_cfg.snapshot_file,
                repo_root=repo_root,
                limit=history_limit,
            )
            payload["history"] = [item.to_public_dict() for item in history]
        return JSONResponse(payload)

    @router.get("/platform/compliance")
    async def api_v2_platform_compliance(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_ADMIN)
        from repave_engine.portal_platform import build_platform_compliance_page
        from repave_engine.settings import load_platform_metrics_config

        if load_platform_metrics_config(repo_root) is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "platform_metrics is not configured "
                    "(set platform_metrics.enabled or REPAVE_PLATFORM_METRICS=1)"
                ),
            )
        token = resolve_github_access_token(None)
        page = build_platform_compliance_page(
            repo_root,
            github_token=token,
            persist=False,
        )
        return JSONResponse(page.to_public_dict())

    @router.get("/platform/value-stream")
    async def api_v2_platform_value_stream(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_ADMIN)
        from repave_engine.portal_platform import build_platform_value_stream_page
        from repave_engine.settings import load_platform_metrics_config

        if load_platform_metrics_config(repo_root) is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "platform_metrics is not configured "
                    "(set platform_metrics.enabled or REPAVE_PLATFORM_METRICS=1)"
                ),
            )
        token = resolve_github_access_token(None)
        page = build_platform_value_stream_page(
            repo_root,
            github_token=token,
            persist=False,
        )
        return JSONResponse(page.to_public_dict())

    @router.get("/platform/roadmap-evidence")
    async def api_v2_platform_roadmap_evidence(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_ADMIN)
        from repave_engine.portal_platform import build_platform_roadmap_page
        from repave_engine.roadmap_evidence import load_roadmap_evidence_settings

        if load_roadmap_evidence_settings(repo_root) is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "platform_metrics is not configured "
                    "(set platform_metrics.enabled or REPAVE_PLATFORM_METRICS=1)"
                ),
            )
        token = resolve_github_access_token(None)
        page = build_platform_roadmap_page(
            repo_root,
            github_token=token,
            persist=False,
        )
        return JSONResponse(page.to_public_dict())

    @router.get("/platform/maturity")
    async def api_v2_platform_maturity(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_ADMIN)
        if load_service_catalog_config(repo_root) is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "service_catalog is not configured "
                    "(set service_catalog.enabled or REPAVE_SERVICE_CATALOG=1)"
                ),
            )
        page = build_platform_maturity_page(repo_root, resolved_output=output_config)
        return JSONResponse(page.to_public_dict())

    def _initiatives_store_or_404() -> Path:
        catalog_cfg = load_service_catalog_config(repo_root)
        if catalog_cfg is None or catalog_cfg.initiatives is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Initiatives store is not configured "
                    "(set service_catalog.enabled and service_catalog.initiatives)"
                ),
            )
        return catalog_cfg.initiatives

    @router.get("/platform/initiatives")
    async def api_v2_platform_initiatives(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_ADMIN)
        if load_service_catalog_config(repo_root) is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "service_catalog is not configured "
                    "(set service_catalog.enabled or REPAVE_SERVICE_CATALOG=1)"
                ),
            )
        page = build_platform_initiatives_page(repo_root, resolved_output=output_config)
        return JSONResponse(page.to_public_dict())

    @router.post("/platform/initiatives")
    async def api_v2_platform_initiatives_create(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_ADMIN)
        from repave_engine.initiatives import append_initiative, build_initiative_from_form

        store_path = _initiatives_store_or_404()
        try:
            body = await request.json()
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="JSON body required") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="JSON object required")
        try:
            initiative = build_initiative_from_form(body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            append_initiative(store_path, initiative)
        except OSError as exc:
            logger.warning("Failed to persist initiative: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Failed to persist initiative",
            ) from exc
        return JSONResponse(initiative.to_public_dict(), status_code=201)

    @router.patch("/platform/initiatives/{initiative_id}")
    async def api_v2_platform_initiatives_patch(
        request: Request,
        initiative_id: str,
    ) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_ADMIN)
        from repave_engine.initiatives import (
            apply_initiative_patch,
            get_initiative,
            upsert_initiative,
        )

        store_path = _initiatives_store_or_404()
        existing = get_initiative(store_path, initiative_id)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"initiative not found: {initiative_id}")
        try:
            body = await request.json()
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="JSON body required") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="JSON object required")
        try:
            updated = apply_initiative_patch(existing, body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            upsert_initiative(store_path, updated)
        except OSError as exc:
            logger.warning("Failed to update initiative: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Failed to update initiative",
            ) from exc
        return JSONResponse(updated.to_public_dict())

    @router.delete("/platform/initiatives/{initiative_id}")
    async def api_v2_platform_initiatives_delete(
        request: Request,
        initiative_id: str,
    ) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_ADMIN)
        from repave_engine.initiatives import deactivate_initiative

        store_path = _initiatives_store_or_404()
        try:
            deactivated = deactivate_initiative(store_path, initiative_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except OSError as exc:
            logger.warning("Failed to deactivate initiative: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Failed to deactivate initiative",
            ) from exc
        return JSONResponse(deactivated.to_public_dict())

    @router.post("/platform/feedback")
    async def api_v2_platform_feedback_post(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_GENERATOR, ROLE_ADMIN)
        from datetime import datetime, timezone

        from repave_engine.feedback import (
            build_feedback_event,
            normalize_friction_tags,
            normalize_surface,
            validate_csat,
        )
        from repave_engine.feedback_store import append_feedback_event
        from repave_engine.settings import load_platform_metrics_config

        metrics_cfg = load_platform_metrics_config(repo_root)
        if metrics_cfg is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "platform_metrics is not configured "
                    "(set platform_metrics.enabled or REPAVE_PLATFORM_METRICS=1)"
                ),
            )
        body = await _parse_json_object(request)
        try:
            csat = validate_csat(body.get("csat"))
            friction_tags = normalize_friction_tags(body.get("friction_tags"))
            surface = normalize_surface(body.get("surface"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        blueprint_name = str(body.get("blueprint_name", "")).strip()
        if not blueprint_name:
            raise HTTPException(status_code=400, detail="blueprint_name is required")
        comment = str(body.get("comment", "")).strip()
        if len(comment) > 2000:
            raise HTTPException(status_code=400, detail="comment must be at most 2000 characters")
        submitted_at = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
        event = build_feedback_event(
            submitted_at=submitted_at,
            csat=csat,
            friction_tags=friction_tags,
            comment=comment,
            blueprint_name=blueprint_name,
            blueprint_version=str(body.get("blueprint_version", "")).strip(),
            dry_run=bool(body.get("dry_run")),
            gates_outcome=str(body.get("gates_outcome", "")).strip(),
            acting_user=_acting_user(request),
            run_id=str(body.get("run_id", "")).strip(),
            surface=surface,
        )
        try:
            append_feedback_event(
                metrics_cfg.feedback_file,
                event,
                repo_root=repo_root,
            )
        except OSError as exc:
            logger.warning("Failed to persist feedback event: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Failed to persist feedback event",
            ) from exc
        return JSONResponse(event.to_public_dict(), status_code=201)

    @router.get("/platform/feedback")
    async def api_v2_platform_feedback_get(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_ADMIN)
        from repave_engine.feedback_store import load_feedback_rollup
        from repave_engine.settings import load_platform_metrics_config

        metrics_cfg = load_platform_metrics_config(repo_root)
        if metrics_cfg is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "platform_metrics is not configured "
                    "(set platform_metrics.enabled or REPAVE_PLATFORM_METRICS=1)"
                ),
            )
        history_raw = str(request.query_params.get("limit", "50")).strip() or "50"
        try:
            limit = max(1, min(int(history_raw), 200))
        except ValueError:
            limit = 50
        rollup, events = load_feedback_rollup(repo_root, limit=limit)
        return JSONResponse(
            {
                "rollup": rollup.to_public_dict(),
                "events": [event.to_public_dict() for event in events],
            }
        )

    @router.get("/platform/finops/export")
    async def api_v2_platform_finops_export(request: Request) -> Response:
        _require_roles(request, auth_config, ROLE_ADMIN)
        from repave_engine.finops_anomalies import evaluate_finops_anomalies
        from repave_engine.finops_export import (
            build_chargeback_export,
            chargeback_export_to_csv,
            chargeback_export_to_json,
        )
        from repave_engine.finops_rollup import build_finops_rollup

        portal_cfg = load_portal_config(repo_root)
        finops_active = (
            cost_reader_configured(
                cost_reader=portal_cfg.cost_reader,
                cost_actuals_url=portal_cfg.cost_actuals_url,
                cost_focus_file=portal_cfg.cost_focus.file,
            )
            or portal_cfg.cost_snapshots_file is not None
        )
        if not finops_active:
            raise HTTPException(
                status_code=404,
                detail=(
                    "FinOps is not configured (set portal.cost_reader or portal.cost_snapshots)"
                ),
            )
        entities = build_portal_catalog_entities(repo_root, output_config)
        rollup = build_finops_rollup(entities, portal_cfg, repo_root=repo_root)
        rows = build_chargeback_export(rollup)
        detect_raw = str(request.query_params.get("detect_anomalies", "")).strip().lower()
        detect = detect_raw in {"1", "true", "yes", "on"} or portal_cfg.cost_anomalies.enabled
        anomalies: list[dict[str, object]] = []
        if detect and portal_cfg.cost_anomalies.enabled:
            detected = evaluate_finops_anomalies(
                entities,
                portal_cfg,
                repo_root=repo_root,
            )
            anomalies = [item.to_public_dict() for item in detected]
        export_format = str(request.query_params.get("format", "json")).strip().lower()
        if export_format == "csv":
            return Response(
                content=chargeback_export_to_csv(rows),
                media_type="text/csv",
                headers={"Content-Disposition": 'attachment; filename="finops-chargeback.csv"'},
            )
        if export_format not in ("json", ""):
            raise HTTPException(status_code=400, detail="format must be json or csv")
        return JSONResponse(
            {
                "count": len(rows),
                "currency": rollup.currency,
                "rows": chargeback_export_to_json(rows),
                "anomalies": anomalies,
            }
        )

    @router.get("/platform/ops")
    async def api_v2_platform_ops(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_ADMIN)
        from repave_engine.portal_platform import build_platform_ops_page
        from repave_engine.settings import load_durability_config

        durability = load_durability_config(repo_root)
        session_store = getattr(request.app.state, "session_store", None)
        probe_token = resolve_github_access_token() if github_credentials_configured() else None
        page = build_platform_ops_page(
            repo_root,
            run_queue=_run_queue(request),
            modules_root=output_config.modules_root,
            runs_db=durability.runs_db if durability is not None else None,
            shutting_down=bool(getattr(request.app.state, "shutting_down", False)),
            auth_service_enabled=auth_config is not None and auth_config.service_enabled,
            require_session_secret=(
                durability.require_session_secret if durability is not None else False
            ),
            github_token_configured=github_credentials_configured(),
            github_probe_token=probe_token,
            sql_session_store_ok=session_store.ping() if session_store is not None else None,
        )
        return JSONResponse(page.to_public_dict())

    @router.get("/platform/standards")
    async def api_v2_platform_standards(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_ADMIN)
        from repave_engine.portal_platform import build_platform_standards_page

        return JSONResponse(build_platform_standards_page(repo_root).to_public_dict())

    @router.get("/platform/campaigns")
    async def api_v2_platform_campaigns(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_ADMIN)
        from repave_engine.portal_platform import build_platform_campaigns_page

        return JSONResponse(build_platform_campaigns_page(repo_root).to_public_dict())

    @router.post("/platform/campaigns/{namespace}/{name}/paused")
    async def api_v2_platform_campaign_paused(
        request: Request,
        namespace: str,
        name: str,
    ) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_ADMIN)
        from repave_engine.fleet_operator_actions import patch_upgrade_campaign_paused
        from repave_engine.portal_platform import (
            build_platform_campaigns_page,
            find_campaign_in_snapshot,
        )

        payload = await _parse_json_object(request)
        paused_raw = payload.get("paused")
        if not isinstance(paused_raw, bool):
            raise HTTPException(status_code=400, detail="paused must be a boolean")
        page = build_platform_campaigns_page(repo_root)
        campaign = find_campaign_in_snapshot(
            page.snapshot,
            namespace=namespace,
            name=name,
        )
        if campaign is None:
            raise HTTPException(
                status_code=404,
                detail=f"Campaign {namespace}/{name} not in snapshot",
            )
        try:
            patch_upgrade_campaign_paused(
                campaign.name,
                campaign.namespace,
                paused=paused_raw,
            )
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return JSONResponse(
            {
                "namespace": campaign.namespace or "default",
                "name": campaign.name,
                "paused": paused_raw,
            }
        )

    return router
