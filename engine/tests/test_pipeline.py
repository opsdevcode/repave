from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from repave_engine.blueprint import load_blueprint, validate_inputs
from repave_engine.pipeline import generate_from_blueprint, generate_from_path
from repave_engine.target_repo import resolve_module_repository

pytestmark = pytest.mark.slow


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
    workflow = module_repo.local_path / ".github" / "workflows" / "terraform-gates.yml"
    assert workflow.is_file()
    assert "repave gates --path ." in workflow.read_text(encoding="utf-8")
    assert result.pr_plan is not None
    assert result.pr_plan.repository.web_url.endswith("/tf-aws-example")
    assert all(g.passed or g.skipped for g in result.gates)


def test_generate_terraform_module_resource_single_file(
    repo_root: Path,
    resource_module_inputs,
    output_config,
    staging_root,
) -> None:
    from repave_engine.blueprint import load_blueprint

    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-module-resource",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        resource_module_inputs,
        output_config=output_config,
        dry_run=False,
        staging_root=staging_root,
    )

    module_repo = result.module_repository
    assert module_repo is not None
    assert module_repo.name == "tfm-aws-s3-acme-bucket"
    assert (module_repo.local_path / "s3_bucket.tf").exists()
    assert not (module_repo.local_path / "ec2_diff.tf").exists()
    assert (module_repo.local_path / "repave.yaml").exists()
    provenance = (module_repo.local_path / "repave.yaml").read_text(encoding="utf-8")
    assert "provider_service: s3" in provenance or '"provider_service": "s3"' in provenance
    assert all(g.passed or g.skipped for g in result.gates)


def test_generate_terraform_environment_stack_publishes_repo(
    repo_root: Path,
    env_stack_inputs,
    output_config,
    staging_root,
) -> None:
    from repave_engine.blueprint import load_blueprint

    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-environment-stack",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        env_stack_inputs,
        output_config=output_config,
        dry_run=False,
        staging_root=staging_root,
        repo_root=repo_root,
    )

    module_repo = result.module_repository
    assert module_repo is not None
    assert module_repo.name == "env-aws-platform"
    assert (module_repo.local_path / "main.tf").exists()
    assert (module_repo.local_path / "modules" / "_example" / "main.tf").exists()
    assert (module_repo.local_path / "repave.yaml").exists()
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
                "  infracost:",
                "    required: true",
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
        require_run=False,
        on_event=None,
        **_kwargs,
    ):
        captured["gate_overrides"] = gate_overrides
        captured["gate_names"] = gate_names
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
    assert "infracost" in captured["gate_names"]


def test_generate_ansible_playbook_project_publishes_repo(
    repo_root: Path,
    ansible_playbook_sample_inputs,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "ansible-playbook-project",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        ansible_playbook_sample_inputs,
        output_config=output_config,
        dry_run=False,
        staging_root=staging_root,
        repo_root=repo_root,
    )

    module_repo = result.module_repository
    assert module_repo is not None
    assert module_repo.name == "ansible-playbook-baseline"
    assert (module_repo.local_path / "site.yml").exists()
    assert (module_repo.local_path / "inventories" / "dev" / "hosts.yml").exists()
    assert (module_repo.local_path / "requirements.yml").exists()
    assert (module_repo.local_path / "repave.yaml").exists()
    assert all(g.passed or g.skipped for g in result.gates)


def test_generate_ansible_playbook_linux_patch_pattern_dry_run(
    repo_root: Path,
    ansible_playbook_sample_inputs,
    output_config,
    staging_root,
) -> None:
    import yaml

    blueprint = load_blueprint(
        repo_root / "blueprints" / "ansible-playbook-project",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        ansible_playbook_sample_inputs,
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
    )
    output_dir = result.render.output_dir
    site = (output_dir / "site.yml").read_text(encoding="utf-8")
    assert "hosts: linux" in site
    assert "ansible.builtin.dnf" in site
    hosts = output_dir / "inventories" / "dev" / "hosts.yml"
    assert hosts.is_file()
    assert "linux:" in hosts.read_text(encoding="utf-8")
    spec = yaml.safe_load((output_dir / "repave.yaml").read_text(encoding="utf-8"))["spec"]
    assert spec["ansiblePlaybookProject"]["playbook_pattern_source"] == "linux-patch-baseline"


