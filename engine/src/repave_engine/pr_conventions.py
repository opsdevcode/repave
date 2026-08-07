from __future__ import annotations

import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repave_engine.gate_registry import GateResult
from repave_engine.settings import _load_config_file

_BRANCH_SEGMENT_RE = re.compile(r"[^a-zA-Z0-9._-]+")


@dataclass(frozen=True)
class PullRequestConventions:
    branch_prefix_generate: str = "repave/bootstrap"
    branch_prefix_upgrade: str = "repave/upgrade"
    branch_prefix_import: str = "repave/import"
    branch_prefix_add: str = "repave/add"
    branch_prefix_vend: str = "repave/environment"
    branch_prefix_reclaim: str = "repave/environment-reclaim"
    labels: tuple[str, ...] = ("repave", "governed")
    evidence_checklist: bool = True


def load_pull_request_conventions(repo_root: Path) -> PullRequestConventions:
    file_data = _load_config_file(repo_root / "repave.config.yaml")
    block = file_data.get("pull_requests")
    if block is None:
        defaults = PullRequestConventions()
        env_labels = _env_labels()
        return PullRequestConventions(
            branch_prefix_upgrade=_env_prefix(
                "REPAVE_PR_BRANCH_PREFIX_UPGRADE", defaults.branch_prefix_upgrade
            ),
            branch_prefix_import=_env_prefix(
                "REPAVE_PR_BRANCH_PREFIX_IMPORT", defaults.branch_prefix_import
            ),
            branch_prefix_add=_env_prefix(
                "REPAVE_PR_BRANCH_PREFIX_ADD", defaults.branch_prefix_add
            ),
            branch_prefix_vend=_env_prefix(
                "REPAVE_PR_BRANCH_PREFIX_VEND", defaults.branch_prefix_vend
            ),
            branch_prefix_reclaim=_env_prefix(
                "REPAVE_PR_BRANCH_PREFIX_RECLAIM", defaults.branch_prefix_reclaim
            ),
            branch_prefix_generate=_env_prefix(
                "REPAVE_PR_BRANCH_PREFIX_GENERATE", defaults.branch_prefix_generate
            ),
            labels=env_labels if env_labels else defaults.labels,
            evidence_checklist=_env_bool(
                "REPAVE_PR_EVIDENCE_CHECKLIST", defaults.evidence_checklist
            ),
        )
    if not isinstance(block, dict):
        raise ValueError("pull_requests must be a mapping in repave.config.yaml")

    prefixes = block.get("branch_prefix", {})
    if prefixes is not None and not isinstance(prefixes, dict):
        raise ValueError("pull_requests.branch_prefix must be a mapping")

    labels_raw = block.get("labels", list(PullRequestConventions().labels))
    if not isinstance(labels_raw, list):
        raise ValueError("pull_requests.labels must be a list of label names")

    evidence_raw = block.get("evidence_checklist", True)
    if not isinstance(evidence_raw, bool):
        raise ValueError("pull_requests.evidence_checklist must be a boolean")

    return PullRequestConventions(
        branch_prefix_generate=_resolve_prefix(
            prefixes.get("generate") if isinstance(prefixes, dict) else None,
            "REPAVE_PR_BRANCH_PREFIX_GENERATE",
            "repave/bootstrap",
        ),
        branch_prefix_upgrade=_resolve_prefix(
            prefixes.get("upgrade") if isinstance(prefixes, dict) else None,
            "REPAVE_PR_BRANCH_PREFIX_UPGRADE",
            "repave/upgrade",
        ),
        branch_prefix_import=_resolve_prefix(
            prefixes.get("import") if isinstance(prefixes, dict) else None,
            "REPAVE_PR_BRANCH_PREFIX_IMPORT",
            "repave/import",
        ),
        branch_prefix_add=_resolve_prefix(
            prefixes.get("add") if isinstance(prefixes, dict) else None,
            "REPAVE_PR_BRANCH_PREFIX_ADD",
            "repave/add",
        ),
        branch_prefix_vend=_resolve_prefix(
            prefixes.get("vend") if isinstance(prefixes, dict) else None,
            "REPAVE_PR_BRANCH_PREFIX_VEND",
            "repave/environment",
        ),
        branch_prefix_reclaim=_resolve_prefix(
            prefixes.get("reclaim") if isinstance(prefixes, dict) else None,
            "REPAVE_PR_BRANCH_PREFIX_RECLAIM",
            "repave/environment-reclaim",
        ),
        labels=_env_labels()
        or tuple(str(item).strip() for item in labels_raw if str(item).strip())
        or PullRequestConventions().labels,
        evidence_checklist=_env_bool("REPAVE_PR_EVIDENCE_CHECKLIST", evidence_raw),
    )


def branch_name(prefix: str, *segments: str) -> str:
    cleaned_prefix = prefix.strip().rstrip("/")
    safe_segments = [_sanitize_branch_segment(part) for part in segments if str(part).strip()]
    if not safe_segments:
        return cleaned_prefix or "repave/change"
    return f"{cleaned_prefix}/{'-'.join(safe_segments)}"


def upgrade_pull_request_title(blueprint_name: str, blueprint_version: str) -> str:
    return f"chore(repave): upgrade {blueprint_name} to {blueprint_version}"


def import_pull_request_title(blueprint_name: str, blueprint_version: str) -> str:
    return f"refactor(repave): adopt {blueprint_name}@{blueprint_version} golden path"


def add_pull_request_title(blueprint_name: str, component_id: str) -> str:
    return f"feat(repave): add {blueprint_name} component ({component_id})"


def render_evidence_checklist(gates: Sequence[GateResult]) -> str:
    if not gates:
        return ""
    from repave_engine.cost_estimate import cost_estimate_from_gates

    lines = ["## Gate evidence", ""]
    for gate in gates:
        if gate.skipped:
            mark = "[~]"
            state = "skipped"
        elif gate.passed:
            mark = "[x]"
            state = "passed"
        else:
            mark = "[ ]"
            state = "failed"
        detail = gate.message.strip()
        suffix = f" — {detail}" if detail else ""
        lines.append(f"- {mark} `{gate.name}` ({state}){suffix}")
    estimate = cost_estimate_from_gates(list(gates))
    if estimate is not None:
        lines.extend(["", f"**Cost estimate:** {estimate.detail}"])
    return "\n".join(lines) + "\n"


def append_evidence_section(body: str, gates: Sequence[GateResult], *, enabled: bool) -> str:
    if not enabled:
        return body
    section = render_evidence_checklist(gates)
    if not section:
        return body
    trimmed = body.rstrip() + "\n"
    return trimmed + "\n" + section


def _sanitize_branch_segment(value: str) -> str:
    value = value.strip()
    if not value:
        return "unknown"
    return _BRANCH_SEGMENT_RE.sub("-", value).strip("-") or "unknown"


def _resolve_prefix(file_value: Any, env_name: str, default: str) -> str:
    env_value = os.environ.get(env_name, "").strip()
    if env_value:
        return env_value
    if file_value is not None and str(file_value).strip():
        return str(file_value).strip()
    return default


def _env_prefix(env_name: str, default: str) -> str:
    return os.environ.get(env_name, default).strip() or default


def _env_labels() -> tuple[str, ...]:
    raw = os.environ.get("REPAVE_PR_LABELS", "").strip()
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _env_bool(env_name: str, default: bool) -> bool:
    raw = os.environ.get(env_name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
