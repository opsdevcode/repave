"""Tests for composite bundle loading and generation."""

from __future__ import annotations

from pathlib import Path

import pytest

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
    }


def test_list_bundles_includes_service_stack(repo_root: Path) -> None:
    bundles = list_bundles(repo_root)
    names = [item.name for item in bundles]
    assert "service-stack" in names


def test_load_service_stack_bundle(repo_root: Path) -> None:
    bundle = load_bundle(repo_root / "blueprints" / "bundles" / "service-stack", repo_root)
    assert bundle.name == "service-stack"
    assert len(bundle.members) == 3
    member_ids = {member.member_id for member in bundle.members}
    assert member_ids == {"app", "helm", "dashboards"}


def test_bundle_context_wires_cross_references(
    repo_root: Path,
    bundle_fixture_inputs: dict[str, str],
) -> None:
    bundle = load_bundle(repo_root / "blueprints" / "bundles" / "service-stack", repo_root)
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


def test_generate_service_stack_bundle_dry_run(
    repo_root: Path,
    output_config: OutputConfig,
    bundle_fixture_inputs: dict[str, str],
) -> None:
    bundle = load_bundle(repo_root / "blueprints" / "bundles" / "service-stack", repo_root)
    result = generate_from_bundle(
        bundle,
        bundle_fixture_inputs,
        repo_root=repo_root,
        output_config=output_config,
        dry_run=True,
    )
    assert len(result.members) == 3
    for member in result.members:
        assert member.result.rendered_files, f"{member.member_id} should expose dry-run files"
    app = next(item for item in result.members if item.member_id == "app")
    readme_paths = {file.path for file in app.result.rendered_files}
    assert any(path.endswith("README.md") for path in readme_paths)
