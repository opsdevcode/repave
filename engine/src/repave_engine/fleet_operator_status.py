"""Operator GoldenPathRepo status overlaid on fleet registry rows."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repave_engine.fleet import normalize_repo_url
from repave_engine.subprocess_run import run_subprocess

logger = logging.getLogger(__name__)

SNAPSHOT_VERSION = 1


@dataclass(frozen=True)
class FleetOperatorStatus:
    repo_url: str
    phase: str = ""
    message: str = ""
    remediation_pr_url: str = ""
    resource_name: str = ""
    namespace: str = ""

    def to_dict(self) -> dict[str, str]:
        payload = {
            "repo_url": self.repo_url,
            "phase": self.phase,
            "message": self.message,
            "remediation_pr_url": self.remediation_pr_url,
            "resource_name": self.resource_name,
            "namespace": self.namespace,
        }
        return {key: value for key, value in payload.items() if value}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    if isinstance(status, dict):
        phase = str(status.get("phase", "")).strip()
        message = str(status.get("message", "")).strip()
        remediation = status.get("remediationPR")
        if isinstance(remediation, dict):
            pr_url = str(remediation.get("url", "")).strip()
    return FleetOperatorStatus(
        repo_url=normalize_repo_url(repo_url),
        phase=phase,
        message=message,
        remediation_pr_url=pr_url,
        resource_name=str(metadata.get("name", "")).strip(),
        namespace=str(metadata.get("namespace", "")).strip(),
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


def load_operator_status_file(path: Path) -> dict[str, FleetOperatorStatus]:
    """Return latest operator status keyed by normalized repo URL."""
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Fleet operator status unreadable (%s): %s", path, exc)
        return {}
    repos = raw.get("repos") if isinstance(raw, dict) else raw
    if not isinstance(repos, list):
        return {}
    by_url: dict[str, FleetOperatorStatus] = {}
    for entry in repos:
        if not isinstance(entry, dict):
            continue
        repo_url = str(entry.get("repo_url", "")).strip()
        if not repo_url:
            continue
        normalized = normalize_repo_url(repo_url)
        by_url[normalized] = FleetOperatorStatus(
            repo_url=normalized,
            phase=str(entry.get("phase", "")).strip(),
            message=str(entry.get("message", "")).strip(),
            remediation_pr_url=str(entry.get("remediation_pr_url", "")).strip(),
            resource_name=str(entry.get("resource_name", "")).strip(),
            namespace=str(entry.get("namespace", "")).strip(),
        )
    return by_url


def write_operator_status_snapshot(
    path: Path,
    statuses: tuple[FleetOperatorStatus, ...] | list[FleetOperatorStatus],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": SNAPSHOT_VERSION,
        "updated_at": _now(),
        "repos": [row.to_dict() for row in statuses],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def kubectl_goldenpathrepo_list(
    *,
    namespace: str = "",
    all_namespaces: bool = False,
) -> dict[str, Any]:
    cmd = ["kubectl", "get", "goldenpathrepos"]
    if all_namespaces:
        cmd.append("-A")
    elif namespace.strip():
        cmd.extend(["-n", namespace.strip()])
    cmd.extend(["-o", "json"])
    result = run_subprocess(
        cmd,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "kubectl failed").strip()
        raise RuntimeError(detail)
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("kubectl returned unexpected JSON")
    return payload
