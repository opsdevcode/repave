from __future__ import annotations

from repave_engine.cost_budgets import budget_status, resolve_entity_monthly_budget
from repave_engine.settings import CostBudgetConfig


def test_resolve_entity_monthly_budget_prefers_config() -> None:
    budgets = CostBudgetConfig(
        default_monthly_usd=100.0,
        entities={"acme-tf-vpc": 250.0},
    )
    resolved = resolve_entity_monthly_budget(
        "acme-tf-vpc",
        catalog_budget_usd="50",
        budgets=budgets,
    )
    assert resolved is not None
    assert resolved.monthly_usd == 250.0
    assert resolved.source == "config"


def test_resolve_entity_monthly_budget_uses_catalog_then_default() -> None:
    budgets = CostBudgetConfig(default_monthly_usd=100.0, entities={})
    resolved = resolve_entity_monthly_budget(
        "acme-tf-eks",
        catalog_budget_usd="75.5",
        budgets=budgets,
    )
    assert resolved is not None
    assert resolved.monthly_usd == 75.5
    assert resolved.source == "catalog"

    fallback = resolve_entity_monthly_budget("other", budgets=budgets)
    assert fallback is not None
    assert fallback.monthly_usd == 100.0
    assert fallback.source == "default"


def test_budget_status_over_and_under() -> None:
    level, detail = budget_status(amount_30d=120.0, monthly_budget_usd=100.0)
    assert level == "fail"
    assert "exceeds" in detail

    level, detail = budget_status(amount_30d=40.0, monthly_budget_usd=100.0)
    assert level == "pass"
    assert "40%" in detail
