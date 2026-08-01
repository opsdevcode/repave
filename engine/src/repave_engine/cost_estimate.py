"""Parse and persist Infracost breakdown output for portal cost panels."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from repave_engine.gate_registry import GateResult

if TYPE_CHECKING:
    from repave_engine.pipeline import GenerationResult

COST_ESTIMATE_REL_PATH = Path(".repave") / "cost-estimate.json"


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
