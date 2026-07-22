from __future__ import annotations

from pathlib import Path

from repave_engine.gates import GateResult, all_gates_passed, run_gates


def test_docs_drift_passes_with_rendered_readme(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# example\n\n## Usage\n\nUse this module.\n", encoding="utf-8")

    results = run_gates(tmp_path, ("docs-drift",))

    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].skipped is False


def test_docs_drift_fails_when_readme_missing(tmp_path: Path) -> None:
    results = run_gates(tmp_path, ("docs-drift",))

    assert results[0].passed is False
    assert "README.md missing" in results[0].message


def test_docs_drift_fails_on_unresolved_placeholders(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# {{ module_name }}\n\n## Usage\n\nExample.\n", encoding="utf-8")

    results = run_gates(tmp_path, ("docs-drift",))

    assert results[0].passed is False
    assert "unresolved template placeholders" in results[0].message


def test_docs_drift_fails_without_usage_section(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# example\n\nNo usage here.\n", encoding="utf-8")

    results = run_gates(tmp_path, ("docs-drift",))

    assert results[0].passed is False
    assert "missing Usage section" in results[0].message


def test_unknown_gate_fails(tmp_path: Path) -> None:
    results = run_gates(tmp_path, ("not-a-real-gate",))

    assert results[0].passed is False
    assert "Unknown gate" in results[0].message


def test_all_gates_passed_treats_skipped_as_ok() -> None:
    results = [
        GateResult("terraform-fmt", True, True, "skipped"),
        GateResult("docs-drift", True, False, "ok"),
    ]
    assert all_gates_passed(results) is True


def test_all_gates_passed_fails_on_failed_gate() -> None:
    results = [
        GateResult("docs-drift", False, False, "failed"),
    ]
    assert all_gates_passed(results) is False
