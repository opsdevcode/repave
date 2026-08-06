from __future__ import annotations

from repave_engine.cost_actuals import CostActualsSummary
from repave_engine.entity_catalog import _cost_scorecard_dimension


def test_cost_scorecard_fails_when_actuals_tag_coverage_incomplete() -> None:
    dim = _cost_scorecard_dimension(
        owner="platform",
        display_name="tf-vpc",
        cost_actuals=CostActualsSummary(
            currency="USD",
            amount_30d="10.00",
            as_of="2026-08-01T00:00:00Z",
            detail="partial tags",
            tag_coverage="partial",
            source_url="",
        ),
        cost_actuals_configured=True,
    )
    assert dim.level == "fail"
    assert dim.key == "cost"


def test_cost_scorecard_fails_when_reader_configured_tags_missing() -> None:
    dim = _cost_scorecard_dimension(
        owner="",
        display_name="",
        cost_actuals=None,
        cost_actuals_configured=True,
    )
    assert dim.level == "fail"
    assert "owner" in dim.detail.lower() or "service" in dim.detail.lower()


def test_cost_scorecard_passes_when_actuals_complete() -> None:
    dim = _cost_scorecard_dimension(
        owner="platform",
        display_name="tf-vpc",
        cost_actuals=CostActualsSummary(
            currency="USD",
            amount_30d="42.00",
            as_of="2026-08-01T00:00:00Z",
            detail="ok",
            tag_coverage="complete",
            source_url="",
        ),
        cost_actuals_configured=True,
    )
    assert dim.level == "pass"
