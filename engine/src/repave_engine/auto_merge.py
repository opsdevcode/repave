"""Pure auto-merge decision for low-risk mechanical remediations (v3)."""

from __future__ import annotations

from dataclasses import dataclass

from repave_engine.risk_class import ChangeClassification, RiskClass
from repave_engine.waivers import WaiverStatus


@dataclass(frozen=True)
class GateOutcome:
    gate_id: str
    passed: bool


@dataclass(frozen=True)
class AutoMergeDecision:
    allowed: bool
    reason: str


def decide_auto_merge(
    *,
    classification: ChangeClassification,
    gates: tuple[GateOutcome, ...],
    waiver_status: WaiverStatus,
    error_budget_healthy: bool,
    v3_enabled: bool,
    auto_merge_enabled: bool,
    kill_switch: bool,
) -> AutoMergeDecision:
    """Decide from declared inputs only — no I/O (ADR 008 autonomy safety)."""
    if not v3_enabled:
        return AutoMergeDecision(
            False,
            "v3 foundation is off; set v3.enabled: true before auto-merge",
        )
    if kill_switch:
        return AutoMergeDecision(
            False,
            "v3.auto_merge.kill_switch is true; set it false to allow mechanical auto-merge",
        )
    if not auto_merge_enabled:
        return AutoMergeDecision(
            False,
            "auto-merge is off; set v3.auto_merge.enabled: true",
        )
    if classification.risk_class is not RiskClass.MECHANICAL:
        return AutoMergeDecision(
            False,
            f"change type {classification.change_type!r} is {classification.risk_class}; "
            "only mechanical pin bumps auto-merge",
        )
    failed = tuple(gate.gate_id for gate in gates if not gate.passed)
    if failed:
        return AutoMergeDecision(
            False,
            f"gate {failed[0]} is not green; auto-merge requires every configured gate to pass",
        )
    if waiver_status in {WaiverStatus.ACTIVE, WaiverStatus.EXPIRING}:
        return AutoMergeDecision(
            False,
            f"open waiver ({waiver_status}); auto-merge requires no open waiver",
        )
    if waiver_status is WaiverStatus.EXPIRED:
        return AutoMergeDecision(
            False,
            "expired waiver; remove it or restore a green gate run before auto-merge",
        )
    if not error_budget_healthy:
        return AutoMergeDecision(
            False,
            "error budget is not healthy; restore the fleet SLO before auto-merge",
        )
    return AutoMergeDecision(True, "mechanical change with green gates and a healthy error budget")
