from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def _ansible_lint_available() -> bool:
    return shutil.which("ansible-lint") is not None


pytestmark = pytest.mark.skipif(
    not _ansible_lint_available(),
    reason="ansible-lint not installed",
)


@pytest.fixture
def fixtures_root(repo_root: Path) -> Path:
    return repo_root / "examples" / "ansible-lint" / "tests" / "fixtures"


def run_ansible_lint(role_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ansible-lint"],
        cwd=role_dir,
        capture_output=True,
        text=True,
        check=False,
    )


def test_compliant_role_fixture_passes_ansible_lint(fixtures_root: Path) -> None:
    role_dir = fixtures_root / "role-pass"
    result = run_ansible_lint(role_dir)
    assert result.returncode == 0, result.stdout + result.stderr


def test_non_fqcn_role_fixture_fails_ansible_lint(fixtures_root: Path) -> None:
    role_dir = fixtures_root / "role-fail-short-module"
    result = run_ansible_lint(role_dir)
    assert result.returncode != 0
    assert "fqcn" in (result.stdout + result.stderr).lower()
