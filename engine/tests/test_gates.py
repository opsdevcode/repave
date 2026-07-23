from __future__ import annotations

from pathlib import Path

from repave_engine.gates import (
    GateResult,
    all_gates_passed,
    clean_gate_artifacts,
    is_gate_artifact_path,
    run_gates,
)


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


def test_is_gate_artifact_path() -> None:
    assert is_gate_artifact_path(".terraform/providers/foo/LICENSE.txt") is True
    assert is_gate_artifact_path(".terraform.lock.hcl") is True
    assert is_gate_artifact_path(".tflint.d/plugins/foo") is True
    assert is_gate_artifact_path("main.tf") is False
    assert is_gate_artifact_path("LICENSE") is False


def test_clean_gate_artifacts_removes_terraform_and_lock(tmp_path: Path) -> None:
    terraform_dir = tmp_path / ".terraform" / "providers" / "hashicorp" / "aws"
    terraform_dir.mkdir(parents=True)
    (terraform_dir / "LICENSE.txt").write_text("license", encoding="utf-8")
    (tmp_path / ".terraform.lock.hcl").write_text('provider "aws" {}\n', encoding="utf-8")
    tflint_dir = tmp_path / ".tflint.d" / "plugins"
    tflint_dir.mkdir(parents=True)
    (tflint_dir / "plugin").write_text("bin", encoding="utf-8")
    (tmp_path / "main.tf").write_text("# keep\n", encoding="utf-8")

    clean_gate_artifacts(tmp_path)

    assert not (tmp_path / ".terraform").exists()
    assert not (tmp_path / ".terraform.lock.hcl").exists()
    assert not (tmp_path / ".tflint.d").exists()
    assert (tmp_path / "main.tf").read_text(encoding="utf-8") == "# keep\n"
