from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from repave_engine.blueprint import Blueprint
from repave_engine.pipeline import _fleet_message_after_github_repo_publish
from repave_engine.settings import FleetConfig, OutputConfig
from repave_engine.target_repo import resolve_module_repository


def _blueprint() -> Blueprint:
    return Blueprint(
        path=Path("blueprints/github-repo-generic"),
        name="github-repo-generic",
        version="0.2.0",
        description="test",
        artifact_type="github-repo",
        standard_source="standards/github/repo-provisioning-standard.md",
        standard_version="1.1.0",
        inputs=(),
        template_engine="copier",
        template_path="template",
        gates=(),
        output_type="pull_request",
        output_repo_name_template="{repo_name}",
        output_title_template="Provision {repo_name}",
        provenance_file="repave.yaml",
    )


def test_fleet_message_when_disabled(tmp_path: Path) -> None:
    config = OutputConfig(github_org="example-org", modules_root=tmp_path / "modules")
    repository = resolve_module_repository(
        module_name="platform-demo",
        config=config,
        name_template="{repo_name}",
        template_values={"repo_name": "platform-demo"},
    )
    message = _fleet_message_after_github_repo_publish(
        repo_root=tmp_path,
        blueprint=_blueprint(),
        repository=repository,
    )
    assert "Fleet disabled" in message
    assert "GoldenPathRepo" in message


def test_fleet_message_registers_when_enabled(tmp_path: Path) -> None:
    config = OutputConfig(github_org="example-org", modules_root=tmp_path / "modules")
    repository = resolve_module_repository(
        module_name="platform-demo",
        config=config,
        name_template="{repo_name}",
        template_values={"repo_name": "platform-demo"},
    )
    fleet_file = tmp_path / "fleet.jsonl"
    with (
        patch(
            "repave_engine.pipeline.load_fleet_config",
            return_value=FleetConfig(enabled=True, file=fleet_file),
        ),
        patch("repave_engine.pipeline.register_repo") as register,
    ):
        message = _fleet_message_after_github_repo_publish(
            repo_root=tmp_path,
            blueprint=_blueprint(),
            repository=repository,
        )
    assert message.startswith("Fleet registered:")
    register.assert_called_once()
    entry = register.call_args.args[1]
    assert entry.repo_url == repository.web_url
    assert entry.blueprint_name == "github-repo-generic"
    assert entry.blueprint_version == "0.2.0"
