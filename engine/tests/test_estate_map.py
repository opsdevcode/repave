from __future__ import annotations

from repave_engine.audit_history import AuditHistoryEntry
from repave_engine.estate_map import build_estate_tiles


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
            blueprint_name="terraform-module-generic",
            blueprint_version="1.0.0",
            module_name="tf-vpc",
            dry_run=True,
            gates_outcome="passed",
            acting_user="tester@example.com",
            repository_url="https://github.com/acme/tf-vpc",
        ),
    )
    tiles = build_estate_tiles(rows, audit_entries=audit, sparkline_slots=4)
    assert len(tiles) == 1
    assert tiles[0].freshness == "fresh"
    assert 1 in tiles[0].sparkline
