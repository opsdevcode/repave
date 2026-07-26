from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from repave_engine.gates import run_gates


def test_promtool_skips_when_tool_missing(tmp_path: Path, monkeypatch) -> None:
    rules_dir = tmp_path / "prometheus" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "alerts.yaml").write_text("groups: []\n", encoding="utf-8")

    monkeypatch.setattr("repave_engine.gate_runners.tool_available", lambda name: False)

    results = run_gates(tmp_path, ("promtool",))

    assert results[0].passed is True
    assert results[0].skipped is True
    assert "not installed" in results[0].message


def test_promtool_passes_when_check_succeeds(tmp_path: Path, monkeypatch) -> None:
    rules_dir = tmp_path / "prometheus" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "alerts.yaml").write_text("groups: []\n", encoding="utf-8")

    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda name: name == "promtool",
    )
    monkeypatch.setattr(
        "repave_engine.gate_runners.run_command",
        lambda cmd, cwd, **kwargs: MagicMock(returncode=0, stdout="", stderr=""),
    )

    results = run_gates(tmp_path, ("promtool",))

    assert results[0].passed is True
    assert results[0].skipped is False


def test_promtool_skips_when_no_rule_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda name: name == "promtool",
    )

    results = run_gates(tmp_path, ("promtool",))

    assert results[0].passed is True
    assert results[0].skipped is True
    assert "no Prometheus rule files" in results[0].message
