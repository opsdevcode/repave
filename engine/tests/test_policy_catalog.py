from __future__ import annotations

from pathlib import Path

from repave_engine.policy_catalog import load_policy_catalog, resolve_profile_rule_ids


def test_resolve_estate_default_includes_required(repo_root: Path) -> None:
    catalog = load_policy_catalog(repo_root)
    enabled = resolve_profile_rule_ids(
        catalog,
        profile="estate-default",
        artifact_type="terraform-module",
    )
    assert "checkov:CKV2_REPAVE_1" in enabled
    assert "opa:destructive_changes" in enabled
    assert "checkov:CKV2_REPAVE_2" not in enabled


def test_strict_enables_all_terraform_rules(repo_root: Path) -> None:
    catalog = load_policy_catalog(repo_root)
    enabled = resolve_profile_rule_ids(
        catalog,
        profile="strict",
        artifact_type="terraform-module",
    )
    assert "checkov:CKV2_REPAVE_2" in enabled


def test_custom_adds_required_rules_when_no_optional_selected(repo_root: Path) -> None:
    catalog = load_policy_catalog(repo_root)
    enabled = resolve_profile_rule_ids(
        catalog,
        profile="custom",
        artifact_type="terraform-module",
        custom_rules=(),
    )
    assert "checkov:CKV2_REPAVE_1" in enabled
    assert "opa:destructive_changes" in enabled
