"""Library catalog cost badges: actuals, local estimates, trends, and batch enrichment."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from repave_engine.cost_actuals import (
    CostActualsSummary,
    cost_reader_configured,
    fetch_entity_cost_actuals_for_portal,
)
from repave_engine.cost_estimate import CostEstimate, load_cost_estimate_file
from repave_engine.cost_snapshot_store import (
    build_cost_sparkline,
    capture_cost_snapshots,
    cost_sparkline_detail,
    read_entity_cost_snapshots,
)
from repave_engine.entity_catalog import CatalogEntity, apply_cost_to_scorecard

if TYPE_CHECKING:
    from repave_engine.settings import PortalConfig


def format_cost_badge(
    *,
    actuals: CostActualsSummary | None,
    estimate: CostEstimate | None,
) -> tuple[str, str]:
    """Return (badge label, tooltip detail) for library tiles; actuals beat estimate."""
    if actuals is not None:
        as_of = actuals.as_of[:19] if actuals.as_of else "unknown"
        detail = actuals.detail or f"Last 30 days as of {as_of}"
        return f"L30D {actuals.currency} {actuals.amount_30d}", detail
    if estimate is not None and estimate.monthly_cost and estimate.monthly_cost != "—":
        return f"Est {estimate.currency} {estimate.monthly_cost}/mo", estimate.detail
    return "", ""


def local_cost_estimate(entity: CatalogEntity) -> CostEstimate | None:
    if entity.local_path is None:
        return None
    return load_cost_estimate_file(Path(entity.local_path))


def enrich_entity_cost(
    entity: CatalogEntity,
    portal_config: PortalConfig,
    *,
    cost_actuals: CostActualsSummary | None = None,
) -> tuple[CatalogEntity, CostActualsSummary | None, CostEstimate | None]:
    """Apply cost badge and scorecard dimension from reader actuals and/or local estimate."""
    configured = cost_reader_configured(
        cost_reader=portal_config.cost_reader,
        cost_actuals_url=portal_config.cost_actuals_url,
    )
    actuals = (
        cost_actuals
        if cost_actuals is not None
        else (fetch_entity_cost_actuals_for_portal(portal_config, entity) if configured else None)
    )
    estimate = local_cost_estimate(entity)
    badge, badge_detail = format_cost_badge(actuals=actuals, estimate=estimate)
    patched = replace(
        entity,
        scorecard=apply_cost_to_scorecard(
            entity.scorecard,
            owner=entity.owner,
            display_name=entity.display_name,
            cost_actuals=actuals,
            cost_actuals_configured=configured,
            cost_estimate=estimate,
        ),
        cost_badge=badge,
        cost_badge_detail=badge_detail,
    )
    return patched, actuals, estimate


def attach_cost_sparkline(entity: CatalogEntity, portal_config: PortalConfig) -> CatalogEntity:
    if not portal_config.cost_snapshots_enabled or portal_config.cost_snapshots_file is None:
        return entity
    snapshots = read_entity_cost_snapshots(portal_config.cost_snapshots_file, entity.entity_id)
    sparkline = build_cost_sparkline(snapshots)
    if not sparkline:
        return entity
    currency = snapshots[-1].currency if snapshots else "USD"
    return replace(
        entity,
        cost_sparkline=sparkline,
        cost_sparkline_detail=cost_sparkline_detail(snapshots, currency=currency),
    )


def enrich_catalog_entities_with_cost(
    entities: Sequence[CatalogEntity],
    portal_config: PortalConfig,
) -> tuple[CatalogEntity, ...]:
    """Fetch cost actuals (cached) and local estimates; patch scorecards, badges, and trends."""
    enriched: list[CatalogEntity] = []
    capture_pairs: list[tuple[str, CostActualsSummary]] = []
    for entity in entities:
        patched, actuals, _estimate = enrich_entity_cost(entity, portal_config)
        if (
            actuals is not None
            and portal_config.cost_snapshots_enabled
            and portal_config.cost_snapshots_file is not None
        ):
            capture_pairs.append((patched.entity_id, actuals))
        enriched.append(patched)
    if capture_pairs and portal_config.cost_snapshots_file is not None:
        capture_cost_snapshots(portal_config.cost_snapshots_file, capture_pairs)
    if portal_config.cost_snapshots_file is not None:
        enriched = [attach_cost_sparkline(entity, portal_config) for entity in enriched]
    return tuple(enriched)
    return tuple(enriched)
