"""Effective infracost gate list for platform floor (FinOps v1.91)."""

from __future__ import annotations

from collections.abc import Sequence

from repave_engine.blueprint import Blueprint
from repave_engine.settings import GateOverrides, InfracostGatePolicy

_TERRAFORM_GATE_HINTS = frozenset(
    {
        "terraform-fmt",
        "terraform-validate",
        "terraform-test",
        "tflint",
        "infracost",
    }
)


def blueprint_has_terraform_gates(gate_names: Sequence[str]) -> bool:
    return any(name in _TERRAFORM_GATE_HINTS for name in gate_names)


def effective_gate_names(
    blueprint: Blueprint,
    gate_overrides: GateOverrides | None,
) -> tuple[str, ...]:
    """Return blueprint gates, injecting infracost when the org floor requires it."""
    names = list(blueprint.gates)
    policy = gate_overrides.infracost if gate_overrides is not None else InfracostGatePolicy()
    if not policy.required:
        return tuple(names)
    if "infracost" in names:
        return tuple(names)
    if not blueprint_has_terraform_gates(names) and blueprint.artifact_type not in (
        "terraform-module",
        "terraform-environment-stack",
    ):
        return tuple(names)
    # Keep infracost near other cost/plan gates when present; otherwise append.
    if "tflint" in names:
        idx = names.index("tflint") + 1
        names.insert(idx, "infracost")
    else:
        names.append("infracost")
    return tuple(names)
