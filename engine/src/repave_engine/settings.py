from __future__ import annotations

import logging
import os
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from repave_engine.auth import AuthConfig

logger = logging.getLogger(__name__)

CONFIG_API_VERSION = "repave.dev/v1"
SUPPORTED_CONFIG_API_VERSIONS = frozenset({CONFIG_API_VERSION})
_ACCENT_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def normalize_portal_logo_url(raw: str) -> str:
    """Accept same-origin paths or http(s) URLs for white-label logos."""
    value = raw.strip()
    if not value:
        return ""
    lower = value.lower()
    if lower.startswith(("javascript:", "data:", "vbscript:")):
        raise ValueError(
            "portal.logo_url must be an http(s) URL or a root-relative path "
            "(for example /static/brand/custom.svg)"
        )
    if value.startswith("/"):
        return value
    if lower.startswith("https://") or lower.startswith("http://"):
        return value
    raise ValueError(
        "portal.logo_url must be an http(s) URL or a root-relative path "
        "(for example /static/brand/custom.svg)"
    )


def normalize_portal_accent_color(raw: str) -> str:
    """Accept #RGB or #RRGGBB brand accent overrides."""
    value = raw.strip()
    if not value:
        return ""
    if not _ACCENT_HEX_RE.fullmatch(value):
        raise ValueError(
            "portal.accent_color must be a hex color like #F59E0B or #F90 "
            "(set portal.accent_color or REPAVE_PORTAL_ACCENT_COLOR)"
        )
    return value.lower() if len(value) == 4 else f"#{value[1:].lower()}"


@dataclass(frozen=True)
class InfracostGatePolicy:
    """Org floor for FinOps estimate policy (v1.91)."""

    required: bool = False
    max_monthly_usd: float | None = None


@dataclass(frozen=True)
class GateOverrides:
    checkov_skip_checks: tuple[str, ...] = ()
    blocked_policy_rule_skips: tuple[str, ...] = ()
    infracost: InfracostGatePolicy = field(default_factory=InfracostGatePolicy)


@dataclass(frozen=True)
class OutputConfig:
    github_org: str
    modules_root: Path
    repo_name_template: str = "tf-{module_name}"


@dataclass(frozen=True)
class NotificationsConfig:
    enabled: bool
    slack_webhook_url: str | None
    teams_webhook_url: str | None
    webhook_url: str | None
    events: frozenset[str]

    def webhook_urls(self) -> tuple[str, ...]:
        urls: list[str] = []
        for candidate in (self.slack_webhook_url, self.teams_webhook_url, self.webhook_url):
            if candidate:
                urls.append(candidate)
        return tuple(urls)


def load_output_config(
    repo_root: Path,
    *,
    github_org: str | None = None,
    modules_root: Path | str | None = None,
    repo_name_template: str | None = None,
) -> OutputConfig:
    file_data = _load_config_file(repo_root / "repave.config.yaml")
    output = file_data.get("output", {}) if isinstance(file_data, dict) else {}

    resolved_org = (
        github_org or os.environ.get("REPAVE_GITHUB_ORG") or output.get("github_org") or ""
    )
    modules_root_value = (
        modules_root or os.environ.get("REPAVE_MODULES_ROOT") or output.get("modules_root") or ""
    )
    resolved_template = repo_name_template or output.get("repo_name_template") or "tf-{module_name}"

    if not resolved_org:
        raise ValueError(
            "GitHub organization is required. Set output.github_org in repave.config.yaml "
            "or REPAVE_GITHUB_ORG."
        )
    if not modules_root_value:
        raise ValueError(
            "Module output root is required. Set output.modules_root in repave.config.yaml "
            "or REPAVE_MODULES_ROOT to a directory outside the repave repo."
        )

    root_path = Path(modules_root_value).expanduser()
    if not root_path.is_absolute():
        root_path = (repo_root / root_path).resolve()

    return OutputConfig(
        github_org=str(resolved_org),
        modules_root=root_path,
        repo_name_template=str(resolved_template),
    )


_DEFAULT_NOTIFY_EVENTS = frozenset({"publish_complete", "generation_failed"})


@dataclass(frozen=True)
class AuditConfig:
    enabled: bool
    file: Path


def load_audit_config(repo_root: Path) -> AuditConfig | None:
    file_data = _load_config_file(repo_root / "repave.config.yaml")
    block = file_data.get("audit")
    if block is None:
        env_path = os.environ.get("REPAVE_AUDIT_FILE", "").strip()
        if not env_path:
            return None
        path = Path(env_path).expanduser()
        if not path.is_absolute():
            path = (repo_root / path).resolve()
        return AuditConfig(enabled=True, file=path)

    if not isinstance(block, dict):
        raise ValueError("audit must be a mapping in repave.config.yaml")

    enabled_raw = block.get("enabled", True)
    if not isinstance(enabled_raw, bool):
        raise ValueError("audit.enabled must be a boolean")

    file_value = block.get("file", "audit/generation.jsonl")
    path = Path(str(file_value)).expanduser()
    if not path.is_absolute():
        path = (repo_root / path).resolve()

    env_override = os.environ.get("REPAVE_AUDIT_FILE", "").strip()
    if env_override:
        path = Path(env_override).expanduser()
        if not path.is_absolute():
            path = (repo_root / path).resolve()

    if not enabled_raw:
        return AuditConfig(enabled=False, file=path)
    return AuditConfig(enabled=True, file=path)


@dataclass(frozen=True)
class TracingConfig:
    enabled: bool
    otlp_endpoint: str
    service_name: str


