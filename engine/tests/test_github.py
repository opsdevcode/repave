from __future__ import annotations

import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from repave_engine.github import (
    GitHubError,
    ensure_github_repository,
    push_module_repository,
)
from repave_engine.settings import OutputConfig
from repave_engine.target_repo import ModuleRepository, resolve_module_repository


def _repository(tmp_path: Path) -> ModuleRepository:
    config = OutputConfig(github_org="example-org", modules_root=tmp_path / "modules")
    return resolve_module_repository(
        module_name="networking",
        config=config,
        name_template="tf-{cloud_provider}-{module_name}",
        template_values={"cloud_provider": "aws"},
    )


def test_ensure_github_repository_returns_exists_when_repo_present(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    with patch("repave_engine.github._github_request") as request:
        request.return_value = {"name": repository.name}
        action = ensure_github_repository(repository, "ghp_test")

    assert action == "exists"
    request.assert_called_once_with(
        "GET",
        f"/repos/{repository.owner}/{repository.name}",
        "ghp_test",
    )


def test_ensure_github_repository_creates_org_repo(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    with (
        patch("repave_engine.github._repository_exists", return_value=False),
        patch(
            "repave_engine.github._create_org_repository",
        ) as create_org,
    ):
        action = ensure_github_repository(repository, "ghp_test")

    assert action == "created"
    create_org.assert_called_once()


def test_ensure_github_repository_falls_back_to_user_repo(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    with (
        patch("repave_engine.github._repository_exists", return_value=False),
        patch(
            "repave_engine.github._create_org_repository",
            side_effect=GitHubError(404, "org not found"),
        ),
        patch("repave_engine.github._create_user_repository") as create_user,
    ):
        action = ensure_github_repository(repository, "ghp_test")

    assert action == "created"
    create_user.assert_called_once()


def test_push_module_repository_adds_remote_and_pushes(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.local_path.mkdir(parents=True)

    with (
        patch("repave_engine.github._git_executable", return_value="git"),
        patch(
            "repave_engine.github.subprocess.run",
        ) as run,
        patch("repave_engine.github._run_git") as run_git,
    ):
        run.return_value = MagicMock(stdout="")
        push_module_repository(repository, "ghp_test")

    run.assert_called_once()
    assert run_git.call_args_list[0].args[0][:2] == ["remote", "add"]
    assert run_git.call_args_list[1].args[0] == ["branch", "-M", "main"]
    assert run_git.call_args_list[2].args[0] == ["push", "-u", "origin", "main"]


def test_github_request_raises_github_error_on_http_failure() -> None:
    from repave_engine.github import _github_request

    http_error = urllib.error.HTTPError(
        "https://api.github.com/orgs/example/repos",
        403,
        "Forbidden",
        {},
        BytesIO(b"forbidden"),
    )

    with (
        patch("urllib.request.urlopen", side_effect=http_error),
        pytest.raises(
            GitHubError,
            match="forbidden",
        ),
    ):
        _github_request("POST", "/orgs/example/repos", "ghp_test", {"name": "demo"})
