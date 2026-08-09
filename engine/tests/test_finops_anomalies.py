from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from repave_engine.audit_history import read_recent_audit_entries
from repave_engine.cost_snapshot_store import CostSnapshotEntry, append_cost_snapshot
from repave_engine.entity_catalog import CatalogEntity
from repave_engine.finops_anomalies import (
    detect_entity_cost_anomalies,
    evaluate_finops_anomalies,
)
from repave_engine.notifications import notify_finops_anomalies
from repave_engine.settings import CostAnomalyConfig, PortalConfig


def _entity() -> CatalogEntity:
    return CatalogEntity(
        entity_id="acme-tf-vpc",
        display_name="tf-vpc",
        repo_url="https://github.com/acme/tf-vpc",
        local_path=None,
        owner="platform",
        blueprint_name="terraform-module-generic",
        blueprint_version="1.0.0",
        standard_source="",
        standard_version="",
        component_type="service",
        lifecycle="production",
        operator_phase="",
        operator_message="",
        remediation_pr_url="",
        manifest_name="",
        manifest_namespace="",
        source="fleet",
    )


def _snapshots(path: Path) -> None:
    for captured_at, amount in (
        ("2026-08-02T00:00:00Z", "100.00"),
        ("2026-08-09T00:00:00Z", "200.00"),
    ):
        append_cost_snapshot(
            path,
            CostSnapshotEntry(
                entity_id="acme-tf-vpc",
                captured_at=captured_at,
                currency="USD",
                amount_30d=amount,
            ),
        )


def test_detect_entity_cost_anomalies_flags_wow_spike(tmp_path: Path) -> None:
    path = tmp_path / "cost-snapshots.jsonl"
    _snapshots(path)
    snapshots = (
        CostSnapshotEntry("acme-tf-vpc", "2026-08-02T00:00:00Z", "USD", "100.00"),
        CostSnapshotEntry("acme-tf-vpc", "2026-08-09T00:00:00Z", "USD", "200.00"),
    )
    config = CostAnomalyConfig(enabled=True, wow_threshold_pct=25.0, mom_threshold_pct=200.0)
    anomalies = detect_entity_cost_anomalies(_entity(), snapshots, config)
    assert len(anomalies) == 1
    assert anomalies[0].kind == "wow"
    assert anomalies[0].change_pct == pytest.approx(100.0)


def test_evaluate_finops_anomalies_writes_audit_and_notifies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot_file = tmp_path / "cost-snapshots.jsonl"
    _snapshots(snapshot_file)
    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "audit:",
                "  enabled: true",
                "  file: audit/generation.jsonl",
                "notifications:",
                "  enabled: true",
                "  webhook_url: https://hooks.example.test/finops",
                "  events:",
                "    - finops_anomaly",
                "portal:",
                "  cost_snapshots:",
                "    enabled: true",
                "    file: cost-snapshots.jsonl",
                "  cost_anomalies:",
                "    enabled: true",
                "    wow_threshold_pct: 25",
            ]
        ),
        encoding="utf-8",
    )
    posted: list[str] = []
    monkeypatch.setattr(
        "repave_engine.notifications.httpx.post",
        lambda url, **kwargs: posted.append(url) or MagicMock(status_code=200),
    )
    portal = PortalConfig(
        density="default",
        cost_snapshots_enabled=True,
        cost_snapshots_file=snapshot_file,
        cost_anomalies=CostAnomalyConfig(enabled=True, wow_threshold_pct=25.0),
    )
    anomalies = evaluate_finops_anomalies(
        [_entity()],
        portal,
        repo_root=tmp_path,
        notify=False,
    )
    assert len(anomalies) == 1
    audit_entries = read_recent_audit_entries(
        tmp_path / "audit" / "generation.jsonl",
        limit=5,
        repo_root=tmp_path,
    )
    assert len(audit_entries) == 1
    assert audit_entries[0].extra.get("kind") == "wow"
    notify_finops_anomalies(tmp_path, anomalies)
    assert posted == ["https://hooks.example.test/finops"]


def test_collect_finops_anomalies_skips_audit_and_notify(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot_file = tmp_path / "cost-snapshots.jsonl"
    _snapshots(snapshot_file)
    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "audit:",
                "  enabled: true",
                "  file: audit/generation.jsonl",
                "portal:",
                "  cost_snapshots:",
                "    enabled: true",
                "    file: cost-snapshots.jsonl",
                "  cost_anomalies:",
                "    enabled: true",
                "    wow_threshold_pct: 25",
            ]
        ),
        encoding="utf-8",
    )
    posted: list[str] = []
    monkeypatch.setattr(
        "repave_engine.notifications.httpx.post",
        lambda url, **kwargs: posted.append(url) or MagicMock(status_code=200),
    )
    portal = PortalConfig(
        density="default",
        cost_snapshots_enabled=True,
        cost_snapshots_file=snapshot_file,
        cost_anomalies=CostAnomalyConfig(enabled=True, wow_threshold_pct=25.0),
    )
    from repave_engine.finops_anomalies import collect_finops_anomalies

    anomalies = collect_finops_anomalies([_entity()], portal, repo_root=tmp_path)
    assert len(anomalies) == 1
    assert not (tmp_path / "audit" / "generation.jsonl").exists()
    assert posted == []