def load_tracing_config(repo_root: Path) -> TracingConfig | None:
    """Resolve OpenTelemetry OTLP export from config and standard OTEL env vars."""
    file_data = _load_config_file(repo_root / "repave.config.yaml")
    block = file_data.get("tracing") if isinstance(file_data, dict) else None

    env_endpoint = (
        os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "").strip()
        or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
        or os.environ.get("REPAVE_OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    )
    env_service = os.environ.get("OTEL_SERVICE_NAME", "").strip() or os.environ.get(
        "REPAVE_OTEL_SERVICE_NAME", "repave-engine"
    )

    enabled = bool(env_endpoint)
    endpoint = env_endpoint
    service_name = env_service or "repave-engine"

    if isinstance(block, dict):
        block_enabled = block.get("enabled", True)
        if not isinstance(block_enabled, bool):
            raise ValueError("tracing.enabled must be a boolean")
        if block.get("otlp_endpoint") is not None:
            endpoint = str(block["otlp_endpoint"]).strip()
        if block.get("service_name") is not None:
            service_name = str(block["service_name"]).strip() or service_name
        if env_endpoint:
            enabled = True
        elif endpoint:
            enabled = block_enabled
        else:
            enabled = False

    if not enabled or not endpoint:
        return None
    return TracingConfig(enabled=True, otlp_endpoint=endpoint, service_name=service_name)


@dataclass(frozen=True)
class FleetConfig:
    enabled: bool
    file: Path
    operator_status_file: Path | None = None
    gitops_namespace: str = "default"


@dataclass(frozen=True)
class PlatformMetricsConfig:
    """Outcome metrics for golden-path adoption (platform-as-a-product)."""

    enabled: bool
    snapshot_file: Path
    feedback_file: Path
    github_orgs: tuple[str, ...] = ()
    github_topics: tuple[str, ...] = ()
    search_limit: int = 100
    baseline_adoption_ratio: float | None = None
    baseline_plan_apply_ratio: float | None = None


def load_platform_metrics_config(repo_root: Path) -> PlatformMetricsConfig | None:
    """Resolve platform_metrics from repave.config.yaml and env overrides."""
    env_flag = os.environ.get("REPAVE_PLATFORM_METRICS", "").strip().lower()
    if env_flag in {"0", "false", "no", "off"}:
        return None

    file_data = _load_config_file(repo_root / "repave.config.yaml")
    block = file_data.get("platform_metrics")
    env_enabled = env_flag in {
        "1",
        "true",
        "yes",
        "on",
    }
    env_file = os.environ.get("REPAVE_PLATFORM_METRICS_FILE", "").strip()
    env_feedback_file = os.environ.get("REPAVE_PLATFORM_FEEDBACK_FILE", "").strip()

    def _resolve(value: str) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = (repo_root / path).resolve()
        return path

    if block is None:
        if not env_enabled and not env_file:
            return None
        return PlatformMetricsConfig(
            enabled=True,
            snapshot_file=_resolve(env_file or "data/platform-metrics/snapshots.jsonl"),
            feedback_file=_resolve(env_feedback_file or "data/platform-metrics/feedback.jsonl"),
        )

    if not isinstance(block, dict):
        raise ValueError("platform_metrics must be a mapping in repave.config.yaml")

    enabled_raw = block.get("enabled", True)
    if not isinstance(enabled_raw, bool):
        raise ValueError("platform_metrics.enabled must be a boolean")
    enabled = enabled_raw or env_enabled

    path = _resolve(str(block.get("snapshot_file", "data/platform-metrics/snapshots.jsonl")))
    if env_file:
        path = _resolve(env_file)

    feedback_path = _resolve(
        str(block.get("feedback_file", "data/platform-metrics/feedback.jsonl"))
    )
    if env_feedback_file:
        feedback_path = _resolve(env_feedback_file)

    orgs_raw = block.get("github_orgs", [])
    topics_raw = block.get("github_topics", [])
    if orgs_raw is None:
        orgs_raw = []
    if topics_raw is None:
        topics_raw = []
    if not isinstance(orgs_raw, list) or not all(isinstance(item, str) for item in orgs_raw):
        raise ValueError("platform_metrics.github_orgs must be a list of strings")
    if not isinstance(topics_raw, list) or not all(isinstance(item, str) for item in topics_raw):
        raise ValueError("platform_metrics.github_topics must be a list of strings")

    limit_raw = block.get("search_limit", 100)
    try:
        search_limit = int(limit_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("platform_metrics.search_limit must be an integer") from exc
    search_limit = max(1, min(search_limit, 1000))

    def _optional_ratio(key: str) -> float | None:
        raw = block.get(key)
        if raw is None:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"platform_metrics.{key} must be a number") from exc
        if value < 0.0 or value > 1.0:
            raise ValueError(f"platform_metrics.{key} must be between 0 and 1")
        return value

    if not enabled:
        return None
    return PlatformMetricsConfig(
        enabled=True,
        snapshot_file=path,
        feedback_file=feedback_path,
        github_orgs=tuple(item.strip() for item in orgs_raw if item.strip()),
        github_topics=tuple(item.strip() for item in topics_raw if item.strip()),
        search_limit=search_limit,
        baseline_adoption_ratio=_optional_ratio("baseline_adoption_ratio"),
        baseline_plan_apply_ratio=_optional_ratio("baseline_plan_apply_ratio"),
    )


def load_fleet_config(repo_root: Path) -> FleetConfig | None:
    """Resolve the fleet registry sink, mirroring load_audit_config."""
    file_data = _load_config_file(repo_root / "repave.config.yaml")
    block = file_data.get("fleet")
    env_override = os.environ.get("REPAVE_FLEET_FILE", "").strip()

    def _resolve(value: str) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = (repo_root / path).resolve()
        return path

    if block is None:
        if not env_override:
            return None
        status_env = os.environ.get("REPAVE_FLEET_OPERATOR_STATUS_FILE", "").strip()
        status_path = _resolve(status_env) if status_env else None
        return FleetConfig(
            enabled=True,
            file=_resolve(env_override),
            operator_status_file=status_path,
        )

    if not isinstance(block, dict):
        raise ValueError("fleet must be a mapping in repave.config.yaml")

    enabled_raw = block.get("enabled", True)
    if not isinstance(enabled_raw, bool):
        raise ValueError("fleet.enabled must be a boolean")

    path = _resolve(str(block.get("file", "fleet/registry.jsonl")))
    if env_override:
        path = _resolve(env_override)

    status_env = os.environ.get("REPAVE_FLEET_OPERATOR_STATUS_FILE", "").strip()
    operator_status_path: Path | None = None
    status_raw = block.get("operator_status_file")
    if status_env:
        operator_status_path = _resolve(status_env)
    elif isinstance(status_raw, str) and status_raw.strip():
        operator_status_path = _resolve(status_raw.strip())

    namespace_raw = block.get("gitops_namespace", "default")
    gitops_namespace = str(namespace_raw).strip() or "default"

    return FleetConfig(
        enabled=enabled_raw,
        file=path,
        operator_status_file=operator_status_path,
        gitops_namespace=gitops_namespace,
    )


@dataclass(frozen=True)
class LivePlanEnvironment:
    """Per-entity live-plan target and optional Job credential secret."""

    target: str
    secret_name: str = ""
    policies_dir: str = "policy/opa/policies"
    use_backend: bool = True


@dataclass(frozen=True)
class LivePlanConfig:
    enabled: bool
    environments: dict[str, LivePlanEnvironment] = field(default_factory=dict)
    policies_dir: str = "policy/opa/policies"

    def environment_for(self, entity_id: str) -> LivePlanEnvironment | None:
        key = entity_id.strip()
        if key in self.environments:
            return self.environments[key]
        return self.environments.get("*")


def load_live_plan_config(repo_root: Path) -> LivePlanConfig | None:
    """Optional ADR 003 Phase 2 live terraform plan configuration."""
    file_data = _load_config_file(repo_root / "repave.config.yaml")
    block = file_data.get("live_plan")
    env_enabled = os.environ.get("REPAVE_LIVE_PLAN", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if block is None and not env_enabled:
        return None
    if block is not None and not isinstance(block, dict):
        raise ValueError("live_plan must be a mapping in repave.config.yaml")
    enabled = env_enabled
    policies_dir = "policy/opa/policies"
    environments: dict[str, LivePlanEnvironment] = {}
    if isinstance(block, dict):
        enabled_raw = block.get("enabled", True)
        if not isinstance(enabled_raw, bool):
            raise ValueError("live_plan.enabled must be a boolean")
        enabled = enabled_raw or env_enabled
        policies_dir = str(block.get("policies_dir", policies_dir)).strip() or policies_dir
        env_block = block.get("environments", {})
        if env_block is not None and not isinstance(env_block, dict):
            raise ValueError("live_plan.environments must be a mapping")
        if isinstance(env_block, dict):
            for raw_id, raw_cfg in env_block.items():
                entity_id = str(raw_id).strip()
                if not entity_id:
                    continue
                if isinstance(raw_cfg, str):
                    environments[entity_id] = LivePlanEnvironment(target=raw_cfg.strip())
                    continue
                if not isinstance(raw_cfg, dict):
                    raise ValueError(
                        f"live_plan.environments.{entity_id} must be a string target or mapping"
                    )
                target = str(raw_cfg.get("target", "")).strip()
                if not target:
                    raise ValueError(f"live_plan.environments.{entity_id}.target is required")
                use_backend_raw = raw_cfg.get("use_backend", True)
                if not isinstance(use_backend_raw, bool):
                    raise ValueError(
                        f"live_plan.environments.{entity_id}.use_backend must be a boolean"
                    )
                environments[entity_id] = LivePlanEnvironment(
                    target=target,
                    secret_name=str(raw_cfg.get("secret_name", "")).strip(),
                    policies_dir=str(raw_cfg.get("policies_dir", policies_dir)).strip()
                    or policies_dir,
                    use_backend=use_backend_raw,
                )
    if not enabled:
        return None
    return LivePlanConfig(enabled=True, environments=environments, policies_dir=policies_dir)


@dataclass(frozen=True)
class EnvironmentVendingConfig:
    enabled: bool
    gitops_repo: str = ""
    base_branch: str = "main"
    path_prefix: str = "environments"
    file: Path = Path("data/environments/registry.jsonl")
    default_ttl_hours: int = 0
    ttl_hours_by_class: tuple[tuple[str, int], ...] = ()
    auto_reclaim_classes: tuple[str, ...] = ("sandbox",)
    decommission_review_classes: tuple[str, ...] = ()


def _parse_class_name_list(
    block: dict[str, Any],
    key: str,
    *,
    default: tuple[str, ...],
    label: str,
) -> tuple[str, ...]:
    raw = block.get(key)
    if raw is None:
        return default
    if not isinstance(raw, list):
        raise ValueError(f"environment_vending.{label} must be a list of class names")
    classes = tuple(str(item).strip() for item in raw if str(item).strip())
    return classes if classes else default


def _parse_reclaim_classes(block: dict[str, Any]) -> tuple[str, ...]:
    return _parse_class_name_list(
        block,
        "auto_reclaim_classes",
        default=("sandbox",),
        label="auto_reclaim_classes",
    )


def _parse_decommission_review_classes(block: dict[str, Any]) -> tuple[str, ...]:
    return _parse_class_name_list(
        block,
        "decommission_review_classes",
        default=(),
        label="decommission_review_classes",
    )


def _parse_ttl_hours_by_class(block: dict[str, Any]) -> tuple[tuple[str, int], ...]:
    raw = block.get("ttl_hours_by_class")
    if not isinstance(raw, dict):
        return ()
    pairs: list[tuple[str, int]] = []
    for key, value in raw.items():
        class_name = str(key).strip()
        if not class_name or not isinstance(value, int) or value <= 0:
            continue
        pairs.append((class_name, value))
    return tuple(sorted(pairs))


def load_environment_vending_config(repo_root: Path) -> EnvironmentVendingConfig | None:
    """Optional ADR 003 Phase 3 environment vending configuration."""
    file_data = _load_config_file(repo_root / "repave.config.yaml")
    block = file_data.get("environment_vending")
    env_enabled = os.environ.get("REPAVE_ENVIRONMENT_VENDING", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if block is None and not env_enabled:
        return None
    if block is not None and not isinstance(block, dict):
        raise ValueError("environment_vending must be a mapping in repave.config.yaml")
    enabled = env_enabled
    gitops_repo = ""
    base_branch = "main"
    path_prefix = "environments"
    registry_file = repo_root / "data" / "environments" / "registry.jsonl"
    default_ttl_hours = 0
    ttl_hours_by_class: tuple[tuple[str, int], ...] = ()
    auto_reclaim_classes: tuple[str, ...] = ("sandbox",)
    decommission_review_classes: tuple[str, ...] = ()

    def _resolve(value: str) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = (repo_root / path).resolve()
        return path

    if isinstance(block, dict):
        enabled_raw = block.get("enabled", True)
        if not isinstance(enabled_raw, bool):
            raise ValueError("environment_vending.enabled must be a boolean")
        enabled = enabled_raw or env_enabled
        gitops_repo = str(block.get("gitops_repo", "")).strip()
        base_branch = str(block.get("base_branch", base_branch)).strip() or base_branch
        path_prefix = str(block.get("path_prefix", path_prefix)).strip() or path_prefix
        registry_env = os.environ.get("REPAVE_ENVIRONMENT_REGISTRY_FILE", "").strip()
        if registry_env:
            registry_file = _resolve(registry_env)
        else:
            registry_file = _resolve(str(block.get("file", "data/environments/registry.jsonl")))
        ttl_raw = block.get("default_ttl_hours", 0)
        if isinstance(ttl_raw, int) and ttl_raw >= 0:
            default_ttl_hours = ttl_raw
        ttl_hours_by_class = _parse_ttl_hours_by_class(block)
        auto_reclaim_classes = _parse_reclaim_classes(block)
        decommission_review_classes = _parse_decommission_review_classes(block)
    if not enabled:
        return None
    return EnvironmentVendingConfig(
        enabled=True,
        gitops_repo=gitops_repo,
        base_branch=base_branch,
        path_prefix=path_prefix,
        file=registry_file,
        default_ttl_hours=default_ttl_hours,
        ttl_hours_by_class=ttl_hours_by_class,
        auto_reclaim_classes=auto_reclaim_classes,
        decommission_review_classes=decommission_review_classes,
    )


@dataclass(frozen=True)
class ServiceCatalogConfig:
    """Service catalog overlay: maturity, profiles, initiatives (ADR 006)."""

    enabled: bool
    maturity_rubric: Path | None = None
    workload_profiles: Path | None = None
    deployment_sets: Path | None = None
    initiatives: Path | None = None
    default_team: str = "platform"


def load_service_catalog_config(repo_root: Path) -> ServiceCatalogConfig | None:
    """Optional service catalog overlay; off unless enabled in config or env."""
    env_flag = os.environ.get("REPAVE_SERVICE_CATALOG", "").strip().lower()
    if env_flag in {"0", "false", "no", "off"}:
        return None
    file_data = _load_config_file(repo_root / "repave.config.yaml")
    block = file_data.get("service_catalog")
    env_enabled = env_flag in {"1", "true", "yes", "on"}
    if block is None and not env_enabled:
        return None
    if block is not None and not isinstance(block, dict):
        raise ValueError("service_catalog must be a mapping in repave.config.yaml")

    def _resolve(value: str) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = (repo_root / path).resolve()
        return path

    enabled = env_enabled
    maturity_rubric: Path | None = None
    workload_profiles: Path | None = None
    deployment_sets: Path | None = None
    initiatives: Path | None = None
    default_team = "platform"
    if isinstance(block, dict):
        enabled_raw = block.get("enabled", True)
        if not isinstance(enabled_raw, bool):
            raise ValueError("service_catalog.enabled must be a boolean")
        enabled = enabled_raw or env_enabled
        rubric_raw = block.get("maturity_rubric")
        if isinstance(rubric_raw, str) and rubric_raw.strip():
            maturity_rubric = _resolve(rubric_raw.strip())
        profiles_raw = block.get("workload_profiles")
        if isinstance(profiles_raw, str) and profiles_raw.strip():
            workload_profiles = _resolve(profiles_raw.strip())
        sets_raw = block.get("deployment_sets")
        if isinstance(sets_raw, str) and sets_raw.strip():
            deployment_sets = _resolve(sets_raw.strip())
        initiatives_raw = block.get("initiatives")
        if isinstance(initiatives_raw, str) and initiatives_raw.strip():
            initiatives = _resolve(initiatives_raw.strip())
        default_team = str(block.get("default_team", default_team)).strip() or default_team
    if not enabled:
        return None
    if initiatives is None and env_enabled:
        initiatives = _resolve("data/initiatives.jsonl")
    return ServiceCatalogConfig(
        enabled=True,
        maturity_rubric=maturity_rubric,
        workload_profiles=workload_profiles,
        deployment_sets=deployment_sets,
        initiatives=initiatives,
        default_team=default_team,
    )


@dataclass(frozen=True)
class DurabilityConfig:
    async_generation: bool
    max_concurrent_runs: int
    queue_max_depth: int
    runs_db: Path
    require_session_secret: bool
    max_run_attempts: int = 3
    run_stale_seconds: int = 3600
    run_retry_base_seconds: int = 5


def load_durability_config(repo_root: Path) -> DurabilityConfig | None:
    """Async run queue settings; disabled when absent or async_generation is false."""
    file_data = _load_config_file(repo_root / "repave.config.yaml")
    block = file_data.get("durability")
    env_async = os.environ.get("REPAVE_ASYNC_GENERATION", "").strip().lower()
    if env_async in ("1", "true", "yes"):
        enabled = True
    elif env_async in ("0", "false", "no"):
        enabled = False
    elif isinstance(block, dict):
        raw = block.get("async_generation", False)
        if not isinstance(raw, bool):
            raise ValueError("durability.async_generation must be a boolean")
        enabled = raw
    else:
        return None

    if not enabled:
        return None

    max_workers = 2
    queue_max = 32
    runs_db = repo_root / "data" / "runs.sqlite"
    require_secret = False
    max_attempts = 3
    stale_seconds = 3600
    retry_base_seconds = 5

    if isinstance(block, dict):
        if block.get("max_concurrent_runs") is not None:
            max_workers = int(block["max_concurrent_runs"])
        if block.get("queue_max_depth") is not None:
            queue_max = int(block["queue_max_depth"])
        if block.get("runs_db") is not None:
            runs_db = Path(str(block["runs_db"])).expanduser()
            if not runs_db.is_absolute():
                runs_db = (repo_root / runs_db).resolve()
        req = block.get("require_session_secret", False)
        if not isinstance(req, bool):
            raise ValueError("durability.require_session_secret must be a boolean")
        require_secret = req
        if block.get("max_run_attempts") is not None:
            max_attempts = int(block["max_run_attempts"])
        if block.get("run_stale_seconds") is not None:
            stale_seconds = int(block["run_stale_seconds"])
        if block.get("run_retry_base_seconds") is not None:
            retry_base_seconds = int(block["run_retry_base_seconds"])

    max_workers = max(1, min(max_workers, 16))
    queue_max = max(1, min(queue_max, 256))
    max_attempts = max(1, min(max_attempts, 10))
    stale_seconds = max(60, min(stale_seconds, 86_400))
    retry_base_seconds = max(1, min(retry_base_seconds, 300))

    env_db = os.environ.get("REPAVE_RUNS_DB", "").strip()
    if env_db:
        runs_db = Path(env_db).expanduser()
        if not runs_db.is_absolute():
            runs_db = (repo_root / runs_db).resolve()

    env_attempts = os.environ.get("REPAVE_RUN_MAX_ATTEMPTS", "").strip()
    if env_attempts:
        max_attempts = max(1, min(int(env_attempts), 10))

    env_stale = os.environ.get("REPAVE_RUN_STALE_SECONDS", "").strip()
    if env_stale:
        stale_seconds = max(60, min(int(env_stale), 86_400))

    env_retry_base = os.environ.get("REPAVE_RUN_RETRY_BASE_SECONDS", "").strip()
    if env_retry_base:
        retry_base_seconds = max(1, min(int(env_retry_base), 300))

    return DurabilityConfig(
        async_generation=True,
        max_concurrent_runs=max_workers,
        queue_max_depth=queue_max,
        runs_db=runs_db,
        require_session_secret=require_secret,
        max_run_attempts=max_attempts,
        run_stale_seconds=stale_seconds,
        run_retry_base_seconds=retry_base_seconds,
    )


def load_notifications_config(repo_root: Path) -> NotificationsConfig | None:
    file_data = _load_config_file(repo_root / "repave.config.yaml")
    block = file_data.get("notifications")
    if block is None:
        return None
    if not isinstance(block, dict):
        raise ValueError("notifications must be a mapping in repave.config.yaml")

    enabled_raw = block.get("enabled", True)
    if not isinstance(enabled_raw, bool):
        raise ValueError("notifications.enabled must be a boolean")

    slack = _resolve_secret(
        block.get("slack_webhook_url"),
        os.environ.get("REPAVE_SLACK_WEBHOOK_URL"),
    )
    teams = _resolve_secret(
        block.get("teams_webhook_url"),
        os.environ.get("REPAVE_TEAMS_WEBHOOK_URL"),
    )
    generic = _resolve_secret(
        block.get("webhook_url"),
        os.environ.get("REPAVE_NOTIFY_WEBHOOK_URL"),
    )

    events_raw = block.get("events", list(_DEFAULT_NOTIFY_EVENTS))
    if not isinstance(events_raw, list):
        raise ValueError("notifications.events must be a list of event names")
    events = frozenset(str(item).strip() for item in events_raw if str(item).strip())

    if enabled_raw and not any((slack, teams, generic)):
        raise ValueError(
            "notifications.enabled is true but no webhook URL is configured "
            "(slack_webhook_url, teams_webhook_url, or webhook_url)"
        )

    return NotificationsConfig(
        enabled=enabled_raw,
        slack_webhook_url=slack,
        teams_webhook_url=teams,
        webhook_url=generic,
        events=events or _DEFAULT_NOTIFY_EVENTS,
    )


def _resolve_secret(file_value: object, env_value: str | None) -> str | None:
    if env_value and env_value.strip():
        return env_value.strip()
    if file_value is None:
        return None
    text = str(file_value).strip()
    return text or None


def _load_infracost_gate_policy(gates: dict[str, Any]) -> InfracostGatePolicy:
    block = gates.get("infracost", {})
    if not isinstance(block, dict):
        return InfracostGatePolicy()
    required_raw = block.get("required", False)
    if isinstance(required_raw, str):
        required = required_raw.strip().lower() in ("1", "true", "yes", "on")
    else:
        required = bool(required_raw)
    max_raw = block.get("max_monthly_usd")
    max_monthly: float | None = None
    if max_raw not in (None, ""):
        try:
            max_monthly = float(max_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "gates.infracost.max_monthly_usd must be a number "
                "(set in repave.config.yaml or clear the key)"
            ) from exc
    env_required = os.environ.get("REPAVE_INFRACOST_REQUIRED", "").strip().lower()
    if env_required in ("1", "true", "yes", "on"):
        required = True
    env_max = os.environ.get("REPAVE_INFRACOST_MAX_MONTHLY_USD", "").strip()
    if env_max:
        try:
            max_monthly = float(env_max)
        except ValueError as exc:
            raise ValueError("REPAVE_INFRACOST_MAX_MONTHLY_USD must be a number") from exc
    return InfracostGatePolicy(required=required, max_monthly_usd=max_monthly)


def load_gate_overrides(repo_root: Path) -> GateOverrides:
    file_data = _load_config_file(repo_root / "repave.config.yaml")
    gates = file_data.get("gates", {})
    if not isinstance(gates, dict):
        return GateOverrides(infracost=_load_infracost_gate_policy({}))

    checkov = gates.get("checkov", {})
    skip_checks: list[Any] = []
    if isinstance(checkov, dict):
        raw_skips = checkov.get("skip_checks", [])
        if not isinstance(raw_skips, list):
            raise ValueError("gates.checkov.skip_checks must be a list of check IDs")
        skip_checks = raw_skips
    elif checkov not in (None, {}):
        raise ValueError("gates.checkov must be a mapping")

    policy = gates.get("policy", {})
    blocked: tuple[str, ...] = ()
    if isinstance(policy, dict):
        floor = policy.get("required_rules", [])
        if floor is not None and not isinstance(floor, list):
            raise ValueError("gates.policy.required_rules must be a list of rule IDs")
        blocked = tuple(str(item) for item in (floor or []))

    return GateOverrides(
        checkov_skip_checks=tuple(str(item) for item in skip_checks),
        blocked_policy_rule_skips=blocked,
        infracost=_load_infracost_gate_policy(gates),
    )


@dataclass(frozen=True)
class CostAllocationConfig:
    tag_key_owner: str = "Owner"
    tag_key_service: str = "Service"
    tag_key_environment: str = "Environment"
    tag_key_cost_center: str = "CostCenter"


_DEFAULT_COST_ALLOCATION = CostAllocationConfig()


def _coerce_tag_key(value: Any, *, default: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


def _parse_cost_allocation_tag_keys_env() -> dict[str, str]:
    raw = os.environ.get("REPAVE_COST_ALLOCATION_TAG_KEYS", "").strip()
    if not raw:
        return {}
    parsed: dict[str, str] = {}
    for segment in raw.split(","):
        part = segment.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            parsed[key] = value
    return parsed


def _load_cost_allocation_config(block: dict[str, Any] | None) -> CostAllocationConfig:
    defaults = _DEFAULT_COST_ALLOCATION
    tag_keys: dict[str, Any] = {}
    if isinstance(block, dict):
        raw_keys = block.get("tag_keys")
        if raw_keys is not None and not isinstance(raw_keys, dict):
            raise ValueError("portal.cost_allocation.tag_keys must be a mapping")
        if isinstance(raw_keys, dict):
            tag_keys = raw_keys
    env_map = _parse_cost_allocation_tag_keys_env()
    merged = {**{str(k): str(v) for k, v in tag_keys.items()}, **env_map}
    return CostAllocationConfig(
        tag_key_owner=_coerce_tag_key(merged.get("owner"), default=defaults.tag_key_owner),
        tag_key_service=_coerce_tag_key(merged.get("service"), default=defaults.tag_key_service),
        tag_key_environment=_coerce_tag_key(
            merged.get("environment"), default=defaults.tag_key_environment
        ),
        tag_key_cost_center=_coerce_tag_key(
            merged.get("cost_center"), default=defaults.tag_key_cost_center
        ),
    )


def _load_cost_budgets_config(block: dict[str, Any] | None) -> CostBudgetConfig:
    if not isinstance(block, dict):
        return CostBudgetConfig()
    default_raw = block.get("default_monthly_usd")
    default_monthly: float | None = None
    if default_raw is not None:
        try:
            default_monthly = float(default_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("portal.cost_budgets.default_monthly_usd must be a number") from exc
        if default_monthly < 0:
            raise ValueError("portal.cost_budgets.default_monthly_usd must be >= 0")
    entities_raw = block.get("entities", {})
    if entities_raw is not None and not isinstance(entities_raw, dict):
        raise ValueError("portal.cost_budgets.entities must be a mapping")
    entities: dict[str, float] = {}
    if isinstance(entities_raw, dict):
        for key, value in entities_raw.items():
            entity_id = str(key).strip()
            if not entity_id:
                continue
            try:
                amount = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"portal.cost_budgets.entities.{entity_id} must be a number"
                ) from exc
            if amount < 0:
                raise ValueError(f"portal.cost_budgets.entities.{entity_id} must be >= 0")
            entities[entity_id] = amount
    return CostBudgetConfig(default_monthly_usd=default_monthly, entities=entities)


def _load_cost_anomalies_config(block: dict[str, Any] | None) -> CostAnomalyConfig:
    if not isinstance(block, dict):
        return CostAnomalyConfig()
    enabled_raw = block.get("enabled", False)
    if not isinstance(enabled_raw, bool):
        raise ValueError("portal.cost_anomalies.enabled must be a boolean")
    wow_raw = block.get("wow_threshold_pct", 25.0)
    mom_raw = block.get("mom_threshold_pct", 50.0)
    try:
        wow_threshold = float(wow_raw)
        mom_threshold = float(mom_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("portal.cost_anomalies thresholds must be numbers") from exc
    if wow_threshold < 0 or mom_threshold < 0:
        raise ValueError("portal.cost_anomalies thresholds must be >= 0")
    return CostAnomalyConfig(
        enabled=enabled_raw,
        wow_threshold_pct=wow_threshold,
        mom_threshold_pct=mom_threshold,
    )


@dataclass(frozen=True)
class CostAwsConfig:
    tag_key_owner: str = "Owner"
    tag_key_service: str = "Service"


@dataclass(frozen=True)
class CostAzureConfig:
    subscription_id: str = ""
    scope: str = ""
    tag_key_owner: str = "Owner"
    tag_key_service: str = "Service"


@dataclass(frozen=True)
class CostK8sConfig:
    base_url: str = ""
    aggregate: str = "label:app.kubernetes.io/name"
    allocation_key: str = "{name}"
    window: str = "30d"
    currency: str = "USD"


@dataclass(frozen=True)
class DeploymentArgocdConfig:
    base_url: str = ""
    application: str = "{name}"


@dataclass(frozen=True)
class DeploymentFluxConfig:
    api_server: str = ""
    namespace: str = "default"
    name: str = "{name}"
    kind: str = "kustomization"


@dataclass(frozen=True)
class CostFocusConfig:
    file: str = ""
    tag_key_owner: str = "Owner"
    tag_key_service: str = "Service"
    lookback_days: int = 30
    currency: str = "USD"


@dataclass(frozen=True)
class CostAnomalyConfig:
    enabled: bool = False
    wow_threshold_pct: float = 25.0
    mom_threshold_pct: float = 50.0


@dataclass(frozen=True)
class CostBudgetConfig:
    default_monthly_usd: float | None = None
    entities: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PortalConfig:
    density: str
    observability_dashboard_url: str = ""
    observability_slo_url: str = ""
    # Optional white-label: empty keeps v3 platform-layer defaults.
    logo_url: str = ""
    accent_color: str = ""
    cost_reader: str = ""
    cost_actuals_url: str = ""
    cost_allocation: CostAllocationConfig = field(default_factory=CostAllocationConfig)
    cost_aws: CostAwsConfig = field(default_factory=CostAwsConfig)
    cost_azure: CostAzureConfig = field(default_factory=CostAzureConfig)
    cost_k8s: CostK8sConfig = field(default_factory=CostK8sConfig)
    cost_focus: CostFocusConfig = field(default_factory=CostFocusConfig)
    cost_snapshots_enabled: bool = False
    cost_snapshots_file: Path | None = None
    cost_budgets: CostBudgetConfig = field(default_factory=CostBudgetConfig)
    cost_anomalies: CostAnomalyConfig = field(default_factory=CostAnomalyConfig)
    deployment_reader: str = ""
    deployment_status_url: str = ""
    deployment_argocd: DeploymentArgocdConfig = field(default_factory=DeploymentArgocdConfig)
    deployment_flux: DeploymentFluxConfig = field(default_factory=DeploymentFluxConfig)


def load_portal_config(repo_root: Path) -> PortalConfig:
    file_data = _load_config_file(repo_root / "repave.config.yaml")
    block = file_data.get("portal")
    if not isinstance(block, dict):
        block = {}
    density = str(block.get("density", "default")).strip().lower()
    if density not in ("default", "compact"):
        raise ValueError("portal.density must be 'default' or 'compact'")
    logo_url = normalize_portal_logo_url(str(block.get("logo_url", "")))
    accent_color = normalize_portal_accent_color(str(block.get("accent_color", "")))
    env_logo = os.environ.get("REPAVE_PORTAL_LOGO_URL", "").strip()
    if env_logo:
        logo_url = normalize_portal_logo_url(env_logo)
    env_accent = os.environ.get("REPAVE_PORTAL_ACCENT_COLOR", "").strip()
    if env_accent:
        accent_color = normalize_portal_accent_color(env_accent)
    obs_url = str(block.get("observability_dashboard_url", "")).strip()
    slo_url = str(block.get("observability_slo_url", "")).strip()
    cost_url = str(block.get("cost_actuals_url", "")).strip()
    cost_reader = str(block.get("cost_reader", "")).strip().lower()
    cost_alloc_block = block.get("cost_allocation", {})
    cost_budgets = _load_cost_budgets_config(
        block.get("cost_budgets") if isinstance(block.get("cost_budgets"), dict) else None
    )
    cost_anomalies = _load_cost_anomalies_config(
        block.get("cost_anomalies") if isinstance(block.get("cost_anomalies"), dict) else None
    )
    cost_allocation = _load_cost_allocation_config(
        cost_alloc_block if isinstance(cost_alloc_block, dict) else {}
    )
    aws_block = block.get("cost_aws", {})
    azure_block = block.get("cost_azure", {})
    k8s_block = block.get("cost_k8s", {})
    focus_block = block.get("cost_focus", {})
    cost_aws = CostAwsConfig(
        tag_key_owner=_coerce_tag_key(
            aws_block.get("tag_key_owner") if isinstance(aws_block, dict) else None,
            default=cost_allocation.tag_key_owner,
        ),
        tag_key_service=_coerce_tag_key(
            aws_block.get("tag_key_service") if isinstance(aws_block, dict) else None,
            default=cost_allocation.tag_key_service,
        ),
    )
    cost_azure = CostAzureConfig(
        subscription_id=str(azure_block.get("subscription_id", "")).strip()
        if isinstance(azure_block, dict)
        else "",
        scope=str(azure_block.get("scope", "")).strip() if isinstance(azure_block, dict) else "",
        tag_key_owner=_coerce_tag_key(
            azure_block.get("tag_key_owner") if isinstance(azure_block, dict) else None,
            default=cost_allocation.tag_key_owner,
        ),
        tag_key_service=_coerce_tag_key(
            azure_block.get("tag_key_service") if isinstance(azure_block, dict) else None,
            default=cost_allocation.tag_key_service,
        ),
    )
    cost_k8s = CostK8sConfig(
        base_url=str(k8s_block.get("base_url", "")).strip() if isinstance(k8s_block, dict) else "",
        aggregate=str(k8s_block.get("aggregate", "label:app.kubernetes.io/name")).strip()
        or "label:app.kubernetes.io/name"
        if isinstance(k8s_block, dict)
        else "label:app.kubernetes.io/name",
        allocation_key=str(k8s_block.get("allocation_key", "{name}")).strip() or "{name}"
        if isinstance(k8s_block, dict)
        else "{name}",
        window=str(k8s_block.get("window", "30d")).strip() or "30d"
        if isinstance(k8s_block, dict)
        else "30d",
        currency=str(k8s_block.get("currency", "USD")).strip() or "USD"
        if isinstance(k8s_block, dict)
        else "USD",
    )
    focus_file = str(focus_block.get("file", "")).strip() if isinstance(focus_block, dict) else ""
    focus_lookback_raw = (
        focus_block.get("lookback_days", 30) if isinstance(focus_block, dict) else 30
    )
    try:
        focus_lookback = int(focus_lookback_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("portal.cost_focus.lookback_days must be an integer") from exc
    if focus_lookback <= 0:
        raise ValueError("portal.cost_focus.lookback_days must be > 0")
    cost_focus = CostFocusConfig(
        file=focus_file,
        tag_key_owner=_coerce_tag_key(
            focus_block.get("tag_key_owner") if isinstance(focus_block, dict) else None,
            default=cost_allocation.tag_key_owner,
        ),
        tag_key_service=_coerce_tag_key(
            focus_block.get("tag_key_service") if isinstance(focus_block, dict) else None,
            default=cost_allocation.tag_key_service,
        ),
        lookback_days=focus_lookback,
        currency=str(focus_block.get("currency", "USD")).strip() or "USD"
        if isinstance(focus_block, dict)
        else "USD",
    )
    deployment_status_url = str(block.get("deployment_status_url", "")).strip()
    deployment_reader = str(block.get("deployment_reader", "")).strip().lower()
    argocd_block = block.get("deployment_argocd", {})
    flux_block = block.get("deployment_flux", {})
    deployment_argocd = DeploymentArgocdConfig(
        base_url=str(argocd_block.get("base_url", "")).strip()
        if isinstance(argocd_block, dict)
        else "",
        application=str(argocd_block.get("application", "{name}")).strip() or "{name}"
        if isinstance(argocd_block, dict)
        else "{name}",
    )
    deployment_flux = DeploymentFluxConfig(
        api_server=str(flux_block.get("api_server", "")).strip()
        if isinstance(flux_block, dict)
        else "",
        namespace=str(flux_block.get("namespace", "default")).strip() or "default"
        if isinstance(flux_block, dict)
        else "default",
        name=str(flux_block.get("name", "{name}")).strip() or "{name}"
        if isinstance(flux_block, dict)
        else "{name}",
        kind=str(flux_block.get("kind", "kustomization")).strip().lower() or "kustomization"
        if isinstance(flux_block, dict)
        else "kustomization",
    )
    env_obs = os.environ.get("REPAVE_OBSERVABILITY_DASHBOARD_URL", "").strip()
    if env_obs:
        obs_url = env_obs
    env_slo = os.environ.get("REPAVE_OBSERVABILITY_SLO_URL", "").strip()
    if env_slo:
        slo_url = env_slo
    env_cost = os.environ.get("REPAVE_COST_ACTUALS_URL", "").strip()
    if env_cost:
        cost_url = env_cost
    env_reader = os.environ.get("REPAVE_COST_READER", "").strip().lower()
    if env_reader:
        cost_reader = env_reader
    env_k8s_base = os.environ.get("REPAVE_COST_K8S_BASE_URL", "").strip()
    if env_k8s_base:
        cost_k8s = CostK8sConfig(
            base_url=env_k8s_base,
            aggregate=cost_k8s.aggregate,
            allocation_key=cost_k8s.allocation_key,
            window=cost_k8s.window,
            currency=cost_k8s.currency,
        )
    env_focus_file = os.environ.get("REPAVE_COST_FOCUS_FILE", "").strip()
    if env_focus_file:
        cost_focus = CostFocusConfig(
            file=env_focus_file,
            tag_key_owner=cost_focus.tag_key_owner,
            tag_key_service=cost_focus.tag_key_service,
            lookback_days=cost_focus.lookback_days,
            currency=cost_focus.currency,
        )
    env_deploy_url = os.environ.get("REPAVE_DEPLOYMENT_STATUS_URL", "").strip()
    if env_deploy_url:
        deployment_status_url = env_deploy_url
    env_deploy_reader = os.environ.get("REPAVE_DEPLOYMENT_READER", "").strip().lower()
    if env_deploy_reader:
        deployment_reader = env_deploy_reader
    env_argocd_base = os.environ.get("REPAVE_ARGOCD_BASE_URL", "").strip()
    if env_argocd_base:
        deployment_argocd = DeploymentArgocdConfig(
            base_url=env_argocd_base,
            application=deployment_argocd.application,
        )
    env_flux_server = os.environ.get("REPAVE_FLUX_API_SERVER", "").strip()
    if env_flux_server:
        deployment_flux = DeploymentFluxConfig(
            api_server=env_flux_server,
            namespace=deployment_flux.namespace,
            name=deployment_flux.name,
            kind=deployment_flux.kind,
        )
    if cost_reader not in ("", "url", "aws", "azure", "k8s", "focus"):
        raise ValueError("portal.cost_reader must be 'url', 'aws', 'azure', 'k8s', or 'focus'")
    if cost_reader == "focus" and not cost_focus.file.strip():
        raise ValueError("portal.cost_focus.file is required when cost_reader is 'focus'")
    if deployment_reader not in ("", "url", "argocd", "flux"):
        raise ValueError("portal.deployment_reader must be 'url', 'argocd', or 'flux'")
    if deployment_flux.kind not in ("kustomization", "helmrelease"):
        raise ValueError("portal.deployment_flux.kind must be 'kustomization' or 'helmrelease'")
    from repave_engine.cost_actuals import cost_reader_configured

    cost_reader_active = cost_reader_configured(
        cost_reader=cost_reader,
        cost_actuals_url=cost_url,
        cost_focus_file=cost_focus.file,
    )
    snapshots_block = block.get("cost_snapshots", {})
    cost_snapshots_enabled = False
    cost_snapshots_file: Path | None = None
    default_snapshots = (repo_root / "data/fleet/cost-snapshots.jsonl").resolve()
    env_snapshots_file = os.environ.get("REPAVE_COST_SNAPSHOTS_FILE", "").strip()
    snapshots_explicit = isinstance(snapshots_block, dict)
    snapshots_enabled_flag = snapshots_block.get("enabled") if snapshots_explicit else None
    if (
        snapshots_explicit
        and not isinstance(snapshots_enabled_flag, bool)
        and snapshots_enabled_flag is not None
    ):
        raise ValueError("portal.cost_snapshots.enabled must be a boolean")
    should_enable_snapshots = cost_reader_active or snapshots_enabled_flag is True
    if should_enable_snapshots:
        cost_snapshots_enabled = (
            snapshots_enabled_flag if snapshots_enabled_flag is not None else True
        )
        file_value = str(snapshots_block.get("file", "")).strip() if snapshots_explicit else ""
        if env_snapshots_file:
            path = Path(env_snapshots_file).expanduser()
            cost_snapshots_file = path if path.is_absolute() else (repo_root / path).resolve()
            cost_snapshots_enabled = True
        elif file_value:
            path = Path(file_value).expanduser()
            cost_snapshots_file = path if path.is_absolute() else (repo_root / path).resolve()
        elif cost_snapshots_enabled:
            cost_snapshots_file = default_snapshots
    return PortalConfig(
        density=density,
        observability_dashboard_url=obs_url,
        observability_slo_url=slo_url,
        logo_url=logo_url,
        accent_color=accent_color,
        cost_reader=cost_reader,
        cost_actuals_url=cost_url,
        cost_allocation=cost_allocation,
        cost_aws=cost_aws,
        cost_azure=cost_azure,
        cost_k8s=cost_k8s,
        cost_focus=cost_focus,
        cost_snapshots_enabled=cost_snapshots_enabled,
        cost_snapshots_file=cost_snapshots_file,
        cost_budgets=cost_budgets,
        cost_anomalies=cost_anomalies,
        deployment_reader=deployment_reader,
        deployment_status_url=deployment_status_url,
        deployment_argocd=deployment_argocd,
        deployment_flux=deployment_flux,
    )


def load_auth_config(repo_root: Path) -> AuthConfig | None:
    file_data = _load_config_file(repo_root / "repave.config.yaml")
    block = file_data.get("auth")
    env_service = os.environ.get("REPAVE_SERVICE_MODE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if block is None and not env_service:
        return None
    if block is not None and not isinstance(block, dict):
        raise ValueError("auth must be a mapping in repave.config.yaml")

    service_enabled = env_service
    if isinstance(block, dict):
        service_enabled = bool(block.get("service_mode", service_enabled))

    session_secret = os.environ.get("REPAVE_SESSION_SECRET", "").strip()
    if isinstance(block, dict) and block.get("session_secret"):
        session_secret = str(block.get("session_secret")).strip() or session_secret
    api_token = os.environ.get("REPAVE_API_TOKEN", "").strip()
    if isinstance(block, dict):
        resolved = _resolve_secret(block.get("api_token"), api_token)
        if resolved:
            api_token = resolved
    if service_enabled and not session_secret:
        raise ValueError("auth.service_mode requires REPAVE_SESSION_SECRET or auth.session_secret")

    oidc_block = block.get("oidc", {}) if isinstance(block, dict) else {}
    if not isinstance(oidc_block, dict):
        oidc_block = {}

    issuer = str(oidc_block.get("issuer", os.environ.get("REPAVE_OIDC_ISSUER", ""))).strip()
    client_id = str(
        oidc_block.get("client_id", os.environ.get("REPAVE_OIDC_CLIENT_ID", ""))
    ).strip()
    client_secret = (
        _resolve_secret(
            oidc_block.get("client_secret"),
            os.environ.get("REPAVE_OIDC_CLIENT_SECRET"),
        )
        or ""
    )
    redirect_uri = str(
        oidc_block.get("redirect_uri", os.environ.get("REPAVE_OIDC_REDIRECT_URI", ""))
    ).strip()
    scopes_raw = oidc_block.get("scopes", ["openid", "profile", "email"])
    if isinstance(scopes_raw, str):
        scopes = tuple(part.strip() for part in scopes_raw.split() if part.strip())
    elif isinstance(scopes_raw, list):
        scopes = tuple(str(item).strip() for item in scopes_raw if str(item).strip())
    else:
        scopes = ("openid", "profile", "email")

    groups_claim = str(oidc_block.get("groups_claim", "groups")).strip() or "groups"
    logout_return_to = str(oidc_block.get("logout_return_to", "")).strip()
    roles_block = oidc_block.get("roles", {}) if isinstance(oidc_block, dict) else {}
    if not isinstance(roles_block, dict):
        roles_block = {}

    def _groups(key: str) -> frozenset[str]:
        raw = roles_block.get(key, [])
        if not isinstance(raw, list):
            return frozenset()
        return frozenset(str(item).strip() for item in raw if str(item).strip())

    # Secure cookies default on in service mode (TLS-terminated EKS ingress).
    session_https_only = service_enabled
    env_https = os.environ.get("REPAVE_SESSION_HTTPS_ONLY", "").strip().lower()
    if env_https in ("1", "true", "yes", "on"):
        session_https_only = True
    elif env_https in ("0", "false", "no", "off"):
        session_https_only = False
    if isinstance(block, dict) and "session_https_only" in block:
        session_https_only = bool(block.get("session_https_only"))

    coarse_rbac_enabled = False
    if isinstance(block, dict):
        coarse_rbac_enabled = bool(block.get("coarse_rbac_enabled", False))

    if service_enabled and not all((issuer, client_id, client_secret, redirect_uri)):
        raise ValueError(
            "auth.service_mode requires oidc issuer, client_id, client_secret, and redirect_uri"
        )

    if not service_enabled:
        return AuthConfig(
            service_enabled=False,
            session_secret=session_secret or secrets.token_hex(32),
            api_token=api_token,
            oidc_issuer=issuer,
            oidc_client_id=client_id,
            oidc_client_secret=client_secret,
            oidc_redirect_uri=redirect_uri,
            oidc_scopes=scopes,
            groups_claim=groups_claim,
            admin_groups=_groups("admin"),
            generator_groups=_groups("generator"),
            session_https_only=session_https_only,
            oidc_logout_return_to=logout_return_to,
            coarse_rbac_enabled=coarse_rbac_enabled,
        )

    return AuthConfig(
        service_enabled=True,
        session_secret=session_secret,
        api_token=api_token,
        oidc_issuer=issuer,
        oidc_client_id=client_id,
        oidc_client_secret=client_secret,
        oidc_redirect_uri=redirect_uri,
        oidc_scopes=scopes,
        groups_claim=groups_claim,
        admin_groups=_groups("admin"),
        generator_groups=_groups("generator"),
        session_https_only=session_https_only,
        oidc_logout_return_to=logout_return_to,
        coarse_rbac_enabled=coarse_rbac_enabled,
    )


def validate_hosted_service_config(
    repo_root: Path,
    *,
    auth_config: AuthConfig | None,
) -> None:
    """Hosted service mode requires a unified SQL store (contract freeze at v2.0.0)."""
    if auth_config is None or not auth_config.service_enabled:
        return
    from repave_engine.sql_store import load_database_config

    if load_database_config(repo_root) is None:
        raise ValueError(
            "auth.service_mode requires durability.database_url or REPAVE_DATABASE_URL "
            "(JSONL stores are export-only in hosted mode)"
        )


def _load_config_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    api_version = data.get("apiVersion")
    if api_version is None:
        logger.warning(
            "%s is missing apiVersion; add %r (unversioned config is deprecated for v2)",
            path.name,
            CONFIG_API_VERSION,
        )
    else:
        version = str(api_version).strip()
        if version not in SUPPORTED_CONFIG_API_VERSIONS:
            supported = ", ".join(sorted(SUPPORTED_CONFIG_API_VERSIONS))
            raise ValueError(
                f"Unsupported apiVersion {version!r} in {path.name} (supported: {supported})"
            )
    return data
