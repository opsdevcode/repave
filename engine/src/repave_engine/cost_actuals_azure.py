"""Read-only Azure Cost Management actuals for portal catalog entities."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import httpx

from repave_engine.cost_actuals import CostActualsSummary, CostEntity, entity_tag_coverage
from repave_engine.cost_cache import cache_get, cache_set

if TYPE_CHECKING:
    from repave_engine.settings import CostAzureConfig

_AZURE_MGMT_SCOPE = "https://management.azure.com/.default"
_QUERY_API = "2023-11-01"


def _cache_key(entity: CostEntity) -> str:
    return f"azure:{entity.entity_id}:{entity.owner}:{entity.display_name}"


def _resolve_scope(config: CostAzureConfig) -> str | None:
    scope = config.scope.strip()
    if scope:
        return scope if scope.startswith("/") else f"/{scope}"
    subscription_id = config.subscription_id.strip()
    if subscription_id:
        return f"/subscriptions/{subscription_id}"
    return None


def _build_tag_filter(
    *,
    tag_key_owner: str,
    tag_key_service: str,
    owner: str,
    display_name: str,
    coverage: str,
) -> dict[str, object] | None:
    filters: list[dict[str, object]] = []
    if owner.strip():
        filters.append(
            {
                "tags": {
                    "name": tag_key_owner,
                    "operator": "In",
                    "values": [owner.strip()],
                }
            }
        )
    if display_name.strip() and coverage == "complete":
        filters.append(
            {
                "tags": {
                    "name": tag_key_service,
                    "operator": "In",
                    "values": [display_name.strip()],
                }
            }
        )
    if not filters:
        return None
    if len(filters) == 1:
        return filters[0]
    return {"and": filters}


def _parse_query_response(payload: Any) -> tuple[float, str] | None:
    if not isinstance(payload, dict):
        return None
    properties = payload.get("properties")
    if not isinstance(properties, dict):
        return None
    rows = properties.get("rows")
    if not isinstance(rows, list):
        return None
    total = 0.0
    currency = "USD"
    for row in rows:
        if not isinstance(row, list) or not row:
            continue
        try:
            total += float(row[0])
        except (TypeError, ValueError):
            continue
        if len(row) > 1 and isinstance(row[1], str) and row[1].strip():
            currency = row[1].strip()
    return total, currency


def fetch_entity_cost_actuals_azure(
    config: CostAzureConfig,
    entity: CostEntity,
) -> CostActualsSummary | None:
    """Fetch last-30-day spend from Azure Cost Management (read-only, server-side)."""
    cached = cache_get(_cache_key(entity))
    if cached is not None:
        return cached

    coverage, cov_detail = entity_tag_coverage(entity)
    if coverage == "missing":
        return None

    scope = _resolve_scope(config)
    if scope is None:
        return None

    tag_filter = _build_tag_filter(
        tag_key_owner=config.tag_key_owner,
        tag_key_service=config.tag_key_service,
        owner=entity.owner,
        display_name=entity.display_name,
        coverage=coverage,
    )
    if tag_filter is None:
        return None

    try:
        from azure.identity import DefaultAzureCredential
    except ImportError:
        return None

    body: dict[str, object] = {
        "type": "ActualCost",
        "timeframe": "TheLast30Days",
        "dataset": {
            "granularity": "None",
            "aggregation": {
                "totalCost": {
                    "name": "Cost",
                    "function": "Sum",
                }
            },
            "filter": tag_filter,
        },
    }

    url = f"https://management.azure.com{scope}/providers/Microsoft.CostManagement/query?api-version={_QUERY_API}"
    try:
        credential = DefaultAzureCredential()
        token = credential.get_token(_AZURE_MGMT_SCOPE)
        response = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {token.token}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=8.0,
        )
        response.raise_for_status()
        parsed = _parse_query_response(response.json())
    except Exception:
        return None

    if parsed is None:
        return None
    amount, currency = parsed
    as_of = datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()
    detail = f"Azure Cost Management L30D ({cov_detail}; provider data may lag 24-48h)"
    portal_url = (
        f"https://portal.azure.com/#view/Microsoft_Azure_CostManagement/"
        f"Menu/~/overview/scope/{scope.lstrip('/')}"
    )
    summary = CostActualsSummary(
        currency=currency,
        amount_30d=f"{amount:.2f}",
        as_of=as_of,
        detail=detail,
        tag_coverage=coverage,
        source_url=portal_url,
    )
    cache_set(_cache_key(entity), summary)
    return summary
