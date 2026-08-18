from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.safe_paths import confined_join, trusted_path


def test_trusted_path_keeps_existing_dir(tmp_path: Path) -> None:
    nested = tmp_path / "modules" / "demo"
    nested.mkdir(parents=True)
    assert trusted_path(nested) == nested


def test_trusted_path_rejects_parent_segments(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="path traversal rejected"):
        trusted_path(tmp_path / ".." / "etc")


def test_confined_join_keeps_child_inside_root(tmp_path: Path) -> None:
    dest = confined_join(tmp_path, "out", "README.md")
    assert dest == tmp_path / "out" / "README.md"
    dest.relative_to(tmp_path)


def test_confined_join_rejects_parent_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="path escapes root"):
        confined_join(tmp_path, "..", "etc", "passwd")


def test_confined_join_rejects_absolute_segment(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="path escapes root"):
        confined_join(tmp_path, "/etc/passwd")
