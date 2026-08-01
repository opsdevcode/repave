"""Read-only SLO summary fetch for portal entity health panels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import httpx

from repave_engine.entity_catalog import CatalogEntity

SloStatus = Literal["healthy", "degraded", "unknown"]


@dataclass(frozen=True)
class SloSummary:
    status: SloStatus
    slo_target: str
    slo_current: str
    detail: str
    source_url: str

    def to_public_dict(self) -> dict[str, str]:
        return {
            "status": self.status,
            "slo_target": self.slo_target,
            "slo_current": self.slo_current,
            "detail": self.detail,
            "source_url": self.source_url,
        }


def format_slo_url(template: str, entity: CatalogEntity) -> str | None:
    raw = template.strip()
    if not raw:
        return None
    try:
        return raw.format(
            name=entity.display_name,
            service=entity.display_name,
            entity_id=entity.entity_id,
        )
    except KeyError:
        return raw.format(name=entity.display_name)


def _normalize_status(raw: str) -> SloStatus:
    lowered = raw.strip().lower()
    if lowered in ("healthy", "ok", "pass", "green"):
        return "healthy"
    if lowered in ("degraded", "warn", "yellow", "breaching"):
        return "degraded"
    return "unknown"


def parse_slo_payload(payload: Any, *, source_url: str) -> SloSummary | None:
    if not isinstance(payload, dict):
        return None
    status = _normalize_status(str(payload.get("status", "unknown")))
    target = str(payload.get("slo_target", payload.get("target", ""))).strip()
    current = str(payload.get("slo_current", payload.get("current", ""))).strip()
    detail = str(payload.get("detail", payload.get("message", ""))).strip()
    if not any((target, current, detail)):
        return None
    return SloSummary(
        status=status,
        slo_target=target,
        slo_current=current,
        detail=detail,
        source_url=source_url,
    )


def fetch_entity_slo_summary(
    template: str,
    entity: CatalogEntity,
    *,
    timeout: float = 4.0,
) -> SloSummary | None:
    """Fetch JSON SLO summary from a configured read-only URL template."""
    url = format_slo_url(template, entity)
    if not url:
        return None
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    return parse_slo_payload(payload, source_url=url)
