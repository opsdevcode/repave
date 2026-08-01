from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from repave_engine.cost_actuals import CostActualsSummary
from repave_engine.cost_actuals_azure import fetch_entity_cost_actuals_azure
from repave_engine.cost_cache import cache_clear
from repave_engine.entity_catalog import CatalogEntity, ScorecardDimension
from repave_engine.settings import CostAzureConfig


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


def test_fetch_entity_cost_actuals_azure_parses_query(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    cache_clear()

    class FakeCredential:
        def get_token(self, _scope: str) -> MagicMock:
            token = MagicMock()
            token.token = "test-token"
            return token

    azure_identity = types.ModuleType("azure.identity")
    azure_identity.DefaultAzureCredential = FakeCredential
    azure = types.ModuleType("azure")
    azure.identity = azure_identity
    monkeypatch.setitem(sys.modules, "azure", azure)
    monkeypatch.setitem(sys.modules, "azure.identity", azure_identity)

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"properties": {"rows": [[456.78, "USD"]]}}

    monkeypatch.setattr(
        "repave_engine.cost_actuals_azure.httpx.post",
        lambda *_args, **_kwargs: FakeResponse(),
    )

    config = CostAzureConfig(subscription_id="sub-123")
    summary = fetch_entity_cost_actuals_azure(config, _entity())
    assert isinstance(summary, CostActualsSummary)
    assert summary.amount_30d == "456.78"
    assert summary.currency == "USD"
