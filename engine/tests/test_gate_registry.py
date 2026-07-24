from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.gate_registry import (
    GateContext,
    GateRegistryError,
    GateResult,
    GateSpec,
    artifact_paths_for_type,
    get_gate,
    is_gate_artifact_path,
    register_gate,
    registered_gate_names,
    unregister_gate,
)
from repave_engine.gates import run_gates


def test_builtin_gates_are_registered() -> None:
    names = registered_gate_names()
    assert "terraform-fmt" in names
    assert "checkov" in names
    assert "secrets" in names
    assert "terraform-test" in names
    assert "yamllint" in names
    assert "ansible-lint" in names
    assert "ansible-syntax-check" in names
    assert "molecule" in names


def test_get_gate_returns_spec_for_known_gate() -> None:
    spec = get_gate("docs-drift")
    assert spec is not None
    assert spec.name == "docs-drift"


def test_register_gate_rejects_duplicate_name() -> None:
    def runner(ctx: GateContext) -> GateResult:
        return GateResult("dup-gate", True, False, "ok")

    register_gate(GateSpec(name="dup-gate", runner=runner))
    with pytest.raises(GateRegistryError, match="already registered"):
        register_gate(GateSpec(name="dup-gate", runner=runner))


def test_custom_gate_runs_without_core_dispatcher_changes(tmp_path: Path) -> None:
    def runner(ctx: GateContext) -> GateResult:
        marker = ctx.output_dir / "marker.txt"
        marker.write_text("ok", encoding="utf-8")
        return GateResult("custom-marker", True, False, "marked")

    register_gate(GateSpec(name="custom-marker", runner=runner))
    results = run_gates(tmp_path, ("custom-marker",))

    assert results[0].passed is True
    assert (tmp_path / "marker.txt").read_text(encoding="utf-8") == "ok"
    unregister_gate("custom-marker")


def test_artifact_paths_include_terraform_defaults() -> None:
    paths = artifact_paths_for_type("terraform-module")
    assert ".terraform" in paths
    assert ".terraform.lock.hcl" in paths
    assert ".tflint.d" in paths


def test_artifact_paths_include_ansible_type_paths() -> None:
    paths = artifact_paths_for_type("ansible-role")
    assert ".ansible" in paths
    assert ".molecule" in paths
    assert "*.retry" in paths


def test_is_gate_artifact_path_matches_retry_files() -> None:
    assert is_gate_artifact_path("playbook.retry", artifact_type="ansible-role") is True
    assert is_gate_artifact_path("playbook.retry", artifact_type="terraform-module") is False
