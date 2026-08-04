"""Tests for composite bundle loading and generation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from repave_engine.bundle import (
    build_bundle_context,
    list_bundles,
    load_bundle,
    map_member_inputs,
    validate_bundle_inputs,
)
from repave_engine.pipeline import generate_from_bundle
from repave_engine.settings import OutputConfig


@pytest.fixture
def bundle_fixture_inputs() -> dict[str, str]:
    return {
        "service_name": "bundle-test",
        "description": "Bundle unit test service",
        "owner": "group:platform",
        "organization": "platform",
        "team": "payments",
        "port": "8080",
        "runtime": "python",
        "catalog_lifecycle": "experimental",
        "cloud_provider": "aws",
        "provider_services": "ec2,s3",
    }


@pytest.fixture
def microservice_full_inputs() -> dict[str, str]:
    return {
        "service_name": "checkout",
        "description": "Checkout microservice bundle",
        "owner": "group:platform",
        "organization": "platform",
        "team": "payments",
        "port": "8080",
        "runtime": "python",
        "catalog_lifecycle": "experimental",
        "runbook_url": "https://wiki.example.com/runbooks/checkout",
        "slo_target_percent": "99.9",
        "environment": "dev",
        "gitops_engine": "argocd",
        "sync_policy": "manual",
        "target_namespace": "default",
    }


def test_list_bundles_includes_service_stack_and_microservice_full(repo_root: Path) -> None:
    bundles = list_bundles(repo_root)
    names = [item.name for item in bundles]
    assert "service-stack" in names
    assert "microservice-full" in names


def test_load_service_stack_bundle(repo_root: Path) -> None:
    bundle = load_bundle(
        repo_root / "blueprints" / "bundles" / "service-stack", repo_root=repo_root
    )
    assert bundle.name == "service-stack"
    assert len(bundle.members) == 4
    member_ids = {member.member_id for member in bundle.members}
    assert member_ids == {"app", "helm", "dashboards", "terraform"}


def test_load_microservice_full_bundle(repo_root: Path) -> None:
    bundle = load_bundle(
        repo_root / "blueprints" / "bundles" / "microservice-full", repo_root=repo_root
    )
    assert bundle.name == "microservice-full"
    assert len(bundle.members) == 6
    member_ids = {member.member_id for member in bundle.members}
    assert member_ids == {"app", "helm", "gitops", "dashboards", "monitors", "slo"}


def test_bundle_context_wires_cross_references(
    repo_root: Path,
    bundle_fixture_inputs: dict[str, str],
) -> None:
    bundle = load_bundle(
        repo_root / "blueprints" / "bundles" / "service-stack", repo_root=repo_root
    )
    shared = validate_bundle_inputs(bundle, bundle_fixture_inputs)
    context = build_bundle_context(shared, github_org="acme")
    assert context["helm_chart_repo"] == "https://github.com/acme/helm-bundle-test"
    assert context["image_repository"] == "ghcr.io/acme/app-bundle-test"

    app_member = next(member for member in bundle.members if member.member_id == "app")
    app_values = map_member_inputs(app_member, context)
    assert app_values["include_helm_reference"] == "true"
    assert app_values["helm_chart_repo"] == context["helm_chart_repo"]

    helm_member = next(member for member in bundle.members if member.member_id == "helm")
    helm_values = map_member_inputs(helm_member, context)
    assert helm_values["chart_name"] == "bundle-test"
    assert helm_values["image_repository"] == context["image_repository"]

    tf_member = next(member for member in bundle.members if member.member_id == "terraform")
    tf_values = map_member_inputs(tf_member, context)
    assert tf_values["module_name"] == "bundle-test"
    assert tf_values["cloud_provider"] == "aws"
    assert tf_values["provider_services"] == "ec2,s3"
    assert tf_values["include_backstage_catalog"] == "true"


def test_microservice_full_gitops_uses_helm_chart_repo(
    repo_root: Path,
    microservice_full_inputs: dict[str, str],
) -> None:
    bundle = load_bundle(
        repo_root / "blueprints" / "bundles" / "microservice-full", repo_root=repo_root
    )
    shared = validate_bundle_inputs(bundle, microservice_full_inputs)
    context = build_bundle_context(shared, github_org="acme")
    gitops_member = next(member for member in bundle.members if member.member_id == "gitops")
    gitops_values = map_member_inputs(gitops_member, context)
    assert gitops_values["chart_repo_url"] == "https://github.com/acme/helm-checkout"
    assert gitops_values["chart_name"] == "checkout"
    assert gitops_values["environment"] == "dev"


def _assert_bundle_conformance(
    bundle_dir: Path,
    result_members: tuple,
    *,
    repo_root: Path,
) -> None:
    spec_path = bundle_dir / "conformance.yaml"
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    required_members = set(raw["required_members"])
    assert {item.member_id for item in result_members} == required_members
    member_files = raw.get("member_required_files", {})
    by_id = {item.member_id: item for item in result_members}
    for member_id, paths in member_files.items():
        output_dir = by_id[member_id].result.render.output_dir
        for rel in paths:
            assert (output_dir / rel).is_file(), f"{member_id}: missing {rel}"


def test_generate_service_stack_bundle_dry_run(
    repo_root: Path,
    output_config: OutputConfig,
    bundle_fixture_inputs: dict[str, str],
    staging_root: Path,
) -> None:
    bundle = load_bundle(
        repo_root / "blueprints" / "bundles" / "service-stack", repo_root=repo_root
    )
    result = generate_from_bundle(
        bundle,
        bundle_fixture_inputs,
        repo_root=repo_root,
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
    )
    assert len(result.members) == 4
    for member in result.members:
        assert member.result.rendered_files, f"{member.member_id} should expose dry-run files"
    app = next(item for item in result.members if item.member_id == "app")
    readme_paths = {file.path for file in app.result.rendered_files}
    assert any(path.endswith("README.md") for path in readme_paths)
    terraform = next(item for item in result.members if item.member_id == "terraform")
    assert (terraform.result.render.output_dir / "versions.tf").is_file()
    _assert_bundle_conformance(
        repo_root / "blueprints" / "bundles" / "service-stack",
        result.members,
        repo_root=repo_root,
    )


def test_generate_microservice_full_bundle_dry_run(
    repo_root: Path,
    output_config: OutputConfig,
    microservice_full_inputs: dict[str, str],
    staging_root: Path,
) -> None:
    bundle = load_bundle(
        repo_root / "blueprints" / "bundles" / "microservice-full", repo_root=repo_root
    )
    result = generate_from_bundle(
        bundle,
        microservice_full_inputs,
        repo_root=repo_root,
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
    )
    assert len(result.members) == 6
    gitops = next(item for item in result.members if item.member_id == "gitops")
    assert (gitops.result.render.output_dir / "apps" / "release.yaml").is_file()
    slo = next(item for item in result.members if item.member_id == "slo")
    assert (slo.result.render.output_dir / "prometheus" / "rules" / "slo-burn.yaml").is_file()
    _assert_bundle_conformance(
        repo_root / "blueprints" / "bundles" / "microservice-full",
        result.members,
        repo_root=repo_root,
    )
