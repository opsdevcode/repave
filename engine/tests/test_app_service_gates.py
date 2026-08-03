from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from repave_engine.gates import run_gates


def test_dockerfile_lint_skips_when_hadolint_missing(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    monkeypatch.setattr("repave_engine.gate_runners.tool_available", lambda name: False)

    results = run_gates(tmp_path, ("dockerfile-lint",))

    assert results[0].passed is True
    assert results[0].skipped is True


def test_python_lint_skips_when_ruff_missing(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    monkeypatch.setattr("repave_engine.gate_runners.tool_available", lambda name: False)

    results = run_gates(tmp_path, ("python-lint",))

    assert results[0].passed is True
    assert results[0].skipped is True


def test_python_test_skips_when_pytest_missing(tmp_path: Path, monkeypatch) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_ok.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
    monkeypatch.setattr("repave_engine.gate_runners.tool_available", lambda name: False)

    results = run_gates(tmp_path, ("python-test",))

    assert results[0].passed is True
    assert results[0].skipped is True


def test_dockerfile_lint_passes_when_hadolint_succeeds(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda name: name == "hadolint",
    )
    monkeypatch.setattr(
        "repave_engine.gate_runners.run_command",
        lambda cmd, cwd, **kwargs: MagicMock(returncode=0, stdout="", stderr=""),
    )

    results = run_gates(tmp_path, ("dockerfile-lint",))

    assert results[0].passed is True
    assert results[0].skipped is False


def test_go_lint_skips_without_go_mod(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("repave_engine.gate_runners.tool_available", lambda name: name == "go")

    results = run_gates(tmp_path, ("go-lint",))

    assert results[0].passed is True
    assert results[0].skipped is True


def test_go_test_skips_without_go_mod(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("repave_engine.gate_runners.tool_available", lambda name: name == "go")

    results = run_gates(tmp_path, ("go-test",))

    assert results[0].passed is True
    assert results[0].skipped is True


def test_node_lint_skips_without_package_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda name: name in {"node", "npm"},
    )

    results = run_gates(tmp_path, ("node-lint",))

    assert results[0].passed is True
    assert results[0].skipped is True


def test_node_test_skips_without_package_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda name: name in {"node", "npm"},
    )

    results = run_gates(tmp_path, ("node-test",))

    assert results[0].passed is True
    assert results[0].skipped is True
