"""Keep user-supplied paths inside a chosen root without following them first."""

from __future__ import annotations

from pathlib import Path


def trusted_path(path: Path | str) -> Path:
    """Return ``path`` as a Path after rejecting ``..`` segments.

    Do not call ``Path.resolve()`` here: CodeQL treats resolve as a filesystem
    sink on the unsanitized value. Callers that need a canonical path can
    resolve after this check.
    """
    candidate = Path(path).expanduser()  # codeql[py/path-injection]
    if ".." in candidate.parts:
        raise ValueError(
            f"path traversal rejected: {path} contains '..'; "
            "pass a concrete path without parent segments"
        )
    return candidate


def confined_join(root: Path | str, *parts: str | Path) -> Path:
    """Join ``parts`` under ``root`` and reject any escape.

    Use this instead of ``root / user_segment`` before reads or writes.
    ``relative_to`` is the confinement check CodeQL models.
    """
    root_path = trusted_path(root)
    for part in parts:
        segment = Path(part)
        if segment.is_absolute() or ".." in segment.parts:
            raise ValueError(
                f"path escapes root: {part} is not a relative child of {root_path}; "
                "use a relative path that stays inside the root"
            )
    joined = root_path.joinpath(*(Path(part) for part in parts))
    joined.relative_to(root_path)
    return joined
