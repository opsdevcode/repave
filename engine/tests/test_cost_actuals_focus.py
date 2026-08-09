from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from repave_engine.cost_actuals import (
    cost_reader_configured,
    fetch_entity_cost_actuals_for_portal,
    resolve_cost_reader,
)
from repave_engine.cost_actuals_focus import (
    FOCUS_SUPPORTED_COLUMNS,
    aggregate_focus_actuals,
    clear_focus_source_cache,
    load_focus_rows,
    parse_focus_row,
    parse_focus_tags,
)
from repave_engine.cost_cache import cache_clear
from repave_engine.entity_catalog import CatalogEntity
from repave_engine.finops_rollup import build_finops_rollup
from repave_engine.settings import CostBudgetConfig, CostFocusConfig, PortalConfig


def _entity(
    *,
    entity_id: str = "acme-tf-vpc",
    owner: str = "platform",
    display_name: str = "tf-vpc",
) -> CatalogEntity:
    return CatalogEntity(
        entity_id=entity_id,
        display_name=display_name,
        repo_url="https://github.com/acme/tf-vpc",
        local_path=None,
        owner=owner,
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


def test_focus_supported_columns_include_required_subset() -> None:
    assert "BilledCost" in FOCUS_SUPPORTED_COLUMNS
    assert "BillingCurrency" in FOCUS_SUPPORTED_COLUMNS
    assert "ServiceName" in FOCUS_SUPPORTED_COLUMNS
    assert "Tags" in FOCUS_SUPPORTED_COLUMNS


def test_parse_focus_tags_accepts_map_and_kv_list() -> None:
    assert parse_focus_tags({"Owner": "platform", "Service": "tf-vpc"}) == {
        "Owner": "platform",
        "Service": "tf-vpc",
    }
    assert parse_focus_tags([{"Key": "Owner", "Value": "platform"}]) == {"Owner": "platform"}


def test_parse_focus_row_reads_billed_cost_and_period() -> None:
    row = parse_focus_row(
        {
            "BilledCost": "12.34",
            "BillingCurrency": "USD",
            "ChargePeriodStart": "2026-07-10T00:00:00Z",
            "ServiceName": "Compute",
            "Tags": {"Owner": "platform"},
        }
    )
    assert row is not None
    assert row.billed_cost == 12.34
    assert row.currency == "USD"
    assert row.service_name == "Compute"
    assert row.tags["Owner"] == "platform"


def test_load_focus_rows_from_fixture(tmp_path: Path) -> None:
    clear_focus_source_cache()
    fixture = Path(__file__).resolve().parent / "fixtures" / "focus" / "sample.json"
    config = CostFocusConfig(file=str(fixture))
    rows = load_focus_rows(config, repo_root=tmp_path)
    assert len(rows) == 4


def test_fetch_entity_cost_actuals_focus_sums_matching_rows(tmp_path: Path) -> None:
    cache_clear()
    clear_focus_source_cache()
    fixture = Path(__file__).resolve().parent / "fixtures" / "focus" / "sample.json"
    config = CostFocusConfig(file=str(fixture), lookback_days=30)
    portal = PortalConfig(
        density="default",
        cost_reader="focus",
        cost_focus=config,
    )
    fixed_now = datetime(2026, 8, 9, tzinfo=timezone.utc)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[no-untyped-def]
            return fixed_now

    with patch("repave_engine.cost_actuals_focus.datetime", _FixedDatetime):
        summary = fetch_entity_cost_actuals_for_portal(portal, _entity(), repo_root=tmp_path)

    assert summary is not None
    assert summary.amount_30d == "125.50"
    assert summary.currency == "USD"
    assert summary.tag_coverage == "complete"
    assert "FOCUS ingest" in summary.detail


def test_resolve_cost_reader_focus_requires_file() -> None:
    assert resolve_cost_reader(cost_reader="focus", cost_actuals_url="", cost_focus_file="") is None
    assert (
        resolve_cost_reader(
            cost_reader="focus",
            cost_actuals_url="",
            cost_focus_file="data/focus.json",
        )
        == "focus"
    )
    assert cost_reader_configured(
        cost_reader="focus",
        cost_actuals_url="",
        cost_focus_file="data/focus.json",
    )


def test_focus_fixture_drives_finops_rollup(tmp_path: Path) -> None:
    cache_clear()
    clear_focus_source_cache()
    fixture = Path(__file__).resolve().parent / "fixtures" / "focus" / "sample.json"
    portal = PortalConfig(
        density="default",
        cost_reader="focus",
        cost_focus=CostFocusConfig(file=str(fixture), lookback_days=30),
        cost_budgets=CostBudgetConfig(default_monthly_usd=100.0, entities={}),
    )
    fixed_now = datetime(2026, 8, 9, tzinfo=timezone.utc)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[no-untyped-def]
            return fixed_now

    with patch("repave_engine.cost_actuals_focus.datetime", _FixedDatetime):
        rollup = build_finops_rollup([_entity()], portal, repo_root=tmp_path)

    assert rollup.entity_count == 1
    assert rollup.entities_with_actuals == 1
    assert rollup.total_actual_30d == 125.5
    assert rollup.over_budget_count == 1


def test_portal_config_loads_cost_focus_block(tmp_path: Path) -> None:
    from repave_engine.settings import load_portal_config

    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "portal:",
                "  cost_reader: focus",
                "  cost_focus:",
                "    file: data/focus/export.json",
                "    lookback_days: 45",
                "    tag_key_owner: Team",
                "    tag_key_service: App",
            ]
        ),
        encoding="utf-8",
    )
    config = load_portal_config(tmp_path)
    assert config.cost_reader == "focus"
    assert config.cost_focus == CostFocusConfig(
        file="data/focus/export.json",
        tag_key_owner="Team",
        tag_key_service="App",
        lookback_days=45,
        currency="USD",
    )


def test_portal_config_rejects_focus_without_file(tmp_path: Path) -> None:
    from repave_engine.settings import load_portal_config

    (tmp_path / "repave.config.yaml").write_text(
        "portal:\n  cost_reader: focus\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"cost_focus\.file"):
        load_portal_config(tmp_path)


def test_aggregate_focus_actuals_uses_service_name_fallback() -> None:
    config = CostFocusConfig(lookback_days=30)
    row = parse_focus_row(
        {
            "BilledCost": "9.99",
            "BillingCurrency": "USD",
            "ChargePeriodStart": "2026-08-01T00:00:00Z",
            "ServiceName": "tf-vpc",
            "Tags": {"Owner": "platform"},
        }
    )
    assert row is not None
    summary = aggregate_focus_actuals((row,), _entity(), config)
    assert summary is not None
    assert summary.amount_30d == "9.99"
