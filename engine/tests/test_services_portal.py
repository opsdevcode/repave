from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from portal_moved import assert_surface_moved
from repave_engine.api import create_app
from repave_engine.audit import AuditRecord, append_audit_record
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
    assert "library-drawers" in body
    assert 'href="/library/terraform"' in body
    assert "home-catalog-column" in body
    assert "catalog-inventory--browse" not in body
    assert "catalog-inventory__summary" not in body
    assert "data-library-drawer" in body
    assert "/static/repave-library.mjs" in body

    family = client.get("/library/terraform")
    assert family.status_code == 200
    assert "library-shelf" in family.text
    assert "/static/repave-library.mjs" in family.text
    assert (
        "tf-vpc" in family.text or "VPC" in family.text or "terraform-module-generic" in family.text
    )


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

    assert_surface_moved(response, "services")


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


def test_library_lists_successful_apply_from_audit_without_fleet(
    repo_root,
    output_config,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit_path = tmp_path / "audit.jsonl"
    fleet_path = tmp_path / "fleet.jsonl"
    monkeypatch.setenv("REPAVE_AUDIT_FILE", str(audit_path))
    monkeypatch.setenv("REPAVE_FLEET_FILE", str(fleet_path))
    append_audit_record(
        audit_path,
        AuditRecord(
            event="generation",
            blueprint_name="terraform-module-generic",
            blueprint_version="0.12.0",
            module_name="tf-aws-eks",
            dry_run=False,
            gates_outcome="passed",
            repository_url="https://github.com/opsdevcode/tf-aws-eks",
            acting_user="alice",
            extra={"publish_succeeded": True, "run_id": "run-yesterday"},
        ),
        repo_root=repo_root,
    )
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/library")
    assert response.status_code == 200
    assert "library-drawers" in response.text
    assert 'href="/library/terraform"' in response.text
    family = client.get("/library/terraform")
    assert family.status_code == 200
    assert "tf-aws-eks" in family.text
    entity_id = entity_id_for_repo_url("https://github.com/opsdevcode/tf-aws-eks")
    assert f"/services/{entity_id}" in family.text


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
        "'https://grafana.example/d/s?var-service={name}'\n"
        "  observability_slo_url: "
        "'https://slo.example/v1/{name}'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {
                "status": "healthy",
                "slo_target": "99.9%",
                "slo_current": "99.95%",
                "detail": "All good",
            }

    monkeypatch.setattr(
        "repave_engine.observability_slo.httpx.get",
        lambda *_args, **_kwargs: FakeResponse(),
    )
    entity_dir = output_config.modules_root / "tf-vpc"
    entity_dir.mkdir(parents=True)
    (entity_dir / "repave.yaml").write_text("spec:\n  blueprint: x\n", encoding="utf-8")
    (entity_dir / "UPGRADE.md").write_text("# Upgrade notes\n", encoding="utf-8")
    entity_id = entity_id_for_repo_url(PROVENANCE_ENTRY.repo_url)
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))

    response = client.get(f"/services/{entity_id}")

    assert_surface_moved(response, "services")


def test_api_v2_entity_detail_includes_deployment_status(
    output_config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registry: Path
) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    (tmp_path / "repave.config.yaml").write_text(
        f"fleet:\n  enabled: true\n  file: {registry}\n"
        "portal:\n  deployment_reader: url\n"
        "  deployment_status_url: 'https://status.example/{name}'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {
                "sync_status": "synced",
                "health": "healthy",
                "revision": "abc123",
                "last_synced": "2026-08-01T12:00:00Z",
            }

    monkeypatch.setattr(
        "repave_engine.deployment_status.httpx.get",
        lambda *_args, **_kwargs: FakeResponse(),
    )
    entity_id = entity_id_for_repo_url(PROVENANCE_ENTRY.repo_url)
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))

    detail = client.get(f"/api/v2/catalog/entities/{entity_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["deployment_status"]["sync_status"] == "synced"
    assert payload["deployment_status"]["health"] == "healthy"
    scorecard = {dim["key"]: dim for dim in payload["scorecard"]}
    assert scorecard["deployment"]["level"] == "pass"

    list_body = client.get("/api/v2/catalog/entities").json()
    list_scorecard = {dim["key"]: dim for dim in list_body["entities"][0]["scorecard"]}
    assert list_scorecard["deployment"]["level"] == "pass"
    assert "deployment_status" not in list_body["entities"][0]


def test_library_shows_deployment_scorecard_in_rollup(
    output_config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registry: Path
) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    (tmp_path / "repave.config.yaml").write_text(
        f"fleet:\n  enabled: true\n  file: {registry}\n"
        "portal:\n  deployment_reader: url\n"
        "  deployment_status_url: 'https://status.example/{name}'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"sync_status": "synced", "health": "healthy"}

    monkeypatch.setattr(
        "repave_engine.deployment_status.httpx.get",
        lambda *_args, **_kwargs: FakeResponse(),
    )
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))

    body = client.get("/library").text

    assert "library-drawers" in body
    assert 'href="/library/terraform"' in body
    assert "Fleet scorecard" not in body


def test_library_fleet_scorecard_rollup(repo_root, output_config, registry: Path) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    entity_dir = output_config.modules_root / "tf-vpc"
    entity_dir.mkdir(parents=True)
    (entity_dir / "repave.yaml").write_text("spec:\n  blueprint: x\n", encoding="utf-8")
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    body = client.get("/library").text

    assert "library-drawers" in body
    assert "fleet-scorecard-rollup" not in body


def test_library_owner_filter(repo_root, output_config, registry: Path) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    body = client.get("/library", params={"owner": "platform"}).text

    assert "matching owner" in body
    assert "platform" in body


def test_library_shows_cost_badge_from_local_estimate(
    repo_root, output_config, registry: Path
) -> None:
    from repave_engine.cost_estimate import CostEstimate, write_cost_estimate_file

    register_repo(registry, PROVENANCE_ENTRY)
    entity_dir = output_config.modules_root / "tf-vpc"
    entity_dir.mkdir(parents=True)
    (entity_dir / "repave.yaml").write_text("spec:\n  blueprint: x\n", encoding="utf-8")
    write_cost_estimate_file(
        entity_dir,
        CostEstimate(
            currency="USD",
            monthly_cost="25.00",
            hourly_cost="—",
            resource_count=1,
            detail="Estimated USD 25.00/month",
        ),
    )
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    index = client.get("/library").text
    assert "library-drawers" in index
    assert "Est USD 25.00/mo" not in index

    body = client.get("/library/terraform").text
    assert "catalog-inventory__cost-badge" in body
    assert "Est USD 25.00/mo" in body


def test_service_detail_shows_cost_estimate_panel(repo_root, output_config, registry: Path) -> None:
    from repave_engine.cost_estimate import CostEstimate, write_cost_estimate_file

    register_repo(registry, PROVENANCE_ENTRY)
    entity_dir = output_config.modules_root / "tf-vpc"
    entity_dir.mkdir(parents=True)
    (entity_dir / "repave.yaml").write_text("spec:\n  blueprint: x\n", encoding="utf-8")
    write_cost_estimate_file(
        entity_dir,
        CostEstimate(
            currency="USD",
            monthly_cost="25.00",
            hourly_cost="—",
            resource_count=2,
            detail="Estimated USD 25.00/month",
        ),
    )
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    assert_surface_moved(client.get("/services/acme-tf-vpc"), "services")
