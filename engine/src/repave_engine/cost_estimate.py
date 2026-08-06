"""Parse and persist Infracost breakdown output for portal cost panels."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Any

from repave_engine.gate_registry import GateResult

if TYPE_CHECKING:
    from repave_engine.pipeline import GenerationResult

COST_ESTIMATE_REL_PATH = Path(".repave") / "cost-estimate.json"


@dataclass(frozen=True)
class ResourceCost:
    """Monthly cost of one resource, addressable the same way the state graph is."""

    address: str
    currency: str
    monthly_cost: Decimal

    def merge(self, other: ResourceCost) -> ResourceCost:
        """Combine duplicate addresses across projects into one figure."""
        return ResourceCost(
            address=self.address,
            currency=self.currency,
            monthly_cost=self.monthly_cost + other.monthly_cost,
        )

    def to_public_dict(self) -> dict[str, str]:
        return {
            "address": self.address,
            "currency": self.currency,
            "monthly_cost": f"{self.monthly_cost:.2f}",
        }


@dataclass(frozen=True)
class CostEstimate:
    currency: str
    monthly_cost: str
    hourly_cost: str
    resource_count: int
    detail: str

    def to_public_dict(self) -> dict[str, str | int]:
        return {
            "currency": self.currency,
            "monthly_cost": self.monthly_cost,
            "hourly_cost": self.hourly_cost,
            "resource_count": self.resource_count,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class CostEstimateDelta:
    """Before/after estimate comparison for upgrade/import previews (v1.91)."""

    before: CostEstimate | None
    after: CostEstimate | None
    delta_monthly: str | None
    detail: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "before": None if self.before is None else self.before.to_public_dict(),
            "after": None if self.after is None else self.after.to_public_dict(),
            "delta_monthly": self.delta_monthly,
            "detail": self.detail,
        }


def _monthly_as_decimal(value: str) -> Decimal | None:
    text = value.strip()
    if not text or text == "—":
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def diff_cost_estimates(
    before: CostEstimate | None,
    after: CostEstimate | None,
) -> CostEstimateDelta | None:
    if before is None and after is None:
        return None
    before_val = None if before is None else _monthly_as_decimal(before.monthly_cost)
    after_val = None if after is None else _monthly_as_decimal(after.monthly_cost)
    delta_monthly: str | None = None
    if (
        before is not None
        and after is not None
        and before_val is not None
        and after_val is not None
    ):
        delta = after_val - before_val
        sign = "+" if delta >= 0 else ""
        currency = after.currency
        delta_monthly = f"{sign}{delta:.2f}"
        detail = (
            f"Estimate delta {currency} {delta_monthly}/month "
            f"({before.monthly_cost} → {after.monthly_cost})"
        )
    elif after is not None:
        detail = f"New estimate {after.detail}"
    else:
        detail = f"Previous estimate {before.detail}" if before is not None else "No estimate"
    return CostEstimateDelta(
        before=before,
        after=after,
        delta_monthly=delta_monthly,
        detail=detail,
    )


def cost_estimate_from_gate_results(gates: Iterable[GateResult]) -> CostEstimate | None:
    """Prefer persisted message parse; used for audit/PR evidence."""
    return cost_estimate_from_gates(list(gates))


def audit_extra_for_cost_estimate(estimate: CostEstimate | None) -> dict[str, Any]:
    """Flat audit `extra` fields for outcome correlation (FinOps v1.91)."""
    if estimate is None:
        return {}
    return {
        "cost_estimate_monthly": estimate.monthly_cost,
        "cost_estimate_currency": estimate.currency,
        "cost_estimate_resources": estimate.resource_count,
        "cost_estimate_detail": estimate.detail,
    }


def parse_infracost_breakdown(payload: Any) -> CostEstimate | None:
    if not isinstance(payload, dict):
        return None
    currency = str(payload.get("currency", "USD")).strip() or "USD"
    monthly = str(payload.get("totalMonthlyCost", "")).strip()
    hourly = str(payload.get("totalHourlyCost", "")).strip()
    resources = 0
    projects = payload.get("projects")
    if isinstance(projects, list):
        for project in projects:
            if not isinstance(project, dict):
                continue
            breakdown = project.get("breakdown")
            if isinstance(breakdown, dict):
                items = breakdown.get("resources")
                if isinstance(items, list):
                    resources += len(items)
    if not monthly and not hourly:
        return None
    monthly_label = monthly or "—"
    detail = f"Estimated {currency} {monthly_label}/month"
    if resources:
        detail = f"{detail} across {resources} resource(s)"
    return CostEstimate(
        currency=currency,
        monthly_cost=monthly_label,
        hourly_cost=hourly or "—",
        resource_count=resources,
        detail=detail,
    )


def parse_resource_costs(payload: Any) -> dict[str, ResourceCost]:
    """Per-resource monthly cost from an Infracost breakdown, keyed by address.

    Feeds the join onto the state graph (ADR 004 Phase 2): with an address key on both
    sides, "what does this blast radius cost" is a lookup rather than a second tool run.
    Subresources roll up into their parent, because the graph has no node for them.
    """
    costs: dict[str, ResourceCost] = {}
    if not isinstance(payload, dict):
        return costs
    currency = str(payload.get("currency", "USD")).strip() or "USD"

    projects = payload.get("projects")
    if not isinstance(projects, list):
        return costs
    for project in projects:
        if not isinstance(project, dict):
            continue
        breakdown = project.get("breakdown")
        if not isinstance(breakdown, dict):
            continue
        resources = breakdown.get("resources")
        if not isinstance(resources, list):
            continue
        for resource in resources:
            parsed = _resource_cost(resource, currency)
            if parsed is None:
                continue
            existing = costs.get(parsed.address)
            costs[parsed.address] = parsed if existing is None else existing.merge(parsed)
    return costs


def _resource_cost(resource: Any, currency: str) -> ResourceCost | None:
    if not isinstance(resource, dict):
        return None
    address = str(resource.get("name", "")).strip()
    if not address:
        return None
    monthly = _as_decimal(resource.get("monthlyCost"))
    for sub in resource.get("subresources") or []:
        if isinstance(sub, dict):
            monthly += _as_decimal(sub.get("monthlyCost"))
    return ResourceCost(address=address, currency=currency, monthly_cost=monthly)


def _as_decimal(value: Any) -> Decimal:
    """Infracost emits costs as strings; null means "not priced", which is not zero cost."""
    if value is None:
        return Decimal(0)
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal(0)


def total_monthly_cost(
    costs: dict[str, ResourceCost], addresses: Iterable[str]
) -> tuple[Decimal, tuple[str, ...]]:
    """Sum costs over addresses. Returns (total, addresses with no price)."""
    total = Decimal(0)
    unpriced: list[str] = []
    for address in addresses:
        found = costs.get(address)
        if found is None:
            unpriced.append(address)
            continue
        total += found.monthly_cost
    return total, tuple(sorted(unpriced))


def write_cost_estimate_file(output_dir: Path, estimate: CostEstimate) -> Path:
    path = output_dir / COST_ESTIMATE_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(estimate.to_public_dict(), indent=2), encoding="utf-8")
    return path


def load_cost_estimate_file(output_dir: Path) -> CostEstimate | None:
    path = output_dir / COST_ESTIMATE_REL_PATH
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return CostEstimate(
        currency=str(payload.get("currency", "USD")),
        monthly_cost=str(payload.get("monthly_cost", "")),
        hourly_cost=str(payload.get("hourly_cost", "")),
        resource_count=int(payload.get("resource_count", 0)),
        detail=str(payload.get("detail", "")),
    )


def cost_estimate_from_gates(gates: list[GateResult]) -> CostEstimate | None:
    for gate in gates:
        if gate.name != "infracost" or gate.skipped:
            continue
        text = gate.message.strip()
        if not text or "estimated" not in text.lower():
            return None
        parts = text.split("Estimated ", 1)
        if len(parts) != 2:
            return None
        tail = parts[1]
        currency = "USD"
        monthly = tail.split("/month", 1)[0].strip()
        if " " in monthly:
            currency, monthly = monthly.split(" ", 1)
        return CostEstimate(
            currency=currency,
            monthly_cost=monthly,
            hourly_cost="—",
            resource_count=0,
            detail=text,
        )
    return None


def cost_estimate_for_result(result: GenerationResult) -> CostEstimate | None:
    loaded = load_cost_estimate_file(result.render.output_dir)
    if loaded is not None:
        return loaded
    return cost_estimate_from_gates(result.gates)
