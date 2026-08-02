"""OIDC login, session roles, and service-mode access control."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)

ROLE_VIEWER = "viewer"
ROLE_GENERATOR = "generator"
ROLE_ADMIN = "admin"

SERVICE_API_TOKEN_SUBJECT = "service:api-token"
SERVICE_API_TOKEN_EMAIL = "service@repave.internal"

_PUBLIC_PREFIXES = ("/static", "/health", "/readyz", "/metrics", "/auth/")


@dataclass(frozen=True)
class AuthUser:
    subject: str
    email: str
    role: str


@dataclass(frozen=True)
class AuthConfig:
    service_enabled: bool
    session_secret: str
    api_token: str
    oidc_issuer: str
    oidc_client_id: str
    oidc_client_secret: str
    oidc_redirect_uri: str
    oidc_scopes: tuple[str, ...]
    groups_claim: str
    admin_groups: frozenset[str]
    generator_groups: frozenset[str]


def is_public_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)


def session_user(request: Request) -> AuthUser | None:
    payload = request.session.get("repave_user")
    if not isinstance(payload, dict):
        return None
    subject = str(payload.get("sub", "")).strip()
    if not subject:
        return None
    email = str(payload.get("email", subject)).strip()
    role = str(payload.get("role", ROLE_VIEWER)).strip() or ROLE_VIEWER
    return AuthUser(subject=subject, email=email, role=role)


def bearer_token_from_request(request: Request) -> str | None:
    header = request.headers.get("Authorization", "").strip()
    if not header.lower().startswith("bearer "):
        return None
    token = header[7:].strip()
    return token or None


def service_user_from_bearer(request: Request, config: AuthConfig) -> AuthUser | None:
    if not config.service_enabled or not config.api_token:
        return None
    token = bearer_token_from_request(request)
    if token is None:
        return None
    if not secrets.compare_digest(token, config.api_token):
        return None
    return AuthUser(
        subject=SERVICE_API_TOKEN_SUBJECT,
        email=SERVICE_API_TOKEN_EMAIL,
        role=ROLE_ADMIN,
    )


def authenticated_user(request: Request, config: AuthConfig | None) -> AuthUser | None:
    user = session_user(request)
    if user is not None:
        return user
    if config is None:
        return None
    return service_user_from_bearer(request, config)


def role_for_groups(groups: list[str], config: AuthConfig) -> str:
    normalized = {item.strip().lower() for item in groups if item.strip()}
    admin = {item.lower() for item in config.admin_groups}
    generator = {item.lower() for item in config.generator_groups}
    if normalized.intersection(admin):
        return ROLE_ADMIN
    if normalized.intersection(generator):
        return ROLE_GENERATOR
    return ROLE_VIEWER


def require_role(user: AuthUser | None, *allowed: str) -> None:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.role not in allowed:
        raise HTTPException(status_code=403, detail="Insufficient role")


async def fetch_oidc_discovery(issuer: str) -> dict[str, Any]:
    base = issuer.rstrip("/")
    url = f"{base}/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict):
        raise ValueError(
            f"invalid OIDC discovery document from {url}; "
            "check REPAVE_OIDC_ISSUER points at a valid OpenID provider"
        )
    return data


def build_login_redirect(
    request: Request,
    config: AuthConfig,
    discovery: dict[str, Any],
) -> RedirectResponse:
    state = secrets.token_urlsafe(24)
    request.session["oidc_state"] = state
    next_path = request.query_params.get("next", "/")
    request.session["oidc_next"] = next_path
    params = {
        "client_id": config.oidc_client_id,
        "response_type": "code",
        "scope": " ".join(config.oidc_scopes),
        "redirect_uri": config.oidc_redirect_uri,
        "state": state,
    }
    authorize = str(discovery.get("authorization_endpoint", ""))
    if not authorize:
        raise HTTPException(status_code=500, detail="OIDC authorization_endpoint missing")
    return RedirectResponse(f"{authorize}?{urlencode(params)}", status_code=302)


async def complete_oidc_callback(
    request: Request,
    config: AuthConfig,
    *,
    code: str,
    state: str,
) -> RedirectResponse:
    expected = request.session.pop("oidc_state", None)
    if not expected or state != expected:
        raise HTTPException(status_code=400, detail="Invalid OIDC state")
    next_path = str(request.session.pop("oidc_next", "/") or "/")
    discovery = await fetch_oidc_discovery(config.oidc_issuer)
    token_endpoint = str(discovery.get("token_endpoint", ""))
    userinfo_endpoint = str(discovery.get("userinfo_endpoint", ""))
    if not token_endpoint or not userinfo_endpoint:
        raise HTTPException(status_code=500, detail="OIDC token or userinfo endpoint missing")

    async with httpx.AsyncClient(timeout=15.0) as client:
        token_response = await client.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config.oidc_redirect_uri,
                "client_id": config.oidc_client_id,
                "client_secret": config.oidc_client_secret,
            },
            headers={"Accept": "application/json"},
        )
        token_response.raise_for_status()
        token_payload = token_response.json()
        if not isinstance(token_payload, dict):
            raise HTTPException(status_code=502, detail="Invalid token response")
        access_token = str(token_payload.get("access_token", "")).strip()
        if not access_token:
            raise HTTPException(status_code=502, detail="Missing access_token")

        userinfo_response = await client.get(
            userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        userinfo_response.raise_for_status()
        claims = userinfo_response.json()

    if not isinstance(claims, dict):
        raise HTTPException(status_code=502, detail="Invalid userinfo response")

    subject = str(claims.get("sub", "")).strip()
    if not subject:
        raise HTTPException(status_code=502, detail="OIDC sub claim missing")

    email = str(claims.get("email", subject)).strip()
    groups_raw = claims.get(config.groups_claim, [])
    groups: list[str] = []
    if isinstance(groups_raw, list):
        groups = [str(item) for item in groups_raw]
    elif isinstance(groups_raw, str) and groups_raw.strip():
        groups = [groups_raw.strip()]

    role = role_for_groups(groups, config)
    request.session["repave_user"] = {"sub": subject, "email": email, "role": role}
    if not next_path.startswith("/"):
        next_path = "/"
    return RedirectResponse(next_path, status_code=302)


def clear_session(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/", status_code=302)