def test_generate_ansible_playbook_pinned_roles_rollout_dry_run(
    repo_root: Path,
    ansible_playbook_sample_inputs,
    output_config,
    staging_root,
) -> None:
    import yaml

    blueprint = load_blueprint(
        repo_root / "blueprints" / "ansible-playbook-project",
        repo_root=repo_root,
    )
    inputs = {
        **ansible_playbook_sample_inputs,
        "playbook_pattern_source": "pinned-roles-rollout",
        "pinned_roles": (
            '[{"galaxy_name":"acme.web","version":"1.0.0",'
            '"src":"https://github.com/acme/ansible-role-web",'
            '"repo_name":"ansible-role-web"}]'
        ),
    }
    result = generate_from_blueprint(
        blueprint,
        inputs,
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
    )
    output_dir = result.render.output_dir
    site = (output_dir / "site.yml").read_text(encoding="utf-8")
    assert "role: acme.web" in site
    assert 'serial: "1"' in site or "serial: 1" in site
    vars_text = (output_dir / "group_vars" / "all" / "vars.yml").read_text(encoding="utf-8")
    assert "playbook_rollout_serial: 1" in vars_text
    spec = yaml.safe_load((output_dir / "repave.yaml").read_text(encoding="utf-8"))["spec"]
    assert spec["ansiblePlaybookProject"]["playbook_pattern_source"] == "pinned-roles-rollout"


def test_generate_ansible_collection_publishes_repo(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "ansible-collection-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "namespace": "acme",
            "collection_name": "platform",
            "description": "Platform collection",
            "min_ansible_version": "2.18",
        },
        output_config=output_config,
        dry_run=False,
        staging_root=staging_root,
        repo_root=repo_root,
    )

    module_repo = result.module_repository
    assert module_repo is not None
    assert module_repo.name == "ansible-collection-acme-platform"
    assert (module_repo.local_path / "galaxy.yml").exists()
    assert (module_repo.local_path / "roles" / "sample" / "tasks" / "main.yml").exists()
    assert (module_repo.local_path / "repave.yaml").exists()
    spec = yaml.safe_load((module_repo.local_path / "repave.yaml").read_text(encoding="utf-8"))[
        "spec"
    ]
    assert spec["artifactType"] == "ansible-collection"
    assert spec["ansibleCollection"]["namespace"] == "acme"
    assert all(g.passed or g.skipped for g in result.gates)


def test_generate_ansible_collection_linux_service_sample_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    import yaml

    blueprint = load_blueprint(
        repo_root / "blueprints" / "ansible-collection-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "namespace": "acme",
            "collection_name": "platform",
            "description": "Platform collection",
            "sample_role_name": "sample",
            "min_ansible_version": "2.18",
            "support_linux": "true",
            "support_windows": "false",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
    )
    output_dir = result.render.output_dir
    main_yml = (output_dir / "roles" / "sample" / "tasks" / "main.yml").read_text(encoding="utf-8")
    assert "ansible.builtin.package" in main_yml
    spec = yaml.safe_load((output_dir / "repave.yaml").read_text(encoding="utf-8"))["spec"]
    assert spec["ansibleCollection"]["sample_role_pattern_source"] == "linux-service"


def test_generate_ansible_role_linux_service_pattern_dry_run(
    ansible_blueprint,
    ansible_sample_inputs,
    output_config,
    staging_root,
) -> None:
    result = generate_from_blueprint(
        ansible_blueprint,
        ansible_sample_inputs,
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
    )
    output_dir = result.render.output_dir
    run_yml = (output_dir / "tasks" / "run.yml").read_text(encoding="utf-8")
    assert "ansible.builtin.package" in run_yml
    assert (output_dir / "requirements.yml").is_file()
    verify = (output_dir / "molecule" / "default" / "verify.yml").read_text(encoding="utf-8")
    assert "package_facts" in verify
    spec = yaml.safe_load((output_dir / "repave.yaml").read_text(encoding="utf-8"))["spec"]
    assert spec["ansibleRole"]["role_pattern_source"] == "linux-service"


