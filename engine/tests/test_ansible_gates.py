from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from repave_engine.gates import run_gates


def test_yamllint_skips_when_tool_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("repave_engine.gate_runners.tool_available", lambda name: False)

    results = run_gates(tmp_path, ("yamllint",))

    assert results[0].passed is True
    assert results[0].skipped is True
    assert "not installed" in results[0].message


def test_yamllint_passes_when_tool_succeeds(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda name: name == "yamllint",
    )
    monkeypatch.setattr(
        "repave_engine.gate_runners.run_command",
        lambda cmd, cwd, **kwargs: MagicMock(returncode=0, stdout="", stderr=""),
    )

    results = run_gates(tmp_path, ("yamllint",))

    assert results[0].passed is True
    assert results[0].skipped is False


def test_ansible_lint_skips_when_tool_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("repave_engine.gate_runners.tool_available", lambda name: False)

    results = run_gates(tmp_path, ("ansible-lint",))

    assert results[0].passed is True
    assert results[0].skipped is True


def test_ansible_syntax_check_skips_without_playbook(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda name: name == "ansible-playbook",
    )

    results = run_gates(tmp_path, ("ansible-syntax-check",))

    assert results[0].passed is True
    assert results[0].skipped is True
    assert "no molecule converge playbook" in results[0].message


def test_ansible_syntax_check_runs_against_converge_playbook(
    tmp_path: Path,
    monkeypatch,
) -> None:
    playbook = tmp_path / "molecule" / "default" / "converge.yml"
    playbook.parent.mkdir(parents=True)
    playbook.write_text("---\n- hosts: all\n  tasks: []\n", encoding="utf-8")

    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda name: name == "ansible-playbook",
    )
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, cwd, *, extra_env=None):
        captured["cmd"] = cmd
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("repave_engine.gate_runners.run_command", fake_run)

    results = run_gates(tmp_path, ("ansible-syntax-check",))

    assert results[0].passed is True
    assert captured["cmd"][:2] == ["ansible-playbook", "--syntax-check"]


def test_molecule_skips_without_scenario(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("repave_engine.gate_runners.tool_available", lambda name: True)

    results = run_gates(tmp_path, ("molecule",))

    assert results[0].passed is True
    assert results[0].skipped is True
    assert "no molecule scenario" in results[0].message


def test_molecule_skips_when_tool_missing(tmp_path: Path, monkeypatch) -> None:
    molecule_config = tmp_path / "molecule" / "default" / "molecule.yml"
    molecule_config.parent.mkdir(parents=True)
    molecule_config.write_text("---\n", encoding="utf-8")
    monkeypatch.setattr("repave_engine.gate_runners.tool_available", lambda name: False)

    results = run_gates(tmp_path, ("molecule",))

    assert results[0].passed is True
    assert results[0].skipped is True
    assert "molecule not installed" in results[0].message
