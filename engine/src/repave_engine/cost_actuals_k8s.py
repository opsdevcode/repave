"""Read-only in-cluster Kubernetes cost allocation (OpenCost-compatible API)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import httpx

from repave_engine.cost_actuals import (
    CostActualsSummary,
    CostEntity,
    TagCoverage,
    entity_tag_coverage,
    format_cost_actuals_url,
)
from repave_engine.cost_cache import cache_get, cache_set

if TYPE_CHECKING:
    from repave_engine.settings import CostK8sConfig

logger = logging.getLogger(__name__)


def _cache_key(entity: CostEntity) -> str:
    return f"k8s:{entity.entity_id}:{entity.display_name}"


def format_allocation_key(template: str, entity: CostEntity) -> str | None:
    """Resolve the OpenCost allocation map key for an entity."""
    key = format_cost_actuals_url(template, entity)
    if not key:
        return None
    return key.strip()


def parse_opencost_allocation_payload(
    payload: Any,
    *,
    allocation_key: str,
    source_url: str,
    tag_coverage: TagCoverage,
    currency: str,
) -> CostActualsSummary | None:
    """Extract L30D spend for one allocation key from an OpenCost /allocation response."""
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return None
    allocation_set = data[-1]
    if not isinstance(allocation_set, dict):
        return None
    entry = allocation_set.get(allocation_key)
    if not isinstance(entry, dict):
        return None
    raw_cost = entry.get("totalCost", entry.get("total_cost"))
    if raw_cost is None:
        return None
    try:
        amount = float(raw_cost)
    except (TypeError, ValueError):
        return None

    as_of = datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()
    window = entry.get("window")
    if isinstance(window, dict):
        end = str(window.get("end", "")).strip()
        if end:
            as_of = end

    detail = (
        f"OpenCost K8s allocation ({allocation_key}); "
        "in-cluster list/on-demand pricing; idle/unshared costs excluded by default"
    )
    return CostActualsSummary(
        currency=currency,
        amount_30d=f"{amount:.2f}",
        as_of=as_of,
        detail=detail,
        tag_coverage=tag_coverage,
        source_url=source_url,
    )


def fetch_entity_cost_actuals_k8s(
    config: CostK8sConfig,
    entity: CostEntity,
    *,
    timeout: float = 4.0,
) -> CostActualsSummary | None:
    """Fetch last-window spend from an in-cluster OpenCost allocation API."""
    cached = cache_get(_cache_key(entity))
    if cached is not None:
        return cached

    coverage, _ = entity_tag_coverage(entity)
    if coverage == "missing":
        return None

    allocation_key = format_allocation_key(config.allocation_key, entity)
    if not allocation_key:
        return None

    base = config.base_url.strip().rstrip("/")
    if not base:
        return None

    params = {
        "window": config.window.strip() or "30d",
        "aggregate": config.aggregate.strip() or "label:app.kubernetes.io/name",
        "accumulate": "true",
    }
    api_url = f"{base}/allocation"
    headers: dict[str, str] = {"Accept": "application/json"}
    token = os.environ.get("REPAVE_OPENCOST_TOKEN", "").strip()
    if not token:
        token = os.environ.get("REPAVE_KUBE_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = httpx.get(
            api_url,
            params=params,
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.info("k8s cost allocation fetch failed for %s: %s", entity.entity_id, exc)
        return None

    summary = parse_opencost_allocation_payload(
        payload,
        allocation_key=allocation_key,
        source_url=api_url,
        tag_coverage=coverage,
        currency=config.currency.strip() or "USD",
    )
    if summary is not None:
        cache_set(_cache_key(entity), summary)
    return summary