def test_generate_ansible_role_windows_service_pattern_dry_run(
    ansible_blueprint,
    output_config,
    staging_root,
) -> None:
    inputs = {
        "role_name": "iis",
        "namespace": "acme",
        "description": "Windows IIS-style service role",
        "min_ansible_version": "2.18",
        "support_linux": "false",
        "support_windows": "true",
        "windows_server_generation": "2022",
        "target_platforms_advanced": "",
        "role_pattern_source": "windows-service",
    }
    result = generate_from_blueprint(
        ansible_blueprint,
        inputs,
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
    )
    output_dir = result.render.output_dir
    run_yml = (output_dir / "tasks" / "run.yml").read_text(encoding="utf-8")
    assert "ansible.windows." in run_yml
    req = (output_dir / "requirements.yml").read_text(encoding="utf-8")
    assert "ansible.windows" in req
    assert not (output_dir / "molecule" / "default" / "molecule.yml").is_file()
    assert (output_dir / "molecule" / "windows" / "molecule.yml").is_file()
    spec = yaml.safe_load((output_dir / "repave.yaml").read_text(encoding="utf-8"))["spec"]
    assert spec["ansibleRole"]["role_pattern_source"] == "windows-service"
    assert "ansible.windows" in spec["ansibleRole"]["required_collections"]


def test_generate_ansible_role_managed_local_account_dry_run(
    ansible_blueprint,
    output_config,
    staging_root,
) -> None:
    inputs = {
        "role_name": "svcacct",
        "namespace": "acme",
        "description": "Cross-platform service account role",
        "min_ansible_version": "2.18",
        "support_linux": "true",
        "support_windows": "true",
        "windows_server_generation": "2022",
        "target_platforms_advanced": "",
        "role_pattern_source": "managed-local-account",
    }
    result = generate_from_blueprint(
        ansible_blueprint,
        inputs,
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
    )
    output_dir = result.render.output_dir
    run_yml = (output_dir / "tasks" / "run.yml").read_text(encoding="utf-8")
    assert "ansible.builtin.user" in run_yml
    assert "ansible.windows.win_user" in run_yml
    spec = yaml.safe_load((output_dir / "repave.yaml").read_text(encoding="utf-8"))["spec"]
    assert spec["ansibleRole"]["role_pattern_source"] == "managed-local-account"


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


def test_generate_helm_chart_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "helm-chart-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "chart_name": "api",
            "app_name": "api",
            "owner": "platform-engineering",
            "description": "HTTP API",
            "image_repository": "ghcr.io/acme/api",
            "image_tag": "1.2.3",
            "service_type": "ClusterIP",
            "enable_ingress": "false",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )

    output_dir = result.render.output_dir
    assert (output_dir / "Chart.yaml").is_file()
    assert (output_dir / "values.yaml").is_file()
    assert (output_dir / "templates" / "deployment.yaml").is_file()
    assert (output_dir / "repave.yaml").is_file()
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "## Provenance" in readme
    assert "helm-chart-generic" in readme
    spec = yaml.safe_load((output_dir / "repave.yaml").read_text(encoding="utf-8"))["spec"]
    assert spec["artifactType"] == "helm-chart"
    assert spec["helmChart"]["chart_name"] == "api"
    lint = next(g for g in result.gates if g.name == "helm-lint")
    template = next(g for g in result.gates if g.name == "helm-template")
    assert lint.passed or lint.skipped
    assert template.passed or template.skipped
    assert all(g.passed or g.skipped for g in result.gates)


def test_generate_app_service_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "app-service-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "service_name": "checkout-api",
            "description": "Checkout HTTP API",
            "owner": "team:payments",
            "port": "8080",
            "runtime": "python",
            "include_helm_reference": "false",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )

    output_dir = result.render.output_dir
    assert (output_dir / "Dockerfile").is_file()
    assert (output_dir / "catalog-info.yaml").is_file()
    assert (output_dir / "RUNBOOK.md").is_file()
    catalog = yaml.safe_load((output_dir / "catalog-info.yaml").read_text(encoding="utf-8"))
    assert catalog["metadata"]["name"] == "checkout-api"
    assert catalog["spec"]["owner"] == "team:payments"
    assert catalog["metadata"]["annotations"]["repave.dev/blueprint"] == "app-service-generic"
    assert (output_dir / "src" / "app" / "main.py").is_file()
    assert (output_dir / ".github" / "workflows" / "repave-gates.yml").is_file()
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "## Provenance" in readme
    spec = yaml.safe_load((output_dir / "repave.yaml").read_text(encoding="utf-8"))["spec"]
    assert spec["artifactType"] == "app-service"
    assert spec["appService"]["service_name"] == "checkout-api"
    assert spec["appService"].get("layout", "http-api") == "http-api"
    assert all(g.passed or g.skipped for g in result.gates)


