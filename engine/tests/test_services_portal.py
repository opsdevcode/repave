from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.entity_catalog import entity_id_for_repo_url
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


def test_services_page_lists_fleet_entity(repo_root, output_config, registry: Path) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    entity_dir = output_config.modules_root / "tf-vpc"
    entity_dir.mkdir(parents=True)
    (entity_dir / "repave.yaml").write_text("spec:\n  blueprint: x\n", encoding="utf-8")
    (entity_dir / "README.md").write_text("# VPC module\n\nHello.", encoding="utf-8")
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    response = client.get("/library")
    body = response.text

    assert response.status_code == 200
    assert "Library" in body
    assert "catalog-inventory__category" in body
    assert "catalog-inventory__summary" in body


def test_service_detail_renders_scorecard_and_readme(
    repo_root, output_config, registry: Path
) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    entity_dir = output_config.modules_root / "tf-vpc"
    entity_dir.mkdir(parents=True)
    (entity_dir / "repave.yaml").write_text("spec:\n  blueprint: x\n", encoding="utf-8")
    (entity_dir / "README.md").write_text("# VPC module\n\nHello catalog.", encoding="utf-8")
    entity_id = entity_id_for_repo_url(PROVENANCE_ENTRY.repo_url)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    response = client.get(f"/services/{entity_id}")

    assert response.status_code == 200
    body = response.text
    assert "Scorecard" in body
    assert "VPC module" in body or "Hello catalog" in body


def test_api_catalog_entities_json(repo_root, output_config, registry: Path) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    response = client.get("/api/v1/catalog/entities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 1
    assert payload["entities"][0]["entity_id"]


def test_services_redirects_to_library(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    response = client.get("/services", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/library"


def test_catalog_entities_redirect(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    response = client.get("/catalog/entities", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/library"


def test_nav_exposes_library_link(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    assert 'href="/library"' in client.get("/").text


def test_observability_url_on_detail(
    output_config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registry: Path
) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    (tmp_path / "repave.config.yaml").write_text(
        f"fleet:\n  enabled: true\n  file: {registry}\n"
        "portal:\n  observability_dashboard_url: "
        "'https://grafana.example/d/s?var-service={name}'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    entity_dir = output_config.modules_root / "tf-vpc"
    entity_dir.mkdir(parents=True)
    (entity_dir / "repave.yaml").write_text("spec:\n  blueprint: x\n", encoding="utf-8")
    entity_id = entity_id_for_repo_url(PROVENANCE_ENTRY.repo_url)
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))

    body = client.get(f"/services/{entity_id}").text

    assert "grafana.example" in body
    assert "Observability" in body
