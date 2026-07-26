"""Reconstruct blueprint gate context from a generated repo's repave.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

from repave_engine.blueprint import (
    AnsibleLintGateConfig,
    AzurePolicyGateConfig,
    AzurePolicyPack,
    Blueprint,
    CheckovGateConfig,
    CheckovPolicyPack,
    OpaGateConfig,
    OpaPolicyPack,
    TerraformTestGateConfig,
    TflintGateConfig,
)


def _checkov_from_spec(spec: dict[str, Any]) -> CheckovPolicyPack | None:
    raw = spec.get("checkov")
    if not isinstance(raw, dict):
        return None
    return CheckovPolicyPack(
        policies_source=str(raw.get("policies_source", "")),
        policy_version=str(raw.get("policy_version", "1.0.0")),
    )


def _opa_from_spec(spec: dict[str, Any]) -> OpaPolicyPack | None:
    raw = spec.get("opa")
    if not isinstance(raw, dict):
        return None
    return OpaPolicyPack(
        policies_source=str(raw.get("policies_source", "")),
        policy_version=str(raw.get("policy_version", "1.0.0")),
    )


def _azure_from_spec(spec: dict[str, Any]) -> AzurePolicyPack | None:
    raw = spec.get("azurePolicyDefinitions") or spec.get("azure_policy")
    if not isinstance(raw, dict):
        return None
    return AzurePolicyPack(
        definitions_source=str(raw.get("definitions_source", "")),
        policy_version=str(raw.get("policy_version", "1.0.0")),
    )


def blueprint_from_repave_file(repave_path: Path) -> Blueprint:
    """Build a minimal Blueprint for running gates in a published golden-path repo."""
    repave_path = repave_path.resolve()
    if not repave_path.is_file():
        raise FileNotFoundError(f"Provenance file missing: {repave_path}")

    document = yaml.safe_load(repave_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("repave.yaml must be a mapping")
    spec = document.get("spec")
    if not isinstance(spec, dict):
        raise ValueError("repave.yaml missing spec")

    ci = spec.get("ci")
    if not isinstance(ci, dict) or not ci.get("gates"):
        raise ValueError("repave.yaml spec.ci.gates is required for repave gates")

    gate_config_raw = ci.get("gate_config", {})
    if not isinstance(gate_config_raw, dict):
        gate_config_raw = {}

    blueprint_meta = spec.get("blueprint", {})
    standard = spec.get("standard", {})
    if not isinstance(blueprint_meta, dict):
        blueprint_meta = {}
    if not isinstance(standard, dict):
        standard = {}

    checkov_raw = gate_config_raw.get("checkov", {}) if isinstance(gate_config_raw, dict) else {}
    if not isinstance(checkov_raw, dict):
        checkov_raw = {}
    opa_raw = gate_config_raw.get("opa", {}) if isinstance(gate_config_raw, dict) else {}
    if not isinstance(opa_raw, dict):
        opa_raw = {}
    tflint_raw = gate_config_raw.get("tflint", {}) if isinstance(gate_config_raw, dict) else {}
    if not isinstance(tflint_raw, dict):
        tflint_raw = {}
    test_raw = (
        gate_config_raw.get("terraform-test", {}) if isinstance(gate_config_raw, dict) else {}
    )
    if not isinstance(test_raw, dict):
        test_raw = {}
    ansible_lint_raw = (
        gate_config_raw.get("ansible-lint", {}) if isinstance(gate_config_raw, dict) else {}
    )
    if not isinstance(ansible_lint_raw, dict):
        ansible_lint_raw = {}
    azure_raw = gate_config_raw.get("azure-policy", {}) if isinstance(gate_config_raw, dict) else {}
    if not isinstance(azure_raw, dict):
        azure_raw = {}

    repo_root = repave_path.parent
    return Blueprint(
        path=repo_root,
        name=str(blueprint_meta.get("name", "unknown")),
        version=str(blueprint_meta.get("version", "0.0.0")),
        description="",
        artifact_type=str(spec.get("artifactType", "terraform-module")),
        standard_source=str(standard.get("source", "")),
        standard_version=str(standard.get("version", "")),
        inputs=(),
        template_engine="copier",
        template_path=".",
        gates=tuple(str(g) for g in ci["gates"]),
        output_type="local",
        output_repo_name_template="",
        output_title_template="",
        provenance_file=repave_path.name,
        checkov_policies=_checkov_from_spec(spec),
        opa_policies=_opa_from_spec(spec),
        azure_policy_pack=_azure_from_spec(spec),
        checkov_gate=CheckovGateConfig(
            external_checks_dir=str(checkov_raw.get("external_checks_dir", "policy/checkov")),
            config_file=str(checkov_raw.get("config_file", ".checkov.yml")),
            scan_dir=str(checkov_raw.get("scan_dir", "")),
            skip_checks=tuple(checkov_raw.get("skip_checks", [])),
            soft_fail=bool(checkov_raw.get("soft_fail", False)),
        ),
        opa_gate=OpaGateConfig(
            policies_dir=str(opa_raw.get("policies_dir", "policy/opa/policies")),
            fixtures_dir=str(opa_raw.get("fixtures_dir", "tests/fixtures")),
            plan_subdir=str(opa_raw.get("plan_subdir", ".repave")),
        ),
        azure_policy_gate=AzurePolicyGateConfig(
            definitions_dir=str(azure_raw.get("definitions_dir", "policy/definitions")),
        ),
        ansible_lint_gate=AnsibleLintGateConfig(
            config_file=str(ansible_lint_raw.get("config_file", ".ansible-lint")),
        ),
        tflint_gate=TflintGateConfig(config_file=str(tflint_raw.get("config_file", ".tflint.hcl"))),
        terraform_test_gate=TerraformTestGateConfig(
            test_directory=str(test_raw.get("test_directory", "tests")),
        ),
        gate_config_raw=cast(dict[str, Any], gate_config_raw),
    )
