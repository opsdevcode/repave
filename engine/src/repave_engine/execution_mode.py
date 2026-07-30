"""Hosted execution mode: in-process workers vs enqueue-only API (service decomposition Phase 1)."""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

SYNC_GENERATE_UNAVAILABLE_DETAIL = (
    "Sync generation is unavailable when execution_mode=worker; "
    "set async=true or POST /api/v1/runs (or /api/v2/runs)"
)


class ExecutionMode(str, Enum):
    INPROCESS = "inprocess"
    WORKER = "worker"


def parse_execution_mode(raw: str) -> ExecutionMode:
    value = raw.strip().lower()
    if value in ("worker", "external", "kubernetes", "job"):
        return ExecutionMode.WORKER
    if value in ("inprocess", "inline", ""):
        return ExecutionMode.INPROCESS
    raise ValueError(f"durability.execution_mode must be 'inprocess' or 'worker' (got {raw!r})")


def execution_mode_from_env() -> ExecutionMode | None:
    raw = os.environ.get("REPAVE_EXECUTION_MODE", "").strip()
    if not raw:
        return None
    return parse_execution_mode(raw)


def worker_execution_mode_active(repo_root: Path) -> bool:
    """True when API/portal pods must enqueue runs instead of executing gates locally."""
    from repave_engine.durability_store import load_durability_runtime

    return load_durability_runtime(repo_root).execution_mode == ExecutionMode.WORKER
