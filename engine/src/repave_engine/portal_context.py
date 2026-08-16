"""Shared portal/catalog helpers used by HTML routes and /api/v1 JSON handlers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException

from repave_engine.audit_history import (
    AuditHistoryEntry,
    AuditQueryFilters,
    query_audit_entries,
    read_recent_audit_entries,
)
from repave_engine.component_registry import read_components
from repave_engine.entity_catalog import (
    CatalogEntity,
    build_catalog_entities,
    build_catalog_from_audit_applies,
    build_catalog_from_components,
    build_catalog_from_environments,
    build_catalog_from_fleet,
    fetch_remote_entity_docs,
    merge_catalog_entities,
    read_entity_docs,
)
from repave_engine.environment_registry import read_environments
from repave_engine.fleet import normalize_repo_url, read_fleet
from repave_engine.fleet_operator_status import FleetOperatorStatus, load_operator_status_file
from repave_engine.fleet_view import build_fleet_rows
from repave_engine.settings import (
    OutputConfig,
    PortalConfig,
    load_audit_config,
    load_component_vending_config,
    load_environment_vending_config,
    load_fleet_config,
    load_service_catalog_config,
)


def audit_portal_enabled(repo_root: Path) -> bool:
    try:
        audit_cfg = load_audit_config(repo_root)
    except ValueError:
        return False
    return audit_cfg is not None and audit_cfg.enabled


def audit_file_or_http404(repo_root: Path) -> Path:
    try:
        audit_cfg = load_audit_config(repo_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if audit_cfg is None or not audit_cfg.enabled:
        raise HTTPException(
            status_code=404,
            detail="Audit log is not configured (set audit.enabled in repave.config.yaml)",
        )
    return audit_cfg.file


def fleet_registry_path_or_http404(repo_root: Path) -> Path:
    try:
        fleet_cfg = load_fleet_config(repo_root)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if fleet_cfg is None or not fleet_cfg.enabled:
        raise HTTPException(
            status_code=404,
            detail="Fleet registry is not configured (set fleet.file or REPAVE_FLEET_FILE)",
        )
    return fleet_cfg.file


def portal_recent_activity(
    repo_root: Path,
    *,
    limit: int = 8,
    filters: AuditQueryFilters | None = None,
) -> tuple[AuditHistoryEntry, ...]:
    try:
        audit_cfg = load_audit_config(repo_root)
    except ValueError:
        return ()
    if audit_cfg is None or not audit_cfg.enabled:
        return ()
    if filters is None:
        return read_recent_audit_entries(audit_cfg.file, limit=limit, repo_root=repo_root)
    merged = AuditQueryFilters(
        blueprint_name=filters.blueprint_name,
        module_name=filters.module_name,
        repository_url=filters.repository_url,
        acting_user=filters.acting_user,
        gates_outcome=filters.gates_outcome,
        since=filters.since,
        until=filters.until,
        limit=limit,
        offset=filters.offset,
    )
    return query_audit_entries(
        audit_cfg.file,
        merged,
        repo_root=repo_root,
    ).entries


def portal_fleet_context(
    repo_root: Path,
) -> tuple[bool, list[dict[str, object]], str]:
    try:
        fleet_cfg = load_fleet_config(repo_root)
    except ValueError:
        return False, [], "default"
    if fleet_cfg is None or not fleet_cfg.enabled:
        return False, [], "default"
    entries = read_fleet(fleet_cfg.file, repo_root=repo_root)
    operator_by = (
        load_operator_status_file(fleet_cfg.operator_status_file)
        if fleet_cfg.operator_status_file is not None
        else {}
    )
    rows = build_fleet_rows(
        entries,
        operator_by_url=operator_by,
        namespace=fleet_cfg.gitops_namespace,
    )
    return True, rows, fleet_cfg.gitops_namespace


def build_portal_catalog_entities(
    repo_root: Path,
    output_config: OutputConfig,
    *,
    cost_actuals_configured: bool = False,
) -> list[CatalogEntity]:
    audit_entries: tuple[AuditHistoryEntry, ...] = ()
    if audit_portal_enabled(repo_root):
        try:
            audit_cfg = load_audit_config(repo_root)
        except ValueError:
            audit_cfg = None
        if audit_cfg is not None:
            audit_entries = read_recent_audit_entries(
                audit_cfg.file,
                limit=250,
                repo_root=repo_root,
            )
    modules_root = output_config.modules_root
    try:
        fleet_cfg = load_fleet_config(repo_root)
    except ValueError:
        fleet_cfg = None
    operator_by_url: dict[str, FleetOperatorStatus] = {}
    if fleet_cfg is not None and fleet_cfg.enabled:
        entries = read_fleet(fleet_cfg.file)
        operator_by_url = (
            load_operator_status_file(fleet_cfg.operator_status_file)
            if fleet_cfg.operator_status_file is not None
            else {}
        )
        entities = build_catalog_from_fleet(
            entries,
            modules_root=modules_root,
            operator_by_url=operator_by_url,
            namespace=fleet_cfg.gitops_namespace,
            audit_entries=audit_entries,
            cost_actuals_configured=cost_actuals_configured,
        )
    else:
        entities = build_catalog_entities(
            fleet_rows=[],
            modules_root=modules_root,
            operator_by_url={},
            audit_entries=audit_entries,
            cost_actuals_configured=cost_actuals_configured,
        )
    known_urls = {normalize_repo_url(entity.repo_url) for entity in entities if entity.repo_url}
    audit_entities = build_catalog_from_audit_applies(
        audit_entries,
        known_urls=known_urls,
        modules_root=modules_root,
        operator_by_url=operator_by_url,
        cost_actuals_configured=cost_actuals_configured,
    )
    if audit_entities:
        entities = merge_catalog_entities(entities, audit_entities)
    try:
        vend_cfg = load_environment_vending_config(repo_root)
    except ValueError:
        vend_cfg = None
    if vend_cfg is not None:
        env_records = read_environments(vend_cfg.file)
        if env_records:
            env_entities = build_catalog_from_environments(
                env_records,
                cost_actuals_configured=cost_actuals_configured,
            )
            entities = merge_catalog_entities(entities, env_entities)
    try:
        cmp_cfg = load_component_vending_config(repo_root)
    except ValueError:
        cmp_cfg = None
    if cmp_cfg is not None:
        cmp_records = read_components(cmp_cfg.file)
        if cmp_records:
            entities = merge_catalog_entities(entities, build_catalog_from_components(cmp_records))
    return sorted(entities, key=lambda item: item.display_name.lower())


def build_enriched_portal_catalog_entities(
    repo_root: Path,
    output_config: OutputConfig,
    portal_config: PortalConfig,
    *,
    cost_actuals_configured: bool = False,
) -> list[CatalogEntity]:
    """Catalog entities with cost, deployment, and optional service-catalog overlay."""
    from repave_engine.catalog_cost import enrich_catalog_entities_with_cost
    from repave_engine.catalog_deployment import enrich_catalog_entities_with_deployment
    from repave_engine.service_catalog_overlay import enrich_catalog_entities_with_overlay

    entities = build_portal_catalog_entities(
        repo_root,
        output_config,
        cost_actuals_configured=cost_actuals_configured,
    )
    entities = list(enrich_catalog_entities_with_cost(entities, portal_config, repo_root=repo_root))
    entities = list(enrich_catalog_entities_with_deployment(entities, portal_config))
    try:
        catalog_cfg = load_service_catalog_config(repo_root)
    except ValueError:
        catalog_cfg = None
    return enrich_catalog_entities_with_overlay(entities, catalog_cfg)


def build_library_catalog_payload(
    repo_root: Path,
    output_config: OutputConfig,
    portal_config: PortalConfig,
    *,
    owner: str = "",
    family: str = "",
) -> dict[str, Any]:
    """Grouped library catalog for GET /api/v2/library (HTML /library uses the same groups)."""
    from repave_engine.blueprint import list_catalog_blueprints
    from repave_engine.cost_actuals import cost_reader_configured
    from repave_engine.entity_catalog import (
        EntityLibraryGroup,
        filter_entities_by_owner,
        group_catalog_entities,
        library_family_copy,
        library_family_known,
        rollup_fleet_scorecard,
    )

    owner = owner.strip()
    family = family.strip()
    cost_configured = cost_reader_configured(
        cost_reader=portal_config.cost_reader,
        cost_actuals_url=portal_config.cost_actuals_url,
        cost_focus_file=portal_config.cost_focus.file,
    )
    entities = build_enriched_portal_catalog_entities(
        repo_root,
        output_config,
        portal_config,
        cost_actuals_configured=cost_configured,
    )
    if owner:
        entities = filter_entities_by_owner(entities, owner)
    blueprint_types = {
        blueprint.name: blueprint.artifact_type for blueprint in list_catalog_blueprints(repo_root)
    }
    groups = group_catalog_entities(entities, blueprint_artifact_types=blueprint_types)
    if family:
        if not library_family_known(family):
            raise ValueError(
                f"unknown library family {family!r}; omit family or use a known family"
            )
        match = next((item for item in groups if item.family == family), None)
        if match is None:
            title, subtitle = library_family_copy(family)
            match = EntityLibraryGroup(
                family=family,
                title=title,
                subtitle=subtitle,
                entities=(),
            )
        scoped = list(match.entities)
        groups = [match]
    else:
        scoped = list(entities)
    return {
        "entity_count": len(scoped),
        "owner": owner,
        "family": family or None,
        "groups": [item.to_public_dict() for item in groups],
        "scorecard": rollup_fleet_scorecard(scoped).to_public_dict(),
    }


def resolve_entity_docs(entity: CatalogEntity, *, github_token: str | None) -> dict[str, str]:
    if entity.local_path is not None:
        return read_entity_docs(entity.local_path)
    if entity.repo_url and github_token:
        remote = fetch_remote_entity_docs(entity.repo_url, github_token)
        if remote:
            return remote
    if entity.readme_preview:
        return {"readme": entity.readme_preview}
    return {}
