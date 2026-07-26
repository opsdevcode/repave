"""Tests for portal result view context."""

from __future__ import annotations

from pathlib import Path

from helpers import make_blueprint
from repave_engine.pipeline import GenerationResult
from repave_engine.policy_selection import PolicySelection
from repave_engine.portal_result import build_result_portal_context
from repave_engine.render import RenderResult


def test_build_result_portal_context_includes_policy_rules(repo_root: Path, tmp_path: Path) -> None:
    blueprint = make_blueprint(
        tmp_path,
        artifact_type="terraform-module",
        gates=("checkov", "opa"),
    )
    selection = PolicySelection(
        profile="estate-default",
        pack_source="repave-default",
        enabled_rules=("checkov:CKV2_REPAVE_1", "opa:destructive_changes"),
        checkov_skip_checks=(),
        opa_rego_files=("destructive_changes.rego",),
        azure_definition_files=(),
        pack_versions={"checkov": "1.0.0", "opa": "1.0.0"},
    )
    values = {"_policy_selection": selection, "module_name": "demo"}
    result = GenerationResult(
        blueprint=blueprint,
        render=RenderResult(output_dir=repo_root / "out", values=values),
        gates=[],
        module_repository=None,
        pr_plan=None,
        pr_message="",
        dry_run=True,
    )
    ctx = build_result_portal_context(result, repo_root)
    assert ctx["policy_profile"] == "estate-default"
    assert len(ctx["policy_rules"]) >= 1
    assert any(row.rule_id == "opa:destructive_changes" for row in ctx["policy_rules"])
    assert ctx["repave_yaml_excerpt"] is not None
