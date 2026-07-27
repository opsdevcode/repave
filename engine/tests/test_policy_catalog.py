from __future__ import annotations

from pathlib import Path

from repave_engine.blueprint import load_blueprint
from repave_engine.policy_catalog import (
    load_policy_catalog,
    pack_sources_for_artifact,
    resolve_profile_rule_ids,
)
from repave_engine.policy_selection import policy_input_defaults


def test_pack_sources_filtered_for_azure_policy(repo_root: Path) -> None:
    catalog = load_policy_catalog(repo_root)
    packs = pack_sources_for_artifact(catalog, "azure-policy")
    ids = {pack["id"] for pack in packs}
    assert "repave-azure-samples" in ids
    assert "repave-terraform-strict" not in ids


def test_policy_input_defaults_from_blueprint(repo_root: Path) -> None:
    blueprint = load_blueprint(repo_root / "blueprints" / "checkov-policy-generic", repo_root)
    defaults = policy_input_defaults(blueprint)
    assert defaults["policy_pack_source"] == "repave-checkov-pack"
    assert defaults["policy_profile"] == "checkov-full"


def test_observability_policy_input_defaults(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "observability-as-code-generic",
        repo_root,
    )
    defaults = policy_input_defaults(blueprint)
    assert defaults["policy_pack_source"] == "repave-observability-pack"
    assert defaults["policy_profile"] == "observability-default"


def test_observability_pack_source_filtered(repo_root: Path) -> None:
    catalog = load_policy_catalog(repo_root)
    packs = pack_sources_for_artifact(catalog, "observability")
    ids = {pack["id"] for pack in packs}
    assert "repave-observability-pack" in ids
    assert "repave-checkov-pack" not in ids


def test_observability_default_profile_rules(repo_root: Path) -> None:
    catalog = load_policy_catalog(repo_root)
    enabled = resolve_profile_rule_ids(
        catalog,
        profile="observability-default",
        artifact_type="observability",
    )
    assert "opa:destructive_changes" in enabled
    assert "opa:observability_native" in enabled
    assert "checkov:CKV2_REPAVE_1" not in enabled


def test_resolve_estate_default_includes_required(repo_root: Path) -> None:
    catalog = load_policy_catalog(repo_root)
    enabled = resolve_profile_rule_ids(
        catalog,
        profile="estate-default",
        artifact_type="terraform-module",
    )
    assert "checkov:CKV2_REPAVE_1" in enabled
    assert "checkov:CKV2_REPAVE_3" in enabled
    assert "opa:destructive_changes" in enabled
    assert "checkov:CKV2_REPAVE_2" not in enabled


def test_layout_profile_enables_layout_rules(repo_root: Path) -> None:
    catalog = load_policy_catalog(repo_root)
    enabled = resolve_profile_rule_ids(
        catalog,
        profile="layout",
        artifact_type="terraform-module",
    )
    assert "checkov:CKV2_REPAVE_7" in enabled
    assert "checkov:CKV2_REPAVE_8" not in enabled


def test_strict_enables_all_terraform_rules(repo_root: Path) -> None:
    catalog = load_policy_catalog(repo_root)
    enabled = resolve_profile_rule_ids(
        catalog,
        profile="strict",
        artifact_type="terraform-module",
    )
    assert "checkov:CKV2_REPAVE_2" in enabled


def test_azure_community_profile_includes_all_catalog_azure_rules(repo_root: Path) -> None:
    catalog = load_policy_catalog(repo_root)
    enabled = resolve_profile_rule_ids(
        catalog,
        profile="azure-community",
        artifact_type="azure-policy",
    )
    assert "azure:sample_audit_storage" in enabled
    assert "azure:sample_require_https_storage" in enabled
    assert "azure:sample_deny_public_blob_access" in enabled
    assert "azure:sample_audit_environment_tag" in enabled


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
