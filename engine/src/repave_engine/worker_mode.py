"""Async worker execution mode (inline thread pool, external Deployment, or Job)."""

from __future__ import annotations

from enum import Enum


class WorkerMode(Enum):
    INLINE = "inline"
    EXTERNAL = "external"
    JOB = "job"


def parse_worker_mode(raw: str) -> WorkerMode:
    value = raw.strip().lower()
    if value in ("inline", "inprocess", ""):
        return WorkerMode.INLINE
    if value in ("external", "kubernetes"):
        return WorkerMode.EXTERNAL
    if value == "job":
        return WorkerMode.JOB
    raise ValueError(
        f"worker_mode must be inline, external, or job (got {raw!r}); "
        "kubernetes is an alias for external"
    )
