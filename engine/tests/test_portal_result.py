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


def test_build_result_portal_context_includes_cost_estimate(tmp_path: Path) -> None:
    from repave_engine.cost_estimate import CostEstimate, write_cost_estimate_file

    blueprint = make_blueprint(tmp_path, artifact_type="terraform-module")
    write_cost_estimate_file(
        tmp_path,
        CostEstimate(
            currency="USD",
            monthly_cost="42.00",
            hourly_cost="0.06",
            resource_count=2,
            detail="Estimated USD 42.00/month across 2 resource(s)",
        ),
    )
    result = GenerationResult(
        blueprint=blueprint,
        render=RenderResult(output_dir=tmp_path, values={}),
        gates=[],
        module_repository=None,
        pr_plan=None,
        pr_message="",
        dry_run=True,
    )
    ctx = build_result_portal_context(result, tmp_path)
    assert ctx["cost_estimate"] is not None
    assert ctx["cost_estimate"].monthly_cost == "42.00"


def test_backstage_preview_extracts_slug_tags_and_relations() -> None:
    from repave_engine.portal_result import _backstage_preview

    content = """
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: checkout
  tags: [payments, api]
  links:
    - url: https://runbooks.example/checkout
      title: Runbook
  annotations:
    github.com/project-slug: acme/app-checkout
    backstage.io/kubernetes-id: checkout
    repave.dev/catalog-domain: commerce
spec:
  owner: group:payments
  consumesApis: [api:default/payments]
  subcomponentOf: component:default/commerce
"""
    preview = _backstage_preview(content, "catalog-info.yaml")
    assert preview is not None
    assert preview.github_slug == "acme/app-checkout"
    assert preview.github_source_url == "https://github.com/acme/app-checkout"
    assert preview.kubernetes_id == "checkout"
    assert preview.catalog_domain == "commerce"
    assert preview.tags == ("payments", "api")
    assert preview.links == (("Runbook", "https://runbooks.example/checkout"),)
    assert preview.consumes_apis == ("api:default/payments",)
    assert preview.subcomponent_of == "component:default/commerce"
