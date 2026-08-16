from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from portal_moved import assert_surface_moved
from repave_engine.api import create_app
from repave_engine.portal_surface_moved import (
    CATALOG_MOVED,
    RESULT_MOVED,
    moved_page_context,
    platform_moved,
)
from repave_engine.run_store import RunStatus


def test_moved_page_context_exposes_surface_id() -> None:
    ctx = moved_page_context(CATALOG_MOVED)
    assert ctx["moved_surface_id"] == "catalog"
    assert ctx["moved_backstage_path"] == "/generate"
    assert ctx["nav_active"] == "catalog"


def test_platform_moved_ids() -> None:
    assert platform_moved("finops").surface_id == "platform-finops"
    assert platform_moved("ops").backstage_path == "/ops"


@pytest.mark.parametrize(
    ("path", "surface_id"),
    [
        ("/", "catalog"),
        ("/library", "library"),
        ("/activity", "activity"),
        ("/estate", "estate"),
        ("/import", "import"),
        ("/import/batch", "import-batch"),
        ("/verify", "verify"),
        ("/update", "upgrade"),
        ("/bundles/service-stack", "bundle"),
        ("/platform/fleet", "platform-fleet"),
        ("/platform/ops", "platform-ops"),
        ("/platform/standards", "platform-standards"),
        ("/platform/campaigns", "platform-campaigns"),
        ("/platform/finops", "platform-finops"),
        ("/platform/adoption", "platform-adoption"),
        ("/platform/compliance", "platform-compliance"),
        ("/platform/value-stream", "platform-value-stream"),
        ("/platform/roadmap", "platform-roadmap"),
        ("/platform/feedback", "platform-feedback"),
        ("/platform/maturity", "platform-maturity"),
        ("/platform/initiatives", "platform-initiatives"),
    ],
)
def test_browse_pages_point_to_backstage(
    repo_root, output_config, path: str, surface_id: str
) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    assert_surface_moved(client.get(path), surface_id)


def test_import_and_verify_posts_point_to_backstage(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    assert_surface_moved(client.post("/import", data={}), "import")
    assert_surface_moved(client.post("/import/apply", data={}), "import")
    assert_surface_moved(client.post("/import/batch", data={}), "import-batch")
    assert_surface_moved(client.post("/verify", data={}), "verify")
    assert_surface_moved(client.post("/update", data={}), "upgrade")


def test_generate_post_points_to_backstage_result(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "helm-chart-generic",
            "dry_run": "true",
            "image_repository": "ghcr.io/example/checkout-api",
            "owner": "platform-engineering",
            "environment": "dev",
            "service_type": "ClusterIP",
            "service_port": "8080",
            "enable_ingress": "false",
        },
    )
    assert_surface_moved(response, RESULT_MOVED.surface_id)
    assert "data-form-mode" not in response.text
    assert "Generated files" not in response.text


def test_bundle_generate_post_points_to_backstage(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "bundle_name": "service-stack",
            "dry_run": "true",
            "service_name": "portal-bundle",
            "description": "Portal bundle dry-run test",
            "owner": "group:platform",
            "organization": "platform",
            "team": "payments",
            "port": "8080",
            "runtime": "python",
            "catalog_lifecycle": "experimental",
            "cloud_provider": "aws",
            "provider_services": "ec2,s3",
        },
    )
    assert_surface_moved(response, "bundle-result")
    assert "Generated files" not in response.text


def test_bundle_run_result_points_to_backstage(
    repo_root, output_config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REPAVE_ASYNC_GENERATION", "true")
    monkeypatch.setenv("REPAVE_RUNS_DB", str(tmp_path / "runs.sqlite"))
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    queue = client.app.state.run_queue
    assert queue is not None
    record = queue._store.create_run(
        blueprint_name="service-stack",
        dry_run=True,
        payload={"bundle": "service-stack", "inputs": {}, "dry_run": True},
        acting_user="tester",
    )
    queue._store.update_status(record.run_id, RunStatus.SUCCEEDED)
    assert_surface_moved(client.get(f"/runs/{record.run_id}/result"), "bundle-result")
