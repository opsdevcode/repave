from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.cost_actuals import CostActualsSummary
from repave_engine.fleet import FleetEntry, register_repo


@pytest.fixture
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "registry.jsonl"
    monkeypatch.setenv("REPAVE_FLEET_FILE", str(path))
    return path


PROVENANCE_ENTRY = FleetEntry(
    repo_url="https://github.com/acme/tf-vpc",
    blueprint_name="terraform-module-generic",
    blueprint_version="0.9.0",
    standard_source="standards/terraform-standards",
    standard_version="1.1.0",
    owner="platform",
    registered_by="tester@example.com",
)


def test_platform_finops_export_json_and_csv(
    output_config,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    registry: Path,
) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    (tmp_path / "repave.config.yaml").write_text(
        (
            f"fleet:\n  enabled: true\n  file: {registry}\n"
            "portal:\n"
            "  cost_actuals_url: https://cost.example.test/actuals\n"
            "  cost_snapshots:\n"
            "    enabled: true\n"
            "    file: data/fleet/cost-snapshots.jsonl\n"
            "  cost_budgets:\n"
            "    default_monthly_usd: 100\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    def _fetch(_portal: object, _entity: object, **kwargs: object) -> CostActualsSummary | None:
        return CostActualsSummary(
            currency="USD",
            amount_30d="42.00",
            as_of="2026-08-09T00:00:00Z",
            detail="ok",
            tag_coverage="complete",
            source_url="",
        )

    import repave_engine.catalog_cost as catalog_cost

    original = catalog_cost.fetch_entity_cost_actuals_for_portal
    catalog_cost.fetch_entity_cost_actuals_for_portal = _fetch
    try:
        client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))
        json_response = client.get("/api/v2/platform/finops/export")
        assert json_response.status_code == 200
        body = json_response.json()
        assert body["count"] == 1
        assert body["rows"][0]["Owner"] == "platform"
        assert body["rows"][0]["ServiceName"] == "acme-tf-vpc"
        assert body["rows"][0]["BilledCost"] == "42.00"

        csv_response = client.get("/api/v2/platform/finops/export", params={"format": "csv"})
        assert csv_response.status_code == 200
        assert "text/csv" in csv_response.headers["content-type"]
        assert "Owner,ServiceName,BillingCurrency" in csv_response.text
        assert "platform,acme-tf-vpc,USD,42.00" in csv_response.text
    finally:
        catalog_cost.fetch_entity_cost_actuals_for_portal = original


def test_platform_finops_export_lists_in_api_v2_metadata(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    payload = client.get("/api/v2").json()
    assert "GET /api/v2/platform/finops/export" in payload["endpoints"]
