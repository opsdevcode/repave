"""Shared portal/catalog helpers used by HTML routes and /api/v1 JSON handlers."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from repave_engine.audit_history import (
    AuditHistoryEntry,
    AuditQueryFilters,
    query_audit_entries,
    read_recent_audit_entries,
)
from repave_engine.entity_catalog import (
    CatalogEntity,
    build_catalog_entities,
    build_catalog_from_fleet,
    fetch_remote_entity_docs,
    read_entity_docs,
)
from repave_engine.fleet import read_fleet
from repave_engine.fleet_operator_status import load_operator_status_file
from repave_engine.fleet_view import build_fleet_rows
from repave_engine.settings import (
    OutputConfig,
    load_audit_config,
    load_fleet_config,
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
            audit_entries = read_recent_audit_entries(audit_cfg.file, limit=100)
    modules_root = output_config.modules_root
    try:
        fleet_cfg = load_fleet_config(repo_root)
    except ValueError:
        fleet_cfg = None
    if fleet_cfg is not None and fleet_cfg.enabled:
        entries = read_fleet(fleet_cfg.file)
        operator_by = (
            load_operator_status_file(fleet_cfg.operator_status_file)
            if fleet_cfg.operator_status_file is not None
            else {}
        )
        return build_catalog_from_fleet(
            entries,
            modules_root=modules_root,
            operator_by_url=operator_by,
            namespace=fleet_cfg.gitops_namespace,
            audit_entries=audit_entries,
            cost_actuals_configured=cost_actuals_configured,
        )
    return build_catalog_entities(
        fleet_rows=[],
        modules_root=modules_root,
        operator_by_url={},
        audit_entries=audit_entries,
        cost_actuals_configured=cost_actuals_configured,
    )


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
