from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.blueprint import load_blueprint, validate_inputs
from repave_engine.policy_selection import (
    PolicySelection,
    load_policy_selection_file,
    write_policy_selection_file,
)
from repave_engine.settings import GateOverrides


def test_normalize_strict_profile_writes_selection(repo_root: Path, tmp_path: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-module-generic",
        repo_root,
    )
    values = validate_inputs(
        blueprint,
        {
            "module_name": "net",
            "description": "Networking",
            "cloud_provider": "aws",
            "provider_services": "ec2",
            "policy_profile": "strict",
        },
        repo_root=repo_root,
    )
    selection = values.get("_policy_selection")
    assert isinstance(selection, PolicySelection)
    assert "checkov:CKV2_REPAVE_2" in selection.enabled_rules


def test_platform_cannot_skip_required_checkov(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-module-generic",
        repo_root,
    )
    overrides = GateOverrides(checkov_skip_checks=("CKV2_REPAVE_1",))
    with pytest.raises(ValueError, match="required rule"):
        validate_inputs(
            blueprint,
            {
                "module_name": "net",
                "description": "Networking",
                "cloud_provider": "aws",
                "provider_services": "ec2",
            },
            repo_root=repo_root,
            gate_overrides=overrides,
        )


def test_policy_selection_file_roundtrip(tmp_path: Path) -> None:
    selection = PolicySelection(
        profile="estate-default",
        pack_source="repave-default",
        enabled_rules=("checkov:CKV2_REPAVE_1",),
        checkov_skip_checks=("CKV2_REPAVE_2",),
        opa_rego_files=("destructive_changes.rego",),
        azure_definition_files=(),
        pack_versions={"checkov": "1.2.0"},
    )
    write_policy_selection_file(tmp_path, selection)
    loaded = load_policy_selection_file(tmp_path)
    assert loaded is not None
    assert loaded.profile == "estate-default"
    assert loaded.checkov_skip_checks == ("CKV2_REPAVE_2",)
