from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.fleet import FleetEntry, register_repo

PROVENANCE_ENTRY = FleetEntry(
    repo_url="https://github.com/acme/tf-vpc",
    blueprint_name="terraform-module-generic",
    blueprint_version="0.9.0",
    standard_source="standards/terraform-standards",
    standard_version="1.1.0",
    owner="platform",
    registered_by="tester@example.com",
)


@pytest.fixture
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "registry.jsonl"
    monkeypatch.setenv("REPAVE_FLEET_FILE", str(path))
    return path


def test_estate_map_page_lists_tiles(repo_root, output_config, registry: Path) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    response = client.get("/estate")

    assert response.status_code == 200
    assert "Estate map" in response.text
    assert "tf-vpc" in response.text
    assert "estate-tile" in response.text


def test_blueprint_preflight_panel(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    body = client.get("/blueprints/terraform-module-generic").text

    assert "preflight-panel" in body
    assert "Example repo" in body


def test_bundle_topology_section(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    body = client.get("/bundles/service-stack").text

    assert "bundle-topology" in body


def test_presenter_mode_hides_nav(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    body = client.get("/?presenter=1").text

    assert "shell--presenter" in body


def test_api_estate_json(repo_root, output_config, registry: Path) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    response = client.get("/api/v1/estate")

    assert response.status_code == 200
    assert response.json()["count"] == 1
