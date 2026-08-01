"""Catalog manifests must validate against frozen v2 schemas (see docs/blueprint-versioning.md)."""

from __future__ import annotations

import re
from pathlib import Path

from repave_engine.blueprint import blueprints_dir, list_blueprints
from repave_engine.bundle import list_bundles

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def test_all_catalog_blueprints_validate_against_frozen_schema(repo_root: Path) -> None:
    blueprints = list_blueprints(blueprints_dir(repo_root))
    assert blueprints, "expected at least one catalog blueprint"
    for blueprint in blueprints:
        assert _SEMVER.match(blueprint.version), (
            f"{blueprint.name} metadata.version must be semver MAJOR.MINOR.PATCH"
        )


def test_all_catalog_bundles_validate_against_frozen_schema(repo_root: Path) -> None:
    bundles = list_bundles(repo_root)
    assert bundles, "expected at least one catalog bundle"
    for bundle in bundles:
        assert _SEMVER.match(bundle.version), (
            f"{bundle.name} metadata.version must be semver MAJOR.MINOR.PATCH"
        )
