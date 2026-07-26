from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from repave_engine.api import create_app
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


def test_index_lists_blueprints(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/")

    assert response.status_code == 200
    assert "terraform-module-generic" in response.text
    assert "/static/repave.css" in response.text
    assert "/static/repave.js" in response.text
    assert 'id="last-run-snippet"' in response.text
    assert 'class="shell"' in response.text
    assert "shell__atmosphere" in response.text
    assert "home-hero" in response.text
    assert "home-hero__wordmark" in response.text
    assert 'id="golden-paths"' in response.text
    assert "catalog-grid" in response.text
    assert "catalog-group__title" in response.text
    assert "Terraform" in response.text
    assert "Ansible" in response.text
    assert 'class="catalog-group catalog-group--terraform"' in response.text
    assert 'class="catalog-group catalog-group--ansible"' in response.text
    assert 'class="catalog-group catalog-group--policy"' in response.text
    assert 'id="catalog-policy"' in response.text
    assert "opa-policy-generic" in response.text
    assert "azure-policy-generic" in response.text


def test_static_repave_js_served(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/static/repave.js")

    assert response.status_code == 200
    assert "repavePortal" in response.text
    assert "sessionStorage" in response.text


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
    assert "Dry-run" in response.text
    assert "result-hero" in response.text
    assert "gate-table" in response.text
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
    assert "Dry-run preview" in response.text
    assert "Publish locally" in response.text
    assert "chip" in response.text
    assert "service-presets" in response.text
    assert "form-validation" in response.text
    assert "scope-resource-filter" in response.text


def test_resource_blueprint_form_renders_catalog_dropdowns(repo_root, output_config) -> None:
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


def test_ansible_form_is_single_column(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/ansible-role-generic")

    assert response.status_code == 200
    assert "governance-card" in response.text
    assert "form-layout--split" not in response.text
    assert "ansible-lint" in response.text or "ansible_lint" in response.text
    assert 'id="support_linux_cb"' in response.text
    assert 'name="support_linux"' in response.text
    assert 'id="target_platforms_advanced"' in response.text
    assert "Advanced Galaxy platforms" in response.text
    assert 'id="min_ansible_version"' in response.text
    assert "2.18" in response.text
    assert 'option value="2.18" selected' in response.text


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
    assert "Published locally" in response.text
    assert "repo-card" in response.text
    assert "Open on GitHub" in response.text
    assert "repo-local-path" in response.text


def test_update_form_page(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/update")

    assert response.status_code == 200
    assert "Update existing repository" in response.text
    assert 'name="target_repo"' in response.text
    assert "Update repo" in response.text


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
    assert "upgrade-diff" in response.text
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
