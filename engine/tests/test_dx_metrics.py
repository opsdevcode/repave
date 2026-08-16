"""Tests for golden-path adoption / DX outcome metrics."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from portal_moved import assert_surface_moved
from repave_engine.api import create_app
from repave_engine.audit_history import AuditHistoryEntry
from repave_engine.dx_metrics import (
    BlueprintFriction,
    build_dx_metrics_snapshot,
    collect_eligible_repo_urls,
    compute_adoption,
    compute_gate_friction,
    compute_plan_apply_funnels,
    compute_time_to_first_artifact,
    gate_pass_rate_from_friction,
)
from repave_engine.dx_metrics_store import (
    capture_dx_metrics,
    read_dx_metrics_snapshots,
)
from repave_engine.fleet import FleetEntry, register_repo
from repave_engine.settings import load_platform_metrics_config


def _entry(
    *,
    ts: str,
    blueprint: str,
    dry_run: bool,
    outcome: str,
    user: str = "alice",
    duration: float | None = None,
) -> AuditHistoryEntry:
    extra = {}
    if duration is not None:
        extra["duration_seconds"] = duration
    return AuditHistoryEntry(
        timestamp=ts,
        event="generation",
        blueprint_name=blueprint,
        blueprint_version="1.0.0",
        module_name="demo",
        dry_run=dry_run,
        gates_outcome=outcome,
        acting_user=user,
        repository_url="https://github.com/acme/demo",
        extra=extra,
    )


def test_compute_adoption_bypass_list() -> None:
    ratio, bypass, eligible, governed = compute_adoption(
        governed_urls=["https://github.com/acme/a.git"],
        eligible_urls=[
            "https://github.com/acme/a",
            "https://github.com/acme/b",
            "https://github.com/acme/c.git",
        ],
    )
    assert eligible == 3
    assert governed == 1
    assert ratio == 0.3333
    assert bypass == (
        "https://github.com/acme/b",
        "https://github.com/acme/c",
    )


def test_compute_plan_apply_funnels_and_friction() -> None:
    entries = [
        _entry(
            ts="2026-01-03T00:00:00Z",
            blueprint="helm-chart-generic",
            dry_run=True,
            outcome="passed",
        ),
        _entry(
            ts="2026-01-03T01:00:00Z",
            blueprint="helm-chart-generic",
            dry_run=True,
            outcome="passed",
        ),
        _entry(
            ts="2026-01-03T02:00:00Z",
            blueprint="helm-chart-generic",
            dry_run=False,
            outcome="passed",
            duration=12.5,
        ),
        _entry(
            ts="2026-01-03T03:00:00Z",
            blueprint="app-service-generic",
            dry_run=False,
            outcome="failed",
        ),
    ]
    plans, applies, ratio, funnels = compute_plan_apply_funnels(entries)
    assert plans == 2
    assert applies == 2
    assert ratio == 1.0
    by_name = {item.blueprint_name: item for item in funnels}
    assert by_name["helm-chart-generic"].conversion_ratio == 0.5
    friction = compute_gate_friction(entries)
    assert friction[0].blueprint_name == "app-service-generic"
    assert friction[0].failed == 1


def test_gate_pass_rate_from_friction() -> None:
    assert gate_pass_rate_from_friction(()) is None
    rate = gate_pass_rate_from_friction(
        (
            BlueprintFriction("a", total=4, failed=1, fail_ratio=0.25),
            BlueprintFriction("b", total=6, failed=1, fail_ratio=0.1667),
        )
    )
    assert rate == 0.8


def test_compute_time_to_first_artifact() -> None:
    entries = [
        _entry(
            ts="2026-01-01T10:00:00Z",
            blueprint="helm-chart-generic",
            dry_run=True,
            outcome="passed",
        ),
        _entry(
            ts="2026-01-01T10:30:00Z",
            blueprint="helm-chart-generic",
            dry_run=False,
            outcome="passed",
            duration=8.0,
        ),
    ]
    # audit_history is newest-first; reverse for our helper's chronological walk
    newest_first = list(reversed(entries))
    p50, p90 = compute_time_to_first_artifact(newest_first)
    assert p50 == 1800.0
    assert p90 == 1800.0


def test_build_snapshot_degrades_without_audit() -> None:
    fleet = [
        FleetEntry(
            repo_url="https://github.com/acme/a",
            blueprint_name="helm-chart-generic",
            blueprint_version="1.0.0",
            standard_source="",
            standard_version="",
            owner="platform",
            registered_by="alice",
        )
    ]
    snap = build_dx_metrics_snapshot(
        captured_at="2026-01-01T00:00:00Z",
        fleet_entries=fleet,
        eligible_urls=[],
        audit_entries=None,
        audit_available=False,
        fleet_enabled=True,
    )
    assert snap.audit_available is False
    assert snap.adoption_ratio == 1.0
    assert snap.plan_count == 0
    assert "Audit is disabled" in snap.message


def test_collect_eligible_repo_urls_uses_search_fn() -> None:
    def fake_search(query: str, token: str, *, limit: int = 30) -> tuple[str, ...]:
        assert token == "tok"
        if query == "org:acme":
            return ("https://github.com/acme/one", "https://github.com/acme/two")
        return ()

    urls, source, message = collect_eligible_repo_urls(
        github_orgs=["acme"],
        github_topics=[],
        token="tok",
        search_limit=10,
        search_fn=fake_search,
    )
    assert source == "github_search"
    assert message == ""
    assert urls == ("https://github.com/acme/one", "https://github.com/acme/two")


def test_load_platform_metrics_config(tmp_path: Path, monkeypatch) -> None:
    assert load_platform_metrics_config(tmp_path) is None
    (tmp_path / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\n"
        "platform_metrics:\n"
        "  enabled: true\n"
        "  snapshot_file: data/metrics.jsonl\n"
        "  github_orgs: [acme]\n"
        "  baseline_adoption_ratio: 0.5\n",
        encoding="utf-8",
    )
    config = load_platform_metrics_config(tmp_path)
    assert config is not None
    assert config.enabled is True
    assert config.github_orgs == ("acme",)
    assert config.baseline_adoption_ratio == 0.5
    assert config.snapshot_file == (tmp_path / "data" / "metrics.jsonl").resolve()

    monkeypatch.setenv("REPAVE_PLATFORM_METRICS_FILE", str(tmp_path / "override.jsonl"))
    overridden = load_platform_metrics_config(tmp_path)
    assert overridden is not None
    assert overridden.snapshot_file == tmp_path / "override.jsonl"

    (tmp_path / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\nplatform_metrics:\n  enabled: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REPAVE_PLATFORM_METRICS", "0")
    assert load_platform_metrics_config(tmp_path) is None


def test_snapshot_roundtrip_jsonl(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\n"
        "platform_metrics:\n"
        "  enabled: true\n"
        "  snapshot_file: snaps.jsonl\n"
        "fleet:\n"
        "  enabled: true\n"
        "  file: fleet.jsonl\n"
        "audit:\n"
        "  enabled: false\n"
        "  file: audit.jsonl\n",
        encoding="utf-8",
    )
    register_repo(
        tmp_path / "fleet.jsonl",
        FleetEntry(
            repo_url="https://github.com/acme/a",
            blueprint_name="helm-chart-generic",
            blueprint_version="1.0.0",
            standard_source="",
            standard_version="",
            owner="",
            registered_by="test",
        ),
        repo_root=tmp_path,
    )
    snap = capture_dx_metrics(tmp_path, github_token=None, persist=True)
    assert snap.governed_count == 1
    history = read_dx_metrics_snapshots(tmp_path / "snaps.jsonl", repo_root=tmp_path, limit=5)
    assert len(history) == 1
    assert history[0].governed_count == 1


def test_platform_adoption_page_and_api(
    repo_root: Path,
    output_config,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("REPAVE_PLATFORM_METRICS", "1")
    monkeypatch.setenv("REPAVE_PLATFORM_METRICS_FILE", str(tmp_path / "snaps.jsonl"))
    monkeypatch.setenv("REPAVE_FLEET_FILE", str(tmp_path / "fleet.jsonl"))
    monkeypatch.delenv("REPAVE_AUDIT_FILE", raising=False)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    page = client.get("/platform/adoption")
    assert_surface_moved(page, "platform-adoption")

    api = client.get("/api/v2/platform/metrics")
    assert api.status_code == 200
    body = api.json()
    assert "adoption_ratio" in body
    assert body["audit_available"] in {True, False}


def test_platform_stakeholder_pages_and_api(
    repo_root: Path,
    output_config,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("REPAVE_PLATFORM_METRICS", "1")
    monkeypatch.setenv("REPAVE_PLATFORM_METRICS_FILE", str(tmp_path / "snaps.jsonl"))
    monkeypatch.setenv("REPAVE_FLEET_FILE", str(tmp_path / "fleet.jsonl"))
    monkeypatch.delenv("REPAVE_AUDIT_FILE", raising=False)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    compliance = client.get("/platform/compliance")
    assert_surface_moved(compliance, "platform-compliance")

    value_stream = client.get("/platform/value-stream")
    assert_surface_moved(value_stream, "platform-value-stream")

    compliance_api = client.get("/api/v2/platform/compliance")
    assert compliance_api.status_code == 200
    compliance_body = compliance_api.json()
    assert compliance_body["metrics_enabled"] is True
    assert "gate_pass_rate" in compliance_body
    assert "bypass_count" in compliance_body

    value_api = client.get("/api/v2/platform/value-stream")
    assert value_api.status_code == 200
    value_body = value_api.json()
    assert value_body["metrics_enabled"] is True
    assert "adoption_ratio" in value_body
    assert "history" in value_body


def test_platform_metrics_api_404_when_disabled(repo_root, output_config, monkeypatch) -> None:
    monkeypatch.setenv("REPAVE_PLATFORM_METRICS", "0")
    monkeypatch.delenv("REPAVE_PLATFORM_METRICS_FILE", raising=False)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/api/v2/platform/metrics")
    assert response.status_code == 404
