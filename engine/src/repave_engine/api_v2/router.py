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
from repave_engine.auth import (
    ROLE_ADMIN,
    ROLE_GENERATOR,
    ROLE_VIEWER,
    AuthConfig,
    require_role,
    session_user,
)
from repave_engine.auth_context import current_acting_user
from repave_engine.execution_mode import (
    SYNC_GENERATE_UNAVAILABLE_DETAIL,
    worker_execution_mode_active,
)
from repave_engine.generate_api import run_generate_api
from repave_engine.github_auth import resolve_github_access_token
from repave_engine.run_events import TERMINAL_EVENT_KINDS
from repave_engine.run_queue import RunQueue, RunQueueFullError, RunQueueShuttingDownError
from repave_engine.settings import OutputConfig
from repave_engine.upgrade_api import (
    UpgradeTargetError,
    resolve_upgrade_target,
    run_apply_upgrade,
    run_plan_upgrade,
)

V2_ENDPOINTS: tuple[str, ...] = (
    "GET /api/v2",
    "POST /api/v2/generate",
    "POST /api/v2/runs",
    "GET /api/v2/runs/{run_id}",
    "POST /api/v2/runs/{run_id}/replay",
    "GET /api/v2/runs/{run_id}/events",
    "POST /api/v2/upgrades/plan",
    "POST /api/v2/upgrades/apply",
)


def _require_roles(request: Request, auth_config: AuthConfig | None, *roles: str) -> None:
    if auth_config is None or not auth_config.service_enabled:
        return
    require_role(session_user(request), *roles)


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

    @router.get("")
    async def api_v2_metadata() -> JSONResponse:
        return JSONResponse(
            {
                "api_version": "v2",
                "engine_version": __version__,
                "endpoints": list(V2_ENDPOINTS),
            }
        )

    @router.post("/generate")
    async def api_v2_generate(request: Request) -> JSONResponse:
        _require_roles(request, auth_config, ROLE_GENERATOR, ROLE_ADMIN)
        payload = await _parse_json_object(request)
        blueprint_name = str(payload.get("blueprint", "")).strip()
        if not blueprint_name:
            raise HTTPException(status_code=400, detail="blueprint is required")
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
                record = queue.submit(
                    blueprint_name=blueprint_name,
                    inputs=inputs_raw,
                    dry_run=dry_run,
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
            body = run_generate_api(
                repo_root=repo_root,
                output_config=output_config,
                blueprint_name=blueprint_name,
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
        blueprint_name = str(payload.get("blueprint", "")).strip()
        if not blueprint_name:
            raise HTTPException(status_code=400, detail="blueprint is required")
        dry_run = bool(payload.get("dry_run", True))
        inputs_raw = payload.get("inputs", {})
        if not isinstance(inputs_raw, dict):
            raise HTTPException(status_code=400, detail="inputs must be an object")
        client_request_id = str(payload.get("client_request_id", "")).strip() or None
        idempotency = request.headers.get("Idempotency-Key", "").strip() or None
        try:
            record = queue.submit(
                blueprint_name=blueprint_name,
                inputs=inputs_raw,
                dry_run=dry_run,
                acting_user=_acting_user(request),
                client_request_id=client_request_id or idempotency,
            )
        except RunQueueFullError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except RunQueueShuttingDownError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return JSONResponse(record.to_public_dict(), status_code=202)

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

    return router
