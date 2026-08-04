"""Library catalog deployment scorecard enrichment."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import TYPE_CHECKING

from repave_engine.deployment_status import (
    DeploymentStatus,
    deployment_reader_configured,
    fetch_entity_deployment_status_for_portal,
)
from repave_engine.entity_catalog import CatalogEntity, apply_deployment_to_scorecard

if TYPE_CHECKING:
    from repave_engine.settings import PortalConfig


def enrich_catalog_entities_with_deployment(
    entities: Sequence[CatalogEntity],
    portal_config: PortalConfig,
) -> tuple[CatalogEntity, ...]:
    """Fetch deployment status (best-effort) and patch scorecards when a reader is configured."""
    configured = deployment_reader_configured(
        deployment_reader=portal_config.deployment_reader,
        deployment_status_url=portal_config.deployment_status_url,
    )
    if not configured:
        return tuple(entities)
    enriched: list[CatalogEntity] = []
    for entity in entities:
        deployment = fetch_entity_deployment_status_for_portal(portal_config, entity)
        scorecard = apply_deployment_to_scorecard(
            entity.scorecard,
            deployment=deployment,
        )
        enriched.append(replace(entity, scorecard=scorecard))
    return tuple(enriched)


def deployment_scorecard_for_entity(
    entity: CatalogEntity,
    portal_config: PortalConfig,
    *,
    deployment: DeploymentStatus | None = None,
) -> tuple[CatalogEntity, DeploymentStatus | None]:
    """Return entity with deployment scorecard dimension and optional status payload."""
    configured = deployment_reader_configured(
        deployment_reader=portal_config.deployment_reader,
        deployment_status_url=portal_config.deployment_status_url,
    )
    if not configured:
        return entity, None
    status = (
        deployment
        if deployment is not None
        else fetch_entity_deployment_status_for_portal(portal_config, entity)
    )
    patched = replace(
        entity,
        scorecard=apply_deployment_to_scorecard(entity.scorecard, deployment=status),
    )
    return patched, status
