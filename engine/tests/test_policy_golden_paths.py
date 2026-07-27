"""End-to-end dry-run generate for standalone policy golden paths."""

from __future__ import annotations

from pathlib import Path

import yaml

from repave_engine.blueprint import load_blueprint
from repave_engine.gate_registry import GateContext
from repave_engine.gate_runners import run_azure_policy, run_opa
from repave_engine.pipeline import generate_from_blueprint
from repave_engine.settings import OutputConfig


def _generate_policy(
    repo_root: Path,
    tmp_path: Path,
    blueprint_name: str,
    inputs: dict[str, str],
):
    blueprint = load_blueprint(repo_root / "blueprints" / blueprint_name, repo_root)
    staging = tmp_path / "staging"
    output_config = OutputConfig(
        github_org="example",
        modules_root=tmp_path / "modules",
    )
    return generate_from_blueprint(
        blueprint,
        inputs,
        output_config=output_config,
        dry_run=True,
        repo_root=repo_root,
        staging_root=staging,
    )


def test_opa_policy_golden_path_dry_run(repo_root: Path, tmp_path: Path) -> None:
    result = _generate_policy(
        repo_root,
        tmp_path,
        "opa-policy-generic",
        {
            "policy_name": "estate",
            "organization": "platform",
            "description": "Estate OPA pack",
            "plan_demo": "pass",
        },
    )
    out = result.render.output_dir
    assert result.dry_run is True
    assert (out / "repave.yaml").is_file()
    policies_dir = out / "policy"
    assert policies_dir.is_dir()
    assert any(policies_dir.glob("*.rego"))
    fixtures = out / "tests" / "fixtures"
    assert fixtures.is_dir()
    assert any(fixtures.glob("*.json"))

    provenance = yaml.safe_load((out / "repave.yaml").read_text(encoding="utf-8"))
    assert provenance["spec"]["artifactType"] == "opa-policy"
    assert provenance["spec"]["governance"]["baseline_source"]

    gate = run_opa(GateContext(output_dir=out, blueprint=result.blueprint))
    if gate.skipped and "conftest" in gate.message.lower():
        return
    assert gate.passed, gate.message


def test_azure_policy_golden_path_dry_run(repo_root: Path, tmp_path: Path) -> None:
    result = _generate_policy(
        repo_root,
        tmp_path,
        "azure-policy-generic",
        {
            "policy_name": "estate",
            "organization": "platform",
            "description": "Estate Azure Policy definitions",
        },
    )
    out = result.render.output_dir
    assert result.dry_run is True
    definitions = out / "policy" / "definitions"
    assert definitions.is_dir()
    assert any(definitions.glob("*.json"))

    provenance = yaml.safe_load((out / "repave.yaml").read_text(encoding="utf-8"))
    assert provenance["spec"]["artifactType"] == "azure-policy"

    gate = run_azure_policy(GateContext(output_dir=out, blueprint=result.blueprint))
    assert gate.passed, gate.message


def test_checkov_policy_golden_path_dry_run(repo_root: Path, tmp_path: Path) -> None:
    result = _generate_policy(
        repo_root,
        tmp_path,
        "checkov-policy-generic",
        {
            "policy_name": "estate",
            "organization": "platform",
            "description": "Estate Checkov pack",
        },
    )
    out = result.render.output_dir
    policies_dir = out / "policy" / "checkov"
    assert policies_dir.is_dir()
    assert any(policies_dir.glob("*.py")) or any(policies_dir.glob("*.yaml"))
    provenance = yaml.safe_load((out / "repave.yaml").read_text(encoding="utf-8"))
    assert provenance["spec"]["artifactType"] == "checkov-policy"
