from __future__ import annotations

from repave_engine.blueprint import blueprint_dir, load_blueprint
from repave_engine.pipeline import _summarize_publish_message
from repave_engine.portal_generate import publish_target_for_run
from repave_engine.settings import OutputConfig
from repave_engine.target_repo import ModuleRepository


def test_publish_target_for_run_resolves_repo(repo_root, output_config, sample_inputs) -> None:
    blueprint = load_blueprint(
        blueprint_dir(repo_root, "terraform-module-generic"),
        repo_root=repo_root,
    )
    target = publish_target_for_run(
        blueprint=blueprint,
        payload={"inputs": sample_inputs},
        output_config=output_config,
    )
    assert target is not None
    assert target.name.startswith("tf-")
    assert target.org == output_config.github_org
    assert target.url.endswith(f"/{target.name}")


def test_summarize_publish_message_plan_mode() -> None:
    repository = ModuleRepository(
        name="tf-demo",
        owner="opsdevcode",
        local_path=__import__("pathlib").Path("/tmp/tf-demo"),
        clone_url="https://github.com/opsdevcode/tf-demo.git",
        web_url="https://github.com/opsdevcode/tf-demo",
    )
    summary = _summarize_publish_message(
        dry_run=True,
        repository=repository,
        pr_message="Dry-run: remote GitHub repository not created.",
    )
    assert "no GitHub repo created" in summary
    assert "tf-demo" in summary


def test_summarize_publish_message_apply_success() -> None:
    repository = ModuleRepository(
        name="tf-demo",
        owner="opsdevcode",
        local_path=__import__("pathlib").Path("/tmp/tf-demo"),
        clone_url="https://github.com/opsdevcode/tf-demo.git",
        web_url="https://github.com/opsdevcode/tf-demo",
    )
    summary = _summarize_publish_message(
        dry_run=False,
        repository=repository,
        pr_message="Created GitHub repository and pushed initial commit.",
    )
    assert summary.startswith("Created https://github.com/opsdevcode/tf-demo")