def test_generate_app_service_go_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "app-service-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "service_name": "payments-api",
            "description": "Payments HTTP API",
            "owner": "team:payments",
            "system": "payments",
            "catalog_lifecycle": "production",
            "port": "8080",
            "runtime": "go",
            "include_helm_reference": "false",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )

    output_dir = result.render.output_dir
    assert (output_dir / "go.mod").is_file()
    assert "module " in (output_dir / "go.mod").read_text(encoding="utf-8")
    assert (output_dir / "cmd" / "server" / "main.go").is_file()
    pyproject = output_dir / "pyproject.toml"
    assert not pyproject.is_file() or not pyproject.read_text(encoding="utf-8").strip()
    spec = yaml.safe_load((output_dir / "repave.yaml").read_text(encoding="utf-8"))["spec"]
    assert spec["appService"]["runtime"] == "go"
    assert all(g.passed or g.skipped for g in result.gates)


def test_generate_app_service_nodejs_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "app-service-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "service_name": "orders-api",
            "description": "Orders HTTP API",
            "owner": "team:commerce",
            "system": "commerce",
            "catalog_lifecycle": "production",
            "port": "8080",
            "runtime": "nodejs",
            "include_helm_reference": "false",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )

    output_dir = result.render.output_dir
    assert (output_dir / "package.json").is_file()
    package_text = (output_dir / "package.json").read_text(encoding="utf-8")
    assert '"name": "app-orders-api"' in package_text
    assert (output_dir / "src" / "server.ts").is_file()
    assert (output_dir / "src" / "main.ts").is_file()
    assert (output_dir / "test" / "health.test.ts").is_file()
    go_mod = output_dir / "go.mod"
    assert not go_mod.is_file() or not go_mod.read_text(encoding="utf-8").strip()
    spec = yaml.safe_load((output_dir / "repave.yaml").read_text(encoding="utf-8"))["spec"]
    assert spec["appService"]["runtime"] == "nodejs"
    failing = [g for g in result.gates if not g.passed and not g.skipped]
    assert not failing, [(g.name, g.message) for g in failing]


def test_generate_app_service_java_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "app-service-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "service_name": "inventory-api",
            "description": "Inventory HTTP API",
            "owner": "team:commerce",
            "system": "commerce",
            "catalog_lifecycle": "production",
            "port": "8080",
            "runtime": "java",
            "include_helm_reference": "false",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )

    output_dir = result.render.output_dir
    assert (output_dir / "pom.xml").is_file()
    assert (
        output_dir / "src" / "main" / "java" / "com" / "repave" / "app" / "Application.java"
    ).is_file()
    assert (
        output_dir / "src" / "test" / "java" / "com" / "repave" / "app" / "HealthTest.java"
    ).is_file()
    dockerfile = (output_dir / "Dockerfile").read_text(encoding="utf-8")
    assert "eclipse-temurin:21" in dockerfile
    spec = yaml.safe_load((output_dir / "repave.yaml").read_text(encoding="utf-8"))["spec"]
    assert spec["appService"]["runtime"] == "java"
    failing = [g for g in result.gates if not g.passed and not g.skipped]
    assert not failing, [(g.name, g.message) for g in failing]


def test_generate_app_service_dotnet_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "app-service-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "service_name": "billing-api",
            "description": "Billing HTTP API",
            "owner": "team:payments",
            "system": "payments",
            "catalog_lifecycle": "production",
            "port": "8080",
            "runtime": "dotnet",
            "include_helm_reference": "false",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )

    output_dir = result.render.output_dir
    assert (output_dir / "App.csproj").is_file()
    csproj = (output_dir / "App.csproj").read_text(encoding="utf-8")
    assert "net10.0" in csproj
    assert "BillingApi" in csproj
    assert (output_dir / "Program.cs").is_file()
    assert (output_dir / "tests" / "App.Tests.csproj").is_file()
    assert (output_dir / "tests" / "HealthTests.cs").is_file()
    dockerfile = (output_dir / "Dockerfile").read_text(encoding="utf-8")
    assert "mcr.microsoft.com/dotnet/sdk:10.0" in dockerfile
    spec = yaml.safe_load((output_dir / "repave.yaml").read_text(encoding="utf-8"))["spec"]
    assert spec["appService"]["runtime"] == "dotnet"
    failing = [g for g in result.gates if not g.passed and not g.skipped]
    assert not failing, [(g.name, g.message) for g in failing]


