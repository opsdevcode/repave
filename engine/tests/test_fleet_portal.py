from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from portal_moved import assert_surface_moved
from repave_engine.api import create_app
from repave_engine.fleet import FleetEntry, register_repo
from repave_engine.fleet_operator_status import (
    FleetOperatorStatus,
    write_operator_status_snapshot,
)

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


def test_library_page_shows_operator_phase(
    output_config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = tmp_path / "registry.jsonl"
    register_repo(registry, PROVENANCE_ENTRY)
    status_file = tmp_path / "operator-status.json"
    write_operator_status_snapshot(
        status_file,
        [
            FleetOperatorStatus(
                repo_url=PROVENANCE_ENTRY.repo_url,
                phase="OutOfDate",
                message="pins differ",
            )
        ],
    )
    (tmp_path / "repave.config.yaml").write_text(
        f"fleet:\n  enabled: true\n  file: {registry}\n  operator_status_file: {status_file}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))

    assert_surface_moved(client.get("/library"), "library")
    assert_surface_moved(client.get("/library/terraform"), "library")


def test_library_page_lists_registered_repos(repo_root, output_config, registry: Path) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    response = client.get("/library")

    assert_surface_moved(response, "library")

    family = client.get("/library/terraform")
    assert_surface_moved(family, "library")


def test_library_page_pluralizes_count(repo_root, output_config, registry: Path) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    register_repo(
        registry,
        FleetEntry(
            repo_url="https://github.com/acme/tf-subnet",
            blueprint_name="terraform-module-generic",
            blueprint_version="0.9.0",
        ),
    )
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    assert_surface_moved(client.get("/library"), "library")


def test_library_unknown_family_is_not_found(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    response = client.get("/library/not-a-family")

    assert response.status_code == 404


def test_library_page_empty_state_points_at_register(
    repo_root, output_config, registry: Path
) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    response = client.get("/library")

    assert_surface_moved(response, "library")


def test_fleet_redirects_to_library(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    response = client.get("/fleet", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/library"


def test_nav_exposes_library_link(repo_root, output_config, registry: Path) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    assert_surface_moved(client.get("/"), "catalog")


def test_library_page_marks_nav_current(repo_root, output_config, registry: Path) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    assert_surface_moved(client.get("/library"), "library")
