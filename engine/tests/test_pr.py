from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from repave_engine.github import GitHubError
from repave_engine.github_repo_provision import build_provision_spec
from repave_engine.output_template import format_output_template
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


def _module_values(**overrides: str) -> dict[str, str]:
    values = {
        "module_name": "networking-vnet",
        "description": "VPC networking scaffold",
        "cloud_provider": "aws",
        "provider_services": "ec2,s3",
    }
    values.update(overrides)
    return values


def test_format_output_template_renders_input_placeholders() -> None:
    title = format_output_template(
        "Bootstrap {cloud_provider} module {module_name} ({provider_services})",
        _module_values(),
    )
    assert title == "Bootstrap aws module networking-vnet (ec2,s3)"


def test_format_output_template_rejects_unknown_placeholder() -> None:
    with pytest.raises(ValueError, match="unknown input placeholder"):
        format_output_template("Bootstrap {missing}", _module_values())


def test_plan_pull_request_title_uses_input_template(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    values = _module_values()
    plan = plan_pull_request(
        blueprint_name="terraform-module-generic",
        blueprint_version="0.2.0",
        standard_version="0.1.0",
        title_template="Bootstrap {cloud_provider} module {module_name} ({provider_services})",
        input_fields=("module_name", "description", "cloud_provider", "provider_services"),
        files_root=repository.local_path,
        repository=repository,
        module_values=values,
    )

    assert plan.title == "Bootstrap aws module networking-vnet (ec2,s3)"
    assert "module_name: `networking-vnet`" in plan.body
    assert "provider_services: `ec2,s3`" in plan.body
    assert repository.web_url in plan.body


def test_create_pull_request_dry_run(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    plan = plan_pull_request(
        blueprint_name="terraform-module-generic",
        blueprint_version="0.2.0",
        standard_version="0.1.0",
        title_template="Bootstrap {module_name}",
        input_fields=("module_name", "description"),
        files_root=repository.local_path,
        repository=repository,
        module_values=_module_values(),
    )

    message = create_pull_request(plan, github_token=None)

    assert "Dry-run" in message
    assert repository.web_url in message
    assert f"Repository name: {repository.name}" in message


def test_create_pull_request_publishes_to_github(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    plan = plan_pull_request(
        blueprint_name="terraform-module-generic",
        blueprint_version="0.2.0",
        standard_version="0.1.0",
        title_template="Bootstrap {module_name}",
        input_fields=("module_name", "description"),
        files_root=repository.local_path,
        repository=repository,
        module_values=_module_values(),
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
        blueprint_name="terraform-module-generic",
        blueprint_version="0.2.0",
        standard_version="0.1.0",
        title_template="Bootstrap {module_name}",
        input_fields=("module_name", "description"),
        files_root=repository.local_path,
        repository=repository,
        module_values=_module_values(),
    )

    with patch(
        "repave_engine.pr.ensure_github_repository",
        side_effect=GitHubError(403, "forbidden"),
    ):
        message = create_pull_request(plan, github_token="ghp_test")

    assert "GitHub publish failed" in message
    assert "403" in message


def test_create_pull_request_existing_remote_repo_message(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    plan = plan_pull_request(
        blueprint_name="terraform-module-generic",
        blueprint_version="0.2.0",
        standard_version="0.1.0",
        title_template="Bootstrap {module_name}",
        input_fields=("module_name", "description"),
        files_root=repository.local_path,
        repository=repository,
        module_values=_module_values(),
    )

    with (
        patch("repave_engine.pr.ensure_github_repository", return_value="exists"),
        patch("repave_engine.pr.push_module_repository"),
    ):
        message = create_pull_request(plan, github_token="ghp_test")

    assert "Pushed initial commit to existing GitHub repository" in message


def test_create_pull_request_reports_push_runtime_error(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    plan = plan_pull_request(
        blueprint_name="terraform-module-generic",
        blueprint_version="0.2.0",
        standard_version="0.1.0",
        title_template="Bootstrap {module_name}",
        input_fields=("module_name", "description"),
        files_root=repository.local_path,
        repository=repository,
        module_values=_module_values(),
    )

    with (
        patch("repave_engine.pr.ensure_github_repository", return_value="created"),
        patch(
            "repave_engine.pr.push_module_repository",
            side_effect=RuntimeError("git failed"),
        ),
    ):
        message = create_pull_request(plan, github_token="ghp_test")

    assert "GitHub publish failed while pushing" in message
    assert "git failed" in message


def test_create_pull_request_provision_dry_run(tmp_path: Path) -> None:
    config = OutputConfig(github_org="example-org", modules_root=tmp_path / "modules")
    repository = resolve_module_repository(
        module_name="platform-demo",
        config=config,
        name_template="{repo_name}",
        template_values={"repo_name": "platform-demo"},
    )
    values = {
        "repo_name": "platform-demo",
        "create_mode": "selection",
        "visibility": "private",
        "team_slugs": "platform",
        "team_permission": "push",
    }
    provision = build_provision_spec(repository=repository, values=values)
    plan = plan_pull_request(
        blueprint_name="github-repo-generic",
        blueprint_version="0.1.0",
        standard_version="1.0.0",
        title_template="Provision GitHub repository {repo_name}",
        input_fields=("repo_name", "create_mode", "visibility", "team_slugs"),
        files_root=repository.local_path,
        repository=repository,
        module_values=values,
        provision=provision,
    )
    message = create_pull_request(plan, github_token=None)
    assert "Dry-run: GitHub repository not provisioned" in message
    assert "Would create example-org/platform-demo via selection" in message
    assert "Would grant team 'platform' push" in message


def test_create_pull_request_provision_apply(tmp_path: Path) -> None:
    config = OutputConfig(github_org="example-org", modules_root=tmp_path / "modules")
    repository = resolve_module_repository(
        module_name="platform-demo",
        config=config,
        name_template="{repo_name}",
        template_values={"repo_name": "platform-demo"},
    )
    values = {
        "repo_name": "platform-demo",
        "create_mode": "selection",
        "visibility": "private",
        "team_slugs": "platform",
        "team_permission": "push",
        "ruleset_profile": "default-pr",
        "membership_source_team": "source",
    }
    provision = build_provision_spec(repository=repository, values=values)
    plan = plan_pull_request(
        blueprint_name="github-repo-generic",
        blueprint_version="0.2.0",
        standard_version="1.1.0",
        title_template="Provision GitHub repository {repo_name}",
        input_fields=("repo_name",),
        files_root=repository.local_path,
        repository=repository,
        module_values=values,
        provision=provision,
    )
    from repave_engine.github_repo_provision import (
        RepoCreateResult,
        RulesetApplyResult,
        TeamGrantResult,
        TeamSyncResult,
    )

    with (
        patch(
            "repave_engine.pr.create_github_repository",
            return_value=RepoCreateResult(
                status="created",
                owner="example-org",
                name="platform-demo",
                web_url="https://github.com/example-org/platform-demo",
                create_mode="selection",
                visibility="private",
                message="Created example-org/platform-demo (visibility=private)",
            ),
        ),
        patch(
            "repave_engine.pr.apply_repository_ruleset",
            return_value=RulesetApplyResult(
                profile="default-pr",
                status="applied",
                message=(
                    "Applied ruleset 'repave-default-pr' (default-pr) on example-org/platform-demo"
                ),
            ),
        ),
        patch(
            "repave_engine.pr.sync_and_grant_teams",
            return_value=(
                (
                    TeamSyncResult(
                        team_slug="platform",
                        status="synced",
                        members_added=2,
                        message="Synced 2 member(s) from 'source' into 'platform' (team exists)",
                    ),
                ),
                (
                    TeamGrantResult(
                        team_slug="platform",
                        permission="push",
                        status="granted",
                        message="Granted team 'platform' push on example-org/platform-demo",
                    ),
                ),
            ),
        ),
        patch("repave_engine.pr.push_module_repository") as push,
    ):
        message = create_pull_request(plan, github_token="ghp_test")

    push.assert_called_once()
    assert "Created example-org/platform-demo" in message
    assert "Overlay push: pushed" in message
    assert "Applied ruleset" in message
    assert "Synced 2 member(s)" in message
    assert "Granted team 'platform' push" in message


def test_create_pull_request_provision_dry_run_mentions_ruleset(tmp_path: Path) -> None:
    config = OutputConfig(github_org="example-org", modules_root=tmp_path / "modules")
    repository = resolve_module_repository(
        module_name="platform-demo",
        config=config,
        name_template="{repo_name}",
        template_values={"repo_name": "platform-demo"},
    )
    values = {
        "repo_name": "platform-demo",
        "create_mode": "selection",
        "visibility": "private",
        "ruleset_profile": "default-pr",
    }
    provision = build_provision_spec(repository=repository, values=values)
    plan = plan_pull_request(
        blueprint_name="github-repo-generic",
        blueprint_version="0.2.0",
        standard_version="1.1.0",
        title_template="Provision GitHub repository {repo_name}",
        input_fields=("repo_name",),
        files_root=repository.local_path,
        repository=repository,
        module_values=values,
        provision=provision,
    )
    message = create_pull_request(plan, github_token=None)
    assert "Would apply ruleset profile default-pr" in message
