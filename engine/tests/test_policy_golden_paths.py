"""End-to-end dry-run generate for standalone policy golden paths."""

from __future__ import annotations

from pathlib import Path

import yaml

from repave_engine.pipeline import generate_from_blueprint
from repave_engine.settings import OutputConfig


def _generate_policy(
    repo_root: Path,
    tmp_path: Path,
    blueprint_name: str,
    inputs: dict[str, str],
):
    from repave_engine.blueprint import load_blueprint

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

    opa_gate = next(g for g in result.gates if g.name == "opa")
    assert not opa_gate.skipped, opa_gate.message
    assert opa_gate.passed, opa_gate.message


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

    azure_gate = next(g for g in result.gates if g.name == "azure-policy")
    assert not azure_gate.skipped, azure_gate.message
    assert azure_gate.passed, azure_gate.message


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
    checkov_gate = next(g for g in result.gates if g.name == "checkov")
    assert not checkov_gate.skipped, checkov_gate.message
    assert checkov_gate.passed, checkov_gate.message
