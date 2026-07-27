from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from repave_engine.api import _dry_run_from_form, create_app
from repave_engine.gate_registry import GateResult
from repave_engine.pipeline import GenerationResult
from repave_engine.render import RenderResult
from repave_engine.settings import OutputConfig
from repave_engine.target_repo import ModuleRepository


def test_health(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metrics_exposes_prometheus(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "repave_generations_total" in response.text


def test_index_lists_blueprints(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/")

    assert response.status_code == 200
    assert "terraform-module-generic" in response.text
    assert "/static/repave.css" in response.text
    assert "/static/repave.js" in response.text
    assert 'id="last-run-snippet"' in response.text
    assert 'class="skip-link"' in response.text
    assert 'id="main-content"' in response.text
    assert 'id="repave-toast"' in response.text
    assert 'class="shell"' in response.text
    assert "shell__atmosphere" in response.text
    assert "home-hero" in response.text
    assert "home-hero__wordmark" in response.text
    assert "home-quicknav" in response.text
    assert "data-home-quicknav" in response.text
    assert "data-quicknav-toggle" in response.text
    assert "<details" in response.text
    assert "home-quicknav__summary" in response.text
    assert 'id="golden-paths"' in response.text
    assert "catalog-grid" in response.text
    assert "catalog-group__title" in response.text
    assert "Terraform" in response.text
    assert "Ansible" in response.text
    assert 'class="catalog-group catalog-group--terraform"' in response.text
    assert 'class="catalog-group catalog-group--ansible"' in response.text
    assert 'class="catalog-group catalog-group--policy"' in response.text
    assert 'class="catalog-group catalog-group--observability"' in response.text
    assert 'id="catalog-observability"' in response.text
    assert "Observability" in response.text
    assert "dashboards-as-code-generic" in response.text
    assert 'id="catalog-policy"' in response.text
    assert "opa-policy-generic" in response.text
    assert "azure-policy-generic" in response.text


def test_static_repave_js_served(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/static/repave.js")

    assert response.status_code == 200
    assert "repavePortal" in response.text
    assert "sessionStorage" in response.text
    assert "initCopyButtons" in response.text
    assert "initBusyForms" in response.text
    assert "initFormStepper" in response.text
    assert "initHomeQuicknav" in response.text
    assert "initCatalogSearch" in response.text
    assert "initGateDashboard" in response.text
    assert "initFormDraft" in response.text


def test_activity_page(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/activity")

    assert response.status_code == 200
    assert "Generation activity" in response.text
    assert 'href="/activity"' in response.text


def test_index_catalog_search(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/")

    assert response.status_code == 200
    assert "data-catalog-search" in response.text
    assert "data-catalog-card" in response.text


def test_blueprint_form_draft_and_standards_diff_v2(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/terraform-module-generic")

    assert response.status_code == 200
    assert "data-repave-form-draft" in response.text
    assert "Standard pin drift" in response.text
    assert "form-actions__preflight" in response.text


def test_static_repave_css_served(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/static/repave.css")

    assert response.status_code == 200
    assert "--accent" in response.text
    assert ".shell__wordmark" in response.text
    assert ".home-hero" in response.text
    assert "color-scheme: dark" in response.text
    assert ".shell__atmosphere" in response.text


def test_env_badge_rendered_when_set(repo_root, output_config, monkeypatch) -> None:
    monkeypatch.setenv("REPAVE_ENV", "local")
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/")

    assert response.status_code == 200
    assert "badge--env" in response.text
    assert ">local<" in response.text


def test_generate_form_submission(
    repo_root,
    output_config,
    sample_inputs,
    monkeypatch,
) -> None:
    monkeypatch.setenv("REPAVE_GITHUB_ORG", output_config.github_org)
    monkeypatch.setenv("REPAVE_MODULES_ROOT", str(output_config.modules_root))

    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "terraform-module-generic",
            "dry_run": "true",
            **sample_inputs,
        },
    )

    assert response.status_code == 200
    assert "tf-aws-example" in response.text
    assert "Plan only" in response.text
    assert "result-hero" in response.text
    assert "gate-table" in response.text
    assert "data-gate-dashboard" in response.text
    assert "Generated files" in response.text
    assert "ec2_diff.tf" in response.text
    assert "s3_bucket.tf" in response.text
    assert "publish-plan" in response.text
    assert "repavePortal.saveLastRun" in response.text


def test_generate_publish_passes_github_token_from_env(
    repo_root,
    output_config,
    sample_inputs,
    monkeypatch,
) -> None:
    monkeypatch.setenv("REPAVE_GITHUB_ORG", output_config.github_org)
    monkeypatch.setenv("REPAVE_MODULES_ROOT", str(output_config.modules_root))
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_from_env")
    captured: dict[str, object] = {}

    def fake_generate(blueprint, values, *, output_config, dry_run, github_token, repo_root=None):
        captured["dry_run"] = dry_run
        captured["github_token"] = github_token
        return GenerationResult(
            blueprint=blueprint,
            render=RenderResult(output_dir=output_config.modules_root, values=values),
            gates=[],
            module_repository=None,
            pr_plan=None,
            pr_message="published",
        )

    monkeypatch.setattr("repave_engine.api.generate_from_blueprint", fake_generate)

    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "terraform-module-generic",
            "dry_run": "false",
            **sample_inputs,
        },
    )

    assert response.status_code == 200
    assert captured["dry_run"] is False
    assert captured["github_token"] == "ghp_from_env"


def test_generate_dry_run_ignores_github_token(
    repo_root,
    output_config,
    sample_inputs,
    monkeypatch,
) -> None:
    monkeypatch.setenv("REPAVE_GITHUB_ORG", output_config.github_org)
    monkeypatch.setenv("REPAVE_MODULES_ROOT", str(output_config.modules_root))
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_from_env")
    captured: dict[str, object] = {}

    def fake_generate(blueprint, values, *, output_config, dry_run, github_token, repo_root=None):
        captured["dry_run"] = dry_run
        captured["github_token"] = github_token
        return GenerationResult(
            blueprint=blueprint,
            render=RenderResult(output_dir=output_config.modules_root, values=values),
            gates=[],
            module_repository=None,
            pr_plan=None,
            pr_message="dry-run",
        )

    monkeypatch.setattr("repave_engine.api.generate_from_blueprint", fake_generate)

    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "terraform-module-generic",
            **sample_inputs,
        },
    )

    assert response.status_code == 200
    assert captured["dry_run"] is True
    assert captured["github_token"] is None


def test_dry_run_from_form_prefers_plan_when_both_flags_sent() -> None:
    class _Form:
        def getlist(self, key: str) -> list[str]:
            if key == "dry_run":
                return ["false", "true"]
            return []

    assert _dry_run_from_form(_Form()) is True


def test_provider_service_detail(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/terraform-module-generic/provider-services/aws/s3")

    assert response.status_code == 200
    payload = response.json()
    assert "resources" in payload
    assert "basic" in payload
    assert "bucket" in payload["resources"]


def test_blueprint_form_renders_inputs(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/terraform-module-generic")

    assert response.status_code == 200
    assert "cloud_provider" in response.text
    assert "provider_services" in response.text
    assert "governance-card" in response.text
    assert "form-layout--split" in response.text
    assert "Plan (validate only)" in response.text
    assert "Apply to modules root" in response.text
    assert "chip" in response.text
    assert "service-presets" in response.text
    assert "form-validation" in response.text
    assert "scope-resource-filter" in response.text
    assert "policy-rules-list" in response.text
    assert "policy-catalog" in response.text
    assert "data-repave-busy-form" in response.text
    assert "form-actions--sticky" in response.text
    assert "Standard pin drift" in response.text
    assert "data-form-stepper" in response.text
    assert 'data-form-stepper-kind="terraform"' in response.text
    assert "form-stepper" in response.text
    assert "data-dry-run-run" in response.text
    assert "data-dry-run-force" in response.text
    assert "form-actions__delivery" in response.text
    assert "novalidate" in response.text


def test_terraform_dry_run_shows_files_in_result(repo_root, output_config, sample_inputs) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "terraform-module-generic",
            "dry_run": "true",
            **sample_inputs,
        },
    )
    assert response.status_code == 200
    assert "Plan only" in response.text
    assert "Generated files" in response.text
    assert "result-hero" in response.text


def test_ansible_role_form_stepper(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/ansible-role-generic")
    assert response.status_code == 200
    assert 'data-form-stepper-kind="standard"' in response.text
    assert 'data-form-stepper-max="1"' in response.text
    assert "data-dry-run-run" in response.text
    assert "data-dry-run-force" in response.text
    assert "form-actions__delivery" in response.text
    assert "novalidate" in response.text


def test_ansible_role_dry_run_shows_files_in_result(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "ansible-role-generic",
            "dry_run": "true",
            "role_name": "webserver",
            "namespace": "acme",
            "description": "Example role for portal dry-run test",
            "min_ansible_version": "2.18",
            "support_linux": "true",
            "support_windows": "false",
            "windows_server_generation": "2022",
        },
    )
    assert response.status_code == 200
    assert "Plan only" in response.text
    assert "Generated files" in response.text
    assert "result-hero" in response.text


def test_observability_form_stepper(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/observability-as-code-generic")
    assert response.status_code == 200
    assert 'data-form-stepper-kind="observability"' in response.text
    assert "governance-drift-details" in response.text or "Standard pin drift" in response.text


def test_policy_catalog_endpoint(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/terraform-module-generic/policy-catalog")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["rules"]) >= 1
    assert "includes" in payload["profiles"]["estate-default"]
    assert len(payload["pack_sources"]) >= 2
    assert payload["pack_sources"][0].get("default_profile")
    assert payload["defaults"]["policy_pack_source"] == "repave-default"
    assert payload["defaults"]["policy_profile"] == "estate-default"


def test_terraform_module_form_policy_defaults_and_rule_titles(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    form = client.get("/blueprints/terraform-module-generic")
    assert form.status_code == 200
    assert 'value="estate-default"' in form.text
    estate_block = form.text.split('value="estate-default"', 1)[1][:120]
    assert "selected" in estate_block
    assert "Terraform required_version must be declared" in form.text
    rules_region = form.text.split('id="policy-rules-list"', 1)[1].split("</details>", 1)[0]
    assert "(checkov:CKV2_REPAVE_1)" not in rules_region


def test_policy_catalog_azure_pack_defaults(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    payload = client.get("/blueprints/azure-policy-generic/policy-catalog").json()
    pack_ids = {item["id"] for item in payload["pack_sources"]}
    assert pack_ids <= {"repave-azure-samples", "repave-default"}
    assert payload["defaults"]["policy_pack_source"] == "repave-azure-samples"
    assert payload["defaults"]["policy_profile"] == "azure-community"
    azure_rule_ids = {rule["id"] for rule in payload["rules"]}
    assert "azure:sample_deny_public_blob_access" in azure_rule_ids
    assert "azure:sample_audit_environment_tag" in azure_rule_ids

    obs_payload = client.get(
        "/blueprints/observability-as-code-generic/observability-catalog"
    ).json()
    assert obs_payload["defaults"]["notification_source"] == "repave-estate-oncall"
    assert len(obs_payload["notification_sources"]) >= 2
    pagerduty = next(
        s for s in obs_payload["notification_sources"] if s["id"] == "repave-estate-oncall"
    )
    assert any(t["id"] == "pagerduty-platform-primary" for t in pagerduty["targets"])

    obs_form = client.get("/blueprints/observability-as-code-generic")
    assert obs_form.status_code == 200
    assert 'id="observability-notifications"' in obs_form.text
    assert 'id="notification_source"' in obs_form.text
    assert 'id="notification_target"' in obs_form.text
    assert 'value="pagerduty-platform-primary"' in obs_form.text

    inv = client.get("/blueprints/observability-as-code-generic/service-inventory").json()
    assert "services" in inv
    assert inv["merge_catalog"] is True

    dash_form = client.get("/blueprints/dashboards-as-code-generic")
    assert dash_form.status_code == 200
    assert 'id="obs-backend-decision"' in dash_form.text
    assert 'id="dashboard_pack_source"' in dash_form.text
    assert 'value="datadog"' in dash_form.text
    assert 'value="grafana"' in dash_form.text
    assert 'id="observability-backend-datadog-fields"' in dash_form.text
    assert 'id="dashboard-pack-includes"' in dash_form.text
    assert "grafana-red-plus-node-exporter-1860" in dash_form.text
    assert (
        "datadog-red-plus-apm-service"
        not in dash_form.text.split('id="dashboard_pack_source"', 1)[1].split("</select>", 1)[0]
    )
    backend_pos = dash_form.text.index('id="backend"')
    advanced_pos = dash_form.text.index('id="obs-advanced-fields"')
    assert backend_pos < advanced_pos

    form = client.get("/blueprints/azure-policy-generic")
    assert form.status_code == 200
    assert 'value="repave-azure-samples"' in form.text
    assert (
        "repave-azure-samples" in form.text
        and "selected" in form.text.split("repave-azure-samples", 1)[1][:80]
    )

    checkov_form = client.get("/blueprints/checkov-policy-generic")
    assert checkov_form.status_code == 200
    assert 'value="repave-checkov-pack"' in checkov_form.text
    assert "checkov-full" in checkov_form.text
    assert "CKV2_REPAVE_1" in checkov_form.text
    assert 'id="policy-rules-list"' in checkov_form.text
    assert checkov_form.text.count('class="checkbox-row"') >= 12

    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/terraform-module-resource")

    assert response.status_code == 200
    assert 'id="cloud_provider"' in response.text
    assert 'id="provider_service"' in response.text
    assert 'id="provider_resource"' in response.text
    assert "Select a service" in response.text
    assert "Select a resource" in response.text
    assert "provider-services" not in response.text
    assert "service-presets" not in response.text
    assert "form-layout--split" in response.text


def test_env_stack_form_renders_module_inventory_picker(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/terraform-environment-stack")

    assert response.status_code == 200
    assert 'id="pinned-modules-rows"' in response.text
    assert 'id="add-pinned-module"' in response.text
    assert "module-inventory" in response.text
    assert 'name="pinned_modules"' in response.text
    assert "form-layout--split" in response.text


def test_ansible_playbook_form_renders_role_inventory_picker(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/ansible-playbook-project")

    assert response.status_code == 200
    assert 'id="pinned-roles-rows"' in response.text
    assert 'id="add-pinned-role"' in response.text
    assert "role-inventory" in response.text
    assert 'name="pinned_roles"' in response.text
    assert "form-layout--split" in response.text


def test_role_inventory_api_scans_modules_root(
    repo_root,
    tmp_path: Path,
) -> None:
    import yaml

    modules_root = tmp_path / "modules"
    repo_dir = modules_root / "ansible-role-demo"
    repo_dir.mkdir(parents=True)
    (repo_dir / "repave.yaml").write_text(
        yaml.safe_dump(
            {
                "spec": {
                    "artifactType": "ansible-role",
                    "ansibleRole": {
                        "namespace": "demo",
                        "role_name": "app",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    config = OutputConfig(github_org="acme", modules_root=modules_root)
    client = TestClient(create_app(repo_root=repo_root, output_config=config))
    response = client.get("/blueprints/ansible-playbook-project/role-inventory")

    assert response.status_code == 200
    payload = response.json()
    names = {item["repo_name"] for item in payload["roles"]}
    assert "ansible-role-demo" in names
    assert payload["roles"][0]["galaxy_name"] == "demo.app"


def test_module_inventory_api_scans_modules_root(
    repo_root,
    output_config,
    tmp_path: Path,
) -> None:
    import yaml

    modules_root = tmp_path / "modules"
    repo_dir = modules_root / "tf-aws-demo"
    repo_dir.mkdir(parents=True)
    (repo_dir / "repave.yaml").write_text(
        yaml.safe_dump(
            {
                "spec": {
                    "artifactType": "terraform-module",
                    "terraformModule": {
                        "module_name": "demo",
                        "cloud_provider": "aws",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    config = OutputConfig(github_org="acme", modules_root=modules_root)
    client = TestClient(create_app(repo_root=repo_root, output_config=config))
    response = client.get(
        "/blueprints/terraform-environment-stack/module-inventory?cloud_provider=aws"
    )

    assert response.status_code == 200
    payload = response.json()
    names = {item["repo_name"] for item in payload["modules"]}
    assert "tf-aws-demo" in names


def test_generate_resource_module_from_form(repo_root, output_config, monkeypatch) -> None:
    monkeypatch.setenv("REPAVE_GITHUB_ORG", output_config.github_org)
    monkeypatch.setenv("REPAVE_MODULES_ROOT", str(output_config.modules_root))
    captured: dict[str, object] = {}

    def fake_generate(blueprint, values, *, output_config, dry_run, github_token, repo_root=None):
        captured["values"] = values
        return GenerationResult(
            blueprint=blueprint,
            render=RenderResult(output_dir=output_config.modules_root, values=values),
            gates=[],
            module_repository=None,
            pr_plan=None,
            pr_message="dry-run",
        )

    monkeypatch.setattr("repave_engine.api.generate_from_blueprint", fake_generate)

    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "terraform-module-resource",
            "dry_run": "true",
            "module_name": "acme-bucket",
            "description": "Example",
            "cloud_provider": "aws",
            "provider_service": "s3",
            "provider_resource": "bucket",
        },
    )

    assert response.status_code == 200
    values = captured["values"]
    assert isinstance(values, dict)
    assert values["provider_service"] == "s3"
    assert values["provider_resource"] == "bucket"


def test_ansible_form_renders_split_governance(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/ansible-role-generic")

    assert response.status_code == 200
    assert "governance-card governance-card--ansible" in response.text
    assert "form-layout--split" in response.text
    assert "ansible-lint" in response.text or "ansible_lint" in response.text
    assert 'id="support_linux_cb"' in response.text
    assert 'name="support_linux"' in response.text
    assert 'id="target_platforms_advanced"' in response.text
    assert "Advanced Galaxy platforms" in response.text
    assert 'id="min_ansible_version"' in response.text
    assert "2.18" in response.text
    assert 'option value="2.18" selected' in response.text


def test_app_service_form_renders_backstage_catalog(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/app-service-generic")

    assert response.status_code == 200
    assert 'id="app-service-catalog"' in response.text
    assert "Backstage catalog" in response.text
    assert 'data-form-stepper-kind="standard"' in response.text
    assert "form-actions__delivery" in response.text
    assert "data-dry-run-run" in response.text
    assert 'id="catalog_lifecycle"' in response.text
    assert 'id="runtime"' in response.text
    assert ">go</option>" in response.text


def test_provider_service_detail_unknown_returns_empty(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get(
        "/blueprints/terraform-module-generic/provider-services/aws/not-a-service"
    )

    assert response.status_code == 200
    assert response.json() == {"resources": [], "basic": []}


def test_generate_uses_provider_service_option_fallback(
    repo_root,
    output_config,
    monkeypatch,
) -> None:
    monkeypatch.setenv("REPAVE_GITHUB_ORG", output_config.github_org)
    monkeypatch.setenv("REPAVE_MODULES_ROOT", str(output_config.modules_root))
    captured: dict[str, object] = {}

    def fake_generate(blueprint, values, *, output_config, dry_run, github_token, repo_root=None):
        captured["values"] = values
        return GenerationResult(
            blueprint=blueprint,
            render=RenderResult(output_dir=output_config.modules_root, values=values),
            gates=[],
            module_repository=None,
            pr_plan=None,
            pr_message="dry-run",
        )

    monkeypatch.setattr("repave_engine.api.generate_from_blueprint", fake_generate)

    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "terraform-module-generic",
            "dry_run": "true",
            "module_name": "example",
            "description": "Example module",
            "cloud_provider": "aws",
            "provider_service_option": "ec2",
        },
    )

    assert response.status_code == 200
    values = captured["values"]
    assert isinstance(values, dict)
    assert values["provider_services"] == "ec2"


def test_result_dashboard_failed_gate_excerpt(
    repo_root,
    output_config,
    sample_inputs,
    monkeypatch,
) -> None:
    monkeypatch.setenv("REPAVE_GITHUB_ORG", output_config.github_org)
    monkeypatch.setenv("REPAVE_MODULES_ROOT", str(output_config.modules_root))

    def fake_generate(blueprint, values, *, output_config, dry_run, github_token, repo_root=None):
        return GenerationResult(
            blueprint=blueprint,
            render=RenderResult(output_dir=output_config.modules_root, values=values),
            gates=[
                GateResult("docs-drift", True, False, "README present"),
                GateResult("terraform-fmt", False, False, "Error: fmt failed\nline two"),
            ],
            module_repository=None,
            pr_plan=None,
            pr_message="Gates failed",
            dry_run=True,
        )

    monkeypatch.setattr("repave_engine.api.generate_from_blueprint", fake_generate)

    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "terraform-module-generic",
            "dry_run": "true",
            **sample_inputs,
        },
    )

    assert response.status_code == 200
    assert "result-hero--failed" in response.text
    assert "Generation failed" in response.text
    assert "gate-detail" in response.text
    assert "gate-excerpt-2" in response.text
    assert "fmt failed" in response.text


def test_result_dashboard_published_repo_card(
    repo_root,
    output_config,
    sample_inputs,
    monkeypatch,
) -> None:
    monkeypatch.setenv("REPAVE_GITHUB_ORG", output_config.github_org)
    monkeypatch.setenv("REPAVE_MODULES_ROOT", str(output_config.modules_root))
    local_path = output_config.modules_root / "tf-aws-example"

    def fake_generate(blueprint, values, *, output_config, dry_run, github_token, repo_root=None):
        repo = ModuleRepository(
            name="tf-aws-example",
            owner=output_config.github_org,
            local_path=local_path,
            clone_url=f"https://github.com/{output_config.github_org}/tf-aws-example.git",
            web_url=f"https://github.com/{output_config.github_org}/tf-aws-example",
        )
        return GenerationResult(
            blueprint=blueprint,
            render=RenderResult(output_dir=local_path, values=values),
            gates=[GateResult("docs-drift", True, False, "ok")],
            module_repository=repo,
            pr_plan=None,
            pr_message="published",
            dry_run=False,
        )

    monkeypatch.setattr("repave_engine.api.generate_from_blueprint", fake_generate)

    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "terraform-module-generic",
            "dry_run": "false",
            **sample_inputs,
        },
    )

    assert response.status_code == 200
    assert "result-hero--passed" in response.text
    assert "Applied locally" in response.text
    assert "repo-card" in response.text
    assert "Open on GitHub" in response.text
    assert "repo-local-path" in response.text


def test_result_includes_lineage_and_policy_block(
    repo_root,
    output_config,
    sample_inputs,
    monkeypatch,
) -> None:
    from repave_engine.policy_selection import PolicySelection

    monkeypatch.setenv("REPAVE_GITHUB_ORG", output_config.github_org)
    monkeypatch.setenv("REPAVE_MODULES_ROOT", str(output_config.modules_root))
    selection = PolicySelection(
        profile="estate-default",
        pack_source="repave-default",
        enabled_rules=("checkov:CKV2_REPAVE_1",),
        checkov_skip_checks=(),
        opa_rego_files=("destructive_changes.rego",),
        azure_definition_files=(),
        pack_versions={"checkov": "1.0.0", "opa": "1.0.0"},
    )

    def fake_generate(blueprint, values, *, output_config, dry_run, github_token, repo_root=None):
        merged = {**values, "_policy_selection": selection}
        return GenerationResult(
            blueprint=blueprint,
            render=RenderResult(output_dir=repo_root / ".tmp", values=merged),
            gates=[GateResult("checkov", True, False, "ok")],
            module_repository=None,
            pr_plan=None,
            pr_message="PR body",
            dry_run=True,
        )

    monkeypatch.setattr("repave_engine.api.generate_from_blueprint", fake_generate)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={"blueprint_name": "terraform-module-generic", "dry_run": "true", **sample_inputs},
    )
    assert response.status_code == 200
    assert "Lineage" in response.text
    assert "Policy pack" in response.text
    assert "estate-default" in response.text


def test_update_form_page(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/update")

    assert response.status_code == 200
    assert "Upgrade existing repository" in response.text
    assert 'name="target_repo"' in response.text
    assert "Upgrade repo" in response.text
    assert "data-repave-busy-form" in response.text
    assert "data-busy-stages" in response.text
    assert "shell__main--golden-path" in response.text
    assert "terraform-minimal" in response.text or "Use terraform-minimal" in response.text


def test_update_plan_preview(repo_root, output_config) -> None:
    fixture = repo_root / "operator" / "testdata" / "modules" / "terraform-minimal"
    if not fixture.is_dir():
        import pytest

        pytest.skip("operator fixture not present")

    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/update",
        data={"target_repo": str(fixture)},
    )

    assert response.status_code == 200
    assert "Upgrade preview" in response.text
    assert (
        "Standards &amp; pin changes" in response.text or "Standards & pin changes" in response.text
    )
    assert "pin-diff-table" in response.text
    assert "upgrade-diff" in response.text
    assert "upgrade-diff__item--" in response.text
    assert "repave update --no-dry-run" in response.text


def test_update_plan_shows_error_for_missing_provenance(repo_root, output_config, tmp_path) -> None:
    empty = tmp_path / "empty-module"
    empty.mkdir()

    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/update",
        data={"target_repo": str(empty)},
    )

    assert response.status_code == 200
    assert "alert--fail" in response.text
    assert "repave.yaml" in response.text


def test_readyz(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/readyz")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["config_loaded"] is True


def test_api_v1_generate_dry_run(repo_root, output_config, monkeypatch) -> None:
    monkeypatch.setenv("REPAVE_GITHUB_ORG", output_config.github_org)
    monkeypatch.setenv("REPAVE_MODULES_ROOT", str(output_config.modules_root))

    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/api/v1/generate",
        json={
            "blueprint": "terraform-module-resource",
            "dry_run": True,
            "inputs": {
                "module_name": "api-demo",
                "description": "API test",
                "cloud_provider": "aws",
                "provider_service": "s3",
                "provider_resource": "bucket",
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["blueprint"] == "terraform-module-resource"
    assert payload["dry_run"] is True
    assert "gates_outcome" in payload
