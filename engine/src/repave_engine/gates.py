from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

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
from repave_engine.gate_toolchain import ensure_gate_path
from repave_engine.settings import GateOverrides

__all__ = [
    "GateResult",
    "all_gates_passed",
    "build_checkov_command",
    "build_secrets_scan_command",
    "clean_gate_artifacts",
    "gate_outcome",
    "gate_summary",
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

# require_run (dry-run preview): benign skips stay skipped; others become failures.
_DRY_RUN_SKIP_ALLOWED_FRAGMENTS = (
    "no terraform tests",
    "not applicable",
    "policy pack not enabled",
    "no opa policies selected",
    "opa policy pack not configured",
    "no molecule scenario",
    "no chart.yaml found",
    "no dockerfile found",
    "no pyproject.toml found",
    "no go.mod found",
    "no python tests",
    "no go tests",
    "provenance not configured",
    "no helm chart found",
    "infracost_api_key not set",
    "infracost not installed",
)

# Gates the local Docker / CI toolchain installs; optional observability/app gates may still skip.
_STRICT_DRY_RUN_GATES = frozenset(
    {
        "terraform-fmt",
        "terraform-validate",
        "terraform-test",
        "tflint",
        "checkov",
        "secrets",
        "opa",
        "azure-policy",
        "docs-drift",
        "provenance-drift",
        "yamllint",
        "ansible-lint",
        "ansible-syntax-check",
        "helm-lint",
        "helm-template",
    }
)


def _dry_run_skip_allowed(message: str) -> bool:
    lowered = message.lower()
    return any(fragment in lowered for fragment in _DRY_RUN_SKIP_ALLOWED_FRAGMENTS)


def _apply_require_run_policy(context: GateContext, result: GateResult) -> GateResult:
    if not context.require_run or not result.skipped:
        return result
    if result.name not in _STRICT_DRY_RUN_GATES:
        return result
    if _dry_run_skip_allowed(result.message):
        return result
    detail = result.message.replace("; skipped", "").strip()
    if not detail.endswith("."):
        detail = f"{detail}."
    return GateResult(
        result.name,
        False,
        False,
        (
            f"{detail} Dry-run preview runs all blueprint gates; install the tool "
            "(see deploy/local) or use Docker compose for a full toolchain."
        ),
    )


RunEventCallback = Callable[[str, dict[str, Any]], None]


def run_gates(
    output_dir: Path,
    gate_names: tuple[str, ...],
    *,
    blueprint: Blueprint | None = None,
    gate_overrides: GateOverrides | None = None,
    require_run: bool = False,
    on_event: RunEventCallback | None = None,
) -> list[GateResult]:
    ensure_gate_path()
    ensure_gates_loaded()
    context = GateContext(
        output_dir=output_dir,
        blueprint=blueprint,
        gate_overrides=gate_overrides,
        require_run=require_run,
    )
    results: list[GateResult] = []
    for gate_name in gate_names:
        if on_event is not None:
            on_event("gate_started", {"gate": gate_name})
        spec = get_gate(gate_name)
        if spec is None:
            gate_result = GateResult(gate_name, False, False, f"Unknown gate: {gate_name}")
        else:
            gate_result = _apply_require_run_policy(context, spec.runner(context))
        results.append(gate_result)
        if on_event is not None:
            on_event(
                "gate_finished",
                {
                    "gate": gate_name,
                    "passed": gate_result.passed,
                    "skipped": gate_result.skipped,
                    "message": gate_result.message,
                },
            )
    return results


def all_gates_passed(results: list[GateResult]) -> bool:
    return all(r.passed or r.skipped for r in results)


def _gate_counts(gates: list[GateResult]) -> tuple[int, int, int]:
    passed = sum(1 for gate in gates if gate.passed and not gate.skipped)
    failed = sum(1 for gate in gates if not gate.passed and not gate.skipped)
    skipped = sum(1 for gate in gates if gate.skipped)
    return passed, failed, skipped


def gate_outcome(gates: list[GateResult]) -> str:
    """Aggregate outcome for audit, metrics, and API (`passed` | `failed` | `timeout` | `empty`)."""
    if any(
        not gate.passed and not gate.skipped and "timed out" in gate.message.lower()
        for gate in gates
    ):
        return "timeout"
    _, failed, _ = _gate_counts(gates)
    if failed:
        return "failed"
    if gates and all(gate.passed or gate.skipped for gate in gates):
        return "passed"
    return "empty"


def gate_summary(gates: list[GateResult]) -> dict[str, int | str]:
    """Counts plus outcome for portal result templates."""
    passed, failed, skipped = _gate_counts(gates)
    return {
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "outcome": gate_outcome(gates),
    }


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
        if name == ".repave" and path.is_dir():
            _clean_repave_gate_scratch(path)
            continue
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink()


def _clean_repave_gate_scratch(repave_dir: Path) -> None:
    """Remove OPA plan scratch; keep policy-selection.json for published repos."""
    keep = frozenset({"policy-selection.json"})
    for child in list(repave_dir.iterdir()):
        if child.name in keep:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def is_gate_artifact_path(relative_path: str, *, artifact_type: str = "terraform-module") -> bool:
    ensure_gates_loaded()
    return _is_gate_artifact_path(relative_path, artifact_type=artifact_type)
