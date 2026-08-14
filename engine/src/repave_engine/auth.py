"""OIDC login, session roles, and service-mode access control."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)

ROLE_VIEWER = "viewer"
ROLE_GENERATOR = "generator"
ROLE_ADMIN = "admin"

SERVICE_BEARER_SUBJECT = "repave:service-bearer"
SERVICE_BEARER_EMAIL = "repave-service@internal.local"

_PUBLIC_EXACT = frozenset({"/", "/signup"})
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
    session_https_only: bool = False
    oidc_logout_return_to: str = ""
    coarse_rbac_enabled: bool = False


def is_public_path(path: str) -> bool:
    if path in _PUBLIC_EXACT:
        return True
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
        subject=SERVICE_BEARER_SUBJECT,
        email=SERVICE_BEARER_EMAIL,
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


def session_role_from_oidc_groups(groups: list[str], config: AuthConfig) -> str:
    """Map IdP groups to a portal session role.

    When coarse RBAC is off (default until FGA), any successful OIDC login is admin.
    """
    if not config.coarse_rbac_enabled:
        return ROLE_ADMIN
    return role_for_groups(groups, config)


def groups_from_claims(claims: dict[str, Any], groups_claim: str) -> list[str]:
    """Read group/role names from userinfo (supports Auth0 namespaced claims)."""
    groups_raw = claims.get(groups_claim, [])
    if isinstance(groups_raw, list):
        return [str(item) for item in groups_raw if str(item).strip()]
    if isinstance(groups_raw, str) and groups_raw.strip():
        return [groups_raw.strip()]
    return []


def _decode_unverified_jwt_payload(token: str) -> dict[str, Any]:
    try:
        import jwt

        payload = jwt.decode(token, options={"verify_signature": False})
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def merge_oidc_user_claims(
    userinfo: dict[str, Any],
    id_token: str | None,
    *,
    groups_claim: str,
) -> dict[str, Any]:
    """Merge role claims from the id_token when userinfo omits them (Auth0 default)."""
    merged = dict(userinfo)
    if groups_from_claims(merged, groups_claim):
        return merged
    if not id_token:
        return merged
    id_claims = _decode_unverified_jwt_payload(id_token)
    if not id_claims:
        return merged
    claim_keys = [groups_claim]
    if groups_claim != "groups" and "groups" not in claim_keys:
        claim_keys.append("groups")
    for key in sorted(id_claims):
        if key.endswith("/groups") and key not in claim_keys:
            claim_keys.append(key)
    for key in claim_keys:
        if key in id_claims and not groups_from_claims(merged, key):
            merged[key] = id_claims[key]
        if groups_from_claims(merged, groups_claim):
            break
    return merged


def logout_return_to(config: AuthConfig) -> str:
    """Post-logout landing URL (Auth0 Allowed Logout URLs / OIDC post_logout_redirect_uri)."""
    explicit = config.oidc_logout_return_to.strip()
    if explicit:
        return explicit
    parsed = urlparse(config.oidc_redirect_uri)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}/"
    return "/"


def build_idp_logout_url(config: AuthConfig, discovery: dict[str, Any]) -> str | None:
    """Build IdP logout URL from discovery, with Auth0 ``/v2/logout`` fallback."""
    return_to = logout_return_to(config)
    end_session = str(discovery.get("end_session_endpoint", "")).strip()
    if end_session:
        params = {
            "client_id": config.oidc_client_id,
            "post_logout_redirect_uri": return_to,
        }
        return f"{end_session}?{urlencode(params)}"
    issuer_host = urlparse(config.oidc_issuer).netloc.lower()
    if "auth0.com" not in issuer_host:
        return None
    issuer = config.oidc_issuer.rstrip("/")
    params = {
        "client_id": config.oidc_client_id,
        "returnTo": return_to,
    }
    return f"{issuer}/v2/logout?{urlencode(params)}"


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
    *,
    screen_hint: str = "",
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
    hint = screen_hint.strip()
    if hint:
        # Auth0 Universal Login; other IdPs ignore unknown authorize params.
        params["screen_hint"] = hint
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

    id_token = str(token_payload.get("id_token", "")).strip() or None
    claims = merge_oidc_user_claims(claims, id_token, groups_claim=config.groups_claim)

    subject = str(claims.get("sub", "")).strip()
    if not subject:
        raise HTTPException(status_code=502, detail="OIDC sub claim missing")

    email = str(claims.get("email", subject)).strip()
    groups = groups_from_claims(claims, config.groups_claim)
    role = session_role_from_oidc_groups(groups, config)
    request.session["repave_user"] = {"sub": subject, "email": email, "role": role}
    if not next_path.startswith("/"):
        next_path = "/"
    return RedirectResponse(next_path, status_code=302)


def clear_session(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/", status_code=302)


async def complete_logout(request: Request, config: AuthConfig) -> RedirectResponse:
    """Clear the local session, then redirect to the IdP logout endpoint when available."""
    request.session.clear()
    if not config.service_enabled or not config.oidc_issuer:
        return RedirectResponse(logout_return_to(config), status_code=302)
    try:
        discovery = await fetch_oidc_discovery(config.oidc_issuer)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("OIDC discovery failed during logout; local session cleared: %s", exc)
        return RedirectResponse(logout_return_to(config), status_code=302)
    idp_url = build_idp_logout_url(config, discovery)
    if idp_url:
        return RedirectResponse(idp_url, status_code=302)
    return RedirectResponse(logout_return_to(config), status_code=302)
