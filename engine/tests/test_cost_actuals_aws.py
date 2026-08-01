from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from repave_engine.cost_actuals import CostActualsSummary
from repave_engine.cost_actuals_aws import fetch_entity_cost_actuals_aws
from repave_engine.cost_cache import cache_clear
from repave_engine.entity_catalog import CatalogEntity, ScorecardDimension
from repave_engine.settings import CostAwsConfig


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


def test_fetch_entity_cost_actuals_aws_parses_cost_explorer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_clear()
    client = MagicMock()
    client.get_cost_and_usage.return_value = {
        "ResultsByTime": [
            {
                "Total": {
                    "UnblendedCost": {"Amount": "123.45", "Unit": "USD"},
                }
            }
        ]
    }
    boto3 = MagicMock()
    boto3.client.return_value = client
    monkeypatch.setitem(__import__("sys").modules, "boto3", boto3)

    summary = fetch_entity_cost_actuals_aws(CostAwsConfig(), _entity())
    assert isinstance(summary, CostActualsSummary)
    assert summary.amount_30d == "123.45"
    assert summary.currency == "USD"
    assert summary.tag_coverage == "complete"


def test_fetch_entity_cost_actuals_aws_uses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    cache_clear()
    client = MagicMock()
    client.get_cost_and_usage.return_value = {
        "ResultsByTime": [
            {"Total": {"UnblendedCost": {"Amount": "10.00", "Unit": "USD"}}},
        ]
    }
    boto3 = MagicMock()
    boto3.client.return_value = client
    monkeypatch.setitem(__import__("sys").modules, "boto3", boto3)

    entity = _entity()
    first = fetch_entity_cost_actuals_aws(CostAwsConfig(), entity)
    second = fetch_entity_cost_actuals_aws(CostAwsConfig(), entity)
    assert first == second
    assert client.get_cost_and_usage.call_count == 1
