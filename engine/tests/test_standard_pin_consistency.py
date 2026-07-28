"""Blueprint standard pins must resolve to a real version in the standard source.

`standards_diff` locates the baseline for an upgrade by searching the standard for
`Version: <pinned>`. A pin that no standard declares silently yields no baseline, so the
upgrade plan cannot show what changed. Two ways that drifted in practice: a standard was
bumped without bumping the blueprint pin, and a pin was bumped without bumping the
standard's own version header.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_VERSION_HEADER = re.compile(r"^Version:\s*(\S+)", re.MULTILINE)


def _blueprint_standards(repo_root: Path) -> list[tuple[str, str, str]]:
    """Return (blueprint, standard source, pinned version) for every pinned blueprint."""
    rows: list[tuple[str, str, str]] = []
    for path in sorted(repo_root.glob("blueprints/*/blueprint.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        standard = (data.get("spec") or {}).get("standard") or {}
        source = str(standard.get("source", "")).strip()
        version = str(standard.get("version", "")).strip()
        if source and version:
            rows.append((path.parent.name, source, version))
    return rows


def _declared_versions(target: Path) -> set[str]:
    """Versions declared by a standard file, or by any file in a standard directory."""
    files = sorted(target.rglob("*.md")) if target.is_dir() else [target]
    versions: set[str] = set()
    for file in files:
        if file.is_file():
            versions.update(_VERSION_HEADER.findall(file.read_text(encoding="utf-8")))
    return versions


def test_blueprints_declare_standards(repo_root: Path) -> None:
    assert _blueprint_standards(repo_root), "expected blueprints pinning a standard"


@pytest.mark.parametrize("case", _blueprint_standards(Path(__file__).resolve().parents[2]))
def test_standard_source_declares_a_version_header(case: tuple[str, str, str]) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    blueprint, source, _ = case
    target = repo_root / source

    assert target.exists(), f"{blueprint} pins missing standard source {source}"
    assert _declared_versions(target), (
        f"{source} declares no `Version:` header, so standards diff cannot resolve a "
        f"baseline for {blueprint}"
    )


@pytest.mark.parametrize("case", _blueprint_standards(Path(__file__).resolve().parents[2]))
def test_pinned_version_is_declared_by_the_standard(case: tuple[str, str, str]) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    blueprint, source, pinned = case
    declared = _declared_versions(repo_root / source)

    assert pinned in declared, (
        f"{blueprint} pins {source} at {pinned}, which the standard does not declare "
        f"(declared: {sorted(declared) or 'none'}). Bump the pin and the standard together."
    )
