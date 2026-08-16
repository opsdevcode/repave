from __future__ import annotations

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
