from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from repave_engine.dx_metrics import BlueprintFriction, BlueprintFunnel, DxMetricsSnapshot
from repave_engine.roadmap_evidence import (
    DEFAULT_ROADMAP_THEMES,
    RoadmapEvidenceSettings,
    RoadmapThemeConfig,
    build_roadmap_evidence_report,
    build_sunset_candidates,
    build_theme_evidence,
)


def _snapshot() -> DxMetricsSnapshot:
    return DxMetricsSnapshot(
        captured_at="2026-08-09T12:00:00Z",
        audit_available=True,
        fleet_enabled=True,
        eligible_count=10,
        governed_count=6,
        adoption_ratio=0.6,
        bypass_repos=("https://github.com/acme/shadow",),
        plan_count=20,
        apply_count=8,
        plan_apply_ratio=0.4,
        funnels=(
            BlueprintFunnel(
                blueprint_name="terraform-module-generic",
                plans=10,
                applies=2,
                passed_applies=2,
                conversion_ratio=0.2,
            ),
            BlueprintFunnel(
                blueprint_name="ansible-role-generic",
                plans=5,
                applies=4,
                passed_applies=4,
                conversion_ratio=0.8,
            ),
            BlueprintFunnel(
                blueprint_name="opa-policy-generic",
                plans=3,
                applies=3,
                passed_applies=3,
                conversion_ratio=1.0,
            ),
        ),
        time_to_first_artifact_seconds_p50=120.0,
        time_to_first_artifact_seconds_p90=300.0,
        service_creation_seconds_p50=40.0,
        service_creation_seconds_p90=90.0,
        friction=(
            BlueprintFriction(
                blueprint_name="app-service-generic",
                total=4,
                failed=2,
                fail_ratio=0.5,
            ),
        ),
        baseline_adoption_ratio=0.5,
        baseline_plan_apply_ratio=0.35,
        eligible_source="fleet",
        message="",
    )


def test_build_theme_evidence_cites_adoption_from_snapshot() -> None:
    snapshot = _snapshot()
    themes = (
        RoadmapThemeConfig(
            key="v185-adoption",
            title="Golden path adoption (v1.85)",
            requesting_team="platform",
            evidence_kind="fleet_adoption",
        ),
    )
    rows = build_theme_evidence(snapshot, themes)
    assert len(rows) == 1
    assert "60%" in rows[0].evidence_summary
    assert (
        "/platform/adoption" in rows[0].evidence_detail
        or "adoption" in rows[0].evidence_detail.lower()
    )
    assert rows[0].meets_baseline is True
    assert rows[0].requesting_team == "platform"


def test_build_sunset_candidates_flags_low_conversion_blueprint() -> None:
    snapshot = _snapshot()
    now = datetime(2026, 8, 9, tzinfo=timezone.utc)
    candidates = build_sunset_candidates(
        snapshot,
        conversion_threshold=0.25,
        min_plans=1,
        review_days=90,
        now=now,
    )
    assert len(candidates) == 1
    assert candidates[0].blueprint_name == "terraform-module-generic"
    assert candidates[0].conversion_ratio == pytest.approx(0.2)
    assert candidates[0].review_by == "2026-11-07"
    assert "simplification" in candidates[0].reason or "sunset" in candidates[0].reason


def test_build_roadmap_evidence_report_uses_default_themes() -> None:
    snapshot = _snapshot()
    report = build_roadmap_evidence_report(snapshot, RoadmapEvidenceSettings())
    assert len(report.themes) == len(DEFAULT_ROADMAP_THEMES)
    guided = next(row for row in report.themes if row.key == "v188-guided-forms")
    assert "terraform-module-generic" in guided.evidence_detail
    assert len(report.sunset_candidates) >= 1
    public = report.to_public_dict()
    assert public["captured_at"] == snapshot.captured_at
    assert public["themes"][0]["requesting_team"]


def test_platform_roadmap_page_and_api(
    repo_root,
    output_config,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from repave_engine.api import create_app
    from repave_engine.fleet import FleetEntry, register_repo

    registry = tmp_path / "fleet.jsonl"
    register_repo(
        registry,
        FleetEntry(
            repo_url="https://github.com/acme/tf-vpc",
            blueprint_name="terraform-module-generic",
            blueprint_version="0.9.0",
            standard_source="",
            standard_version="",
            owner="platform",
            registered_by="test",
        ),
        repo_root=tmp_path,
    )
    audit = tmp_path / "audit.jsonl"
    audit.write_text(
        "\n".join(
            [
                (
                    '{"event":"generation","blueprint_name":"terraform-module-generic",'
                    '"blueprint_version":"0.9.0","module_name":"tf-vpc","dry_run":true,'
                    '"gates_outcome":"passed","repository_url":"https://github.com/acme/tf-vpc",'
                    '"acting_user":"alice","extra":{},"timestamp":"2026-08-01T10:00:00+00:00"}'
                ),
                (
                    '{"event":"generation","blueprint_name":"terraform-module-generic",'
                    '"blueprint_version":"0.9.0","module_name":"tf-vpc","dry_run":false,'
                    '"gates_outcome":"passed","repository_url":"https://github.com/acme/tf-vpc",'
                    '"acting_user":"alice","extra":{},"timestamp":"2026-08-02T14:00:00+00:00"}'
                ),
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "apiVersion: repave.dev/v1",
                f"fleet:\n  enabled: true\n  file: {registry}",
                f"audit:\n  enabled: true\n  file: {audit}",
                "platform_metrics:\n  enabled: true\n  snapshot_file: snaps.jsonl",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))

    page = client.get("/platform/roadmap")
    assert page.status_code == 200
    assert "Roadmap evidence" in page.text
    assert "Theme adoption evidence" in page.text
    assert 'href="/platform/roadmap"' in page.text

    api = client.get("/api/v2/platform/roadmap-evidence")
    assert api.status_code == 200
    body = api.json()
    assert body["metrics_enabled"] is True
    assert body["themes"]
    assert body["themes"][0]["requesting_team"]
