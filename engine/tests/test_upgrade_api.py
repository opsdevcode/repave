from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from repave_engine.upgrade_api import (
    UpgradeTargetError,
    resolve_upgrade_target,
    run_plan_upgrade,
)


def test_resolve_upgrade_target_prefers_repo_url() -> None:
    assert (
        resolve_upgrade_target(
            target_repo="/ignored",
            repo_url="https://github.com/acme/mod.git",
        )
        == "https://github.com/acme/mod.git"
    )


def test_resolve_upgrade_target_requires_one_of() -> None:
    with pytest.raises(UpgradeTargetError):
        resolve_upgrade_target(target_repo="", repo_url=None)


def test_run_plan_upgrade_with_repo_url(repo_root: Path, tmp_path: Path) -> None:
    fixture = repo_root / "operator" / "testdata" / "modules" / "terraform-minimal"
    if not fixture.is_dir():
        pytest.skip("operator fixture not present")

    @contextmanager
    def fake_clone(_url: str, *, token=None, ref=None):
        yield fixture

    with patch("repave_engine.upgrade_api.ephemeral_clone", fake_clone):
        result = run_plan_upgrade(
            repo_root=repo_root,
            target="https://github.com/acme/example.git",
            blueprint_name=None,
            staging_root=tmp_path / "staging",
        )

    assert result.blueprint_name == "terraform-module-generic"
    assert result.changed_file_count > 0
