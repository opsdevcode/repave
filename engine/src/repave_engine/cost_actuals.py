"""Pluggable read-only cloud cost actuals for portal catalog entities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx

TagCoverage = Literal["complete", "partial", "missing"]


class CostEntity(Protocol):
    @property
    def owner(self) -> str: ...

    @property
    def display_name(self) -> str: ...

    @property
    def entity_id(self) -> str: ...


@dataclass(frozen=True)
class CostActualsSummary:
    currency: str
    amount_30d: str
    as_of: str
    detail: str
    tag_coverage: TagCoverage
    source_url: str

    def to_public_dict(self) -> dict[str, str]:
        return {
            "currency": self.currency,
            "amount_30d": self.amount_30d,
            "as_of": self.as_of,
            "detail": self.detail,
            "tag_coverage": self.tag_coverage,
            "source_url": self.source_url,
        }


def entity_tag_coverage(entity: CostEntity) -> tuple[TagCoverage, str]:
    return tag_coverage_for_fields(entity.owner, entity.display_name)


def tag_coverage_for_fields(owner: str, display_name: str) -> tuple[TagCoverage, str]:
    has_owner = bool(owner.strip())
    has_service = bool(display_name.strip())
    if has_owner and has_service:
        return "complete", "Owner and service name available for cost allocation"
    if has_owner or has_service:
        missing = "service name" if has_owner else "owner"
        return "partial", f"Missing {missing} for full tag-based cost mapping"
    return "missing", "Missing owner and service name tags"


def format_cost_actuals_url(template: str, entity: CostEntity) -> str | None:
    raw = template.strip()
    if not raw:
        return None
    try:
        return raw.format(
            name=entity.display_name,
            service=entity.display_name,
            stack_name=entity.display_name,
            entity_id=entity.entity_id,
            owner=entity.owner or "",
        )
    except KeyError:
        return raw.format(name=entity.display_name)


def parse_cost_actuals_payload(
    payload: Any,
    *,
    source_url: str,
    tag_coverage: TagCoverage,
) -> CostActualsSummary | None:
    if not isinstance(payload, dict):
        return None
    currency = str(payload.get("currency", "USD")).strip() or "USD"
    amount = str(payload.get("amount_30d", payload.get("amount", ""))).strip()
    as_of = str(payload.get("as_of", payload.get("timestamp", ""))).strip()
    detail = str(payload.get("detail", payload.get("message", ""))).strip()
    coverage_raw = str(payload.get("tag_coverage", tag_coverage)).strip().lower()
    if coverage_raw in ("complete", "partial", "missing"):
        coverage: TagCoverage = coverage_raw  # type: ignore[assignment]
    else:
        coverage = tag_coverage
    if not amount:
        return None
    if not detail:
        detail = f"Last 30 days spend {currency} {amount}"
    return CostActualsSummary(
        currency=currency,
        amount_30d=amount,
        as_of=as_of,
        detail=detail,
        tag_coverage=coverage,
        source_url=source_url,
    )


def fetch_entity_cost_actuals(
    template: str,
    entity: CostEntity,
    *,
    timeout: float = 4.0,
) -> CostActualsSummary | None:
    """Fetch JSON cost actuals from a configured read-only URL template."""
    url = format_cost_actuals_url(template, entity)
    if not url:
        return None
    coverage, _ = entity_tag_coverage(entity)
    if coverage == "missing":
        return None
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    return parse_cost_actuals_payload(payload, source_url=url, tag_coverage=coverage)


CostReader = Literal["url", "aws", "azure", "k8s"]


def resolve_cost_reader(*, cost_reader: str, cost_actuals_url: str) -> CostReader | None:
    explicit = cost_reader.strip().lower()
    if explicit in ("url", "aws", "azure", "k8s"):
        return explicit  # type: ignore[return-value]
    if cost_actuals_url.strip():
        return "url"
    return None


def cost_reader_configured(*, cost_reader: str, cost_actuals_url: str) -> bool:
    return (
        resolve_cost_reader(cost_reader=cost_reader, cost_actuals_url=cost_actuals_url) is not None
    )


def fetch_entity_cost_actuals_for_portal(
    portal_config: object,
    entity: CostEntity,
) -> CostActualsSummary | None:
    """Dispatch to URL, AWS, or Azure cost reader based on portal config."""
    from repave_engine.settings import PortalConfig

    if not isinstance(portal_config, PortalConfig):
        return None
    reader = resolve_cost_reader(
        cost_reader=portal_config.cost_reader,
        cost_actuals_url=portal_config.cost_actuals_url,
    )
    if reader is None:
        return None
    if reader == "url":
        return fetch_entity_cost_actuals(portal_config.cost_actuals_url, entity)
    if reader == "aws":
        from repave_engine.cost_actuals_aws import fetch_entity_cost_actuals_aws

        return fetch_entity_cost_actuals_aws(portal_config.cost_aws, entity)
    if reader == "azure":
        from repave_engine.cost_actuals_azure import fetch_entity_cost_actuals_azure

        return fetch_entity_cost_actuals_azure(portal_config.cost_azure, entity)
    from repave_engine.cost_actuals_k8s import fetch_entity_cost_actuals_k8s

    return fetch_entity_cost_actuals_k8s(portal_config.cost_k8s, entity)