@pytest.mark.parametrize("runtime", ["python", "go", "nodejs", "java", "dotnet"])
@pytest.mark.parametrize(
    ("layout", "extra_assert"),
    [
        ("worker", lambda out: "QUEUE_URL" in (out / "README.md").read_text(encoding="utf-8")),
        ("scheduled-job", lambda out: "CronJob" in (out / "README.md").read_text(encoding="utf-8")),
        (
            "grpc",
            lambda out: (
                (out / "proto" / "health" / "v1" / "health.proto").is_file()
                and (out / "buf.yaml").is_file()
            ),
        ),
    ],
)
def test_generate_app_service_layout_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
    runtime: str,
    layout: str,
    extra_assert,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "app-service-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "service_name": "orders-worker",
            "description": "Orders background worker",
            "owner": "team:commerce",
            "port": "8080",
            "runtime": runtime,
            "layout": layout,
            "include_helm_reference": "false",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )

    output_dir = result.render.output_dir
    extra_assert(output_dir)
    spec = yaml.safe_load((output_dir / "repave.yaml").read_text(encoding="utf-8"))["spec"]
    assert spec["appService"]["layout"] == layout
    assert spec["appService"]["runtime"] == runtime
    failing = [g for g in result.gates if not g.passed and not g.skipped]
    assert not failing, [(g.name, g.message) for g in failing]


def test_app_service_layout_accepts_all_runtimes(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "app-service-generic",
        repo_root=repo_root,
    )
    for runtime in ("go", "nodejs", "java", "dotnet"):
        normalized = validate_inputs(
            blueprint,
            {
                "service_name": "payments-api",
                "description": "Payments",
                "owner": "team:payments",
                "runtime": runtime,
                "layout": "worker",
                "include_helm_reference": "false",
            },
        )
        assert normalized["runtime"] == runtime
        assert normalized["layout"] == "worker"


def test_generate_observability_as_code_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "observability-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout API alerts",
            "backend": "prometheus",
            "output_mode": "native",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-payments",
            "runbook_url": "https://wiki.example.com/runbooks/checkout",
            "slo_target_percent": "99.9",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )

    output_dir = result.render.output_dir
    rules = output_dir / "prometheus" / "rules" / "service-alerts.yaml"
    assert rules.is_file()
    text = rules.read_text(encoding="utf-8")
    assert "checkout_target_down" in text
    assert "runbook_url" in text
    assert (output_dir / "repave.yaml").is_file()
    assert all(g.passed or g.skipped for g in result.gates)


def test_generate_observability_datadog_native_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "observability-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "configuration_mode": "custom",
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout monitors",
            "backend": "datadog",
            "environment": "prod",
            "output_mode": "native",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-payments",
            "runbook_url": "https://wiki.example.com/runbooks/checkout",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )
    output_dir = result.render.output_dir
    monitors = output_dir / "datadog" / "monitors" / "service-alerts.json"
    assert monitors.is_file()
    assert not (output_dir / "prometheus").exists()
    dd_gate = next(g for g in result.gates if g.name == "datadog-monitor")
    assert dd_gate.passed or dd_gate.skipped
    assert all(g.passed or g.skipped for g in result.gates)


def test_generate_observability_grafana_native_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "observability-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "configuration_mode": "custom",
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout grafana",
            "backend": "grafana",
            "environment": "prod",
            "output_mode": "native",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-payments",
            "runbook_url": "https://wiki.example.com/runbooks/checkout",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )
    output_dir = result.render.output_dir
    dash = output_dir / "grafana" / "dashboards" / "service-overview.json"
    assert dash.is_file()
    assert not (output_dir / "datadog").exists()
    assert all(g.passed or g.skipped for g in result.gates)


def test_observability_generate_vends_selected_opa_policies_only(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "observability-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "configuration_mode": "custom",
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout monitors",
            "backend": "datadog",
            "environment": "prod",
            "output_mode": "native",
            "enable_policy": "true",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-payments",
            "runbook_url": "https://wiki.example.com/runbooks/checkout",
        },
        output_config=output_config,
        dry_run=False,
        staging_root=staging_root,
        repo_root=repo_root,
    )
    output_dir = result.render.output_dir
    selection_path = output_dir / ".repave" / "policy-selection.json"
    assert selection_path.is_file()
    policies_dir = output_dir / "policy" / "opa" / "policies"
    rego_names = {path.name for path in policies_dir.glob("*.rego")}
    assert "kubernetes_workload.rego" not in rego_names
    assert "destructive_changes.rego" in rego_names
    assert "observability_native.rego" in rego_names
    assert (output_dir / "tests" / "fixtures" / "plan-create-only.json").is_file()


