"""Advisory file locks for append-only JSONL stores."""

from __future__ import annotations

import fcntl
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def append_jsonl_line(path: Path, line: str) -> None:
    """Append one line under an exclusive lock. Raises OSError on failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = line if line.endswith("\n") else f"{line}\n"
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(payload)
            handle.flush()
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def append_jsonl_line_best_effort(path: Path, line: str) -> bool:
    """Append one line; return False and log on failure without raising."""
    try:
        append_jsonl_line(path, line)
    except OSError as exc:
        logger.error("JSONL append failed (%s): %s", path, exc)
        return False
    return True
