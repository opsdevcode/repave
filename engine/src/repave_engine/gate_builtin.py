from __future__ import annotations

from repave_engine.gate_registry import GateSpec, register_gate
from repave_engine.gate_runners import (
    run_ansible_lint,
    run_ansible_syntax_check,
    run_checkov,
    run_docs_drift,
    run_molecule,
    run_provenance_drift,
    run_secrets,
    run_terraform_fmt,
    run_terraform_test,
    run_terraform_validate,
    run_tflint,
    run_yamllint,
)

_TERRAFORM_ARTIFACT_TYPES = frozenset({"terraform-module", "terraform-environment-stack"})
_ANSIBLE_ARTIFACT_TYPES = frozenset(
    {"ansible-role", "ansible-playbook-project", "ansible-collection"}
)
_SHARED_ARTIFACT_TYPES = frozenset(
    {
        "terraform-module",
        "terraform-environment-stack",
        "ansible-role",
        "ansible-playbook-project",
        "ansible-collection",
    }
)

register_gate(
    GateSpec(
        name="terraform-fmt",
        runner=run_terraform_fmt,
        artifact_types=_TERRAFORM_ARTIFACT_TYPES,
    )
)
register_gate(
    GateSpec(
        name="terraform-validate",
        runner=run_terraform_validate,
        artifact_types=_TERRAFORM_ARTIFACT_TYPES,
        artifact_paths=(".terraform", ".terraform.lock.hcl"),
    )
)
register_gate(
    GateSpec(
        name="terraform-test",
        runner=run_terraform_test,
        artifact_types=_TERRAFORM_ARTIFACT_TYPES,
        artifact_paths=(".terraform", ".terraform.lock.hcl"),
    )
)
register_gate(
    GateSpec(
        name="tflint",
        runner=run_tflint,
        artifact_types=_TERRAFORM_ARTIFACT_TYPES,
        artifact_paths=(".tflint.d",),
    )
)
register_gate(
    GateSpec(
        name="checkov",
        runner=run_checkov,
        artifact_types=_TERRAFORM_ARTIFACT_TYPES,
    )
)
register_gate(
    GateSpec(
        name="secrets",
        runner=run_secrets,
        artifact_types=_SHARED_ARTIFACT_TYPES,
    )
)
register_gate(
    GateSpec(
        name="docs-drift",
        runner=run_docs_drift,
        artifact_types=_SHARED_ARTIFACT_TYPES,
    )
)
register_gate(
    GateSpec(
        name="provenance-drift",
        runner=run_provenance_drift,
        artifact_types=_SHARED_ARTIFACT_TYPES,
    )
)
register_gate(
    GateSpec(
        name="yamllint",
        runner=run_yamllint,
        artifact_types=_ANSIBLE_ARTIFACT_TYPES,
    )
)
register_gate(
    GateSpec(
        name="ansible-lint",
        runner=run_ansible_lint,
        artifact_types=_ANSIBLE_ARTIFACT_TYPES,
    )
)
register_gate(
    GateSpec(
        name="ansible-syntax-check",
        runner=run_ansible_syntax_check,
        artifact_types=_ANSIBLE_ARTIFACT_TYPES,
    )
)
register_gate(
    GateSpec(
        name="molecule",
        runner=run_molecule,
        artifact_types=_ANSIBLE_ARTIFACT_TYPES,
        artifact_paths=(".molecule",),
    )
)
