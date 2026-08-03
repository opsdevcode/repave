from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.api_read_models import (
    FleetRegistryUnavailableError,
    build_estate_read_model,
    build_governance_annotations_read_model,
)
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


def test_build_estate_read_model_requires_fleet(repo_root: Path) -> None:
    with pytest.raises(FleetRegistryUnavailableError):
        build_estate_read_model(repo_root)


def test_build_estate_read_model_returns_tiles(
    repo_root: Path,
    registry: Path,
) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    body = build_estate_read_model(repo_root)
    assert body["count"] == 1
    assert body["tiles"][0]["repo_url"] == PROVENANCE_ENTRY.repo_url
    assert body["tiles"][0]["freshness"] in {"fresh", "aging", "drift", "error", "unknown"}


def test_build_governance_annotations_read_model(repo_root: Path) -> None:
    body = build_governance_annotations_read_model(repo_root, "terraform-module-generic")
    assert body["blueprint"] == "terraform-module-generic"
    assert body["standard"] == "standards/terraform-standards"
    assert body["pinned_version"]
    assert isinstance(body["previews"], list)


def test_api_v2_estate_matches_v1(repo_root, output_config, registry: Path) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    v1 = client.get("/api/v1/estate")
    v2 = client.get("/api/v2/estate")
    assert v1.status_code == 200
    assert v2.status_code == 200
    assert v1.json() == v2.json()


def test_api_v2_governance_annotations_matches_v1(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    v1 = client.get("/api/v1/governance/annotations/terraform-module-generic")
    v2 = client.get("/api/v2/governance/annotations/terraform-module-generic")
    assert v1.status_code == 200
    assert v2.status_code == 200
    assert v1.json() == v2.json()
    assert v1.json()["previews"]
