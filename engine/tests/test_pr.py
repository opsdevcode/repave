from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from repave_engine.github import GitHubError
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
        "provider_services": "vpc,s3",
    }
    values.update(overrides)
    return values


def test_format_output_template_renders_input_placeholders() -> None:
    title = format_output_template(
        "Bootstrap {cloud_provider} module {module_name} ({provider_services})",
        _module_values(),
    )
    assert title == "Bootstrap aws module networking-vnet (vpc,s3)"


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

    assert plan.title == "Bootstrap aws module networking-vnet (vpc,s3)"
    assert "module_name: `networking-vnet`" in plan.body
    assert "provider_services: `vpc,s3`" in plan.body
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
    assert plan.title in message


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
