from __future__ import annotations

import httpx
import pytest

from repave_engine.cost_actuals import (
    CostActualsSummary,
    cost_reader_configured,
    fetch_entity_cost_actuals_for_portal,
    resolve_cost_reader,
)
from repave_engine.cost_actuals_k8s import (
    fetch_entity_cost_actuals_k8s,
    format_allocation_key,
    parse_opencost_allocation_payload,
)
from repave_engine.cost_cache import cache_clear
from repave_engine.entity_catalog import CatalogEntity, ScorecardDimension
from repave_engine.settings import CostK8sConfig, PortalConfig


def _entity(*, display_name: str = "acme-svc", owner: str = "platform") -> CatalogEntity:
    return CatalogEntity(
        entity_id="acme-svc",
        display_name=display_name,
        repo_url=None,
        local_path=None,
        owner=owner,
        blueprint_name="app-service-generic",
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


def test_format_allocation_key_uses_name() -> None:
    assert format_allocation_key("{name}", _entity()) == "acme-svc"


def test_parse_opencost_allocation_payload_extracts_total_cost() -> None:
    payload = {
        "code": 200,
        "data": [
            {
                "acme-svc": {
                    "name": "acme-svc",
                    "totalCost": 12.345,
                    "window": {"start": "2026-07-05T00:00:00Z", "end": "2026-08-04T00:00:00Z"},
                }
            }
        ],
    }
    summary = parse_opencost_allocation_payload(
        payload,
        allocation_key="acme-svc",
        source_url="http://opencost/allocation",
        tag_coverage="complete",
        currency="USD",
    )
    assert summary == CostActualsSummary(
        currency="USD",
        amount_30d="12.35",
        as_of="2026-08-04T00:00:00Z",
        detail=(
            "OpenCost K8s allocation (acme-svc); "
            "in-cluster list/on-demand pricing; idle/unshared costs excluded by default"
        ),
        tag_coverage="complete",
        source_url="http://opencost/allocation",
    )


def test_fetch_entity_cost_actuals_k8s_uses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    cache_clear()
    entity = _entity()
    config = CostK8sConfig(base_url="http://opencost:9003")
    calls = {"count": 0}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            calls["count"] += 1
            return {
                "data": [
                    {"acme-svc": {"totalCost": 9.99, "window": {"end": "2026-08-04T00:00:00Z"}}}
                ]
            }

    monkeypatch.setattr(
        "repave_engine.cost_actuals_k8s.httpx.get",
        lambda *_args, **_kwargs: FakeResponse(),
    )

    first = fetch_entity_cost_actuals_k8s(config, entity)
    second = fetch_entity_cost_actuals_k8s(config, entity)

    assert first is not None
    assert first.amount_30d == "9.99"
    assert second == first
    assert calls["count"] == 1


def test_fetch_entity_cost_actuals_k8s_skips_missing_service_name() -> None:
    assert (
        fetch_entity_cost_actuals_k8s(
            CostK8sConfig(base_url="http://opencost"), _entity(owner="", display_name="")
        )
        is None
    )


def test_fetch_entity_cost_actuals_k8s_http_error_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_clear()

    def _fail(*_args, **_kwargs) -> None:
        raise httpx.HTTPError("boom")

    monkeypatch.setattr("repave_engine.cost_actuals_k8s.httpx.get", _fail)
    assert (
        fetch_entity_cost_actuals_k8s(CostK8sConfig(base_url="http://opencost"), _entity()) is None
    )


def test_resolve_cost_reader_k8s() -> None:
    assert resolve_cost_reader(cost_reader="k8s", cost_actuals_url="") == "k8s"
    assert cost_reader_configured(cost_reader="k8s", cost_actuals_url="")


def test_portal_config_loads_cost_k8s_block(tmp_path) -> None:
    from repave_engine.settings import load_portal_config

    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "portal:",
                "  cost_reader: k8s",
                "  cost_k8s:",
                "    base_url: http://opencost.opencost:9003",
                "    aggregate: namespace",
                "    allocation_key: '{name}'",
            ]
        ),
        encoding="utf-8",
    )
    config = load_portal_config(tmp_path)
    assert config.cost_reader == "k8s"
    assert config.cost_k8s == CostK8sConfig(
        base_url="http://opencost.opencost:9003",
        aggregate="namespace",
        allocation_key="{name}",
        window="30d",
        currency="USD",
    )


def test_fetch_entity_cost_actuals_for_portal_dispatches_k8s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_clear()
    expected = CostActualsSummary(
        currency="USD",
        amount_30d="3.00",
        as_of="2026-08-04T00:00:00Z",
        detail="test",
        tag_coverage="complete",
        source_url="http://opencost/allocation",
    )

    monkeypatch.setattr(
        "repave_engine.cost_actuals_k8s.fetch_entity_cost_actuals_k8s",
        lambda _config, _entity: expected,
    )
    portal = PortalConfig(
        density="default",
        cost_reader="k8s",
        cost_k8s=CostK8sConfig(base_url="http://opencost:9003"),
    )
    assert fetch_entity_cost_actuals_for_portal(portal, _entity()) == expected
