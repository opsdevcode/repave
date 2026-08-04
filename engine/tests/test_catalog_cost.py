from __future__ import annotations

from repave_engine.catalog_cost import enrich_catalog_entities_with_cost, format_cost_badge
from repave_engine.cost_estimate import CostEstimate
from repave_engine.entity_catalog import CatalogEntity, ScorecardDimension


def _entity(local_path=None) -> CatalogEntity:
    return CatalogEntity(
        entity_id="acme-tf-vpc",
        display_name="tf-vpc",
        repo_url="https://github.com/acme/tf-vpc",
        local_path=local_path,
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
        scorecard=(ScorecardDimension("pins", "Pins", "pass", ""),),
    )


def test_format_cost_badge_prefers_actuals() -> None:
    from repave_engine.cost_actuals import CostActualsSummary

    badge, detail = format_cost_badge(
        actuals=CostActualsSummary(
            currency="USD",
            amount_30d="99.00",
            as_of="2026-08-01T00:00:00Z",
            detail="ok",
            tag_coverage="complete",
            source_url="",
        ),
        estimate=CostEstimate(
            currency="USD",
            monthly_cost="10",
            hourly_cost="—",
            resource_count=0,
            detail="estimate",
        ),
    )
    assert badge == "L30D USD 99.00"
    assert detail == "ok"


def test_format_cost_badge_uses_estimate_when_no_actuals() -> None:
    badge, detail = format_cost_badge(
        actuals=None,
        estimate=CostEstimate(
            currency="USD",
            monthly_cost="42.00",
            hourly_cost="0.06",
            resource_count=2,
            detail="Estimated USD 42.00/month",
        ),
    )
    assert badge == "Est USD 42.00/mo"
    assert "42.00" in detail


def test_enrich_catalog_entities_with_cost_from_local_estimate(tmp_path) -> None:
    from repave_engine.cost_estimate import write_cost_estimate_file
    from repave_engine.settings import PortalConfig

    write_cost_estimate_file(
        tmp_path,
        CostEstimate(
            currency="USD",
            monthly_cost="15.00",
            hourly_cost="—",
            resource_count=1,
            detail="Estimated USD 15.00/month",
        ),
    )
    entity = _entity(local_path=tmp_path)
    enriched = enrich_catalog_entities_with_cost([entity], PortalConfig(density="default"))
    assert enriched[0].cost_badge == "Est USD 15.00/mo"
    assert enriched[0].cost_badge_detail
    cost_dim = next(dim for dim in enriched[0].scorecard if dim.key == "cost")
    assert cost_dim.level == "pass"
    assert "15.00" in cost_dim.detail


def test_enrich_environment_entity_with_cost_url_reader() -> None:
    from repave_engine.cost_actuals import CostActualsSummary
    from repave_engine.entity_catalog import build_catalog_from_environments
    from repave_engine.environment_record import EnvironmentRecord
    from repave_engine.settings import PortalConfig

    record = EnvironmentRecord(
        stack_name="sandbox-alice",
        entity_id="env-aws-sandbox-alice",
        cloud_provider="aws",
        environment_tier="dev",
        owner="platform",
        env_class="sandbox",
        blueprint_name="terraform-environment-stack",
        blueprint_version="0.4.0",
        gitops_repo="https://github.com/acme/gitops",
        gitops_path="environments/sandbox-alice",
        git_branch="main",
        pull_request_url="",
        pull_request_number=0,
        gates_outcome="passed",
        source_entity_id="",
        run_id="run-1",
        vended_by="tester",
        vended_at="2026-08-02T12:00:00+00:00",
        expires_at="2026-08-09T12:00:00+00:00",
        status="active",
    )
    entity = build_catalog_from_environments((record,))[0]
    portal = PortalConfig(
        density="default",
        cost_reader="url",
        cost_actuals_url="https://cost.example/{stack_name}",
    )

    def _fetch(_portal: object, cost_entity: object) -> CostActualsSummary | None:
        assert cost_entity.display_name == "sandbox-alice"
        return CostActualsSummary(
            currency="USD",
            amount_30d="12.50",
            as_of="2026-08-02T00:00:00Z",
            detail="ok",
            tag_coverage="complete",
            source_url="https://cost.example/sandbox-alice",
        )

    import repave_engine.catalog_cost as catalog_cost

    original = catalog_cost.fetch_entity_cost_actuals_for_portal
    catalog_cost.fetch_entity_cost_actuals_for_portal = _fetch
    try:
        enriched = enrich_catalog_entities_with_cost([entity], portal)[0]
    finally:
        catalog_cost.fetch_entity_cost_actuals_for_portal = original

    assert enriched.cost_badge == "L30D USD 12.50"
    cost_dim = next(dim for dim in enriched.scorecard if dim.key == "cost")
    assert cost_dim.level == "pass"
    assert "12.50" in cost_dim.detail
