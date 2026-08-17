"""Handoff URLs between the HTML workbench and the Backstage catalog IDP."""

from __future__ import annotations

from urllib.parse import quote


def backstage_catalog_entity_href(
    backstage_url: str,
    *,
    name: str,
    namespace: str = "default",
    kind: str = "component",
) -> str:
    """Build a Backstage entity page URL, or empty when the IDP base is unset."""
    base = backstage_url.strip().rstrip("/")
    component = name.strip()
    if not base or not component:
        return ""
    safe_ns = quote(namespace.strip() or "default", safe="-_.")
    safe_kind = quote(kind.strip() or "component", safe="-_.")
    safe_name = quote(component, safe="-_.")
    return f"{base}/catalog/{safe_ns}/{safe_kind}/{safe_name}"
