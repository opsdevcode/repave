"""Pure auto-merge decision for low-risk mechanical remediations (v3)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from repave_engine.risk_class import ChangeClassification, RiskClass, classify_change
from repave_engine.v3_foundation import load_v3_foundation_config
from repave_engine.waivers import WaiverStatus, evaluate_waiver, load_waivers

if TYPE_CHECKING:
    from repave_engine.gate_registry import GateResult


@dataclass(frozen=True)
class GateOutcome:
    gate_id: str
    passed: bool


@dataclass(frozen=True)
class AutoMergeDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class AutoMergeAction:
    """Outcome of a merge attempt. Built without I/O; callers invoke GitHub separately."""

    merged: bool
    reason: str
    merge_commit_sha: str = ""
    pull_request_number: int = 0


def skip_github_merge(
    decision: AutoMergeDecision,
    *,
    pull_number: int,
) -> AutoMergeAction | None:
    """Return a skip result, or None when the caller should invoke the GitHub merge API."""
    if not decision.allowed:
        return AutoMergeAction(
            False,
            decision.reason,
            pull_request_number=pull_number,
        )
    if pull_number <= 0:
        return AutoMergeAction(
            False,
            (
                f"cannot merge: invalid pull request number {pull_number}; "
                "open the upgrade PR before auto-merge"
            ),
            pull_request_number=pull_number,
        )
    return None


def merge_action_from_github(
    *,
    pull_number: int,
    sha: str,
    error: str = "",
) -> AutoMergeAction:
    """Map a GitHub merge response or error string to an action (no I/O)."""
    if error:
        return AutoMergeAction(
            False,
            error,
            pull_request_number=pull_number,
        )
    return AutoMergeAction(
        True,
        "merged mechanical pin bump with green gates",
        merge_commit_sha=sha,
        pull_request_number=pull_number,
    )


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


def change_type_from_upgrade(
    *,
    pin_changes: tuple[object, ...],
    policy_changes: tuple[str, ...],
) -> str:
    """Infer a classifier change type from an upgrade plan (no I/O)."""
    if policy_changes:
        return "policy_change"
    if pin_changes:
        return "pin_bump"
    return "standard"


def gate_outcomes_from_results(gates: tuple[GateResult, ...]) -> tuple[GateOutcome, ...]:
    """Skipped gates are not green."""
    return tuple(GateOutcome(gate.name, gate.passed and not gate.skipped) for gate in gates)


def waiver_status_for_gates(
    *,
    repo_root: Path,
    gates: tuple[GateResult, ...],
) -> WaiverStatus:
    """Open/expired waiver on any planned gate blocks auto-merge."""
    config = load_v3_foundation_config(repo_root)
    if not config.enabled or config.waivers_file is None:
        return WaiverStatus.MISSING
    records = load_waivers(config.waivers_file)
    if not records:
        return WaiverStatus.MISSING
    statuses = [
        evaluate_waiver(gate_id=gate.name, waivers=records).status for gate in gates if gate.name
    ]
    if WaiverStatus.EXPIRED in statuses:
        return WaiverStatus.EXPIRED
    if WaiverStatus.ACTIVE in statuses:
        return WaiverStatus.ACTIVE
    if WaiverStatus.EXPIRING in statuses:
        return WaiverStatus.EXPIRING
    return WaiverStatus.MISSING


def decide_auto_merge_for_plan(
    *,
    repo_root: Path,
    blueprint_name: str,
    pin_changes: tuple[object, ...],
    policy_changes: tuple[str, ...],
    gates: tuple[GateResult, ...],
) -> AutoMergeDecision:
    """Load v3 knobs and decide for a plan/upgrade result. Does not merge GitHub PRs."""
    config = load_v3_foundation_config(repo_root)
    classification = classify_change(
        change_type=change_type_from_upgrade(
            pin_changes=pin_changes,
            policy_changes=policy_changes,
        ),
        blueprint=blueprint_name,
    )
    return decide_auto_merge(
        classification=classification,
        gates=gate_outcomes_from_results(gates),
        waiver_status=waiver_status_for_gates(repo_root=repo_root, gates=gates),
        error_budget_healthy=True,
        v3_enabled=config.enabled,
        auto_merge_enabled=config.auto_merge_enabled,
        kill_switch=config.auto_merge_kill_switch,
    )
