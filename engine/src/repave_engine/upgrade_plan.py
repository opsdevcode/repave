from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repave_engine.blueprint import load_blueprint, validate_inputs
from repave_engine.provenance_inputs import (
    blueprint_name_from_provenance,
    inputs_from_provenance,
    load_provenance_document,
)
from repave_engine.render import render_blueprint

_SKIP_DIR_NAMES = frozenset({".git", "__pycache__", ".terraform", ".pytest_cache", ".ruff_cache"})


@dataclass(frozen=True)
class UpgradePlanResult:
    added: tuple[str, ...]
    modified: tuple[str, ...]
    removed: tuple[str, ...]
    blueprint_name: str
    blueprint_version: str

    @property
    def changed_file_count(self) -> int:
        return len(self.added) + len(self.modified) + len(self.removed)

    @property
    def summary(self) -> str:
        return (
            f"{self.changed_file_count} file(s) differ "
            f"({len(self.added)} added, {len(self.modified)} modified, "
            f"{len(self.removed)} removed) "
            f"for blueprint {self.blueprint_name}@{self.blueprint_version}"
        )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "blueprint_name": self.blueprint_name,
            "blueprint_version": self.blueprint_version,
            "changed_file_count": self.changed_file_count,
            "added": list(self.added),
            "modified": list(self.modified),
            "removed": list(self.removed),
            "summary": self.summary,
        }


def _iter_relative_files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    if not root.is_dir():
        return files
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        parts = path.relative_to(root).parts
        if any(part in _SKIP_DIR_NAMES for part in parts):
            continue
        files[rel] = path
    return files


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def diff_directories(
    existing_root: Path,
    rendered_root: Path,
) -> tuple[list[str], list[str], list[str]]:
    left = _iter_relative_files(existing_root)
    right = _iter_relative_files(rendered_root)

    added = sorted(set(right) - set(left))
    removed = sorted(set(left) - set(right))
    modified: list[str] = []
    for rel in sorted(set(left) & set(right)):
        if _file_digest(left[rel]) != _file_digest(right[rel]):
            modified.append(rel)
    return added, modified, removed


def plan_upgrade(
    target_repo: Path,
    repo_root: Path,
    *,
    blueprint_name: str | None = None,
    staging_root: Path | None = None,
) -> UpgradePlanResult:
    target_repo = target_repo.resolve()
    repo_root = repo_root.resolve()
    provenance_path = target_repo / "repave.yaml"
    if not provenance_path.is_file():
        raise FileNotFoundError(f"missing provenance file: {provenance_path}")

    doc = load_provenance_document(provenance_path)
    resolved_blueprint = (blueprint_name or blueprint_name_from_provenance(doc)).strip()
    blueprint_path = repo_root / "blueprints" / resolved_blueprint
    blueprint = load_blueprint(blueprint_path, repo_root)
    values = validate_inputs(blueprint, inputs_from_provenance(doc))

    owns_staging = staging_root is None
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if staging_root is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="repave-plan-")
        staging_dir = Path(temp_dir.name)
    else:
        staging_root.mkdir(parents=True, exist_ok=True)
        staging_dir = staging_root

    try:
        render_blueprint(blueprint, values, staging_dir)
        added, modified, removed = diff_directories(target_repo, staging_dir)
        return UpgradePlanResult(
            added=tuple(added),
            modified=tuple(modified),
            removed=tuple(removed),
            blueprint_name=blueprint.name,
            blueprint_version=blueprint.version,
        )
    finally:
        if owns_staging and temp_dir is not None:
            temp_dir.cleanup()
