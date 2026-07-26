"""Golden-path governance: baseline gates and standards for every artifact type."""

from __future__ import annotations

from repave_engine.blueprint import Blueprint

GOVERNANCE_BASELINE_SOURCE = "standards/policy/governance-baseline.md"
GOVERNANCE_BASELINE_VERSION = "1.0.0"

_BASELINE_GATES: tuple[str, ...] = ("secrets", "docs-drift", "provenance-drift")

_ARTIFACT_REQUIRED_GATES: dict[str, tuple[str, ...]] = {
    "terraform-module": (
        "terraform-fmt",
        "terraform-validate",
        "terraform-test",
        "tflint",
        "checkov",
        *_BASELINE_GATES,
    ),
    "terraform-environment-stack": (
        "terraform-fmt",
        "terraform-validate",
        "terraform-test",
        "tflint",
        "checkov",
        *_BASELINE_GATES,
    ),
    "ansible-role": (
        "yamllint",
        "ansible-lint",
        "ansible-syntax-check",
        "molecule",
        *_BASELINE_GATES,
    ),
    "ansible-collection": (
        "yamllint",
        "ansible-lint",
        *_BASELINE_GATES,
    ),
    "ansible-playbook-project": (
        "yamllint",
        "ansible-lint",
        "ansible-syntax-check",
        *_BASELINE_GATES,
    ),
    "opa-policy": (
        "opa",
        *_BASELINE_GATES,
    ),
    "azure-policy": (
        "azure-policy",
        *_BASELINE_GATES,
    ),
    "checkov-policy": (
        "checkov",
        *_BASELINE_GATES,
    ),
    "helm-chart": (
        "yamllint",
        "helm-lint",
        "helm-template",
        *_BASELINE_GATES,
    ),
}


def governance_provenance_block() -> dict[str, str]:
    return {
        "baseline_source": GOVERNANCE_BASELINE_SOURCE,
        "baseline_version": GOVERNANCE_BASELINE_VERSION,
    }


def missing_governance_gates(blueprint: Blueprint) -> list[str]:
    """Return gate names required by the baseline but missing from the blueprint."""
    required = _ARTIFACT_REQUIRED_GATES.get(blueprint.artifact_type, _BASELINE_GATES)
    gate_set = set(blueprint.gates)
    return [name for name in required if name not in gate_set]
