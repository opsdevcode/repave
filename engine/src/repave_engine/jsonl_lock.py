"""Advisory file locks for append-only JSONL stores."""

from __future__ import annotations

import fcntl
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def append_jsonl_line(path: Path, line: str, *, store: str | None = None) -> None:
    """Append one line under an exclusive lock. Raises OSError on failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = line if line.endswith("\n") else f"{line}\n"
    try:
        with path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                handle.write(payload)
                handle.flush()
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        if store:
            from repave_engine.metrics import record_jsonl_append_failure

            record_jsonl_append_failure(store)
        raise


def append_jsonl_line_best_effort(path: Path, line: str, *, store: str | None = None) -> bool:
    """Append one line; return False and log on failure without raising."""
    try:
        append_jsonl_line(path, line, store=store)
    except OSError as exc:
        logger.error("JSONL append failed (%s): %s", path, exc)
        return False
    return True
