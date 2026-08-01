from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from repave_engine.auth import AuthConfig


@dataclass(frozen=True)
class GateOverrides:
    checkov_skip_checks: tuple[str, ...] = ()
    blocked_policy_rule_skips: tuple[str, ...] = ()


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


def load_gate_overrides(repo_root: Path) -> GateOverrides:
    file_data = _load_config_file(repo_root / "repave.config.yaml")
    gates = file_data.get("gates", {})
    if not isinstance(gates, dict):
        return GateOverrides()

    checkov = gates.get("checkov", {})
    if not isinstance(checkov, dict):
        return GateOverrides()

    skip_checks = checkov.get("skip_checks", [])
    if not isinstance(skip_checks, list):
        raise ValueError("gates.checkov.skip_checks must be a list of check IDs")

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
class PortalConfig:
    density: str
    observability_dashboard_url: str = ""
    observability_slo_url: str = ""
    cost_reader: str = ""
    cost_actuals_url: str = ""
    cost_aws: CostAwsConfig = field(default_factory=CostAwsConfig)
    cost_azure: CostAzureConfig = field(default_factory=CostAzureConfig)


def load_portal_config(repo_root: Path) -> PortalConfig:
    file_data = _load_config_file(repo_root / "repave.config.yaml")
    block = file_data.get("portal")
    if not isinstance(block, dict):
        return PortalConfig(density="default")
    density = str(block.get("density", "default")).strip().lower()
    if density not in ("default", "compact"):
        raise ValueError("portal.density must be 'default' or 'compact'")
    obs_url = str(block.get("observability_dashboard_url", "")).strip()
    slo_url = str(block.get("observability_slo_url", "")).strip()
    cost_url = str(block.get("cost_actuals_url", "")).strip()
    cost_reader = str(block.get("cost_reader", "")).strip().lower()
    aws_block = block.get("cost_aws", {})
    azure_block = block.get("cost_azure", {})
    cost_aws = CostAwsConfig(
        tag_key_owner=str(aws_block.get("tag_key_owner", "Owner")).strip() or "Owner"
        if isinstance(aws_block, dict)
        else "Owner",
        tag_key_service=str(aws_block.get("tag_key_service", "Service")).strip() or "Service"
        if isinstance(aws_block, dict)
        else "Service",
    )
    cost_azure = CostAzureConfig(
        subscription_id=str(azure_block.get("subscription_id", "")).strip()
        if isinstance(azure_block, dict)
        else "",
        scope=str(azure_block.get("scope", "")).strip() if isinstance(azure_block, dict) else "",
        tag_key_owner=str(azure_block.get("tag_key_owner", "Owner")).strip() or "Owner"
        if isinstance(azure_block, dict)
        else "Owner",
        tag_key_service=str(azure_block.get("tag_key_service", "Service")).strip() or "Service"
        if isinstance(azure_block, dict)
        else "Service",
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
    if cost_reader not in ("", "url", "aws", "azure"):
        raise ValueError("portal.cost_reader must be 'url', 'aws', or 'azure'")
    return PortalConfig(
        density=density,
        observability_dashboard_url=obs_url,
        observability_slo_url=slo_url,
        cost_reader=cost_reader,
        cost_actuals_url=cost_url,
        cost_aws=cost_aws,
        cost_azure=cost_azure,
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
    roles_block = oidc_block.get("roles", {}) if isinstance(oidc_block, dict) else {}
    if not isinstance(roles_block, dict):
        roles_block = {}

    def _groups(key: str) -> frozenset[str]:
        raw = roles_block.get(key, [])
        if not isinstance(raw, list):
            return frozenset()
        return frozenset(str(item).strip() for item in raw if str(item).strip())

    if service_enabled and not all((issuer, client_id, client_secret, redirect_uri)):
        raise ValueError(
            "auth.service_mode requires oidc issuer, client_id, client_secret, and redirect_uri"
        )

    if not service_enabled:
        return AuthConfig(
            service_enabled=False,
            session_secret=session_secret or secrets.token_hex(32),
            oidc_issuer=issuer,
            oidc_client_id=client_id,
            oidc_client_secret=client_secret,
            oidc_redirect_uri=redirect_uri,
            oidc_scopes=scopes,
            groups_claim=groups_claim,
            admin_groups=_groups("admin"),
            generator_groups=_groups("generator"),
        )

    return AuthConfig(
        service_enabled=True,
        session_secret=session_secret,
        oidc_issuer=issuer,
        oidc_client_id=client_id,
        oidc_client_secret=client_secret,
        oidc_redirect_uri=redirect_uri,
        oidc_scopes=scopes,
        groups_claim=groups_claim,
        admin_groups=_groups("admin"),
        generator_groups=_groups("generator"),
    )


def _load_config_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data
