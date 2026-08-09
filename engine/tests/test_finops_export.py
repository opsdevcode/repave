from __future__ import annotations

from repave_engine.finops_export import (
    FOCUS_EXPORT_COLUMNS,
    ChargebackExportRow,
    build_chargeback_export,
    chargeback_export_to_csv,
    chargeback_export_to_json,
)
from repave_engine.finops_rollup import FinOpsEntityRow, FinOpsRollup


def _rollup() -> FinOpsRollup:
    return FinOpsRollup(
        snapshots_enabled=True,
        currency="USD",
        entity_count=2,
        entities_with_actuals=2,
        entities_with_budget=1,
        over_budget_count=0,
        total_actual_30d=175.5,
        total_budget_monthly=100.0,
        rows=(
            FinOpsEntityRow(
                entity_id="acme-tf-vpc",
                display_name="tf-vpc",
                owner="platform",
                currency="USD",
                amount_30d="125.50",
                amount_float=125.5,
                monthly_budget_usd=100.0,
                budget_level="fail",
                budget_detail="over",
                sparkline=(20, 40, 80),
                sparkline_detail="trend",
            ),
            FinOpsEntityRow(
                entity_id="acme-checkout",
                display_name="checkout-api",
                owner="payments",
                currency="USD",
                amount_30d="50.00",
                amount_float=50.0,
                monthly_budget_usd=None,
                budget_level="unknown",
                budget_detail="no budget",
                sparkline=(),
                sparkline_detail="",
            ),
        ),
    )


def test_build_chargeback_export_uses_focus_columns() -> None:
    rows = build_chargeback_export(_rollup())
    assert len(rows) == 2
    assert rows[0].owner == "payments"
    assert rows[0].service_name == "checkout-api"
    assert rows[0].billing_currency == "USD"
    assert rows[0].billed_cost == "50.00"
    assert rows[0].entity_id == "acme-checkout"
    assert rows[0].charge_period_start
    assert rows[0].charge_period_end


def test_chargeback_export_json_and_csv_shapes() -> None:
    rows = build_chargeback_export(_rollup())
    payload = chargeback_export_to_json(rows)
    assert payload[0]["Owner"] == "payments"
    assert payload[0]["ServiceName"] == "checkout-api"
    assert payload[0]["BilledCost"] == "50.00"
    csv_text = chargeback_export_to_csv(rows)
    header = csv_text.splitlines()[0]
    for column in FOCUS_EXPORT_COLUMNS:
        assert column in header


def test_chargeback_export_row_to_focus_dict() -> None:
    row = ChargebackExportRow(
        owner="platform",
        service_name="tf-vpc",
        billing_currency="USD",
        billed_cost="10.00",
        charge_period_start="2026-07-10T00:00:00+00:00",
        charge_period_end="2026-08-09T00:00:00+00:00",
        entity_id="acme-tf-vpc",
        monthly_budget_usd="100.00",
    )
    assert row.to_focus_dict()["MonthlyBudgetUsd"] == "100.00"
