from __future__ import annotations

from repave_engine.gate_registry import GateResult
from repave_engine.gates import gate_outcome, gate_summary


def _gate(*, passed: bool, skipped: bool = False) -> GateResult:
    return GateResult("test-gate", passed, skipped, "msg")


def test_gate_outcome_empty() -> None:
    assert gate_outcome([]) == "empty"


def test_gate_outcome_passed() -> None:
    assert gate_outcome([_gate(passed=True)]) == "passed"


def test_gate_outcome_failed() -> None:
    assert gate_outcome([_gate(passed=False)]) == "failed"


def test_gate_outcome_timeout() -> None:
    assert (
        gate_outcome([GateResult("slow-gate", False, False, "command timed out after 1s")])
        == "timeout"
    )


def test_gate_summary_counts() -> None:
    summary = gate_summary(
        [_gate(passed=True), _gate(passed=False), _gate(passed=True, skipped=True)]
    )
    assert summary["outcome"] == "failed"
    assert summary["passed"] == 1
    assert summary["failed"] == 1
