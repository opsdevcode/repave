"""Soft YAML loading helpers for optional catalog files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml_mapping_soft(path: Path) -> dict[str, Any] | None:
    """Return mapping or None if missing/invalid (soft-miss for catalogs)."""
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None
