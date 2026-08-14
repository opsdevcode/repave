"""Table-driven auto-merge decisions — no I/O (ADR 008)."""

from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.auto_merge import (
    AutoMergeDecision,
    GateOutcome,
    change_type_from_upgrade,
    decide_auto_merge,
    decide_auto_merge_for_plan,
)
from repave_engine.gate_registry import GateResult
from repave_engine.risk_class import ChangeClassification, RiskClass, classify_change
from repave_engine.waivers import WaiverStatus

_GREEN = (GateOutcome("checkov", True), GateOutcome("opa", True))
_PIN = ChangeClassification(RiskClass.MECHANICAL, "pin_bump", "terraform-module-generic")


def _decide(
    *,
    classification: ChangeClassification = _PIN,
    gates: tuple[GateOutcome, ...] = _GREEN,
    waiver_status: WaiverStatus = WaiverStatus.MISSING,
    error_budget_healthy: bool = True,
    v3_enabled: bool = True,
    auto_merge_enabled: bool = True,
    kill_switch: bool = False,
) -> AutoMergeDecision:
    return decide_auto_merge(
        classification=classification,
        gates=gates,
        waiver_status=waiver_status,
        error_budget_healthy=error_budget_healthy,
        v3_enabled=v3_enabled,
        auto_merge_enabled=auto_merge_enabled,
        kill_switch=kill_switch,
    )


def test_mechanical_pin_bump_auto_merges_when_gates_and_budget_are_healthy() -> None:
    decision = _decide()
    assert decision.allowed is True
    assert "mechanical" in decision.reason


@pytest.mark.parametrize(
    ("kwargs", "needle"),
    [
        ({"v3_enabled": False}, "v3.enabled"),
        ({"kill_switch": True}, "kill_switch"),
        ({"auto_merge_enabled": False}, "v3.auto_merge.enabled"),
        (
            {
                "classification": ChangeClassification(
                    RiskClass.SENSITIVE, "policy_change", "opa-policy-generic"
                )
            },
            "only mechanical",
        ),
        (
            {
                "classification": classify_change(
                    change_type="pin_bump",
                    blueprint="terraform-module-generic",
                    declared_class="sensitive",
                )
            },
            "only mechanical",
        ),
        (
            {"gates": (GateOutcome("checkov", True), GateOutcome("opa", False))},
            "gate opa is not green",
        ),
        ({"waiver_status": WaiverStatus.ACTIVE}, "open waiver"),
        ({"waiver_status": WaiverStatus.EXPIRING}, "open waiver"),
        ({"waiver_status": WaiverStatus.EXPIRED}, "expired waiver"),
        ({"error_budget_healthy": False}, "error budget"),
    ],
    ids=(
        "v3_off",
        "kill_switch",
        "auto_merge_off",
        "sensitive_change",
        "declared_sensitive_pin",
        "failed_gate",
        "active_waiver",
        "expiring_waiver",
        "expired_waiver",
        "unhealthy_budget",
    ),
)
def test_auto_merge_denies_with_named_fix(
    kwargs: dict[str, object],
    needle: str,
) -> None:
    decision = _decide(**kwargs)  # type: ignore[arg-type]
    assert decision.allowed is False
    assert needle in decision.reason


def test_kill_switch_wins_over_an_otherwise_eligible_change() -> None:
    decision = _decide(kill_switch=True)
    assert decision.allowed is False
    assert "kill_switch" in decision.reason


def test_change_type_from_upgrade_prefers_policy_then_pins() -> None:
    assert change_type_from_upgrade(pin_changes=("x",), policy_changes=("opa",)) == "policy_change"
    assert change_type_from_upgrade(pin_changes=("x",), policy_changes=()) == "pin_bump"
    assert change_type_from_upgrade(pin_changes=(), policy_changes=()) == "standard"


def test_decide_auto_merge_for_plan_names_v3_when_off(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\noutput:\n  github_org: acme\n  modules_root: ../mods\n",
        encoding="utf-8",
    )
    decision = decide_auto_merge_for_plan(
        repo_root=tmp_path,
        blueprint_name="terraform-module-generic",
        pin_changes=("pin",),
        policy_changes=(),
        gates=(GateResult("checkov", True, False, "ok"),),
    )
    assert decision.allowed is False
    assert "v3.enabled" in decision.reason


def test_decide_auto_merge_for_plan_allows_mechanical_when_enabled(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\n"
        "v3:\n"
        "  enabled: true\n"
        "  auto_merge:\n"
        "    enabled: true\n"
        "output:\n"
        "  github_org: acme\n"
        "  modules_root: ../mods\n",
        encoding="utf-8",
    )
    decision = decide_auto_merge_for_plan(
        repo_root=tmp_path,
        blueprint_name="terraform-module-generic",
        pin_changes=("pin",),
        policy_changes=(),
        gates=(GateResult("checkov", True, False, "ok"),),
    )
    assert decision.allowed is True