def test_generate_observability_terraform_datadog_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "observability-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "configuration_mode": "custom",
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout TF monitors",
            "backend": "datadog",
            "environment": "prod",
            "output_mode": "terraform",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-payments",
            "runbook_url": "https://wiki.example.com/runbooks/checkout",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )
    output_dir = result.render.output_dir
    assert (output_dir / "monitors.tf").is_file()
    assert not (output_dir / "datadog").exists()
    assert all(g.passed or g.skipped for g in result.gates)


def test_generate_observability_terraform_grafana_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "observability-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "configuration_mode": "custom",
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout TF dashboard",
            "backend": "grafana",
            "environment": "prod",
            "output_mode": "terraform",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-payments",
            "runbook_url": "https://wiki.example.com/runbooks/checkout",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )
    output_dir = result.render.output_dir
    assert (output_dir / "dashboard.tf").is_file()
    assert not (output_dir / "grafana").exists()
    assert all(g.passed or g.skipped for g in result.gates)


def test_generate_dashboards_terraform_grafana_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "dashboards-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "configuration_mode": "custom",
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout TF dashboards",
            "backend": "grafana",
            "output_mode": "terraform",
            "environment": "prod",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-platform-primary",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )
    output_dir = result.render.output_dir
    assert (output_dir / "dashboard.tf").is_file()
    assert not (output_dir / "datadog").exists()
    assert all(g.passed or g.skipped for g in result.gates)


def test_generate_slo_as_code_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "slo-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout availability SLO",
            "slo_target_percent": "99.9",
            "runbook_url": "https://wiki.example.com/runbooks/checkout",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )
    output_dir = result.render.output_dir
    assert (output_dir / "prometheus" / "rules" / "slo-burn.yaml").is_file()
    assert (output_dir / "RUNBOOK.md").is_file()
    runbook = (output_dir / "RUNBOOK.md").read_text(encoding="utf-8")
    assert "## Rollback procedure" in runbook
    assert "## Game-day checklist" in runbook
    docs_gate = next(g for g in result.gates if g.name == "docs-drift")
    assert docs_gate.passed or docs_gate.skipped
    assert all(g.passed or g.skipped for g in result.gates)


def test_generate_monitors_native_prometheus_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "monitors-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "configuration_mode": "custom",
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout alerts",
            "backend": "prometheus",
            "output_mode": "native",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-payments",
            "runbook_url": "https://wiki.example.com/runbooks/checkout",
            "slo_target_percent": "99.9",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )
    output_dir = result.render.output_dir
    assert (output_dir / "prometheus" / "rules" / "service-alerts.yaml").is_file()
    assert not (output_dir / "datadog").exists()
    assert not (output_dir / "grafana").exists()
    assert all(g.passed or g.skipped for g in result.gates)


def test_generate_observability_policy_disabled_skips_opa_and_selection(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "observability-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "configuration_mode": "custom",
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout alerts",
            "backend": "prometheus",
            "output_mode": "native",
            "enable_policy": "false",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-payments",
            "runbook_url": "https://wiki.example.com/runbooks/checkout",
            "slo_target_percent": "99.9",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )
    output_dir = result.render.output_dir
    assert not (output_dir / ".repave" / "policy-selection.json").is_file()
    assert not (output_dir / "policy" / "opa" / "policies").is_dir()
    opa = next(g for g in result.gates if g.name == "opa")
    assert opa.skipped or opa.passed


def test_generate_monitors_policy_disabled_skips_opa_and_selection(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "monitors-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "configuration_mode": "custom",
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout alerts",
            "backend": "prometheus",
            "output_mode": "native",
            "enable_policy": "false",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-payments",
            "runbook_url": "https://wiki.example.com/runbooks/checkout",
            "slo_target_percent": "99.9",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )
    output_dir = result.render.output_dir
    assert not (output_dir / ".repave" / "policy-selection.json").is_file()
    assert not (output_dir / "policy" / "opa" / "policies").is_dir()
    opa = next(g for g in result.gates if g.name == "opa")
    assert opa.skipped or opa.passed
    assert "not enabled" in (opa.message or "").lower() or opa.skipped


