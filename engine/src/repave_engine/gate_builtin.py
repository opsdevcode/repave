from __future__ import annotations

from repave_engine.gate_registry import GateSpec, register_gate
from repave_engine.gate_runners import (
    run_checkov,
    run_docs_drift,
    run_secrets,
    run_terraform_fmt,
    run_terraform_test,
    run_terraform_validate,
    run_tflint,
)

register_gate(
    GateSpec(
        name="terraform-fmt",
        runner=run_terraform_fmt,
        artifact_types=frozenset({"terraform-module"}),
    )
)
register_gate(
    GateSpec(
        name="terraform-validate",
        runner=run_terraform_validate,
        artifact_types=frozenset({"terraform-module"}),
        artifact_paths=(".terraform", ".terraform.lock.hcl"),
    )
)
register_gate(
    GateSpec(
        name="terraform-test",
        runner=run_terraform_test,
        artifact_types=frozenset({"terraform-module"}),
        artifact_paths=(".terraform", ".terraform.lock.hcl"),
    )
)
register_gate(
    GateSpec(
        name="tflint",
        runner=run_tflint,
        artifact_types=frozenset({"terraform-module"}),
        artifact_paths=(".tflint.d",),
    )
)
register_gate(
    GateSpec(
        name="checkov",
        runner=run_checkov,
        artifact_types=frozenset({"terraform-module"}),
    )
)
register_gate(
    GateSpec(
        name="secrets",
        runner=run_secrets,
        artifact_types=frozenset({"terraform-module"}),
    )
)
register_gate(
    GateSpec(
        name="docs-drift",
        runner=run_docs_drift,
        artifact_types=frozenset({"terraform-module", "ansible-role"}),
    )
)
