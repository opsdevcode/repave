"""Resolve user-supplied paths and keep joins inside a chosen root."""

from __future__ import annotations

import os
from pathlib import Path


def trusted_path(path: Path | str) -> Path:
    """Resolve ``path`` and reject leftover ``..`` segments.

    Uses ``os.path.realpath`` plus an explicit ``..`` check — the normalization
    pattern CodeQL documents for path-injection sinks.
    """
    candidate = Path(path).expanduser()
    if ".." in candidate.parts:
        raise ValueError(
            f"path traversal rejected: {path} contains '..'; "
            "pass a concrete path without parent segments"
        )
    resolved = Path(os.path.realpath(candidate, strict=False))
    if ".." in resolved.parts:
        raise ValueError(
            f"path traversal rejected: {path} resolved to {resolved}; "
            "pass a concrete path without '..'"
        )
    return resolved


def confined_join(root: Path | str, *parts: str | Path) -> Path:
    """Join ``parts`` under ``root`` and reject any escape.

    Use this instead of ``root / user_segment`` before reads or writes.
    """
    root_resolved = trusted_path(root)
    base = os.path.realpath(root_resolved, strict=False)
    for part in parts:
        segment = Path(part)
        if segment.is_absolute() or ".." in segment.parts:
            raise ValueError(
                f"path escapes root: {part} is not a relative child of {root_resolved}; "
                "use a relative path that stays inside the root"
            )
    joined = os.path.join(base, *[os.fspath(Path(part)) for part in parts])
    fullpath = os.path.realpath(joined, strict=False)
    if os.path.commonpath([base, fullpath]) != base:
        raise ValueError(
            f"path escapes root: {fullpath} is not under {base}; "
            "use a relative path that stays inside the root"
        )
    return Path(fullpath)
