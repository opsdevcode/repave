from __future__ import annotations

from repave_engine.entity_catalog import CatalogEntity, ScorecardDimension
from repave_engine.observability_slo import (
    fetch_entity_slo_summary,
    format_slo_url,
    parse_slo_payload,
)


def _entity() -> CatalogEntity:
    return CatalogEntity(
        entity_id="acme-svc",
        display_name="acme-svc",
        repo_url=None,
        local_path=None,
        owner="platform",
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


def test_format_slo_url_placeholders() -> None:
    url = format_slo_url("https://slo.example/{name}?id={entity_id}", _entity())
    assert url == "https://slo.example/acme-svc?id=acme-svc"


def test_parse_slo_payload() -> None:
    summary = parse_slo_payload(
        {
            "status": "healthy",
            "slo_target": "99.9%",
            "slo_current": "99.95%",
            "detail": "Within budget",
        },
        source_url="https://slo.example/acme-svc",
    )
    assert summary is not None
    assert summary.status == "healthy"
    assert summary.slo_target == "99.9%"


def test_fetch_entity_slo_summary(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {
                "status": "degraded",
                "slo_target": "99.9%",
                "slo_current": "98%",
                "detail": "Error budget burn",
            }

    monkeypatch.setattr(
        "repave_engine.observability_slo.httpx.get",
        lambda *_args, **_kwargs: FakeResponse(),
    )
    summary = fetch_entity_slo_summary("https://slo.example/{name}", _entity())
    assert summary is not None
    assert summary.status == "degraded"
