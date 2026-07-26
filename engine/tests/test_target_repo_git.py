from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from repave_engine.target_repo import resolve_module_repository_from_git


@pytest.mark.parametrize(
    ("remote_url", "owner", "name"),
    [
        ("https://github.com/acme-corp/tf-aws-networking.git", "acme-corp", "tf-aws-networking"),
        ("git@github.com:acme-corp/tf-aws-networking.git", "acme-corp", "tf-aws-networking"),
        ("https://github.com/user/my-module", "user", "my-module"),
    ],
)
def test_resolve_module_repository_from_git(
    tmp_path: Path,
    remote_url: str,
    owner: str,
    name: str,
) -> None:
    repo = tmp_path / "module"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=repo, check=True)

    resolved = resolve_module_repository_from_git(repo)

    assert resolved.owner == owner
    assert resolved.name == name
    assert resolved.local_path == repo.resolve()
    assert resolved.web_url == f"https://github.com/{owner}/{name}"


def test_resolve_module_repository_from_git_rejects_non_github(tmp_path: Path) -> None:
    repo = tmp_path / "module"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://gitlab.com/group/project.git"],
        cwd=repo,
        check=True,
    )

    with pytest.raises(RuntimeError, match="cannot parse GitHub"):
        resolve_module_repository_from_git(repo)
