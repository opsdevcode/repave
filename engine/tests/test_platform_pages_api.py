from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.fleet import FleetEntry, register_repo
from repave_engine.fleet_operator_status import (
    UpgradeCampaignStatus,
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


def test_api_v2_platform_ops(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/api/v2/platform/ops")

    assert response.status_code == 200
    payload = response.json()
    assert "readiness" in payload
    assert "doctor_results" in payload
    assert "dead_letter_runs" in payload
    assert payload["queued_runs"] >= 0
    assert payload["running_runs"] >= 0
    assert isinstance(payload["environment_vending_enabled"], bool)


def test_api_v2_platform_standards_without_fleet(
    repo_root, output_config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REPAVE_FLEET_FILE", raising=False)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/api/v2/platform/standards")

    assert response.status_code == 200
    payload = response.json()
    assert payload["fleet_enabled"] is False
    assert payload["summaries"] == []


def test_api_v2_platform_standards_lists_behind_repos(
    repo_root, output_config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = tmp_path / "registry.jsonl"
    monkeypatch.setenv("REPAVE_FLEET_FILE", str(registry))
    register_repo(registry, PROVENANCE_ENTRY)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    response = client.get("/api/v2/platform/standards")

    assert response.status_code == 200
    payload = response.json()
    assert payload["fleet_enabled"] is True
    match = next(
        item
        for item in payload["summaries"]
        if item["blueprint_name"] == "terraform-module-generic"
    )
    assert match["behind_count"] >= 1
    assert match["behind_repos"][0]["repo_url"] == PROVENANCE_ENTRY.repo_url


def test_api_v2_platform_campaigns_and_pause(
    repo_root, output_config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = tmp_path / "registry.jsonl"
    status = tmp_path / "operator-status.json"
    monkeypatch.setenv("REPAVE_FLEET_FILE", str(registry))
    monkeypatch.setenv("REPAVE_FLEET_OPERATOR_STATUS_FILE", str(status))
    register_repo(registry, PROVENANCE_ENTRY)
    write_operator_status_snapshot(
        status,
        [],
        campaigns=[
            UpgradeCampaignStatus(
                name="platform-rollout",
                namespace="repave-system",
                phase="Active",
                open_pr_count=1,
                out_of_date_count=2,
                paused=False,
            )
        ],
    )
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    listed = client.get("/api/v2/platform/campaigns")
    assert listed.status_code == 200
    body = listed.json()
    assert body["operator_status_enabled"] is True
    assert body["snapshot"]["campaigns"][0]["name"] == "platform-rollout"

    missing = client.post(
        "/api/v2/platform/campaigns/repave-system/missing/paused",
        json={"paused": True},
    )
    assert missing.status_code == 404

    bad = client.post(
        "/api/v2/platform/campaigns/repave-system/platform-rollout/paused",
        json={"paused": "yes"},
    )
    assert bad.status_code == 400

    with patch("repave_engine.fleet_operator_actions.patch_upgrade_campaign_paused") as mocked:
        paused = client.post(
            "/api/v2/platform/campaigns/repave-system/platform-rollout/paused",
            json={"paused": True},
        )
    assert paused.status_code == 200
    assert paused.json() == {
        "namespace": "repave-system",
        "name": "platform-rollout",
        "paused": True,
    }
    mocked.assert_called_once_with("platform-rollout", "repave-system", paused=True)
