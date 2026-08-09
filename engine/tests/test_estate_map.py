from __future__ import annotations

from repave_engine.audit_history import AuditHistoryEntry
from repave_engine.estate_map import (
    build_estate_tiles,
    status_label_for_phase,
    summarize_estate_tiles,
)


def test_status_label_for_phase() -> None:
    assert status_label_for_phase("Ready") == "Current"
    assert status_label_for_phase("OutOfDate") == "Needs upgrade"
    assert status_label_for_phase("Error") == "Error"
    assert status_label_for_phase("Custom") == "Custom"


def test_build_estate_tiles_freshness_and_sparkline() -> None:
    rows = [
        {
            "repo_url": "https://github.com/acme/tf-vpc",
            "blueprint_name": "terraform-module-generic",
            "blueprint_version": "1.0.0",
            "owner": "platform",
            "operator_phase": "Ready",
            "operator_message": "ok",
            "registered_at": "2026-01-01T00:00:00Z",
        }
    ]
    audit = (
        AuditHistoryEntry(
            timestamp="2026-01-02T00:00:00Z",
            event="generation",
            blueprint_name="terraform-module-generic",
            blueprint_version="1.0.0",
            module_name="tf-vpc",
            dry_run=True,
            gates_outcome="passed",
            acting_user="tester@example.com",
            repository_url="https://github.com/acme/tf-vpc",
            extra={},
        ),
    )
    tiles = build_estate_tiles(rows, audit_entries=audit, sparkline_slots=4)
    assert len(tiles) == 1
    assert tiles[0].freshness == "fresh"
    assert tiles[0].status_label == "Current"
    assert tiles[0].freshness_detail == "ok"
    assert tiles[0].blueprint_name == "terraform-module-generic"
    assert tiles[0].entity_id == "acme-tf-vpc"
    assert 1 in tiles[0].sparkline


def test_build_estate_tiles_unknown_operator_phase() -> None:
    rows = [
        {
            "repo_url": "https://github.com/acme/tf-lambda",
            "blueprint_name": "terraform-module-generic",
            "blueprint_version": "1.0.0",
            "owner": "platform",
            "operator_phase": "",
            "registered_at": "2026-01-01T00:00:00Z",
        }
    ]
    tiles = build_estate_tiles(rows)
    assert tiles[0].freshness == "unknown"
    assert tiles[0].status_label == ""
    assert tiles[0].freshness_detail == "Upgrade status not available yet"


def test_summarize_estate_tiles() -> None:
    rows = [
        {
            "repo_url": "https://github.com/acme/tf-a",
            "blueprint_name": "terraform-module-generic",
            "blueprint_version": "1.0.0",
            "owner": "platform",
            "operator_phase": "Ready",
            "registered_at": "2026-01-01T00:00:00Z",
        },
        {
            "repo_url": "https://github.com/acme/tf-b",
            "blueprint_name": "terraform-module-generic",
            "blueprint_version": "1.0.0",
            "owner": "platform",
            "operator_phase": "OutOfDate",
            "registered_at": "2026-01-01T00:00:00Z",
        },
        {
            "repo_url": "https://github.com/acme/tf-c",
            "blueprint_name": "terraform-module-generic",
            "blueprint_version": "1.0.0",
            "owner": "platform",
            "operator_phase": "Error",
            "registered_at": "2026-01-01T00:00:00Z",
        },
    ]
    summary = summarize_estate_tiles(build_estate_tiles(rows))
    assert summary.total == 3
    assert summary.fresh_count == 1
    assert summary.drift_count == 1
    assert summary.error_count == 1
