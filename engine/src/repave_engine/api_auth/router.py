"""OIDC login, callback, and logout routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from repave_engine.auth import (
    AuthConfig,
    build_login_redirect,
    clear_session,
    complete_oidc_callback,
    fetch_oidc_discovery,
)


def build_auth_router(*, auth_config: AuthConfig | None) -> APIRouter:
    """Return session auth routes (``/auth/*``)."""
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.get("/login")
    async def auth_login(request: Request) -> RedirectResponse:
        if auth_config is None or not auth_config.service_enabled:
            return RedirectResponse("/", status_code=302)
        discovery = await fetch_oidc_discovery(auth_config.oidc_issuer)
        return build_login_redirect(request, auth_config, discovery)

    @router.get("/callback")
    async def auth_callback(
        request: Request,
        code: str = "",
        state: str = "",
    ) -> RedirectResponse:
        if auth_config is None or not auth_config.service_enabled:
            raise HTTPException(status_code=404, detail="Auth not enabled")
        if not code or not state:
            raise HTTPException(status_code=400, detail="Missing code or state")
        return await complete_oidc_callback(request, auth_config, code=code, state=state)

    @router.post("/logout")
    async def auth_logout(request: Request) -> RedirectResponse:
        return clear_session(request)

    return router
