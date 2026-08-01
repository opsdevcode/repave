"""HTTP deprecation markers for legacy API surfaces (v2.0.0 contract freeze)."""

from __future__ import annotations

# Published sunset for `/api/v1` removal (target v3.0.0 line).
V1_SUNSET_HTTP = "Sat, 01 Aug 2027 00:00:00 GMT"

V1_DEPRECATION_HEADERS: dict[str, str] = {
    "Deprecation": "true",
    "Sunset": V1_SUNSET_HTTP,
    "Link": '</docs/api-v2>; rel="successor-version"',
}
