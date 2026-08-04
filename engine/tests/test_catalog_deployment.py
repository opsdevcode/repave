from __future__ import annotations

import pytest

from repave_engine.catalog_deployment import enrich_catalog_entities_with_deployment
from repave_engine.deployment_status import DeploymentStatus
from repave_engine.entity_catalog import (
    CatalogEntity,
    ScorecardDimension,
    apply_deployment_to_scorecard,
)
from repave_engine.settings import PortalConfig


def _entity() -> CatalogEntity:
    return CatalogEntity(
        entity_id="acme-svc",
        display_name="acme-svc",
        repo_url="https://github.com/acme/acme-svc",
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


def test_apply_deployment_scorecard_synced_healthy() -> None:
    dims = apply_deployment_to_scorecard(
        (),
        deployment=DeploymentStatus(
            sync_status="synced",
            health="healthy",
            revision="abc123456789",
            last_synced="2026-08-01T12:00:00Z",
            detail="Synced",
            deep_link="https://argocd.example/applications/acme-svc",
            source="url",
        ),
    )
    deployment = dims[0]
    assert deployment.key == "deployment"
    assert deployment.level == "pass"
    assert "rev abc123456789" in deployment.detail


def test_apply_deployment_scorecard_out_of_sync_warns() -> None:
    dims = apply_deployment_to_scorecard(
        (),
        deployment=DeploymentStatus(
            sync_status="out_of_sync",
            health="healthy",
            revision="",
            last_synced="",
            detail="Manifest drift",
            deep_link="",
            source="argocd",
        ),
    )
    assert dims[0].level == "warn"


def test_apply_deployment_scorecard_degraded_fails() -> None:
    dims = apply_deployment_to_scorecard(
        (),
        deployment=DeploymentStatus(
            sync_status="synced",
            health="degraded",
            revision="",
            last_synced="",
            detail="CrashLoopBackOff",
            deep_link="",
            source="flux",
        ),
    )
    assert dims[0].level == "fail"


def test_enrich_catalog_entities_skips_when_reader_not_configured() -> None:
    entity = _entity()
    enriched = enrich_catalog_entities_with_deployment((entity,), PortalConfig(density="default"))
    assert enriched[0].scorecard == entity.scorecard


def test_enrich_catalog_entities_adds_deployment_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entity = _entity()
    portal = PortalConfig(
        density="default",
        deployment_reader="url",
        deployment_status_url="https://x/{name}",
    )

    def _fake_fetch(_portal: object, _entity: object) -> DeploymentStatus:
        return DeploymentStatus(
            sync_status="synced",
            health="healthy",
            revision="deadbeef",
            last_synced="2026-08-01T12:00:00Z",
            detail="ok",
            deep_link="",
            source="url",
        )

    monkeypatch.setattr(
        "repave_engine.catalog_deployment.fetch_entity_deployment_status_for_portal",
        _fake_fetch,
    )
    enriched = enrich_catalog_entities_with_deployment((entity,), portal)
    deployment = next(dim for dim in enriched[0].scorecard if dim.key == "deployment")
    assert deployment.level == "pass"
