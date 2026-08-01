"""Read-only AWS Cost Explorer actuals for portal catalog entities."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from repave_engine.cost_actuals import CostActualsSummary, CostEntity, entity_tag_coverage
from repave_engine.cost_cache import cache_get, cache_set

if TYPE_CHECKING:
    from repave_engine.settings import CostAwsConfig


def _cache_key(entity: CostEntity) -> str:
    return f"aws:{entity.entity_id}:{entity.owner}:{entity.display_name}"


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
                "Tags": {
                    "Key": tag_key_owner,
                    "Values": [owner.strip()],
                    "MatchOptions": ["EQUALS"],
                }
            }
        )
    if display_name.strip() and coverage == "complete":
        filters.append(
            {
                "Tags": {
                    "Key": tag_key_service,
                    "Values": [display_name.strip()],
                    "MatchOptions": ["EQUALS"],
                }
            }
        )
    if not filters:
        return None
    if len(filters) == 1:
        return filters[0]
    return {"And": filters}


def fetch_entity_cost_actuals_aws(
    config: CostAwsConfig,
    entity: CostEntity,
) -> CostActualsSummary | None:
    """Fetch last-30-day spend from AWS Cost Explorer (read-only, server-side)."""
    cached = cache_get(_cache_key(entity))
    if cached is not None:
        return cached

    coverage, cov_detail = entity_tag_coverage(entity)
    if coverage == "missing":
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
        import boto3
    except ImportError:
        return None

    end = datetime.now(tz=timezone.utc).date() + timedelta(days=1)
    start = end - timedelta(days=30)
    client = boto3.client("ce")
    try:
        response = client.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            Filter=tag_filter,
        )
    except Exception:
        return None

    amount = 0.0
    currency = "USD"
    for bucket in response.get("ResultsByTime", []):
        total = bucket.get("Total", {})
        unblended = total.get("UnblendedCost", {})
        if not isinstance(unblended, dict):
            continue
        raw_amount = str(unblended.get("Amount", "0")).strip()
        try:
            amount += float(raw_amount)
        except ValueError:
            continue
        unit = str(unblended.get("Unit", "")).strip()
        if unit:
            currency = unit

    as_of = datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()
    detail = f"AWS Cost Explorer L30D ({cov_detail}; provider data may lag 24-48h)"
    summary = CostActualsSummary(
        currency=currency,
        amount_30d=f"{amount:.2f}",
        as_of=as_of,
        detail=detail,
        tag_coverage=coverage,
        source_url="https://console.aws.amazon.com/cost-management/home",
    )
    cache_set(_cache_key(entity), summary)
    return summary
