from __future__ import annotations

from pathlib import Path

from repave_engine.blueprint import blueprint_dir, blueprints_dir, bundles_dir


def test_blueprint_path_helpers(repo_root: Path) -> None:
    assert blueprints_dir(repo_root) == repo_root / "blueprints"
    assert blueprint_dir(repo_root, "terraform-module-generic").name == "terraform-module-generic"
    assert bundles_dir(repo_root).name == "bundles"
