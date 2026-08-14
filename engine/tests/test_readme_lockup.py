from __future__ import annotations

from pathlib import Path

_README = Path(__file__).resolve().parents[2] / "README.md"


def test_readme_uses_raster_compact_lockup() -> None:
    text = _README.read_text(encoding="utf-8")
    assert "docs/brand/assets/png/repave-logo-compact-dark.png" in text
    assert "docs/brand/assets/png/repave-logo-compact.png" in text
    assert "repave-logo-compact-dark.svg" not in text
    assert "repave-logo-compact.svg" not in text
