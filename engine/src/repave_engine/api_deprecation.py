"""HTTP deprecation markers for legacy API and HTML portal surfaces."""

from __future__ import annotations

from repave_engine.deprecations import http_deprecation_headers

V1_DEPRECATION_HEADERS: dict[str, str] = http_deprecation_headers("api_v1_removal")
V1_SUNSET_HTTP: str = V1_DEPRECATION_HEADERS["Sunset"]

HTML_PORTAL_DISABLED_DETAIL: str = (
    "HTML portal is disabled (portal.html=false). "
    "The night-ops HTML workbench is the hosted UI; set portal.html=true or "
    "REPAVE_PORTAL_HTML=1. CLI and /api/v2 stay available."
)

_NON_HTML_EXACT = frozenset(
    {
        "/api",
        "/health",
        "/readyz",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)
_NON_HTML_PREFIXES = ("/api/", "/static/")


def is_html_portal_path(path: str) -> bool:
    """True for FastAPI HTML portal routes (not /api, /static, or probes)."""
    if path in _NON_HTML_EXACT:
        return False
    return not path.startswith(_NON_HTML_PREFIXES)
