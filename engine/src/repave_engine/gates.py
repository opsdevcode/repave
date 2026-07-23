from __future__ import annotations

import shutil
from pathlib import Path

from repave_engine.blueprint import Blueprint
from repave_engine.gate_registry import (
    GateContext,
    GateResult,
    ensure_gates_loaded,
    get_gate,
)
from repave_engine.gate_registry import (
    is_gate_artifact_path as _is_gate_artifact_path,
)
from repave_engine.gate_runners import (
    build_checkov_command,
    build_secrets_scan_command,
    run_checkov,
    run_docs_drift,
    run_provenance_drift,
    run_secrets,
    run_terraform_fmt,
    run_terraform_test,
    run_terraform_validate,
    run_tflint,
)
from repave_engine.settings import GateOverrides

__all__ = [
    "GateResult",
    "all_gates_passed",
    "build_checkov_command",
    "build_secrets_scan_command",
    "clean_gate_artifacts",
    "is_gate_artifact_path",
    "run_checkov",
    "run_docs_drift",
    "run_gates",
    "run_provenance_drift",
    "run_secrets",
    "run_terraform_fmt",
    "run_terraform_test",
    "run_terraform_validate",
    "run_tflint",
]

# Backward-compatible aliases for tests importing private runners.
_gate_terraform_fmt = run_terraform_fmt
_gate_checkov = run_checkov
_gate_secrets = run_secrets


def run_gates(
    output_dir: Path,
    gate_names: tuple[str, ...],
    *,
    blueprint: Blueprint | None = None,
    gate_overrides: GateOverrides | None = None,
) -> list[GateResult]:
    ensure_gates_loaded()
    context = GateContext(
        output_dir=output_dir,
        blueprint=blueprint,
        gate_overrides=gate_overrides,
    )
    results: list[GateResult] = []
    for gate_name in gate_names:
        spec = get_gate(gate_name)
        if spec is None:
            results.append(GateResult(gate_name, False, False, f"Unknown gate: {gate_name}"))
            continue
        results.append(spec.runner(context))
    return results


def all_gates_passed(results: list[GateResult]) -> bool:
    return all(r.passed or r.skipped for r in results)


def clean_gate_artifacts(output_dir: Path, *, artifact_type: str = "terraform-module") -> None:
    from repave_engine.gate_registry import artifact_paths_for_type

    ensure_gates_loaded()
    for name in artifact_paths_for_type(artifact_type):
        if name.startswith("*."):
            for path in output_dir.glob(name):
                if path.is_file():
                    path.unlink()
            continue
        path = output_dir / name
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink()


def is_gate_artifact_path(relative_path: str, *, artifact_type: str = "terraform-module") -> bool:
    ensure_gates_loaded()
    return _is_gate_artifact_path(relative_path, artifact_type=artifact_type)
