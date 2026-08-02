"""Operator GoldenPathRepo and UpgradeCampaign status overlaid on fleet registry rows."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from repave_engine.fleet import normalize_repo_url
from repave_engine.subprocess_run import run_subprocess

logger = logging.getLogger(__name__)

SNAPSHOT_VERSION = 2


@dataclass(frozen=True)
class OperatorPins:
    blueprint_name: str = ""
    blueprint_version: str = ""
    standard_source: str = ""
    standard_version: str = ""

    def to_dict(self) -> dict[str, str]:
        payload = {
            "blueprint_name": self.blueprint_name,
            "blueprint_version": self.blueprint_version,
            "standard_source": self.standard_source,
            "standard_version": self.standard_version,
        }
        return {key: value for key, value in payload.items() if value}


def _pins_from_mapping(raw: Any) -> OperatorPins | None:
    if not isinstance(raw, dict):
        return None
    return OperatorPins(
        blueprint_name=str(raw.get("blueprintName", raw.get("blueprint_name", ""))).strip(),
        blueprint_version=str(
            raw.get("blueprintVersion", raw.get("blueprint_version", ""))
        ).strip(),
        standard_source=str(raw.get("standardSource", raw.get("standard_source", ""))).strip(),
        standard_version=str(raw.get("standardVersion", raw.get("standard_version", ""))).strip(),
    )


@dataclass(frozen=True)
class FleetOperatorStatus:
    repo_url: str
    phase: str = ""
    message: str = ""
    remediation_pr_url: str = ""
    resource_name: str = ""
    namespace: str = ""
    observed_pins: OperatorPins | None = None
    desired_pins: OperatorPins | None = None
    drift_detected_at: str = ""
    upgrade_plan_changed_files: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "repo_url": self.repo_url,
            "phase": self.phase,
            "message": self.message,
            "remediation_pr_url": self.remediation_pr_url,
            "resource_name": self.resource_name,
            "namespace": self.namespace,
        }
        if self.observed_pins is not None:
            payload["observed_pins"] = self.observed_pins.to_dict()
        if self.desired_pins is not None:
            payload["desired_pins"] = self.desired_pins.to_dict()
        if self.drift_detected_at:
            payload["drift_detected_at"] = self.drift_detected_at
        if self.upgrade_plan_changed_files is not None:
            payload["upgrade_plan_changed_files"] = self.upgrade_plan_changed_files
        return {key: value for key, value in payload.items() if value != "" and value is not None}


@dataclass(frozen=True)
class UpgradeCampaignStatus:
    name: str
    namespace: str
    phase: str = ""
    open_pr_count: int = 0
    out_of_date_count: int = 0
    oldest_drift_age_seconds: int = 0
    average_remediation_mttr_seconds: int = 0
    consecutive_gate_failures: int = 0
    github_rate_limit_remaining: int | None = None
    github_rate_limit_reset_at: str = ""
    paused: bool = False
    blueprint_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "namespace": self.namespace,
            "phase": self.phase,
            "open_pr_count": self.open_pr_count,
            "out_of_date_count": self.out_of_date_count,
            "oldest_drift_age_seconds": self.oldest_drift_age_seconds,
            "average_remediation_mttr_seconds": self.average_remediation_mttr_seconds,
            "consecutive_gate_failures": self.consecutive_gate_failures,
            "paused": self.paused,
            "blueprint_name": self.blueprint_name,
        }
        if self.github_rate_limit_remaining is not None:
            payload["github_rate_limit_remaining"] = self.github_rate_limit_remaining
        if self.github_rate_limit_reset_at:
            payload["github_rate_limit_reset_at"] = self.github_rate_limit_reset_at
        return {key: value for key, value in payload.items() if value != "" and value is not False}


@dataclass(frozen=True)
class OperatorStatusSnapshot:
    version: int
    updated_at: str
    repos: tuple[FleetOperatorStatus, ...]
    campaigns: tuple[UpgradeCampaignStatus, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "updated_at": self.updated_at,
            "repos": [row.to_dict() for row in self.repos],
            "campaigns": [row.to_dict() for row in self.campaigns],
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_repo_entry(entry: dict[str, Any]) -> FleetOperatorStatus | None:
    repo_url = str(entry.get("repo_url", "")).strip()
    if not repo_url:
        return None
    observed_raw = entry.get("observed_pins")
    desired_raw = entry.get("desired_pins")
    changed_files = entry.get("upgrade_plan_changed_files")
    return FleetOperatorStatus(
        repo_url=normalize_repo_url(repo_url),
        phase=str(entry.get("phase", "")).strip(),
        message=str(entry.get("message", "")).strip(),
        remediation_pr_url=str(entry.get("remediation_pr_url", "")).strip(),
        resource_name=str(entry.get("resource_name", "")).strip(),
        namespace=str(entry.get("namespace", "")).strip(),
        observed_pins=_pins_from_mapping(observed_raw) if observed_raw else None,
        desired_pins=_pins_from_mapping(desired_raw) if desired_raw else None,
        drift_detected_at=str(entry.get("drift_detected_at", "")).strip(),
        upgrade_plan_changed_files=int(changed_files) if isinstance(changed_files, int) else None,
    )


def _parse_campaign_entry(entry: dict[str, Any]) -> UpgradeCampaignStatus | None:
    name = str(entry.get("name", "")).strip()
    namespace = str(entry.get("namespace", "")).strip()
    if not name:
        return None
    rate_limit = entry.get("github_rate_limit_remaining")
    return UpgradeCampaignStatus(
        name=name,
        namespace=namespace,
        phase=str(entry.get("phase", "")).strip(),
        open_pr_count=int(entry.get("open_pr_count", 0) or 0),
        out_of_date_count=int(entry.get("out_of_date_count", 0) or 0),
        oldest_drift_age_seconds=int(entry.get("oldest_drift_age_seconds", 0) or 0),
        average_remediation_mttr_seconds=int(entry.get("average_remediation_mttr_seconds", 0) or 0),
        consecutive_gate_failures=int(entry.get("consecutive_gate_failures", 0) or 0),
        github_rate_limit_remaining=int(rate_limit) if rate_limit is not None else None,
        github_rate_limit_reset_at=str(entry.get("github_rate_limit_reset_at", "")).strip(),
        paused=bool(entry.get("paused", False)),
        blueprint_name=str(entry.get("blueprint_name", "")).strip(),
    )


def status_from_gpr_item(item: dict[str, Any]) -> FleetOperatorStatus | None:
    metadata = item.get("metadata")
    spec = item.get("spec")
    status = item.get("status")
    if not isinstance(metadata, dict) or not isinstance(spec, dict):
        return None
    repo_url = str(spec.get("repoURL", "")).strip()
    if not repo_url:
        return None
    phase = ""
    message = ""
    pr_url = ""
    observed_pins: OperatorPins | None = None
    desired_pins: OperatorPins | None = None
    drift_detected_at = ""
    changed_files: int | None = None
    if isinstance(status, dict):
        phase = str(status.get("phase", "")).strip()
        message = str(status.get("message", "")).strip()
        remediation = status.get("remediationPR")
        if isinstance(remediation, dict):
            pr_url = str(remediation.get("url", "")).strip()
        observed_pins = _pins_from_mapping(status.get("observedPins"))
        desired_pins = _pins_from_mapping(spec.get("desiredPins"))
        drift_raw = status.get("driftDetectedAt")
        if isinstance(drift_raw, str):
            drift_detected_at = drift_raw.strip()
        elif isinstance(drift_raw, dict):
            drift_detected_at = str(drift_raw.get("Time", drift_raw.get("time", ""))).strip()
        upgrade_plan = status.get("upgradePlan")
        if isinstance(upgrade_plan, dict):
            count = upgrade_plan.get("changedFileCount")
            if isinstance(count, int):
                changed_files = count
    return FleetOperatorStatus(
        repo_url=normalize_repo_url(repo_url),
        phase=phase,
        message=message,
        remediation_pr_url=pr_url,
        resource_name=str(metadata.get("name", "")).strip(),
        namespace=str(metadata.get("namespace", "")).strip(),
        observed_pins=observed_pins,
        desired_pins=desired_pins,
        drift_detected_at=drift_detected_at,
        upgrade_plan_changed_files=changed_files,
    )


def status_from_campaign_item(item: dict[str, Any]) -> UpgradeCampaignStatus | None:
    metadata = item.get("metadata")
    spec = item.get("spec")
    status = item.get("status")
    if not isinstance(metadata, dict):
        return None
    name = str(metadata.get("name", "")).strip()
    if not name:
        return None
    paused = False
    blueprint_name = ""
    if isinstance(spec, dict):
        paused = bool(spec.get("paused", False))
        blueprint_name = str(spec.get("blueprintName", "")).strip()
    phase = ""
    open_pr_count = 0
    out_of_date_count = 0
    oldest_drift = 0
    mttr = 0
    gate_failures = 0
    rate_limit: int | None = None
    rate_reset = ""
    if isinstance(status, dict):
        phase = str(status.get("phase", "")).strip()
        open_pr_count = int(status.get("openPRCount", 0) or 0)
        out_of_date_count = int(status.get("outOfDateCount", 0) or 0)
        oldest_drift = int(status.get("oldestDriftAgeSeconds", 0) or 0)
        mttr = int(status.get("averageRemediationMTTRSeconds", 0) or 0)
        gate_failures = int(status.get("consecutiveGateFailures", 0) or 0)
        remaining = status.get("githubRateLimitRemaining")
        if remaining is not None:
            rate_limit = int(remaining)
        reset_raw = status.get("githubRateLimitResetAt")
        if isinstance(reset_raw, str):
            rate_reset = reset_raw.strip()
        elif isinstance(reset_raw, dict):
            rate_reset = str(reset_raw.get("Time", reset_raw.get("time", ""))).strip()
    return UpgradeCampaignStatus(
        name=name,
        namespace=str(metadata.get("namespace", "")).strip(),
        phase=phase,
        open_pr_count=open_pr_count,
        out_of_date_count=out_of_date_count,
        oldest_drift_age_seconds=oldest_drift,
        average_remediation_mttr_seconds=mttr,
        consecutive_gate_failures=gate_failures,
        github_rate_limit_remaining=rate_limit,
        github_rate_limit_reset_at=rate_reset,
        paused=paused,
        blueprint_name=blueprint_name,
    )


def parse_kubectl_gpr_list(payload: dict[str, Any]) -> tuple[FleetOperatorStatus, ...]:
    items = payload.get("items")
    if not isinstance(items, list):
        return ()
    parsed: list[FleetOperatorStatus] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = status_from_gpr_item(item)
        if row is not None:
            parsed.append(row)
    return tuple(parsed)


def parse_kubectl_campaign_list(payload: dict[str, Any]) -> tuple[UpgradeCampaignStatus, ...]:
    items = payload.get("items")
    if not isinstance(items, list):
        return ()
    parsed: list[UpgradeCampaignStatus] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = status_from_campaign_item(item)
        if row is not None:
            parsed.append(row)
    return tuple(parsed)


def load_operator_status_snapshot(path: Path) -> OperatorStatusSnapshot | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Fleet operator status unreadable (%s): %s", path, exc)
        return None
    if not isinstance(raw, dict):
        return None
    repos_raw = raw.get("repos")
    if not isinstance(repos_raw, list):
        return None
    repos: list[FleetOperatorStatus] = []
    for entry in repos_raw:
        if isinstance(entry, dict):
            row = _parse_repo_entry(entry)
            if row is not None:
                repos.append(row)
    campaigns: list[UpgradeCampaignStatus] = []
    campaigns_raw = raw.get("campaigns")
    if isinstance(campaigns_raw, list):
        for entry in campaigns_raw:
            if isinstance(entry, dict):
                campaign_row = _parse_campaign_entry(entry)
                if campaign_row is not None:
                    campaigns.append(campaign_row)
    version = int(raw.get("version", 1) or 1)
    updated_at = str(raw.get("updated_at", "")).strip()
    return OperatorStatusSnapshot(
        version=version,
        updated_at=updated_at,
        repos=tuple(repos),
        campaigns=tuple(campaigns),
    )


def load_operator_status_file(path: Path) -> dict[str, FleetOperatorStatus]:
    """Return latest operator status keyed by normalized repo URL."""
    snapshot = load_operator_status_snapshot(path)
    if snapshot is None:
        return {}
    return {row.repo_url: row for row in snapshot.repos}


def write_operator_status_snapshot(
    path: Path,
    statuses: tuple[FleetOperatorStatus, ...] | list[FleetOperatorStatus],
    *,
    campaigns: tuple[UpgradeCampaignStatus, ...] | list[UpgradeCampaignStatus] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    campaign_rows = list(campaigns or ())
    payload = {
        "version": SNAPSHOT_VERSION,
        "updated_at": _now(),
        "repos": [row.to_dict() for row in statuses],
        "campaigns": [row.to_dict() for row in campaign_rows],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class KubectlRunner(Protocol):
    def run(self, cmd: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]: ...


class SubprocessKubectlRunner:
    def run(self, cmd: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        return run_subprocess(cmd, check=False, timeout=timeout)


@dataclass(frozen=True)
class StaticKubectlRunner:
    """In-package fake for kubectl list tests."""

    payload: dict[str, Any] | None = None
    returncode: int = 0
    stderr: str = ""

    def run(self, cmd: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        stdout = json.dumps(self.payload) if self.payload is not None else ""
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=self.returncode,
            stdout=stdout,
            stderr=self.stderr,
        )


_default_kubectl_runner = SubprocessKubectlRunner()


def _kubectl_list(
    resource: str,
    *,
    namespace: str = "",
    all_namespaces: bool = False,
    runner: KubectlRunner | None = None,
) -> dict[str, Any]:
    cmd = ["kubectl", "get", resource]
    if all_namespaces:
        cmd.append("-A")
    elif namespace.strip():
        cmd.extend(["-n", namespace.strip()])
    cmd.extend(["-o", "json"])
    kubectl = runner if runner is not None else _default_kubectl_runner
    result = kubectl.run(cmd, timeout=120)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "kubectl failed").strip()
        raise RuntimeError(
            f"kubectl get {resource} failed: {detail}; "
            f"install kubectl, select a cluster context, and ensure RBAC can list {resource}"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"kubectl returned non-JSON stdout for {resource}; run: kubectl get {resource} -o json"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"kubectl {resource} JSON was not an object; run: kubectl get {resource} -o json"
        )
    return payload


def kubectl_goldenpathrepo_list(
    *,
    namespace: str = "",
    all_namespaces: bool = False,
    runner: KubectlRunner | None = None,
) -> dict[str, Any]:
    return _kubectl_list(
        "goldenpathrepos",
        namespace=namespace,
        all_namespaces=all_namespaces,
        runner=runner,
    )


def kubectl_upgradecampaign_list(
    *,
    namespace: str = "",
    all_namespaces: bool = False,
    runner: KubectlRunner | None = None,
) -> dict[str, Any]:
    return _kubectl_list(
        "upgradecampaigns",
        namespace=namespace,
        all_namespaces=all_namespaces,
        runner=runner,
    )
