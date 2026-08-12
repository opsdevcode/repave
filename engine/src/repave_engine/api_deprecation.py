"""HTTP deprecation markers for legacy API surfaces (v2.0.0 contract freeze)."""

from __future__ import annotations

from repave_engine.deprecations import http_deprecation_headers

V1_DEPRECATION_HEADERS: dict[str, str] = http_deprecation_headers("api_v1_removal")
V1_SUNSET_HTTP: str = V1_DEPRECATION_HEADERS["Sunset"]
