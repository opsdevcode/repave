"""Operational endpoints: health, metrics, readiness."""

from __future__ import annotations

import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from repave_engine.auth import AuthConfig
from repave_engine.readiness import evaluate_readiness
from repave_engine.settings import DurabilityConfig, OutputConfig


def build_ops_router(
    *,
    output_config: OutputConfig,
    auth_config: AuthConfig | None,
    durability_config: DurabilityConfig | None,
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
        token_ok = bool(os.environ.get("GITHUB_TOKEN", "").strip())
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
            run_queue_depth=queue.queue_depth() if queue is not None else None,
        )
        status_code = 200 if report.ready else 503
        return JSONResponse(report.to_payload(), status_code=status_code)

    return router
