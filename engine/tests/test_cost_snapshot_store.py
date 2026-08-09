from __future__ import annotations

from pathlib import Path

from repave_engine.cost_actuals import CostActualsSummary
from repave_engine.cost_snapshot_store import (
    CostSnapshotEntry,
    build_cost_sparkline,
    capture_cost_snapshots,
    normalize_cost_sparkline_heights,
    read_entity_cost_snapshots,
)


def _actuals(amount: str) -> CostActualsSummary:
    return CostActualsSummary(
        currency="USD",
        amount_30d=amount,
        as_of="2026-08-09T00:00:00Z",
        detail="ok",
        tag_coverage="complete",
        source_url="",
    )


def test_capture_and_read_cost_snapshots(tmp_path: Path) -> None:
    path = tmp_path / "cost-snapshots.jsonl"
    written = capture_cost_snapshots(
        path,
        [("acme-tf-vpc", _actuals("10.00")), ("acme-tf-eks", _actuals("20.00"))],
        captured_at="2026-08-01T00:00:00Z",
    )
    assert written == 2
    snapshots = read_entity_cost_snapshots(path, "acme-tf-vpc")
    assert len(snapshots) == 1
    assert snapshots[0].amount_30d == "10.00"

    skipped = capture_cost_snapshots(
        path,
        [("acme-tf-vpc", _actuals("10.00"))],
        captured_at="2026-08-01T12:00:00Z",
    )
    assert skipped == 0

    updated = capture_cost_snapshots(
        path,
        [("acme-tf-vpc", _actuals("12.00"))],
        captured_at="2026-08-02T00:00:00Z",
    )
    assert updated == 1
    history = read_entity_cost_snapshots(path, "acme-tf-vpc", limit=4)
    assert [item.amount_30d for item in history] == ["10.00", "12.00"]


def test_build_cost_sparkline_normalizes_heights() -> None:
    snapshots = (
        CostSnapshotEntry("svc", "2026-08-01T00:00:00Z", "USD", "10.00"),
        CostSnapshotEntry("svc", "2026-08-02T00:00:00Z", "USD", "20.00"),
        CostSnapshotEntry("svc", "2026-08-03T00:00:00Z", "USD", "15.00"),
    )
    sparkline = build_cost_sparkline(snapshots, slots=8)
    assert len(sparkline) == 8
    assert sparkline[0] == 0
    assert sparkline[-2] == 100
    assert sparkline[-1] < sparkline[-2]
    assert normalize_cost_sparkline_heights([5.0]) == (100,)
