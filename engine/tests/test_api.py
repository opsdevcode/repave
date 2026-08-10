from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from repave_engine.api import _dry_run_from_form, _plan_preview_from_form, create_app
from repave_engine.audit import AuditRecord, append_audit_record
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
    assert "repave_jsonl_append_failures_total" in response.text


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
    assert "data-demo-pipeline" in response.text
    assert "catalog-inventory__item-icon" in response.text
    assert "catalog-inventory__category" in response.text
    assert "catalog-inventory__summary" in response.text
    assert "<details" in response.text
    assert "Golden paths" in response.text
    assert 'href="/library"' in response.text
    assert "Browse library" in response.text
    assert "shell__nav--primary" in response.text
    assert "shell__bar-start" in response.text
    assert "shell__search" in response.text
    assert response.text.index("Library") < response.text.index("shell__nav-more")
    assert "Terraform" in response.text
    assert "Ansible" in response.text
    assert (
        'class="catalog-inventory__category catalog-inventory__category--terraform"'
        in response.text
    )
    assert (
        'class="catalog-inventory__category catalog-inventory__category--ansible"' in response.text
    )
    assert (
        'class="catalog-inventory__category catalog-inventory__category--policy"' in response.text
    )
    assert (
        'class="catalog-inventory__category catalog-inventory__category--observability"'
        in response.text
    )
    assert 'id="catalog-observability"' in response.text
    assert "Observability" in response.text
    assert "dashboards-as-code-generic" in response.text
    assert "monitors-as-code-generic" in response.text
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
    assert "refreshHomeResumeChip" in response.text
    assert "initGateDashboard" in response.text
    assert "initFormDraft" in response.text


