from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from repave_engine.blueprint import CheckovGateConfig
from repave_engine.gates import (
    GateResult,
    _gate_terraform_fmt,
    all_gates_passed,
    build_checkov_command,
    build_secrets_scan_command,
    clean_gate_artifacts,
    is_gate_artifact_path,
    run_gates,
)
from repave_engine.settings import GateOverrides


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


def test_build_checkov_command_uses_config_and_external_checks(tmp_path: Path) -> None:
    (tmp_path / ".checkov.yml").write_text("framework:\n  - terraform\n", encoding="utf-8")
    policies = tmp_path / "policy/checkov"
    policies.mkdir(parents=True)
    (policies / "custom.yaml").write_text("metadata:\n  id: CKV2_TEST\n", encoding="utf-8")

    cmd = build_checkov_command(
        tmp_path,
        CheckovGateConfig(skip_checks=("CKV_AWS_1",)),
        extra_skip_checks=("CKV_AWS_2",),
    )

    assert cmd[:3] == ["checkov", "-d", str(tmp_path)]
    assert "--config-file" in cmd
    assert str(tmp_path / ".checkov.yml") in cmd
    assert "--external-checks-dir" in cmd
    assert str(policies) in cmd
    assert cmd.count("--skip-check") == 2
    assert "CKV_AWS_1" in cmd
    assert "CKV_AWS_2" in cmd


def test_build_checkov_command_adds_soft_fail(tmp_path: Path) -> None:
    cmd = build_checkov_command(
        tmp_path,
        CheckovGateConfig(soft_fail=True),
    )

    assert "--soft-fail" in cmd


def test_run_gates_checkov_applies_gate_overrides(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("repave_engine.gates._tool_available", lambda name: name == "checkov")
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, cwd, *, extra_env=None):
        captured["cmd"] = cmd
        captured["extra_env"] = extra_env
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("repave_engine.gates._run", fake_run)

    run_gates(
        tmp_path,
        ("checkov",),
        gate_overrides=GateOverrides(checkov_skip_checks=("CKV_X",)),
    )

    assert "CKV_X" in captured["cmd"]
    assert captured["extra_env"]["REPAVE_CHECKOV_SCAN_ROOT"] == str(tmp_path.resolve())


def test_build_secrets_scan_command(tmp_path: Path) -> None:
    cmd = build_secrets_scan_command(tmp_path)
    assert cmd[:3] == ["checkov", "-d", str(tmp_path)]
    assert "--framework" in cmd
    assert "secrets" in cmd
    assert "--enable-secret-scan-all-files" in cmd


def test_run_gates_secrets_invokes_checkov(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("repave_engine.gates._tool_available", lambda name: name == "checkov")
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, cwd, *, extra_env=None):
        captured["cmd"] = cmd
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("repave_engine.gates._run", fake_run)

    run_gates(tmp_path, ("secrets",))

    assert "--framework" in captured["cmd"]
    assert "secrets" in captured["cmd"]


def test_terraform_fmt_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("repave_engine.gates._terraform_usable", lambda _dir: True)

    def fake_run(cmd, cwd):
        return MagicMock(returncode=1, stdout="", stderr="fmt failed")

    monkeypatch.setattr("repave_engine.gates._run", fake_run)

    result = _gate_terraform_fmt(tmp_path)

    assert result.passed is False
    assert "fmt failed" in result.message
