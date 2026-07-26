from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from repave_engine.gates import run_gates


def _minimal_chart(root: Path) -> None:
    (root / "Chart.yaml").write_text(
        "apiVersion: v2\nname: demo\nversion: 0.1.0\n",
        encoding="utf-8",
    )
    (root / "values.yaml").write_text("replicaCount: 1\n", encoding="utf-8")


def test_helm_lint_skips_when_tool_missing(tmp_path: Path, monkeypatch) -> None:
    _minimal_chart(tmp_path)
    monkeypatch.setattr("repave_engine.gate_runners.tool_available", lambda name: False)

    results = run_gates(tmp_path, ("helm-lint",))

    assert results[0].passed is True
    assert results[0].skipped is True
    assert "not installed" in results[0].message


def test_helm_lint_skips_without_chart_yaml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda name: name == "helm",
    )

    results = run_gates(tmp_path, ("helm-lint",))

    assert results[0].passed is True
    assert results[0].skipped is True
    assert "Chart.yaml" in results[0].message


def test_helm_lint_passes_when_check_succeeds(tmp_path: Path, monkeypatch) -> None:
    _minimal_chart(tmp_path)
    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda name: name == "helm",
    )
    monkeypatch.setattr(
        "repave_engine.gate_runners.run_command",
        lambda cmd, cwd, **kwargs: MagicMock(returncode=0, stdout="", stderr=""),
    )

    results = run_gates(tmp_path, ("helm-lint",))

    assert results[0].passed is True
    assert results[0].skipped is False


def test_helm_template_skips_when_tool_missing(tmp_path: Path, monkeypatch) -> None:
    _minimal_chart(tmp_path)
    monkeypatch.setattr("repave_engine.gate_runners.tool_available", lambda name: False)

    results = run_gates(tmp_path, ("helm-template",))

    assert results[0].passed is True
    assert results[0].skipped is True
