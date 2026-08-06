"""Read-models and helpers for admin platform console pages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repave_engine.auth import ROLE_ADMIN, AuthConfig, AuthUser, require_role
from repave_engine.blueprint import Blueprint, blueprints_dir, list_blueprints
from repave_engine.doctor import ToolCheckResult, run_doctor
from repave_engine.environment_reclaim import (
    EnvironmentReclaimSummary,
    reclaim_expired_environments,
)
from repave_engine.environment_registry import read_environments
from repave_engine.fleet import (
    FleetEntry,
    FleetError,
    pins_from_repave_file,
    register_repo,
    unregister_repo,
)
from repave_engine.fleet_drift import BlueprintDriftSummary, estimate_fleet_drift
from repave_engine.fleet_operator_status import (
    OperatorStatusSnapshot,
    UpgradeCampaignStatus,
    load_operator_status_snapshot,
)
from repave_engine.portal_context import fleet_registry_path_or_http404, portal_fleet_context
from repave_engine.readiness import ReadinessReport, evaluate_readiness
from repave_engine.run_queue import RunQueue
from repave_engine.run_store import RunRecord, RunStatus
from repave_engine.settings import (
    FleetConfig,
    load_environment_vending_config,
    load_fleet_config,
)


def platform_admin_visible(
    auth_config: AuthConfig | None,
    auth_user: AuthUser | None,
) -> bool:
    if auth_config is None or not auth_config.service_enabled:
        return True
    return auth_user is not None and auth_user.role == ROLE_ADMIN


def require_platform_admin(user: AuthUser | None, auth_config: AuthConfig | None) -> None:
    if auth_config is None or not auth_config.service_enabled:
        return
    require_role(user, ROLE_ADMIN)


@dataclass(frozen=True)
class PlatformFleetPage:
    fleet_enabled: bool
    fleet_repos: list[dict[str, Any]]
    gitops_namespace: str
    operator_status_enabled: bool
    blueprints: tuple[Blueprint, ...]


def build_platform_fleet_page(repo_root: Path) -> PlatformFleetPage:
    enabled, rows, namespace = portal_fleet_context(repo_root)
    fleet_cfg = load_fleet_config(repo_root)
    operator_enabled = bool(
        fleet_cfg is not None
        and fleet_cfg.enabled
        and fleet_cfg.operator_status_file is not None
        and fleet_cfg.operator_status_file.is_file()
    )
    return PlatformFleetPage(
        fleet_enabled=enabled,
        fleet_repos=rows,
        gitops_namespace=namespace,
        operator_status_enabled=operator_enabled,
        blueprints=tuple(list_blueprints(blueprints_dir(repo_root))),
    )


def register_fleet_entry_from_form(
    repo_root: Path,
    *,
    repo_url: str,
    blueprint_name: str,
    blueprint_version: str,
    standard_source: str,
    standard_version: str,
    owner: str,
    local_path: str,
    acting_user: str,
) -> FleetEntry:
    pins: dict[str, str] = {
        "blueprint_name": blueprint_name.strip(),
        "blueprint_version": blueprint_version.strip(),
        "standard_source": standard_source.strip(),
        "standard_version": standard_version.strip(),
    }
    if local_path.strip():
        pins.update(pins_from_repave_file(Path(local_path).expanduser().resolve()))
    if not pins["blueprint_name"]:
        raise FleetError("blueprint name is required when local path is not supplied")
    return register_repo(
        fleet_registry_path_or_http404(repo_root),
        FleetEntry(
            repo_url=repo_url.strip(),
            blueprint_name=pins["blueprint_name"],
            blueprint_version=pins["blueprint_version"],
            standard_source=pins["standard_source"],
            standard_version=pins["standard_version"],
            owner=owner.strip(),
            registered_by=acting_user,
        ),
        repo_root=repo_root,
    )


def unregister_fleet_entry(repo_root: Path, repo_url: str) -> bool:
    return unregister_repo(
        fleet_registry_path_or_http404(repo_root),
        repo_url,
        repo_root=repo_root,
    )


@dataclass(frozen=True)
class PlatformOpsPage:
    doctor_results: tuple[ToolCheckResult, ...]
    queue_depth: int | None
    dead_letter_runs: tuple[RunRecord, ...]
    queued_runs: int
    running_runs: int
    environment_count: int
    reclaim_preview: EnvironmentReclaimSummary | None
    environment_vending_enabled: bool
    readiness: ReadinessReport
    readiness_payload: dict[str, Any]


def build_platform_ops_page(
    repo_root: Path,
    *,
    run_queue: RunQueue | None,
    modules_root: Path,
    runs_db: Path | None,
    shutting_down: bool,
    auth_service_enabled: bool,
    require_session_secret: bool,
    github_token_configured: bool,
    github_probe_token: str | None,
    sql_session_store_ok: bool | None,
) -> PlatformOpsPage:
    doctor_results = run_doctor(all_pins=False)
    dead_letter: tuple[RunRecord, ...] = ()
    queue_depth: int | None = None
    queued = 0
    running = 0
    if run_queue is not None:
        queue_depth = run_queue.queue_depth()
        dead_letter = tuple(run_queue.list_runs(status=RunStatus.DEAD_LETTER, limit=50))
        queued = len(run_queue.list_runs(status=RunStatus.QUEUED, limit=200))
        running = len(run_queue.list_runs(status=RunStatus.RUNNING, limit=200))

    vend_cfg = load_environment_vending_config(repo_root)
    env_count = 0
    reclaim_preview: EnvironmentReclaimSummary | None = None
    if vend_cfg is not None:
        env_count = len(read_environments(vend_cfg.file))
        reclaim_preview = reclaim_expired_environments(
            repo_root=repo_root,
            config=vend_cfg,
            github_token=None,
            dry_run=True,
        )

    readiness = evaluate_readiness(
        modules_root=modules_root,
        runs_db=runs_db,
        shutting_down=shutting_down,
        auth_service_enabled=auth_service_enabled,
        require_session_secret=require_session_secret,
        github_token_configured=github_token_configured,
        github_probe_token=github_probe_token,
        run_queue_depth=queue_depth,
        sql_session_store_ok=sql_session_store_ok,
    )
    return PlatformOpsPage(
        doctor_results=doctor_results,
        queue_depth=queue_depth,
        dead_letter_runs=dead_letter,
        queued_runs=queued,
        running_runs=running,
        environment_count=env_count,
        reclaim_preview=reclaim_preview,
        environment_vending_enabled=vend_cfg is not None,
        readiness=readiness,
        readiness_payload=readiness.to_payload(),
    )


@dataclass(frozen=True)
class PlatformStandardsPage:
    summaries: tuple[BlueprintDriftSummary, ...]
    fleet_enabled: bool


def build_platform_standards_page(repo_root: Path) -> PlatformStandardsPage:
    enabled, _, _ = portal_fleet_context(repo_root)
    if not enabled:
        return PlatformStandardsPage(summaries=(), fleet_enabled=False)
    try:
        fleet_cfg = load_fleet_config(repo_root)
    except ValueError:
        return PlatformStandardsPage(summaries=(), fleet_enabled=False)
    if fleet_cfg is None or not fleet_cfg.enabled:
        return PlatformStandardsPage(summaries=(), fleet_enabled=False)
    from repave_engine.fleet import read_fleet

    entries = read_fleet(fleet_cfg.file, repo_root=repo_root)
    blueprints = list_blueprints(blueprints_dir(repo_root))
    summaries = estimate_fleet_drift(entries, blueprints)
    return PlatformStandardsPage(summaries=summaries, fleet_enabled=True)


def build_platform_standards_detail(
    repo_root: Path,
    blueprint_name: str,
) -> BlueprintDriftSummary | None:
    page = build_platform_standards_page(repo_root)
    for summary in page.summaries:
        if summary.blueprint_name == blueprint_name:
            return summary
    return None


@dataclass(frozen=True)
class PlatformCampaignsPage:
    snapshot: OperatorStatusSnapshot | None
    fleet_cfg: FleetConfig | None
    remediation_queue: tuple[dict[str, str], ...]


def build_platform_campaigns_page(repo_root: Path) -> PlatformCampaignsPage:
    try:
        fleet_cfg = load_fleet_config(repo_root)
    except ValueError:
        fleet_cfg = None
    snapshot: OperatorStatusSnapshot | None = None
    if fleet_cfg is not None and fleet_cfg.operator_status_file is not None:
        snapshot = load_operator_status_snapshot(fleet_cfg.operator_status_file)
    remediation: list[dict[str, str]] = []
    if snapshot is not None:
        for row in snapshot.repos:
            if row.remediation_pr_url:
                remediation.append(
                    {
                        "repo_url": row.repo_url,
                        "phase": row.phase,
                        "remediation_pr_url": row.remediation_pr_url,
                        "resource_name": row.resource_name,
                        "namespace": row.namespace,
                    }
                )
    return PlatformCampaignsPage(
        snapshot=snapshot,
        fleet_cfg=fleet_cfg,
        remediation_queue=tuple(remediation),
    )


def find_campaign_in_snapshot(
    snapshot: OperatorStatusSnapshot | None,
    *,
    namespace: str,
    name: str,
) -> UpgradeCampaignStatus | None:
    if snapshot is None:
        return None
    target_ns = namespace.strip() or "default"
    target_name = name.strip()
    for campaign in snapshot.campaigns:
        row_ns = campaign.namespace.strip() or "default"
        if campaign.name == target_name and row_ns == target_ns:
            return campaign
    return None


@dataclass(frozen=True)
class AdoptionTrendPoint:
    captured_at: str
    adoption_ratio: float | None
    plan_apply_ratio: float | None
    spark_value: int  # 0 fail-ish, 1 pass-ish, 2 empty


@dataclass(frozen=True)
class PlatformAdoptionPage:
    metrics_enabled: bool
    snapshot: object | None
    history: tuple[AdoptionTrendPoint, ...]
    bypass_preview: tuple[str, ...]


def build_platform_adoption_page(
    repo_root: Path,
    *,
    github_token: str | None = None,
    persist: bool = False,
) -> PlatformAdoptionPage:
    from repave_engine.dx_metrics_store import capture_dx_metrics, read_dx_metrics_snapshots
    from repave_engine.settings import load_platform_metrics_config

    metrics_cfg = load_platform_metrics_config(repo_root)
    if metrics_cfg is None:
        return PlatformAdoptionPage(
            metrics_enabled=False,
            snapshot=None,
            history=(),
            bypass_preview=(),
        )
    snapshot = capture_dx_metrics(
        repo_root,
        github_token=github_token,
        persist=persist,
    )
    history_snaps = read_dx_metrics_snapshots(
        metrics_cfg.snapshot_file,
        repo_root=repo_root,
        limit=12,
    )
    # oldest → newest for sparkline left-to-right
    chronological = tuple(reversed(history_snaps))
    history = tuple(
        AdoptionTrendPoint(
            captured_at=item.captured_at,
            adoption_ratio=item.adoption_ratio,
            plan_apply_ratio=item.plan_apply_ratio,
            spark_value=_adoption_spark_value(
                item.adoption_ratio,
                baseline=item.baseline_adoption_ratio,
            ),
        )
        for item in chronological
    )
    return PlatformAdoptionPage(
        metrics_enabled=True,
        snapshot=snapshot,
        history=history,
        bypass_preview=snapshot.bypass_repos[:25],
    )


def _adoption_spark_value(
    ratio: float | None,
    *,
    baseline: float | None,
) -> int:
    if ratio is None:
        return 2
    threshold = baseline if baseline is not None else 0.5
    return 1 if ratio >= threshold else 0