def test_generate_monitors_policy_enabled_vends_selection(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "monitors-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "configuration_mode": "custom",
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout alerts",
            "backend": "prometheus",
            "output_mode": "native",
            "enable_policy": "true",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-payments",
            "runbook_url": "https://wiki.example.com/runbooks/checkout",
            "slo_target_percent": "99.9",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )
    output_dir = result.render.output_dir
    assert (output_dir / ".repave" / "policy-selection.json").is_file()
    policies_dir = output_dir / "policy" / "opa" / "policies"
    assert policies_dir.is_dir()
    assert any(policies_dir.glob("*.rego"))


def test_generate_monitors_prometheus_pack_materializes_community_rules(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "monitors-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "configuration_mode": "custom",
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout alerts",
            "backend": "prometheus",
            "output_mode": "native",
            "monitor_pack_source": "prometheus-red-plus-host-cpu",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-payments",
            "runbook_url": "https://wiki.example.com/runbooks/checkout",
            "slo_target_percent": "",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )
    output_dir = result.render.output_dir
    community = output_dir / "prometheus" / "rules" / "community-host-cpu.yaml"
    assert community.is_file()
    assert "host_cpu_high" in community.read_text(encoding="utf-8")


def test_generate_monitors_terraform_datadog_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "monitors-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "configuration_mode": "custom",
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout TF monitors",
            "backend": "datadog",
            "output_mode": "terraform",
            "monitor_pack_source": "repave-red-starter",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-payments",
            "runbook_url": "https://wiki.example.com/runbooks/checkout",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )
    output_dir = result.render.output_dir
    assert (output_dir / "monitors.tf").is_file()
    assert not (output_dir / "datadog").exists()
    providers = (output_dir / "providers.tf").read_text(encoding="utf-8")
    assert "validate = false" in providers


def test_generate_monitors_terraform_prometheus_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "monitors-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "configuration_mode": "custom",
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout TF alerts",
            "backend": "prometheus",
            "output_mode": "terraform",
            "monitor_pack_source": "repave-red-starter",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-payments",
            "runbook_url": "https://wiki.example.com/runbooks/checkout",
            "slo_target_percent": "99.9",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )
    output_dir = result.render.output_dir
    assert (output_dir / "prometheus_rules.tf").is_file()
    assert (output_dir / "alertmanager.tf").is_file()
    assert not (output_dir / "prometheus").exists()


def test_generate_monitors_terraform_datadog_community_pack_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "monitors-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "configuration_mode": "custom",
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout TF monitors",
            "backend": "datadog",
            "output_mode": "terraform",
            "monitor_pack_source": "datadog-red-plus-apm-errors",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-payments",
            "runbook_url": "https://wiki.example.com/runbooks/checkout",
            "environment": "prod",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )
    output_dir = result.render.output_dir
    assert not (output_dir / "monitors.tf").is_file()
    pack_tf = output_dir / "monitor_packs.tf"
    assert pack_tf.is_file()
    assert 'resource "datadog_monitor"' in pack_tf.read_text(encoding="utf-8")
    community = output_dir / "datadog" / "monitors" / "community-apm-error-rate.json"
    assert community.is_file()


def test_generate_monitors_terraform_prometheus_community_pack_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "monitors-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "configuration_mode": "custom",
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout TF alerts",
            "backend": "prometheus",
            "output_mode": "terraform",
            "monitor_pack_source": "prometheus-red-plus-host-cpu",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-payments",
            "runbook_url": "https://wiki.example.com/runbooks/checkout",
            "slo_target_percent": "",
            "environment": "prod",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )
    output_dir = result.render.output_dir
    assert not (output_dir / "prometheus_rules.tf").is_file()
    assert (output_dir / "alertmanager.tf").is_file()
    pack_tf = output_dir / "monitor_packs.tf"
    assert pack_tf.is_file()
    assert 'resource "null_resource"' in pack_tf.read_text(encoding="utf-8")
    community = output_dir / "prometheus" / "rules" / "community-host-cpu.yaml"
    assert community.is_file()


