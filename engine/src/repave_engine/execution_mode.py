"""Hosted execution mode: in-process workers vs enqueue-only API (service decomposition Phase 1)."""

from __future__ import annotations

import os
from enum import Enum


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
