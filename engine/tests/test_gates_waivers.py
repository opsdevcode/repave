"""Integration tests for v3 waiver enforcement in run_gates."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from repave_engine.gates import run_gates
from repave_engine.v3_foundation import WaiverPolicy
from repave_engine.waivers import FrozenClock, WaiverRecord


def test_run_gates_waiver_disabled_leaves_failure(tmp_path: Path) -> None:
    policy = WaiverPolicy.disabled()
    results = run_gates(
        tmp_path,
        ("not-a-real-gate",),
        waiver_policy=policy,
    )
    assert len(results) == 1
    assert not results[0].passed


def test_run_gates_active_waiver_converts_failure_to_pass(tmp_path: Path) -> None:
    record = WaiverRecord(
        waiver_id="w-active",
        gate_id="not-a-real-gate",
        expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
    )
    policy = WaiverPolicy(
        enabled=True,
        waivers=(record,),
        clock=FrozenClock(datetime(2026, 6, 1, tzinfo=timezone.utc)),
    )
    results = run_gates(
        tmp_path,
        ("not-a-real-gate",),
        waiver_policy=policy,
    )
    assert results[0].passed
    assert "waived by w-active" in results[0].message


def test_run_gates_expired_waiver_fails_gate(tmp_path: Path) -> None:
    record = WaiverRecord(
        waiver_id="w-expired",
        gate_id="not-a-real-gate",
        expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    policy = WaiverPolicy(
        enabled=True,
        waivers=(record,),
        clock=FrozenClock(datetime(2026, 6, 1, tzinfo=timezone.utc)),
    )
    results = run_gates(
        tmp_path,
        ("not-a-real-gate",),
        waiver_policy=policy,
    )
    assert not results[0].passed
    assert "w-expired expired" in results[0].message


def test_load_waiver_policy_from_repo_config(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "waivers.jsonl").write_text(
        '{"waiver_id":"w1","gate_id":"not-a-real-gate","expires_at":"2027-01-01T00:00:00Z"}\n',
        encoding="utf-8",
    )
    (tmp_path / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\n"
        "v3:\n"
        "  enabled: true\n"
        "output:\n"
        "  github_org: acme\n"
        "  modules_root: ../mods\n",
        encoding="utf-8",
    )
    results = run_gates(tmp_path, ("not-a-real-gate",), repo_root=tmp_path)
    assert results[0].passed
