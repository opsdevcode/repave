from __future__ import annotations

from repave_engine.blueprint import artifact_family
from repave_engine.ci_toolchain import INFRACOST_VERSION, TERRAFORM_VERSION
from repave_engine.ci_workflow import (
    build_ci_provenance_block,
    ci_workflow_relpath,
    render_ci_workflow,
    snapshot_gate_config,
)


def test_ci_workflow_path_for_terraform(terraform_blueprint) -> None:
    assert artifact_family(terraform_blueprint.artifact_type) == "terraform"
    assert ci_workflow_relpath(terraform_blueprint) == ".github/workflows/terraform-gates.yml"


def test_ci_workflow_path_for_helm(repo_root) -> None:
    from repave_engine.blueprint import load_blueprint

    blueprint = load_blueprint(repo_root / "blueprints" / "helm-chart-generic", repo_root=repo_root)
    assert ci_workflow_relpath(blueprint) == ".github/workflows/repave-gates.yml"


def test_build_ci_provenance_block_includes_gates(terraform_blueprint) -> None:
    block = build_ci_provenance_block(terraform_blueprint)
    assert "terraform-fmt" in block["gates"]
    assert block["toolchain"]["terraform"] == TERRAFORM_VERSION
    assert block["toolchain"]["infracost"] == INFRACOST_VERSION
    assert block["workflow"] == ".github/workflows/terraform-gates.yml"


def test_render_ci_workflow_includes_repave_gates_command(terraform_blueprint) -> None:
    text = render_ci_workflow(terraform_blueprint)
    assert "repave gates --path ." in text
    assert "hashicorp/setup-terraform" in text
    assert "setup-tflint" in text
    assert "Install Infracost" in text
    assert INFRACOST_VERSION in text
    assert "INFRACOST_API_KEY" in text


def test_snapshot_gate_config_merges_raw(terraform_blueprint) -> None:
    snapshot = snapshot_gate_config(terraform_blueprint)
    assert "checkov" in snapshot
    assert snapshot["checkov"]["config_file"] == ".checkov.yml"