def test_static_repave_home_mjs_served(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/static/repave-home.mjs")

    assert response.status_code == 200
    assert "initCatalogSearch" in response.text
    assert "repave-metric" in response.text
    assert "repave:recentPaths" in response.text
    assert "startViewTransition" in response.text
    assert "data-catalog-peek" in response.text


def test_activity_page(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/activity")

    assert response.status_code == 200
    assert "Activity" in response.text
    assert 'href="/activity"' in response.text
    assert "data-portal-view-toggle" in response.text or "audit.enabled" in response.text


def test_home_recent_activity_uses_artifact_labels(
    repo_root, output_config, tmp_path: Path, monkeypatch
) -> None:
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("REPAVE_AUDIT_FILE", str(audit_path))
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    append_audit_record(
        audit_path,
        AuditRecord(
            event="generation",
            blueprint_name="terraform-module-generic",
            blueprint_version="0.12.0",
            module_name="vpc-demo",
            dry_run=False,
            gates_outcome="passed",
            repository_url="https://github.com/opsdevcode/tf-aws-vpc-demo",
            acting_user="alice",
            extra={"artifact_version": "0.1.0"},
        ),
        repo_root=repo_root,
    )
    response = client.get("/")
    assert response.status_code == 200
    assert "Recent activity" in response.text
    assert 'activity-list__artifact-name">vpc-demo<' in response.text
    assert 'badge--muted">v0.1.0<' in response.text
    assert "via terraform-module-generic@0.12.0" in response.text
    assert "terraform-module-generic @ 0.12.0" not in response.text


def test_index_catalog_search(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/")

    assert response.status_code == 200
    assert "data-catalog-search" in response.text
    assert "data-catalog-card" in response.text
    assert "home-hero__mesh" in response.text
    assert "/static/repave-home.mjs" in response.text
    assert 'type="module"' in response.text
    assert "data-recent-paths" in response.text
    assert "data-peek-name=" in response.text
    assert "<repave-metric" in response.text
    assert "@view-transition" in response.text


def test_blueprint_form_draft_and_standards_diff_v2(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/terraform-module-generic")

    assert response.status_code == 200
    assert "data-repave-form-draft" in response.text
    assert "Standard pin drift" in response.text
    assert "form-actions__preflight" in response.text
    assert "form-actions__preflight-details" in response.text


def test_terraform_form_guided_advanced_mode(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/terraform-module-generic")

    assert response.status_code == 200
    assert 'data-form-mode="guided"' in response.text
    assert 'id="form-mode-toggle"' in response.text
    assert 'name="form_mode"' in response.text
    assert "data-form-mode-option" in response.text
    assert "Guided" in response.text
    assert "Advanced" in response.text
    assert "not freeform extras" in response.text
    assert 'id="policy-customization"' in response.text
    assert "data-form-advanced" in response.text
    # Advanced field labels remain in HTML (CSS/JS hide them); controls keep defaults.
    assert 'name="policy_pack_source"' in response.text
    assert 'name="include_backstage_catalog"' in response.text
    assert 'name="cost_center"' in response.text
    assert 'id="service-scope-panel"' in response.text


def test_ansible_form_guided_advanced_mode(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/ansible-role-generic")

    assert response.status_code == 200
    assert 'data-form-mode="guided"' in response.text
    assert 'id="form-mode-toggle"' in response.text
    assert 'name="form_mode"' in response.text
    assert 'id="ansible-role-pattern-block"' in response.text
    assert "data-form-advanced" in response.text
    assert 'name="min_ansible_version"' in response.text
    assert 'id="platform-advanced-panel"' in response.text


def test_static_repave_css_served(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/static/repave.css")

    assert response.status_code == 200
    assert "--accent" in response.text
    assert "--teal-500" in response.text
    assert "--dur-fast" in response.text
    assert "--btn-primary-fg" in response.text
    assert "@layer tokens, base, components, pages, utilities;" in response.text
    assert '[data-theme="dark"]' in response.text
    assert ".shell__wordmark" in response.text
    assert ".home-hero" in response.text
    assert "color-scheme: dark" in response.text
    assert ".shell__atmosphere" in response.text
    assert ".alert--fail" in response.text
    assert ".gate-table-wrap" in response.text
    assert 'form[data-form-mode="guided"]' in response.text
    assert ".gate-list" not in response.text


def test_env_badge_rendered_when_set(repo_root, output_config, monkeypatch) -> None:
    monkeypatch.setenv("REPAVE_ENV", "local")
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/")

    assert response.status_code == 200
    assert "badge--env" in response.text
    assert ">local<" in response.text


def test_version_badge_rendered_next_to_env(repo_root, output_config, monkeypatch) -> None:
    from repave_engine import __version__

    monkeypatch.setenv("REPAVE_ENV", "production")
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/")

    assert response.status_code == 200
    assert "badge--env" in response.text
    assert ">production<" in response.text
    assert "badge--version" in response.text
    assert f">v{__version__}<" in response.text
    env_pos = response.text.index("badge--env")
    version_pos = response.text.index("badge--version")
    assert env_pos < version_pos


def test_local_toolchain_warning_when_terraform_missing(
    repo_root, output_config, monkeypatch
) -> None:
    monkeypatch.setenv("REPAVE_ENV", "local")
    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda name: name != "terraform",
    )
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/")

    assert response.status_code == 200
    assert "shell__toolchain-warning" in response.text
    assert "terraform" in response.text.lower()
    assert "Docker Compose" in response.text


@pytest.mark.slow
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
    assert 'data-copy-target="#file-fallback-content-0"' in response.text
    assert 'data-copy-target="#file-explorer-content-0"' in response.text
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

    def fake_generate(
        blueprint,
        values,
        *,
        output_config,
        dry_run,
        github_token,
        repo_root=None,
        require_run=None,
    ):
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

    def fake_generate(
        blueprint,
        values,
        *,
        output_config,
        dry_run,
        github_token,
        repo_root=None,
        require_run=None,
    ):
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


def test_dry_run_from_form_last_value_wins_plan() -> None:
    class _Form:
        def getlist(self, key: str) -> list[str]:
            if key == "dry_run":
                return ["false", "true"]
            return []

    assert _dry_run_from_form(_Form()) is True


def test_dry_run_from_form_last_value_wins_apply() -> None:
    class _Form:
        def getlist(self, key: str) -> list[str]:
            if key == "dry_run":
                return ["true", "false"]
            return []

    assert _dry_run_from_form(_Form()) is False


def test_plan_preview_from_form() -> None:
    class _Form:
        def __init__(self, value: str) -> None:
            self._value = value

        def get(self, key: str, default: object = None) -> object:
            if key == "plan_preview":
                return self._value
            return default

    assert _plan_preview_from_form(_Form("1")) is True
    assert _plan_preview_from_form(_Form("")) is False


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
    assert "governance-card__details" in response.text
    assert "governance-card__summary-meta" in response.text
    assert "form-layout--split" in response.text
    assert "form-panel--terraform" in response.text
    assert "Plan (validate only)" in response.text
    assert "Apply (publish to GitHub)" in response.text
    assert "chip" in response.text
    assert "service-presets" in response.text
    assert "form-validation" in response.text
    assert "scope-resource-filter" in response.text
    assert "policy-rules-list" in response.text
    assert 'id="policy-rules-advanced"' in response.text
    assert 'id="policy-rules-advanced" class="policy-rules-advanced" open' not in response.text
    assert "policy-compact-summary" in response.text
    assert "policy-catalog" in response.text
    assert "data-repave-busy-form" in response.text
    assert "data-portal-submit-error" in response.text
    assert "form-actions--sticky" in response.text
    assert "Standard pin drift" in response.text
    assert "data-form-stepper" not in response.text
    assert "form-stepper" not in response.text
    assert "governance-meter" in response.text
    assert "data-dry-run-run" in response.text
    assert "data-dry-run-force" in response.text
    assert "Plan preview" in response.text
    assert ">Apply<" in response.text or ">Apply</button>" in response.text
    assert "form-actions__preflight-details" in response.text
    assert "form-actions__toolbar" in response.text
    assert "form-actions__delivery" in response.text
    assert "governance-card__gates-details" in response.text
    assert "receipt in" not in response.text.lower()
    assert "form-actions__buttons--stack" in response.text
    assert "repave.yaml" in response.text


def test_portal_static_js_intercepts_post_submit_errors(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/static/repave.js")
    assert response.status_code == 200
    body = response.text
    assert "initPortalFetchSubmit" in body
    assert "showPortalSubmitError" in body
    assert "formatPortalErrorDetail" in body
    assert "insufficient role" in body
    assert "generators group" in body
    assert "pipelineStageLabels" in body
    assert "Publishing to repository" in body
    assert "publish_finished" in body
    assert "data-run-publish-error" in body
    assert "publish_succeeded" in body
    assert "publish_progress" in body
    assert "refreshHomeResumeChip" in body
    assert "initPortalViewToggle" in body
    assert "Lineage summary copied" in body
    assert "Lineage receipt" not in body
    assert 'dryRun ? "Plan" : "Applied"' in body

    home = client.get("/static/repave-home.mjs")
    assert home.status_code == 200
    assert "initDemoPipelineFallback" in home.text
    assert "initCatalogCardMotion" in home.text


def test_portal_generate_viewer_returns_json_insufficient_role(
    tmp_path, output_config, monkeypatch: pytest.MonkeyPatch
) -> None:
    from itsdangerous import URLSafeSerializer

    from repave_engine.session_store import load_session_store

    (tmp_path / "repave.config.yaml").write_text(
        "durability:\n"
        "  async_generation: true\n"
        "  database_url: sqlite:///data/repave.sqlite\n"
        "  export_jsonl: false\n"
        "  require_session_secret: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REPAVE_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("REPAVE_SERVICE_MODE", "1")
    monkeypatch.setenv("REPAVE_OIDC_ISSUER", "https://idp.example.com")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_ID", "client")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_SECRET", "secret")
    monkeypatch.setenv("REPAVE_OIDC_REDIRECT_URI", "https://repave.example.com/auth/callback")

    client = TestClient(
        create_app(repo_root=tmp_path, output_config=output_config),
        raise_server_exceptions=False,
    )
    store = load_session_store(tmp_path)
    assert store is not None
    session_id = store.create_id()
    store.save(
        session_id,
        {"repave_user": {"sub": "viewer-1", "email": "v@example.com", "role": "viewer"}},
    )
    signer = URLSafeSerializer("test-secret", salt="repave-sql-session")
    client.cookies.set("session", signer.dumps(session_id))

    response = client.post(
        "/generate",
        data={
            "blueprint_name": "terraform-module-generic",
            "module_name": "demo",
            "dry_run": "true",
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 403
    assert response.headers.get("content-type", "").startswith("application/json")
    assert response.json()["detail"] == "Insufficient role"


def test_portal_generate_viewer_returns_html_insufficient_role(
    tmp_path, output_config, monkeypatch: pytest.MonkeyPatch
) -> None:
    from itsdangerous import URLSafeSerializer

    from repave_engine.session_store import load_session_store

    (tmp_path / "repave.config.yaml").write_text(
        "durability:\n"
        "  async_generation: true\n"
        "  database_url: sqlite:///data/repave.sqlite\n"
        "  export_jsonl: false\n"
        "  require_session_secret: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REPAVE_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("REPAVE_SERVICE_MODE", "1")
    monkeypatch.setenv("REPAVE_OIDC_ISSUER", "https://idp.example.com")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_ID", "client")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_SECRET", "secret")
    monkeypatch.setenv("REPAVE_OIDC_REDIRECT_URI", "https://repave.example.com/auth/callback")

    client = TestClient(
        create_app(repo_root=tmp_path, output_config=output_config),
        raise_server_exceptions=False,
    )
    store = load_session_store(tmp_path)
    assert store is not None
    session_id = store.create_id()
    store.save(
        session_id,
        {"repave_user": {"sub": "viewer-1", "email": "v@example.com", "role": "viewer"}},
    )
    signer = URLSafeSerializer("test-secret", salt="repave-sql-session")
    client.cookies.set("session", signer.dumps(session_id))

    response = client.post(
        "/generate",
        data={
            "blueprint_name": "terraform-module-generic",
            "module_name": "demo",
            "dry_run": "false",
        },
        headers={
            "Accept": "text/html,application/json;q=0.9",
            "Referer": "https://repave.example.com/blueprints/terraform-module-generic",
        },
    )
    assert response.status_code == 403
    assert "text/html" in response.headers.get("content-type", "")
    assert "data-portal-error-message" in response.text
    assert "generator access" in response.text
    assert "Could not complete request" in response.text


def test_generate_form_includes_plan_preview_flag(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/terraform-module-generic")
    assert response.status_code == 200
    assert "data-plan-preview-flag" in response.text


def test_generate_dry_run_promotes_missing_terraform_to_fail(
    repo_root, output_config, sample_inputs, monkeypatch
) -> None:
    monkeypatch.setattr("repave_engine.gate_runners.terraform_usable", lambda _dir: False)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "terraform-module-generic",
            "dry_run": "true",
            "plan_preview": "1",
            **sample_inputs,
        },
    )
    assert response.status_code == 200
    assert "badge--fail" in response.text
    assert "Dry-run preview runs all blueprint gates" in response.text
    assert "terraform-fmt" in response.text


def test_terraform_guided_only_generate_uses_defaults(
    repo_root, output_config, sample_inputs
) -> None:
    """Guided POST omits advanced catalog/policy fields; defaults still apply."""
    guided = {
        key: value
        for key, value in sample_inputs.items()
        if key
        not in {
            "cost_center",
            "policy_pack_source",
            "policy_profile",
            "policy_rules",
            "include_backstage_catalog",
            "system",
            "catalog_lifecycle",
            "provider_service_scope",
        }
    }
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={"blueprint_name": "terraform-module-generic", "dry_run": "true", **guided},
    )
    assert response.status_code == 200
    assert "Plan only" in response.text
    assert "Generated files" in response.text


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


def test_ansible_role_form_single_page(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/ansible-role-generic")
    assert response.status_code == 200
    assert 'id="role_pattern_source"' in response.text
    assert "data-form-stepper" not in response.text
    assert "form-stepper" not in response.text
    assert "data-dry-run-run" in response.text
    assert "data-dry-run-force" in response.text
    assert "Apply (publish to GitHub)" in response.text
    assert "form-actions__delivery" in response.text
    assert "form-actions__toolbar" in response.text
    assert "governance-card__gates-details" not in response.text
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


def test_ansible_guided_only_generate_uses_defaults(repo_root, output_config) -> None:
    """Guided POST omits advanced fields; blueprint defaults still apply."""
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "ansible-role-generic",
            "dry_run": "true",
            "role_name": "webserver",
            "namespace": "acme",
            "description": "Guided-only ansible generate",
            "support_linux": "true",
            "support_windows": "false",
            "windows_server_generation": "2022",
        },
    )
    assert response.status_code == 200
    assert "Plan only" in response.text
    assert "Generated files" in response.text


def test_observability_form_single_page(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/observability-as-code-generic")
    assert response.status_code == 200
    assert "data-form-stepper" not in response.text
    assert "Alert routing" in response.text
    assert "Legacy umbrella path" in response.text
    assert 'id="enable_policy_toggle"' in response.text
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

    mon_form = client.get("/blueprints/monitors-as-code-generic")
    assert mon_form.status_code == 200
    assert 'id="enable_policy_toggle"' in mon_form.text
    assert 'id="policy-customization"' in mon_form.text
    policy_region = mon_form.text.split('id="policy-customization"', 1)[1][:120]
    assert "hidden" in policy_region
    assert 'id="monitor_pack_source"' in mon_form.text
    assert 'id="monitor-pack-includes"' in mon_form.text
    assert "prometheus-red-plus-host-cpu" in mon_form.text
    mon_obs = client.get("/blueprints/monitors-as-code-generic/observability-catalog").json()
    assert len(mon_obs.get("monitor_packs", [])) >= 2

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


@pytest.mark.slow
def test_generate_resource_module_from_form(repo_root, output_config, monkeypatch) -> None:
    monkeypatch.setenv("REPAVE_GITHUB_ORG", output_config.github_org)
    monkeypatch.setenv("REPAVE_MODULES_ROOT", str(output_config.modules_root))
    captured: dict[str, object] = {}

    def fake_generate(
        blueprint,
        values,
        *,
        output_config,
        dry_run,
        github_token,
        repo_root=None,
        require_run=None,
    ):
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
    assert "governance-card__details" in response.text
    assert "form-layout--split" in response.text
    assert "ansible-lint" in response.text or "ansible_lint" in response.text
    assert 'id="support_linux_cb"' in response.text
    assert 'name="support_linux"' in response.text
    assert 'id="target_platforms_advanced"' in response.text
    assert "Advanced Galaxy platforms" in response.text
    assert 'id="min_ansible_version"' in response.text
    assert "2.18" in response.text
    assert 'option value="2.18" selected' in response.text


def test_github_repo_form_renders_phase2_controls(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/github-repo-generic")

    assert response.status_code == 200
    assert "form-panel--platform" in response.text
    assert "governance-card--platform" in response.text
    assert 'id="create_mode"' in response.text
    assert 'data-github-repo-when="template"' in response.text
    assert 'id="github-team-slugs-block"' in response.text
    assert 'id="team_slugs"' in response.text
    assert 'id="github-teams-hint"' in response.text
    assert 'id="github-team-slugs"' in response.text
    assert 'id="sync_team_membership_toggle"' in response.text
    assert 'id="sync_team_membership"' in response.text
    assert 'name="sync_team_membership"' in response.text
    assert 'id="membership_source_team"' in response.text
    assert 'id="github-source-team-members"' in response.text
    assert 'id="github-source-team-members-list"' in response.text
    assert 'id="ruleset_profile"' in response.text
    assert "default-pr — require PRs" in response.text
    assert "/api/v2/github/teams" in response.text
    assert "/api/v2/github/teams/${encodeURIComponent(slug)}/members" in response.text
    sync_pos = response.text.index('id="sync_team_membership_toggle"')
    source_pos = response.text.index('id="membership_source_team"')
    assert sync_pos < source_pos


def test_app_service_form_renders_backstage_catalog(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/app-service-generic")

    assert response.status_code == 200
    assert 'id="app-service-catalog"' in response.text
    assert "Backstage catalog" in response.text
    assert "governance-card__details" in response.text
    assert "data-form-stepper" not in response.text
    assert "Plan (validate only)" in response.text
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

    def fake_generate(
        blueprint,
        values,
        *,
        output_config,
        dry_run,
        github_token,
        repo_root=None,
        require_run=None,
    ):
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

    def fake_generate(
        blueprint,
        values,
        *,
        output_config,
        dry_run,
        github_token,
        repo_root=None,
        require_run=None,
    ):
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

    def fake_generate(
        blueprint,
        values,
        *,
        output_config,
        dry_run,
        github_token,
        repo_root=None,
        require_run=None,
    ):
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
    assert "Repository published" in response.text
    assert "repo-preview" in response.text
    assert "Open repository" in response.text
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

    def fake_generate(
        blueprint,
        values,
        *,
        output_config,
        dry_run,
        github_token,
        repo_root=None,
        require_run=None,
    ):
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
    assert "result-collapsible" in response.text
    assert "result-gates--animated" in response.text
    assert "Policy pack" in response.text
    assert "Estate default" in response.text


def test_update_form_page(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/update")

    assert response.status_code == 200
    assert "Upgrade existing repository" in response.text
    assert 'name="target_repo"' in response.text
    assert ">Upgrade</a>" in response.text
    assert "form-actions__toolbar" in response.text
    assert "page-supplement" in response.text
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
    assert "diff-viewer" in response.text or "Unified diffs" in response.text
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
    assert payload["checks"]["modules_root_writable"] is True


@pytest.mark.slow
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


def test_index_lists_service_stack_bundle(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/")
    assert response.status_code == 200
    assert "service-stack" in response.text
    assert "microservice-full" in response.text
    assert "/bundles/service-stack" in response.text
    assert "/bundles/microservice-full" in response.text
    assert "preset-chip" in response.text


def test_bundle_form_renders_shared_inputs(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/bundles/service-stack")
    assert response.status_code == 200
    assert 'name="bundle_name"' in response.text
    assert 'name="service_name"' in response.text
    assert "app-service-generic" in response.text
    assert "data-form-stepper" not in response.text
    assert "form-stepper" not in response.text
    assert "data-dry-run-run" in response.text
    assert "data-bundle-preview" in response.text
    assert "Repository preview" in response.text


def test_bundle_generate_dry_run_shows_member_files(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "bundle_name": "service-stack",
            "dry_run": "true",
            "service_name": "portal-bundle",
            "description": "Portal bundle dry-run test",
            "owner": "group:platform",
            "organization": "platform",
            "team": "payments",
            "port": "8080",
            "runtime": "python",
            "catalog_lifecycle": "experimental",
            "cloud_provider": "aws",
            "provider_services": "ec2,s3",
        },
    )
    assert response.status_code == 200
    assert "Bundle service-stack" in response.text
    assert "Generated files" in response.text or "file-explorer" in response.text
    assert "app-service-generic" in response.text
    assert "Lineage" in response.text
    assert "data-bundle-member-tabs" in response.text
    assert "Repositories" in response.text
    assert "bundle-topology" in response.text


def test_generate_stream_redirects_when_async_enabled(
    repo_root,
    output_config,
    sample_inputs,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPAVE_ASYNC_GENERATION", "true")
    monkeypatch.setenv("REPAVE_RUNS_DB", str(tmp_path / "runs.sqlite"))
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "terraform-module-generic",
            "dry_run": "true",
            "stream": "1",
            **sample_inputs,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers.get("location", "")
    assert location.startswith("/runs/")


def test_run_console_page_when_async_enabled(
    repo_root,
    output_config,
    sample_inputs,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPAVE_ASYNC_GENERATION", "true")
    monkeypatch.setenv("REPAVE_RUNS_DB", str(tmp_path / "runs.sqlite"))
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    submit = client.post(
        "/api/v1/runs",
        json={
            "blueprint": "terraform-module-generic",
            "dry_run": True,
            "inputs": sample_inputs,
        },
    )
    assert submit.status_code == 202
    run_id = submit.json()["run_id"]
    page = client.get(f"/runs/{run_id}")
    assert page.status_code == 200
    assert "data-run-console" in page.text
    assert "data-run-progress" in page.text
    assert "command-palette" in page.text


@pytest.mark.slow
def test_run_events_sse_replays_terminal_event(
    repo_root,
    output_config,
    sample_inputs,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import time

    monkeypatch.setenv("REPAVE_ASYNC_GENERATION", "true")
    monkeypatch.setenv("REPAVE_RUNS_DB", str(tmp_path / "runs.sqlite"))
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    submit = client.post(
        "/api/v1/runs",
        json={
            "blueprint": "terraform-module-generic",
            "dry_run": True,
            "inputs": sample_inputs,
        },
    )
    assert submit.status_code == 202
    run_id = submit.json()["run_id"]
    deadline = time.time() + 180
    while time.time() < deadline:
        record = client.get(f"/api/v1/runs/{run_id}").json()
        if record["status"] in ("succeeded", "dead_letter"):
            break
        time.sleep(0.25)
    else:
        pytest.fail("run did not finish in time")

    with client.stream("GET", f"/api/v1/runs/{run_id}/events") as response:
        assert response.status_code == 200
        body = response.read().decode("utf-8")
    assert "run_finished" in body or "run_failed" in body


@pytest.mark.slow
def test_run_result_view_reuses_async_artifact_without_regenerating(
    repo_root,
    output_config,
    sample_inputs,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import time

    from repave_engine.pipeline import generate_from_blueprint as pipeline_generate

    monkeypatch.setenv("REPAVE_ASYNC_GENERATION", "true")
    monkeypatch.setenv("REPAVE_RUNS_DB", str(tmp_path / "runs.sqlite"))
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    submit = client.post(
        "/api/v1/runs",
        json={
            "blueprint": "terraform-module-generic",
            "dry_run": True,
            "inputs": sample_inputs,
        },
    )
    assert submit.status_code == 202
    run_id = submit.json()["run_id"]
    deadline = time.time() + 180
    while time.time() < deadline:
        record = client.get(f"/api/v1/runs/{run_id}").json()
        if record["status"] in ("succeeded", "dead_letter"):
            break
        time.sleep(0.25)
    else:
        pytest.fail("run did not finish in time")
    assert record["status"] == "succeeded"
    assert record.get("result", {}).get("artifact_root")

    regen_calls = 0

    def _spy_generate(*args: object, **kwargs: object) -> GenerationResult:
        nonlocal regen_calls
        regen_calls += 1
        return pipeline_generate(*args, **kwargs)

    monkeypatch.setattr("repave_engine.api.generate_from_blueprint", _spy_generate)
    page = client.get(f"/runs/{run_id}/result")
    assert page.status_code == 200
    assert regen_calls == 0
    assert "terraform-module-generic" in page.text
