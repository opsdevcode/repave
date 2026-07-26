from __future__ import annotations

import json
from pathlib import Path

from repave_engine.gates import run_gates


def test_datadog_monitor_passes_valid_json(tmp_path: Path) -> None:
    monitors_dir = tmp_path / "datadog" / "monitors"
    monitors_dir.mkdir(parents=True)
    payload = [
        {
            "name": "checkout target down",
            "type": "metric alert",
            "query": "avg(last_5m):max:up{service:checkout} < 1",
            "message": "Runbook: https://example.com/runbooks/checkout",
            "tags": [
                "service:checkout",
                "team:payments",
                "org:platform",
                "env:prod",
                "managed-by:repave",
            ],
        }
    ]
    (monitors_dir / "service-alerts.json").write_text(json.dumps(payload), encoding="utf-8")
    results = run_gates(tmp_path, ("datadog-monitor",))
    gate = results[0]
    assert gate.passed
    assert not gate.skipped


def test_datadog_monitor_fails_missing_query(tmp_path: Path) -> None:
    monitors_dir = tmp_path / "datadog" / "monitors"
    monitors_dir.mkdir(parents=True)
    (monitors_dir / "bad.json").write_text(
        '{"name": "x", "type": "metric alert"}', encoding="utf-8"
    )
    results = run_gates(tmp_path, ("datadog-monitor",))
    assert not results[0].passed


def test_datadog_monitor_skips_when_no_files(tmp_path: Path) -> None:
    results = run_gates(tmp_path, ("datadog-monitor",))
    assert results[0].skipped
