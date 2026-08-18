"""Resolve user-supplied paths and keep joins inside a chosen root."""

from __future__ import annotations

from pathlib import Path


def trusted_path(path: Path | str) -> Path:
    """Resolve ``path`` and reject leftover ``..`` segments.

    ``Path.resolve()`` collapses traversal. The explicit ``..`` check is the
    sanitizer CodeQL recognizes, and it names the fix when a resolved path is
    still unsafe.
    """
    resolved = Path(path).expanduser().resolve()
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
    joined = root_resolved.joinpath(*(Path(part) for part in parts))
    resolved = joined.resolve()
    if not resolved.is_relative_to(root_resolved):
        raise ValueError(
            f"path escapes root: {resolved} is not under {root_resolved}; "
            "use a relative path that stays inside the root"
        )
    return resolved
