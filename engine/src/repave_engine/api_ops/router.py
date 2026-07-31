"""Operational endpoints: health, metrics, readiness."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from repave_engine.auth import AuthConfig
from repave_engine.github_auth import github_credentials_configured, resolve_github_access_token
from repave_engine.readiness import evaluate_readiness
from repave_engine.session_store import SessionStore
from repave_engine.settings import DurabilityConfig, OutputConfig


def build_ops_router(
    *,
    output_config: OutputConfig,
    auth_config: AuthConfig | None,
    durability_config: DurabilityConfig | None,
    session_store: SessionStore | None = None,
) -> APIRouter:
    """Return health, metrics, and readiness probes."""
    router = APIRouter(tags=["ops"])

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/metrics")
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @router.get("/readyz")
    async def readyz(request: Request) -> JSONResponse:
        token_ok = github_credentials_configured()
        probe_token = resolve_github_access_token() if token_ok else None
        queue = getattr(request.app.state, "run_queue", None)
        runs_db = durability_config.runs_db if durability_config is not None else None
        shutting_down = bool(getattr(request.app.state, "shutting_down", False))
        report = evaluate_readiness(
            modules_root=output_config.modules_root,
            runs_db=runs_db,
            shutting_down=shutting_down,
            auth_service_enabled=auth_config is not None and auth_config.service_enabled,
            require_session_secret=(
                durability_config.require_session_secret if durability_config else False
            ),
            github_token_configured=token_ok,
            github_probe_token=probe_token,
            run_queue_depth=queue.queue_depth() if queue is not None else None,
            sql_session_store_ok=session_store.ping() if session_store is not None else None,
        )
        status_code = 200 if report.ready else 503
        return JSONResponse(report.to_payload(), status_code=status_code)

    return router
