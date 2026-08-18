"""Resolve user-supplied paths and keep joins inside a chosen root."""

from __future__ import annotations

from pathlib import Path


def trusted_path(path: Path | str) -> Path:
    """Resolve ``path`` and reject leftover ``..`` segments.

    Reject ``..`` before ``resolve()`` so literal traversal is named in errors.
    ``resolve()`` plus the post-resolve ``..`` check is the normalization CodeQL
    models for path-injection sinks.
    """
    candidate = Path(path).expanduser()
    if ".." in candidate.parts:
        raise ValueError(
            f"path traversal rejected: {path} contains '..'; "
            "pass a concrete path without parent segments"
        )
    resolved = candidate.resolve()
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
    for part in parts:
        segment = Path(part)
        if segment.is_absolute() or ".." in segment.parts:
            raise ValueError(
                f"path escapes root: {part} is not a relative child of {root_resolved}; "
                "use a relative path that stays inside the root"
            )
    joined = root_resolved.joinpath(*(Path(part) for part in parts))
    resolved = joined.resolve()
    if not resolved.is_relative_to(root_resolved):
        raise ValueError(
            f"path escapes root: {resolved} is not under {root_resolved}; "
            "use a relative path that stays inside the root"
        )
    return resolved
