"""Fleet FinOps rollup for /platform/finops and Prometheus gauges."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from repave_engine.catalog_cost import enrich_entity_cost
from repave_engine.cost_budgets import budget_status, resolve_entity_monthly_budget
from repave_engine.cost_snapshot_store import (
    CostSnapshotEntry,
    build_cost_sparkline,
    cost_sparkline_detail,
    read_entity_cost_snapshots,
    read_latest_cost_snapshots,
)
from repave_engine.entity_catalog import CatalogEntity
from repave_engine.settings import PortalConfig


@dataclass(frozen=True)
class FinOpsEntityRow:
    entity_id: str
    display_name: str
    owner: str
    currency: str
    amount_30d: str
    amount_float: float | None
    monthly_budget_usd: float | None
    budget_level: str
    budget_detail: str
    sparkline: tuple[int, ...]
    sparkline_detail: str

    def to_public_dict(self) -> dict[str, object]:
        return {
            "entity_id": self.entity_id,
            "display_name": self.display_name,
            "owner": self.owner,
            "currency": self.currency,
            "amount_30d": self.amount_30d,
            "monthly_budget_usd": self.monthly_budget_usd,
            "budget_level": self.budget_level,
            "budget_detail": self.budget_detail,
            "sparkline": list(self.sparkline),
        }


@dataclass(frozen=True)
class FinOpsRollup:
    snapshots_enabled: bool
    currency: str
    entity_count: int
    entities_with_actuals: int
    entities_with_budget: int
    over_budget_count: int
    total_actual_30d: float
    total_budget_monthly: float
    rows: tuple[FinOpsEntityRow, ...]

    def to_public_dict(self) -> dict[str, object]:
        return {
            "snapshots_enabled": self.snapshots_enabled,
            "currency": self.currency,
            "entity_count": self.entity_count,
            "entities_with_actuals": self.entities_with_actuals,
            "entities_with_budget": self.entities_with_budget,
            "over_budget_count": self.over_budget_count,
            "total_actual_30d": f"{self.total_actual_30d:.2f}",
            "total_budget_monthly": f"{self.total_budget_monthly:.2f}",
            "rows": [row.to_public_dict() for row in self.rows],
        }


@dataclass(frozen=True)
class EntityCostShowback:
    sparkline: tuple[int, ...]
    sparkline_detail: str
    monthly_budget_usd: float | None
    budget_level: str
    budget_detail: str
    budget_used_pct: int | None


def _snapshot_history(
    portal_config: PortalConfig,
    entity_id: str,
    *,
    repo_root: Path | None,
) -> tuple[CostSnapshotEntry, ...]:
    if portal_config.cost_snapshots_file is None:
        return ()
    return read_entity_cost_snapshots(
        portal_config.cost_snapshots_file,
        entity_id,
        repo_root=repo_root,
    )


def build_entity_cost_showback(
    entity: CatalogEntity,
    portal_config: PortalConfig,
    *,
    repo_root: Path | None = None,
    amount_float: float | None = None,
    currency: str = "USD",
) -> EntityCostShowback:
    snapshots = _snapshot_history(portal_config, entity.entity_id, repo_root=repo_root)
    sparkline = build_cost_sparkline(snapshots)
    spark_detail = cost_sparkline_detail(snapshots, currency=currency) if snapshots else ""
    budget = resolve_entity_monthly_budget(
        entity.entity_id,
        catalog_budget_usd=entity.monthly_budget_usd,
        budgets=portal_config.cost_budgets,
    )
    monthly = budget.monthly_usd if budget is not None else None
    level, detail = budget_status(amount_30d=amount_float, monthly_budget_usd=monthly)
    used_pct = None
    if monthly is not None and amount_float is not None and monthly > 0:
        used_pct = min(int((amount_float / monthly) * 100), 999)
    return EntityCostShowback(
        sparkline=sparkline,
        sparkline_detail=spark_detail,
        monthly_budget_usd=monthly,
        budget_level=level,
        budget_detail=detail,
        budget_used_pct=used_pct,
    )


def build_finops_rollup(
    entities: Sequence[CatalogEntity],
    portal_config: PortalConfig,
    *,
    repo_root: Path | None = None,
) -> FinOpsRollup:
    snapshots_enabled = portal_config.cost_snapshots_file is not None
    latest: dict[str, CostSnapshotEntry] = {}
    if portal_config.cost_snapshots_file is not None:
        latest = read_latest_cost_snapshots(
            portal_config.cost_snapshots_file,
            repo_root=repo_root,
        )

    rows: list[FinOpsEntityRow] = []
    currency = "USD"
    total_actual = 0.0
    total_budget = 0.0
    with_actuals = 0
    with_budget = 0
    over_budget = 0

    for entity in entities:
        patched, actuals, _estimate = enrich_entity_cost(
            entity,
            portal_config,
            repo_root=repo_root,
        )
        amount_float = actuals.amount_float() if actuals is not None else None
        amount_label = actuals.amount_30d if actuals is not None else "—"
        if actuals is not None:
            currency = actuals.currency or currency
            if amount_float is not None:
                total_actual += amount_float
                with_actuals += 1
        elif entity.entity_id in latest:
            snap = latest[entity.entity_id]
            amount_float = snap.amount_float()
            amount_label = snap.amount_30d
            currency = snap.currency or currency
            if amount_float is not None:
                total_actual += amount_float
                with_actuals += 1

        budget = resolve_entity_monthly_budget(
            patched.entity_id,
            catalog_budget_usd=patched.monthly_budget_usd,
            budgets=portal_config.cost_budgets,
        )
        monthly = budget.monthly_usd if budget is not None else None
        if monthly is not None:
            total_budget += monthly
            with_budget += 1
        level, detail = budget_status(amount_30d=amount_float, monthly_budget_usd=monthly)
        if level == "fail":
            over_budget += 1

        snapshots = _snapshot_history(portal_config, patched.entity_id, repo_root=repo_root)
        if not snapshots and patched.entity_id in latest:
            snapshots = (latest[patched.entity_id],)
        sparkline = build_cost_sparkline(snapshots)
        spark_detail = cost_sparkline_detail(snapshots, currency=currency) if snapshots else ""

        rows.append(
            FinOpsEntityRow(
                entity_id=patched.entity_id,
                display_name=patched.display_name,
                owner=patched.owner,
                currency=currency,
                amount_30d=amount_label,
                amount_float=amount_float,
                monthly_budget_usd=monthly,
                budget_level=level,
                budget_detail=detail,
                sparkline=sparkline,
                sparkline_detail=spark_detail,
            )
        )

    rows.sort(key=lambda row: (row.budget_level != "fail", -(row.amount_float or 0.0)))
    return FinOpsRollup(
        snapshots_enabled=snapshots_enabled,
        currency=currency,
        entity_count=len(rows),
        entities_with_actuals=with_actuals,
        entities_with_budget=with_budget,
        over_budget_count=over_budget,
        total_actual_30d=total_actual,
        total_budget_monthly=total_budget,
        rows=tuple(rows),
    )
