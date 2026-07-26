from __future__ import annotations

import json
from pathlib import Path

from helpers import make_blueprint
from repave_engine.blueprint import AzurePolicyGateConfig, AzurePolicyPack
from repave_engine.gate_registry import GateContext
from repave_engine.gate_runners import run_azure_policy


def _azure_policy_blueprint(tmp_path: Path):
    bp = make_blueprint(
        tmp_path,
        gates=("azure-policy", "secrets", "docs-drift", "provenance-drift"),
        artifact_type="azure-policy",
    )
    from dataclasses import replace

    return replace(
        bp,
        azure_policy_pack=AzurePolicyPack(
            definitions_source="policy/azure/definitions",
            policy_version="1.0.0",
        ),
        azure_policy_gate=AzurePolicyGateConfig(definitions_dir="policy/definitions"),
    )


def test_azure_policy_skips_for_non_artifact(tmp_path: Path) -> None:
    bp = make_blueprint(tmp_path, artifact_type="terraform-module")
    result = run_azure_policy(GateContext(output_dir=tmp_path, blueprint=bp))
    assert result.skipped
    assert result.passed


def test_azure_policy_fails_on_invalid_definition(tmp_path: Path) -> None:
    bp = _azure_policy_blueprint(tmp_path)
    definitions = tmp_path / "policy" / "definitions"
    definitions.mkdir(parents=True)
    (definitions / "bad.json").write_text('{"properties": {}}', encoding="utf-8")
    result = run_azure_policy(GateContext(output_dir=tmp_path, blueprint=bp))
    assert not result.passed
    assert "missing required fields" in result.message


def test_azure_policy_passes_valid_definition(tmp_path: Path) -> None:
    bp = _azure_policy_blueprint(tmp_path)
    definitions = tmp_path / "policy" / "definitions"
    definitions.mkdir(parents=True)
    sample = {
        "properties": {
            "displayName": "Test",
            "policyType": "Custom",
            "mode": "All",
            "description": "Test policy",
            "policyRule": {
                "if": {"field": "type", "equals": "Microsoft.Resources/subscriptions"},
                "then": {"effect": "audit"},
            },
        }
    }
    (definitions / "ok.json").write_text(json.dumps(sample), encoding="utf-8")
    result = run_azure_policy(GateContext(output_dir=tmp_path, blueprint=bp))
    assert result.passed
    assert not result.skipped


def test_azure_policy_passes_monorepo_sample_definitions(repo_root: Path, tmp_path: Path) -> None:
    import shutil

    bp = _azure_policy_blueprint(tmp_path)
    source = repo_root / "policy" / "azure" / "definitions"
    dest = tmp_path / "policy" / "definitions"
    dest.mkdir(parents=True)
    for path in source.glob("*.json"):
        shutil.copy2(path, dest / path.name)
    result = run_azure_policy(GateContext(output_dir=tmp_path, blueprint=bp))
    assert result.passed, result.message
