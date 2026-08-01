from __future__ import annotations

import pytest

from repave_engine.cost_actuals import (
    CostActualsSummary,
    entity_tag_coverage,
    fetch_entity_cost_actuals,
    parse_cost_actuals_payload,
    tag_coverage_for_fields,
)
from repave_engine.entity_catalog import CatalogEntity, ScorecardDimension


def _entity(owner: str = "platform", display_name: str = "tf-vpc") -> CatalogEntity:
    return CatalogEntity(
        entity_id="acme-tf-vpc",
        display_name=display_name,
        repo_url="https://github.com/acme/tf-vpc",
        local_path=None,
        owner=owner,
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
        scorecard=(ScorecardDimension("pins", "Pins", "pass", ""),),
    )


def test_tag_coverage_for_fields() -> None:
    assert tag_coverage_for_fields("platform", "tf-vpc")[0] == "complete"
    assert tag_coverage_for_fields("platform", "")[0] == "partial"
    assert tag_coverage_for_fields("", "")[0] == "missing"


def test_entity_tag_coverage() -> None:
    assert entity_tag_coverage(_entity())[0] == "complete"


def test_parse_cost_actuals_payload() -> None:
    summary = parse_cost_actuals_payload(
        {
            "currency": "USD",
            "amount_30d": "1234.56",
            "as_of": "2026-08-01T00:00:00Z",
            "detail": "30-day spend",
        },
        source_url="https://cost.example/acme-tf-vpc",
        tag_coverage="complete",
    )
    assert summary is not None
    assert summary.amount_30d == "1234.56"


def test_fetch_entity_cost_actuals(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {
                "currency": "USD",
                "amount_30d": "500.00",
                "as_of": "2026-08-01T00:00:00Z",
                "detail": "ok",
            }

    monkeypatch.setattr(
        "repave_engine.cost_actuals.httpx.get",
        lambda *_args, **_kwargs: FakeResponse(),
    )
    summary = fetch_entity_cost_actuals("https://cost.example/{name}", _entity())
    assert isinstance(summary, CostActualsSummary)
    assert summary.amount_30d == "500.00"