def test_generate_observability_terraform_prometheus_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "observability-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "configuration_mode": "custom",
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout TF rules",
            "backend": "prometheus",
            "output_mode": "terraform",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-payments",
            "runbook_url": "https://wiki.example.com/runbooks/checkout",
            "slo_target_percent": "99.9",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )
    output_dir = result.render.output_dir
    assert (output_dir / "prometheus_rules.tf").is_file()
    assert (output_dir / "alertmanager.tf").is_file()
    assert not (output_dir / "prometheus").exists()
    assert all(g.passed or g.skipped for g in result.gates)


def test_generate_observability_terraform_otel_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "observability-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "configuration_mode": "custom",
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout OTel TF",
            "backend": "otel",
            "output_mode": "terraform",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-payments",
            "runbook_url": "https://wiki.example.com/runbooks/checkout",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )
    output_dir = result.render.output_dir
    assert (output_dir / "otel_collector.tf").is_file()
    assert not (output_dir / "otel").exists()
    assert all(g.passed or g.skipped for g in result.gates)


def test_generate_dashboards_terraform_with_pack_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "dashboards-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "configuration_mode": "custom",
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout dashboards pack TF",
            "backend": "grafana",
            "output_mode": "terraform",
            "dashboard_pack_source": "grafana-red-plus-node-exporter-1860",
            "environment": "prod",
            "datasource_uid": "prometheus",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-platform-primary",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )
    output_dir = result.render.output_dir
    assert (output_dir / "dashboard_packs.tf").is_file()
    assert (output_dir / "grafana" / "dashboards").is_dir()
    assert not (output_dir / "dashboard.tf").exists()
    assert all(g.passed or g.skipped for g in result.gates)


def test_generate_dashboards_as_code_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "dashboards-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout service dashboards",
            "backend": "grafana",
            "output_mode": "native",
            "environment": "prod",
            "observability_focus": "dashboards",
            "datasource_uid": "prometheus",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-platform-primary",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )

    output_dir = result.render.output_dir
    overview = output_dir / "grafana" / "dashboards" / "service-overview.json"
    golden = output_dir / "grafana" / "dashboards" / "service-golden-signals.json"
    assert overview.is_file()
    assert golden.is_file()
    assert "service:checkout" in overview.read_text(encoding="utf-8")
    assert "managed-by:repave" in overview.read_text(encoding="utf-8")
    assert not (output_dir / "datadog").exists()
    grafana_gate = next(g for g in result.gates if g.name == "grafana-dashboard")
    assert grafana_gate.passed
    assert not grafana_gate.skipped
    dd_gate = next(g for g in result.gates if g.name == "datadog-dashboard")
    assert dd_gate.skipped
    docs_gate = next(g for g in result.gates if g.name == "docs-drift")
    assert docs_gate.passed, docs_gate.message
    assert all(g.passed or g.skipped for g in result.gates)


def test_generate_dashboards_with_community_pack(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "dashboards-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout service dashboards",
            "backend": "grafana",
            "environment": "prod",
            "output_mode": "native",
            "observability_focus": "dashboards",
            "dashboard_pack_source": "grafana-red-plus-node-exporter-1860",
            "datasource_uid": "prometheus",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-platform-primary",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )

    output_dir = result.render.output_dir
    community = output_dir / "grafana" / "dashboards" / "community-node-exporter-1860.json"
    assert community.is_file()
    assert "grafana-1860" in community.read_text(encoding="utf-8")
    grafana_gate = next(g for g in result.gates if g.name == "grafana-dashboard")
    assert grafana_gate.passed


def test_generate_dashboards_as_code_datadog_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "dashboards-as-code-generic",
        repo_root=repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout service dashboards",
            "backend": "datadog",
            "environment": "prod",
            "output_mode": "native",
            "observability_focus": "dashboards",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-platform-primary",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )

    output_dir = result.render.output_dir
    overview = output_dir / "datadog" / "dashboards" / "service-overview.json"
    golden = output_dir / "datadog" / "dashboards" / "service-golden-signals.json"
    assert overview.is_file()
    assert golden.is_file()
    assert not (output_dir / "grafana").exists()
    assert "trace.http.request.hits" in golden.read_text(encoding="utf-8")
    dd_gate = next(g for g in result.gates if g.name == "datadog-dashboard")
    assert dd_gate.passed
    assert not dd_gate.skipped
    docs_gate = next(g for g in result.gates if g.name == "docs-drift")
    assert docs_gate.passed, docs_gate.message
    assert all(g.passed or g.skipped for g in result.gates)
