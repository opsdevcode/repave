"""Async run kinds for platform console actions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repave_engine.environment_reclaim import reclaim_expired_environments
from repave_engine.settings import EnvironmentVendingConfig, load_environment_vending_config
from repave_engine.verify import VerifyError, verify_target

ENVIRONMENT_RECLAIM_SENTINEL = "__environment_reclaim__"
FLEET_DRIFT_CONFIRM_SENTINEL = "__fleet_drift_confirm__"


def is_environment_reclaim_run(payload: dict[str, Any]) -> bool:
    return str(payload.get("kind", "")).strip() == "environment_reclaim"


def is_fleet_drift_confirm_run(payload: dict[str, Any]) -> bool:
    return str(payload.get("kind", "")).strip() == "fleet_drift_confirm"


@dataclass(frozen=True)
class FleetDriftConfirmResult:
    repos: tuple[dict[str, Any], ...]
    confirmed_behind: int
    confirmed_current: int

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "repos": list(self.repos),
            "confirmed_behind": self.confirmed_behind,
            "confirmed_current": self.confirmed_current,
        }


def run_environment_reclaim(
    repo_root: Path,
    *,
    config: EnvironmentVendingConfig,
    github_token: str | None,
    dry_run: bool,
    stack_name: str | None,
) -> dict[str, Any]:
    summary = reclaim_expired_environments(
        repo_root=repo_root,
        config=config,
        github_token=github_token,
        dry_run=dry_run,
        stack_name=stack_name,
    )
    return summary.to_public_dict()


def run_fleet_drift_confirm(
    repo_root: Path,
    *,
    repo_urls: tuple[str, ...] | list[str],
) -> FleetDriftConfirmResult:
    rows: list[dict[str, Any]] = []
    behind = 0
    current = 0
    for repo_url in repo_urls:
        url = str(repo_url).strip()
        if not url:
            continue
        try:
            outcome = verify_target(url, repo_root)
            aligned = outcome.pins_aligned
            if aligned:
                current += 1
            else:
                behind += 1
            rows.append(
                {
                    "repo_url": url,
                    "ok": outcome.ok,
                    "pins_aligned": aligned,
                    "pin_changes": [change.to_dict() for change in outcome.pin_changes],
                    "gates_passed": outcome.gates_passed,
                }
            )
        except VerifyError as exc:
            rows.append(
                {
                    "repo_url": url,
                    "ok": False,
                    "error": str(exc),
                }
            )
            behind += 1
    return FleetDriftConfirmResult(
        repos=tuple(rows),
        confirmed_behind=behind,
        confirmed_current=current,
    )


def load_environment_reclaim_config(repo_root: Path) -> EnvironmentVendingConfig:
    config = load_environment_vending_config(repo_root)
    if config is None:
        raise ValueError(
            "environment_vending is not enabled; set environment_vending.enabled in "
            "repave.config.yaml"
        )
    return config
