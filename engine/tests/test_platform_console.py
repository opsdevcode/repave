from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.blueprint import blueprints_dir, list_blueprints
from repave_engine.fleet import FleetEntry, register_repo
from repave_engine.fleet_drift import estimate_fleet_drift
from repave_engine.fleet_operator_status import (
    FleetOperatorStatus,
    OperatorPins,
    UpgradeCampaignStatus,
    load_operator_status_snapshot,
    parse_kubectl_campaign_list,
    status_from_campaign_item,
    write_operator_status_snapshot,
)
from repave_engine.portal_platform import (
    build_platform_fleet_page,
    build_platform_standards_page,
    find_campaign_in_snapshot,
    platform_admin_visible,
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


def test_platform_admin_visible_local_mode() -> None:
    assert platform_admin_visible(None, None) is True


def test_estimate_fleet_drift_marks_behind_pins(repo_root: Path, registry: Path) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    blueprints = list_blueprints(blueprints_dir(repo_root))
    target = next(item for item in blueprints if item.name == "terraform-module-generic")
    summaries = estimate_fleet_drift([PROVENANCE_ENTRY], blueprints)
    match = next(item for item in summaries if item.blueprint_name == target.name)
    assert match.behind_count == 1
    assert match.behind_repos[0].repo_url == PROVENANCE_ENTRY.repo_url


def test_operator_status_snapshot_v2_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    write_operator_status_snapshot(
        path,
        [
            FleetOperatorStatus(
                repo_url="https://github.com/acme/tf-vpc",
                phase="OutOfDate",
                observed_pins=OperatorPins(blueprint_version="0.9.0"),
                desired_pins=OperatorPins(blueprint_version="1.0.0"),
                drift_detected_at="2026-08-02T12:00:00Z",
                upgrade_plan_changed_files=3,
            )
        ],
        campaigns=[
            UpgradeCampaignStatus(
                name="default",
                namespace="repave-system",
                phase="Active",
                open_pr_count=2,
                out_of_date_count=5,
            )
        ],
    )
    snapshot = load_operator_status_snapshot(path)
    assert snapshot is not None
    assert snapshot.version == 2
    assert len(snapshot.repos) == 1
    assert snapshot.repos[0].upgrade_plan_changed_files == 3
    assert len(snapshot.campaigns) == 1
    assert snapshot.campaigns[0].open_pr_count == 2


def test_parse_kubectl_campaign_item() -> None:
    row = status_from_campaign_item(
        {
            "metadata": {"name": "platform-rollout", "namespace": "repave-system"},
            "spec": {"paused": False, "blueprintName": "terraform-module-generic"},
            "status": {
                "phase": "Active",
                "openPRCount": 1,
                "outOfDateCount": 4,
                "oldestDriftAgeSeconds": 3600,
                "averageRemediationMTTRSeconds": 900,
                "consecutiveGateFailures": 0,
                "githubRateLimitRemaining": 4000,
            },
        }
    )
    assert row is not None
    assert row.name == "platform-rollout"
    assert row.out_of_date_count == 4
    parsed = parse_kubectl_campaign_list(
        {
            "items": [
                {
                    "metadata": {"name": "platform-rollout", "namespace": "repave-system"},
                    "spec": {"blueprintName": "terraform-module-generic"},
                    "status": {"phase": "Active", "openPRCount": 1, "outOfDateCount": 2},
                }
            ]
        }
    )
    assert len(parsed) == 1


def test_platform_fleet_page_requires_admin_when_service_mode(
    repo_root, output_config, registry: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    monkeypatch.setenv("REPAVE_SERVICE_MODE", "1")
    monkeypatch.setenv("REPAVE_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("REPAVE_DATABASE_URL", f"sqlite:///{tmp_path}/repave.sqlite")
    monkeypatch.setenv("REPAVE_OIDC_ISSUER", "https://idp.example.com")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_ID", "client")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_SECRET", "secret")
    monkeypatch.setenv("REPAVE_OIDC_REDIRECT_URI", "https://repave.example.com/auth/callback")
    client = TestClient(
        create_app(repo_root=repo_root, output_config=output_config),
        raise_server_exceptions=False,
        follow_redirects=False,
    )
    response = client.get("/platform/fleet")
    assert response.status_code == 302
    assert response.headers["location"] == "/auth/login?next=/platform/fleet"


def test_platform_fleet_page_renders(repo_root, output_config, registry: Path) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    body = client.get("/platform/fleet").text
    assert "Governed repositories" in body
    assert "Register repository" in body
    assert "terraform-module-generic@0.9.0" in body
    assert "/platform/ops" in body
    assert "/platform/adoption" in body


def test_platform_fleet_register_and_unregister(repo_root, output_config, registry: Path) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/platform/fleet/register",
        data={
            "repo_url": "https://github.com/acme/tf-vpc",
            "blueprint_name": "terraform-module-generic",
            "blueprint_version": "1.0.0",
            "standard_version": "1.2.0",
            "owner": "platform",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = build_platform_fleet_page(repo_root)
    assert any(row["repo_url"] == "https://github.com/acme/tf-vpc" for row in page.fleet_repos)
    removed = client.post(
        "/platform/fleet/unregister",
        data={"repo_url": "https://github.com/acme/tf-vpc"},
        follow_redirects=False,
    )
    assert removed.status_code == 303
    page = build_platform_fleet_page(repo_root)
    assert page.fleet_repos == []


def test_platform_ops_page_renders(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    body = client.get("/platform/ops").text
    assert "Estate health" in body
    assert "Gate toolchain" in body


def test_platform_standards_page_renders(repo_root, output_config, registry: Path) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    body = client.get("/platform/standards").text
    assert "Standards blast radius" in body
    assert "terraform-module-generic" in body
    page = build_platform_standards_page(repo_root)
    assert page.summaries


def test_platform_campaigns_page_without_snapshot(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    body = client.get("/platform/campaigns").text
    assert "Operator campaigns" in body
    assert "fleet-operator-snapshot" in body


def test_find_campaign_in_snapshot() -> None:
    from repave_engine.fleet_operator_status import OperatorStatusSnapshot

    page_snapshot = OperatorStatusSnapshot(
        version=2,
        updated_at="2026-08-02T12:00:00Z",
        repos=(),
        campaigns=(
            UpgradeCampaignStatus(
                name="platform-rollout",
                namespace="repave-system",
                phase="Active",
                paused=False,
            ),
        ),
    )
    found = find_campaign_in_snapshot(
        page_snapshot,
        namespace="repave-system",
        name="platform-rollout",
    )
    assert found is not None
    assert found.phase == "Active"
    assert (
        find_campaign_in_snapshot(page_snapshot, namespace="repave-system", name="missing") is None
    )


def test_platform_campaign_pause_action(
    repo_root,
    output_config,
    registry: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status_file = tmp_path / "operator-status.json"
    write_operator_status_snapshot(
        status_file,
        [],
        campaigns=[
            UpgradeCampaignStatus(
                name="platform-rollout",
                namespace="repave-system",
                phase="Active",
                paused=False,
            )
        ],
    )
    monkeypatch.setenv("REPAVE_FLEET_FILE", str(registry))
    monkeypatch.setenv("REPAVE_FLEET_OPERATOR_STATUS_FILE", str(status_file))
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    calls: list[tuple[str, str, bool]] = []

    def fake_patch(name: str, namespace: str, *, paused: bool) -> None:
        calls.append((name, namespace, paused))

    monkeypatch.setattr(
        "repave_engine.api.patch_upgrade_campaign_paused",
        fake_patch,
    )
    response = client.post(
        "/platform/campaigns/repave-system/platform-rollout/paused",
        data={"paused": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/platform/campaigns"
    assert calls == [("platform-rollout", "repave-system", True)]
    body = client.get("/platform/campaigns").text
    assert "Pause campaign" in body
    assert "Resume campaign" not in body or "platform-rollout" in body


def test_platform_standards_confirm_drift_submits_run(
    repo_root,
    output_config,
    registry: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    monkeypatch.setenv("REPAVE_ASYNC_GENERATION", "1")
    monkeypatch.setenv("REPAVE_RUNS_DB", str(tmp_path / "runs.sqlite"))
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    try:
        body = client.get("/platform/standards").text
        assert "Confirm drift" in body
        response = client.post(
            "/platform/standards/terraform-module-generic/confirm-drift",
            data={"repo_urls": PROVENANCE_ENTRY.repo_url},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"].startswith("/runs/")
    finally:
        queue = client.app.state.run_queue
        if queue is not None:
            queue.close()


def test_nav_shows_platform_link(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    body = client.get("/").text
    assert 'href="/platform/fleet"' in body
    assert "Platform" in body
