from __future__ import annotations

from pathlib import Path

from repave_engine.cost_actuals import CostActualsSummary
from repave_engine.cost_snapshot_store import capture_cost_snapshots
from repave_engine.entity_catalog import CatalogEntity
from repave_engine.finops_rollup import build_finops_rollup
from repave_engine.settings import CostBudgetConfig, PortalConfig


def _entity(entity_id: str = "acme-tf-vpc") -> CatalogEntity:
    return CatalogEntity(
        entity_id=entity_id,
        display_name="tf-vpc",
        repo_url="https://github.com/acme/tf-vpc",
        local_path=None,
        owner="platform",
        blueprint_name="terraform-module-generic",
        blueprint_version="1.0.0",
        standard_source="",
        standard_version="",
        component_type="service",
        lifecycle="production",
        operator_phase="",
        operator_message="",
        remediation_pr_url="",
        manifest_name="",
        manifest_namespace="",
        source="fleet",
    )


def test_build_finops_rollup_counts_over_budget(tmp_path: Path) -> None:
    snapshot_file = tmp_path / "cost-snapshots.jsonl"
    capture_cost_snapshots(
        snapshot_file,
        [
            (
                "acme-tf-vpc",
                CostActualsSummary(
                    currency="USD",
                    amount_30d="150.00",
                    as_of="2026-08-01T00:00:00Z",
                    detail="ok",
                    tag_coverage="complete",
                    source_url="",
                ),
            )
        ],
        captured_at="2026-08-01T00:00:00Z",
    )
    portal = PortalConfig(
        density="default",
        cost_snapshots_enabled=True,
        cost_snapshots_file=snapshot_file,
        cost_budgets=CostBudgetConfig(default_monthly_usd=100.0, entities={}),
    )

    def _fetch(_portal: object, _entity: object, **kwargs: object) -> CostActualsSummary | None:
        return CostActualsSummary(
            currency="USD",
            amount_30d="150.00",
            as_of="2026-08-01T00:00:00Z",
            detail="ok",
            tag_coverage="complete",
            source_url="",
        )

    import repave_engine.catalog_cost as catalog_cost

    original = catalog_cost.fetch_entity_cost_actuals_for_portal
    catalog_cost.fetch_entity_cost_actuals_for_portal = _fetch
    try:
        rollup = build_finops_rollup([_entity()], portal)
    finally:
        catalog_cost.fetch_entity_cost_actuals_for_portal = original

    assert rollup.entity_count == 1
    assert rollup.over_budget_count == 1
    assert rollup.total_actual_30d == 150.0
    assert rollup.total_budget_monthly == 100.0
    assert rollup.rows[0].budget_level == "fail"
