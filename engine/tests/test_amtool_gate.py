from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from repave_engine.gates import run_gates


def test_amtool_skips_when_tool_missing(tmp_path: Path, monkeypatch) -> None:
    am_dir = tmp_path / "prometheus" / "alertmanager"
    am_dir.mkdir(parents=True)
    (am_dir / "alertmanager.yaml").write_text("route:\n  receiver: default\n", encoding="utf-8")

    monkeypatch.setattr("repave_engine.gate_runners.tool_available", lambda name: False)

    results = run_gates(tmp_path, ("amtool",))

    assert results[0].passed is True
    assert results[0].skipped is True
    assert "not installed" in results[0].message


def test_amtool_passes_when_check_succeeds(tmp_path: Path, monkeypatch) -> None:
    am_dir = tmp_path / "prometheus" / "alertmanager"
    am_dir.mkdir(parents=True)
    (am_dir / "alertmanager.yaml").write_text("route:\n  receiver: default\n", encoding="utf-8")

    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda name: name == "amtool",
    )
    monkeypatch.setattr(
        "repave_engine.gate_runners.run_command",
        lambda cmd, cwd, **kwargs: MagicMock(returncode=0, stdout="", stderr=""),
    )

    results = run_gates(tmp_path, ("amtool",))

    assert results[0].passed is True
    assert results[0].skipped is False


def test_amtool_skips_when_no_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda name: name == "amtool",
    )

    results = run_gates(tmp_path, ("amtool",))

    assert results[0].passed is True
    assert results[0].skipped is True
    assert "no Alertmanager config" in results[0].message
