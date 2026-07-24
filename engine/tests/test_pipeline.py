from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from repave_engine.pipeline import generate_from_blueprint, generate_from_path
from repave_engine.target_repo import resolve_module_repository


def test_generate_terraform_module_generic_publishes_module_repo(
    terraform_blueprint,
    sample_inputs,
    output_config,
    staging_root,
) -> None:
    result = generate_from_blueprint(
        terraform_blueprint,
        sample_inputs,
        output_config=output_config,
        dry_run=False,
        staging_root=staging_root,
    )

    module_repo = result.module_repository
    assert module_repo is not None
    assert module_repo.name == "tf-aws-example"
    assert module_repo.local_path.exists()
    assert (module_repo.local_path / "ec2_diff.tf").exists()
    assert (module_repo.local_path / "s3_bucket.tf").exists()
    assert (module_repo.local_path / "locals.tf").exists()
    assert not (module_repo.local_path / "main.tf").exists()
    assert (module_repo.local_path / "README.md").exists()
    assert "example" in (module_repo.local_path / "README.md").read_text(encoding="utf-8")
    assert not (module_repo.local_path / ".terraform").exists()
    assert (module_repo.local_path / ".git").exists()
    assert result.pr_plan is not None
    assert result.pr_plan.repository.web_url.endswith("/tf-aws-example")
    assert all(g.passed or g.skipped for g in result.gates)


def test_generate_from_path(
    repo_root: Path,
    sample_inputs,
    output_config,
    staging_root,
) -> None:
    result = generate_from_path(
        repo_root / "blueprints" / "terraform-module-generic",
        sample_inputs,
        repo_root=repo_root,
        output_config=output_config,
        dry_run=False,
        staging_root=staging_root,
    )

    assert result.blueprint.name == "terraform-module-generic"
    assert result.module_repository is not None
    assert result.module_repository.local_path.exists()


def test_dry_run_does_not_write_module_repo(
    terraform_blueprint,
    sample_inputs,
    output_config,
    staging_root,
) -> None:
    result = generate_from_blueprint(
        terraform_blueprint,
        sample_inputs,
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
    )

    assert result.module_repository is not None
    assert not result.module_repository.local_path.exists()
    assert "Dry-run" in result.pr_message
    assert result.dry_run is True
    paths = {item.path for item in result.rendered_files}
    assert "ec2_diff.tf" in paths
    assert "s3_bucket.tf" in paths
    assert "locals.tf" in paths
    assert "README.md" in paths
    assert "main.tf" not in paths
    assert any(
        item.path == "ec2_diff.tf" and "null_resource" in item.content
        for item in result.rendered_files
    )
    assert not any(item.path.startswith(".terraform/") for item in result.rendered_files)
    assert ".terraform.lock.hcl" not in paths


def test_gate_failure_blocks_module_repo_publish(
    terraform_blueprint,
    sample_inputs,
    output_config,
    staging_root,
    monkeypatch,
) -> None:
    from repave_engine.gates import GateResult

    monkeypatch.setattr(
        "repave_engine.pipeline.run_gates",
        lambda *_args, **_kwargs: [GateResult("docs-drift", False, False, "failed")],
    )

    result = generate_from_blueprint(
        terraform_blueprint,
        sample_inputs,
        output_config=output_config,
        dry_run=False,
        staging_root=staging_root,
    )

    assert result.module_repository is None
    assert result.pr_plan is None
    assert "Gates failed" in result.pr_message


def test_non_dry_run_passes_github_token(
    terraform_blueprint,
    sample_inputs,
    output_config,
    staging_root,
    monkeypatch,
) -> None:
    messages: list[str] = []

    def fake_create_pr(plan, *, github_token):
        messages.append(github_token or "")
        return "created"

    monkeypatch.setattr("repave_engine.pipeline.create_pull_request", fake_create_pr)

    result = generate_from_blueprint(
        terraform_blueprint,
        sample_inputs,
        output_config=output_config,
        dry_run=False,
        github_token="ghp_test",
        staging_root=staging_root,
    )

    assert "created" in result.pr_message
    assert messages == ["ghp_test"]


def test_generate_publishes_to_github_through_create_pull_request(
    terraform_blueprint,
    sample_inputs,
    output_config,
    staging_root,
    monkeypatch,
) -> None:
    with (
        patch("repave_engine.pr.ensure_github_repository", return_value="created"),
        patch("repave_engine.pr.push_module_repository"),
    ):
        result = generate_from_blueprint(
            terraform_blueprint,
            sample_inputs,
            output_config=output_config,
            dry_run=False,
            github_token="ghp_test",
            staging_root=staging_root,
        )

    assert "Created GitHub repository and pushed initial commit" in result.pr_message
    assert result.module_repository is not None
    assert result.module_repository.local_path.exists()


def test_resolve_module_repository_uses_template(output_config) -> None:
    repository = resolve_module_repository(
        module_name="networking",
        config=output_config,
        name_template="tf-{cloud_provider}-{module_name}",
        template_values={"cloud_provider": "aws"},
    )

    assert repository.name == "tf-aws-networking"
    assert repository.local_path == output_config.modules_root / "tf-aws-networking"
    assert repository.web_url == "https://github.com/example-org/tf-aws-networking"


def test_publish_refuses_existing_nonempty_repo(
    terraform_blueprint,
    sample_inputs,
    output_config,
    staging_root,
) -> None:
    repo_path = output_config.modules_root / "tf-aws-example"
    repo_path.mkdir(parents=True)
    (repo_path / "existing.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        generate_from_blueprint(
            terraform_blueprint,
            sample_inputs,
            output_config=output_config,
            dry_run=False,
            staging_root=staging_root,
        )


def test_generate_applies_gate_overrides_from_config(
    tmp_path: Path,
    terraform_blueprint,
    sample_inputs,
    output_config,
    staging_root,
    monkeypatch,
) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "output:",
                "  github_org: acme",
                "  modules_root: ../modules",
                "gates:",
                "  checkov:",
                "    skip_checks:",
                "      - CKV_TEST",
            ]
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def fake_run_gates(
        output_dir,
        gate_names,
        *,
        blueprint=None,
        gate_overrides=None,
    ):
        captured["gate_overrides"] = gate_overrides
        from repave_engine.gates import GateResult

        return [GateResult("docs-drift", True, False, "ok")]

    monkeypatch.setattr("repave_engine.pipeline.run_gates", fake_run_gates)

    generate_from_blueprint(
        terraform_blueprint,
        sample_inputs,
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=tmp_path,
    )

    overrides = captured["gate_overrides"]
    assert overrides is not None
    assert overrides.checkov_skip_checks == ("CKV_TEST",)


def test_generate_ansible_role_generic_publishes_role_repo(
    ansible_blueprint,
    ansible_sample_inputs,
    output_config,
    staging_root,
) -> None:
    result = generate_from_blueprint(
        ansible_blueprint,
        ansible_sample_inputs,
        output_config=output_config,
        dry_run=False,
        staging_root=staging_root,
    )

    role_repo = result.module_repository
    assert role_repo is not None
    assert role_repo.name == "ansible-role-webserver"
    assert role_repo.local_path.exists()
    assert (role_repo.local_path / "meta" / "main.yml").exists()
    assert (role_repo.local_path / "molecule" / "default" / "converge.yml").exists()
    assert (role_repo.local_path / "repave.yaml").exists()
    assert not (role_repo.local_path / ".molecule").exists()
    assert (role_repo.local_path / ".git").exists()
    assert result.pr_plan is not None
    assert all(g.passed or g.skipped for g in result.gates)
