from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from repave_engine.blueprint import load_blueprint
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
        repo_root,
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
        repo_root,
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


def test_generate_ansible_playbook_project_publishes_repo(
    repo_root: Path,
    ansible_playbook_sample_inputs,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "ansible-playbook-project",
        repo_root,
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


def test_generate_ansible_collection_publishes_repo(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "ansible-collection-generic",
        repo_root,
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
        repo_root,
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "chart_name": "api",
            "app_name": "api",
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
        repo_root,
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
    assert all(g.passed or g.skipped for g in result.gates)


def test_generate_observability_as_code_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "observability-as-code-generic",
        repo_root,
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
        repo_root,
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
        repo_root,
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


def test_generate_observability_terraform_datadog_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "observability-as-code-generic",
        repo_root,
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
        repo_root,
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
        repo_root,
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


def test_generate_observability_terraform_prometheus_dry_run(
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "observability-as-code-generic",
        repo_root,
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
        repo_root,
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
        repo_root,
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
        repo_root,
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
        repo_root,
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
        repo_root,
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
