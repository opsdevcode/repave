"""HTTP deprecation markers for legacy API and HTML portal surfaces."""

from __future__ import annotations

from repave_engine.deprecations import http_deprecation_headers

V1_DEPRECATION_HEADERS: dict[str, str] = http_deprecation_headers("api_v1_removal")
V1_SUNSET_HTTP: str = V1_DEPRECATION_HEADERS["Sunset"]

HTML_PORTAL_DEPRECATION_HEADERS: dict[str, str] = http_deprecation_headers("html_portal_removal")
HTML_PORTAL_SUNSET_HTTP: str = HTML_PORTAL_DEPRECATION_HEADERS["Sunset"]
HTML_PORTAL_DISABLED_DETAIL: str = (
    "HTML portal is disabled (portal.html=false). "
    "Use the hosted Backstage UI or /api/v2. "
    "Set portal.html=true or REPAVE_PORTAL_HTML=1 to serve HTML locally."
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
