from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from repave_engine.github import GitHubError
from repave_engine.pr import create_pull_request, plan_pull_request
from repave_engine.settings import OutputConfig
from repave_engine.target_repo import resolve_module_repository


def _repository(tmp_path: Path):
    config = OutputConfig(github_org="example-org", modules_root=tmp_path / "modules")
    return resolve_module_repository(
        module_name="networking-vnet",
        config=config,
        name_template="tf-{module_name}",
    )


def test_plan_pull_request_fields(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    plan = plan_pull_request(
        module_name="networking-vnet",
        blueprint_name="terraform-module-generic",
        blueprint_version="0.2.0",
        standard_version="0.1.0",
        files_root=repository.local_path,
        repository=repository,
    )

    assert plan.branch == "main"
    assert "networking-vnet" in plan.title
    assert "terraform-module-generic" in plan.body
    assert repository.web_url in plan.body
    assert plan.files_root == repository.local_path


def test_create_pull_request_dry_run(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    plan = plan_pull_request(
        module_name="example",
        blueprint_name="terraform-module-generic",
        blueprint_version="0.2.0",
        standard_version="0.1.0",
        files_root=repository.local_path,
        repository=repository,
    )

    message = create_pull_request(plan, github_token=None)

    assert "Dry-run" in message
    assert repository.web_url in message
    assert plan.title in message


def test_create_pull_request_publishes_to_github(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    plan = plan_pull_request(
        module_name="example",
        blueprint_name="terraform-module-generic",
        blueprint_version="0.2.0",
        standard_version="0.1.0",
        files_root=repository.local_path,
        repository=repository,
    )

    with (
        patch("repave_engine.pr.ensure_github_repository", return_value="created") as ensure,
        patch(
            "repave_engine.pr.push_module_repository",
        ) as push,
    ):
        message = create_pull_request(plan, github_token="ghp_test")

    ensure.assert_called_once()
    push.assert_called_once()
    assert "Created GitHub repository and pushed initial commit" in message
    assert repository.web_url in message


def test_create_pull_request_reports_github_errors(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    plan = plan_pull_request(
        module_name="example",
        blueprint_name="terraform-module-generic",
        blueprint_version="0.2.0",
        standard_version="0.1.0",
        files_root=repository.local_path,
        repository=repository,
    )

    with patch(
        "repave_engine.pr.ensure_github_repository",
        side_effect=GitHubError(403, "forbidden"),
    ):
        message = create_pull_request(plan, github_token="ghp_test")

    assert "GitHub publish failed" in message
    assert "403" in message
