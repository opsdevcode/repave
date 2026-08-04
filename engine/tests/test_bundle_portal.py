"""Tests for bundle portal helpers."""

from __future__ import annotations

from pathlib import Path

from repave_engine.bundle import load_bundle, validate_bundle_inputs
from repave_engine.bundle_portal import (
    build_bundle_provenance_document,
    bundle_member_previews,
)
from repave_engine.pipeline import generate_from_bundle
from repave_engine.settings import OutputConfig


def test_bundle_member_previews_repo_names(
    repo_root: Path,
    output_config: OutputConfig,
) -> None:
    bundle = load_bundle(
        repo_root / "blueprints" / "bundles" / "service-stack", repo_root=repo_root
    )
    shared = {
        "service_name": "payments-api",
        "description": "Payments API",
        "owner": "group:platform",
        "organization": "platform",
        "team": "payments",
        "port": "8080",
        "runtime": "python",
        "catalog_lifecycle": "experimental",
    }
    previews = bundle_member_previews(
        bundle, shared, repo_root=repo_root, output_config=output_config
    )
    by_id = {item.member_id: item for item in previews}
    assert by_id["app"].repo_name == "app-payments-api"
    assert by_id["helm"].repo_name == "helm-payments-api"
    assert by_id["dashboards"].repo_name == "dashboards-platform-payments-api"
    assert by_id["terraform"].repo_name == "tf-aws-payments-api"


def test_bundle_provenance_document(
    repo_root: Path,
    output_config: OutputConfig,
) -> None:
    bundle = load_bundle(
        repo_root / "blueprints" / "bundles" / "service-stack", repo_root=repo_root
    )
    inputs = {
        "service_name": "audit-svc",
        "description": "Audit test",
        "owner": "group:platform",
        "organization": "platform",
        "team": "payments",
        "port": "8080",
        "runtime": "python",
        "catalog_lifecycle": "experimental",
        "cloud_provider": "aws",
        "provider_services": "ec2,s3",
    }
    result = generate_from_bundle(
        bundle,
        inputs,
        repo_root=repo_root,
        output_config=output_config,
        dry_run=True,
    )
    doc = build_bundle_provenance_document(
        bundle, validate_bundle_inputs(bundle, inputs), result.members
    )
    assert doc["kind"] == "BundleGeneration"
    assert doc["spec"]["bundle"] == "service-stack"
    assert len(doc["spec"]["members"]) == 4
    assert result.shared_inputs["service_name"] == "audit-svc"
