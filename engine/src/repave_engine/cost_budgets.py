"""Monthly budget resolution for FinOps showback (v1.92)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from repave_engine.settings import CostBudgetConfig


@dataclass(frozen=True)
class EntityBudget:
    monthly_usd: float
    source: str  # config | catalog | default


def _parse_budget(value: str) -> float | None:
    raw = value.strip()
    if not raw:
        return None
    try:
        amount = float(Decimal(raw))
    except (InvalidOperation, ValueError):
        return None
    if amount < 0:
        return None
    return amount


def resolve_entity_monthly_budget(
    entity_id: str,
    *,
    catalog_budget_usd: str = "",
    budgets: CostBudgetConfig | None = None,
) -> EntityBudget | None:
    """Resolve monthly budget: per-entity config, catalog annotation, then default."""
    normalized_id = entity_id.strip()
    if budgets is not None and normalized_id in budgets.entities:
        return EntityBudget(monthly_usd=budgets.entities[normalized_id], source="config")
    catalog_amount = _parse_budget(catalog_budget_usd)
    if catalog_amount is not None:
        return EntityBudget(monthly_usd=catalog_amount, source="catalog")
    if budgets is not None and budgets.default_monthly_usd is not None:
        return EntityBudget(monthly_usd=budgets.default_monthly_usd, source="default")
    return None


def budget_status(
    *,
    amount_30d: float | None,
    monthly_budget_usd: float | None,
) -> tuple[str, str]:
    """Return (level, detail) for scorecard-style budget comparison."""
    if monthly_budget_usd is None or amount_30d is None:
        return "unknown", "Set monthly_budget_usd or capture cost actuals for budget comparison"
    if amount_30d <= monthly_budget_usd:
        pct = int((amount_30d / monthly_budget_usd) * 100) if monthly_budget_usd else 0
        return (
            "pass",
            f"L30D ${amount_30d:.2f} is {pct}% of ${monthly_budget_usd:.2f} monthly budget",
        )
    over = amount_30d - monthly_budget_usd
    return "fail", f"L30D ${amount_30d:.2f} exceeds ${monthly_budget_usd:.2f} budget by ${over:.2f}"
