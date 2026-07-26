from __future__ import annotations

from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.gate_registry import GateResult
from repave_engine.pipeline import GenerationResult
from repave_engine.render import RenderResult
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
    assert 'class="shell"' in response.text
    assert "shell__atmosphere" in response.text
    assert "home-hero" in response.text
    assert "home-hero__wordmark" in response.text
    assert 'id="golden-paths"' in response.text
    assert "catalog-grid" in response.text
    assert "catalog-group__title" in response.text
    assert "Terraform" in response.text
    assert "Ansible" in response.text


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


def test_ansible_form_is_single_column(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/ansible-role-generic")

    assert response.status_code == 200
    assert "governance-card" in response.text
    assert "form-layout--split" not in response.text
    assert "ansible-lint" in response.text or "ansible_lint" in response.text


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
