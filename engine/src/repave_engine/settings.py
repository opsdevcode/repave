from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


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


def _load_config_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data
