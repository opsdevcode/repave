"""Chargeback export rows for finance handoff (v1.94)."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from repave_engine.finops_rollup import FinOpsRollup

FOCUS_EXPORT_COLUMNS: tuple[str, ...] = (
    "Owner",
    "ServiceName",
    "BillingCurrency",
    "BilledCost",
    "ChargePeriodStart",
    "ChargePeriodEnd",
    "EntityId",
    "MonthlyBudgetUsd",
)


@dataclass(frozen=True)
class ChargebackExportRow:
    owner: str
    service_name: str
    billing_currency: str
    billed_cost: str
    charge_period_start: str
    charge_period_end: str
    entity_id: str
    monthly_budget_usd: str

    def to_focus_dict(self) -> dict[str, str]:
        return {
            "Owner": self.owner,
            "ServiceName": self.service_name,
            "BillingCurrency": self.billing_currency,
            "BilledCost": self.billed_cost,
            "ChargePeriodStart": self.charge_period_start,
            "ChargePeriodEnd": self.charge_period_end,
            "EntityId": self.entity_id,
            "MonthlyBudgetUsd": self.monthly_budget_usd,
        }


def _period_bounds(*, lookback_days: int = 30) -> tuple[str, str]:
    end = datetime.now(tz=timezone.utc).replace(microsecond=0)
    start = end - timedelta(days=lookback_days)
    return start.isoformat(), end.isoformat()


def build_chargeback_export(
    rollup: FinOpsRollup,
    *,
    lookback_days: int = 30,
) -> tuple[ChargebackExportRow, ...]:
    period_start, period_end = _period_bounds(lookback_days=lookback_days)
    rows: list[ChargebackExportRow] = []
    for item in rollup.rows:
        if item.amount_float is None:
            continue
        budget = f"{item.monthly_budget_usd:.2f}" if item.monthly_budget_usd is not None else ""
        rows.append(
            ChargebackExportRow(
                owner=item.owner or "",
                service_name=item.display_name,
                billing_currency=item.currency or rollup.currency,
                billed_cost=item.amount_30d,
                charge_period_start=period_start,
                charge_period_end=period_end,
                entity_id=item.entity_id,
                monthly_budget_usd=budget,
            )
        )
    rows.sort(key=lambda row: (row.owner.casefold(), row.service_name.casefold()))
    return tuple(rows)


def chargeback_export_to_json(rows: tuple[ChargebackExportRow, ...]) -> list[dict[str, str]]:
    return [row.to_focus_dict() for row in rows]


def chargeback_export_to_csv(rows: tuple[ChargebackExportRow, ...]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(FOCUS_EXPORT_COLUMNS), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row.to_focus_dict())
    return buffer.getvalue()
