from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from license_helpers import install_repave_license
from repave_engine.api import _dry_run_from_form, _plan_preview_from_form, create_app
from repave_engine.audit import AuditRecord, append_audit_record
from repave_engine.gate_registry import GateResult
from repave_engine.pipeline import GenerationResult
from repave_engine.render import RenderedFile, RenderResult
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


def test_signup_redirects_when_auth_disabled(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/signup", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/"


def test_index_lists_blueprints(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/")

    assert response.status_code == 200
    assert "terraform-module-generic" in response.text
    assert "/static/repave.css" in response.text
    assert "/static/repave.js" in response.text
    assert "/static/repave-motion.mjs" in response.text
    assert 'id="last-run-snippet"' in response.text
    assert 'class="skip-link"' in response.text
    assert 'id="main-content"' in response.text
    assert 'id="repave-toast"' in response.text
    assert 'class="shell"' in response.text
    assert "shell__atmosphere" in response.text
    assert "home-console" in response.text
    assert 'rel="icon"' in response.text
    assert "/static/brand/favicon.svg" in response.text
    assert "/static/brand/svg/repave-mark-dark.svg" in response.text
    assert "shell__wordmark" in response.text
    assert "shell__edition" in response.text
    assert "shell__tagline" in response.text
    assert "home-console__header" in response.text
    assert "home-console__title" in response.text
    assert "The intelligent platform layer" in response.text
    assert "Golden paths" in response.text
    assert "shell__mark-frame" in response.text
    assert "repave v3 · The intelligent platform layer" in response.text
    assert 'property="og:image"' in response.text
    assert "static/brand/social/repave-social-card.png" in response.text
    assert 'name="twitter:card"' in response.text
    assert "data-home-quick" in response.text
    assert "catalog-inventory__item-icon" in response.text
    assert "catalog-inventory__category" in response.text
    assert "catalog-inventory--browse" in response.text
    assert "catalog-inventory__heading" in response.text
    assert "home-catalog-column" in response.text
    assert "catalog-inventory__summary" not in response.text
    assert 'href="/library"' in response.text
    assert 'href="/library"' in response.text
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
    assert "initChoiceTiles" in response.text


def test_static_repave_home_mjs_served(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/static/repave-home.mjs")

    assert response.status_code == 200
    assert "initCatalogSearch" in response.text
    assert "repave-catalog.mjs" in response.text
    assert "repave-metric" in response.text
    assert "repave:recentPaths" in response.text
    assert "data-catalog-peek" in response.text


def test_static_repave_catalog_and_library_mjs_served(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    catalog = client.get("/static/repave-catalog.mjs")
    assert catalog.status_code == 200
    assert "initCatalogSearch" in catalog.text
    assert "startViewTransition" in catalog.text
    assert "extraConstraintActive" in catalog.text

    library = client.get("/static/repave-library.mjs")
    assert library.status_code == 200
    assert "initCatalogSearch" in library.text
    assert "initLibraryDrawerMotion" in library.text
    assert "repave-catalog.mjs" in library.text

    assert "initLibraryDrawerMotion" in catalog.text
    assert "prefersFinePointer" in catalog.text
    assert "repave-motion.mjs" in catalog.text

    motion = client.get("/static/repave-motion.mjs")
    assert motion.status_code == 200
    assert "initPointerFaces" in motion.text
    assert "prefersFinePointer" in motion.text
    assert "data-library-drawer" in motion.text
    assert "home-catalog" in motion.text
    assert "data-motion-face" in motion.text
    assert "btn--primary" in motion.text
    assert "ATMOSPHERE_RANGE" in motion.text
    assert "motion-ripple" in motion.text
    assert "NEIGHBOR_PUSH" in motion.text
    assert "fleet-tile--choice" in motion.text
    assert "button[type=submit]" in motion.text
    assert "glare" not in motion.text


def test_activity_page(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/activity")

    assert response.status_code == 200
    assert "Activity" in response.text
    assert 'href="/activity"' in response.text
    assert "data-portal-view-toggle" in response.text or "audit.enabled" in response.text


def test_activity_inflight_strip_when_async_enabled(
    repo_root, output_config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REPAVE_ASYNC_GENERATION", "true")
    monkeypatch.setenv("REPAVE_RUNS_DB", str(tmp_path / "runs.sqlite"))
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    body = client.get("/activity").text
    assert "data-activity-inflight" in body
    assert "In-flight runs" in body
    assert "data-activity-inflight-list" in body
    assert "data-activity-inflight-hint" in body
    js = client.get("/static/repave.js").text
    assert "initActivityInflight" in js
    assert "fetchQueuedAndRunning" in js


def test_home_does_not_embed_activity_feed(
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
    assert 'class="home-activity"' not in response.text
    assert 'class="activity-story"' not in response.text
    assert ">vpc-demo<" not in response.text
    assert 'href="/activity"' in response.text


def test_home_no_activity_link_when_audit_disabled(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/")
    assert response.status_code == 200
    assert 'class="home-activity"' not in response.text


def test_index_catalog_search(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/")

    assert response.status_code == 200
    assert "data-catalog-search" in response.text
    assert "data-catalog-card" in response.text
    assert "home-console__title" in response.text
    assert "/static/repave-home.mjs" in response.text
    assert 'type="module"' in response.text
    assert "data-home-quick" in response.text
    assert "data-peek-name=" in response.text
    assert "data-motion-face" in response.text
    assert "data-motion-depth" in response.text
    assert "@view-transition" in response.text


def test_blueprint_form_draft_and_standards_diff_v2(repo_root, output_config) -> None:
    from repave_engine.blueprint import blueprint_dir, load_blueprint
    from repave_engine.standards_diff import standards_diff_for_pin

    blueprint = load_blueprint(
        blueprint_dir(repo_root, "terraform-module-generic"),
        repo_root=repo_root,
    )
    standards = standards_diff_for_pin(
        repo_root,
        standard_source=blueprint.standard_source,
        pinned_version=blueprint.standard_version,
    )

    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/terraform-module-generic")

    assert response.status_code == 200
    assert "data-repave-form-draft" in response.text
    assert "Pin drift" in response.text
    assert "form-actions__preflight" in response.text
    assert "form-actions__preflight-details" in response.text
    if standards.available and standards.has_changes:
        assert "standards-diff-panel" in response.text
        assert "diff-split" in response.text
        assert "Domain standard changes since pin" in response.text
    else:
        assert "Domain standard changes since pin" not in response.text
    assert "Pin drift" in response.text
    assert "Checkov pack" in response.text


def test_terraform_form_guided_advanced_mode(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/terraform-module-generic")

    assert response.status_code == 200
    assert "Could not load resources for this service." in response.text
    assert 'data-form-mode="guided"' in response.text
    assert 'id="form-mode-toggle"' in response.text
    assert 'name="form_mode"' in response.text
    assert "data-form-mode-option" in response.text
    assert "Guided" in response.text
    assert "Advanced" in response.text
    assert "not freeform extras" in response.text
    assert "Generated from your selections" in response.text
    assert "data-form-identity" in response.text
    assert 'data-guided-from="{provider_services}"' in response.text
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
    assert "Generated from your selections" in response.text
    assert 'data-guided-from="{role_pattern_source}"' in response.text
    assert "data-form-advanced" in response.text
    assert 'name="min_ansible_version"' in response.text
    assert 'id="platform-advanced-panel"' in response.text


def test_helm_form_guided_advanced_mode(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/helm-chart-generic")

    assert response.status_code == 200
    assert 'data-form-mode="guided"' in response.text
    assert 'id="form-mode-toggle"' in response.text
    assert "Generated from your selections" in response.text
    assert 'data-guided-from="{image_repository}"' in response.text
    assert "data-form-advanced" in response.text
    assert 'name="include_backstage_catalog"' in response.text
    assert 'name="enable_deploy_pipeline"' in response.text
    assert 'name="gitops_repo"' in response.text
    assert 'name="image_repository"' in response.text


def test_gitops_form_guided_advanced_mode(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/gitops-deployment-generic")

    assert response.status_code == 200
    assert 'data-form-mode="guided"' in response.text
    assert 'id="form-mode-toggle"' in response.text
    assert "Generated from your selections" in response.text
    assert 'data-guided-from="{environment}-{chart_name}"' in response.text
    assert "data-form-advanced" in response.text
    assert 'name="destination_server"' in response.text
    assert 'name="argocd_project"' in response.text
    assert 'name="flux_source_name"' in response.text
    assert 'name="chart_repo_url"' in response.text


@pytest.mark.parametrize(
    ("blueprint_name", "guided_from"),
    [
        ("checkov-policy-generic", "{policy_profile}"),
        ("opa-policy-generic", "{policy_profile}"),
        ("azure-policy-generic", "{policy_profile}"),
    ],
)
def test_policy_form_guided_advanced_mode(
    repo_root, output_config, blueprint_name: str, guided_from: str
) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get(f"/blueprints/{blueprint_name}")

    assert response.status_code == 200
    assert 'data-form-mode="guided"' in response.text
    assert 'id="form-mode-toggle"' in response.text
    assert "Generated from your selections" in response.text
    assert f'data-guided-from="{guided_from}"' in response.text
    assert "data-form-advanced" in response.text
    assert 'id="policy-customization"' in response.text
    assert 'name="policy_pack_source"' in response.text
    assert 'name="policy_profile"' in response.text
    if blueprint_name == "opa-policy-generic":
        assert 'name="plan_demo"' in response.text


def test_helm_guided_only_generate_uses_defaults(repo_root, output_config) -> None:
    """Guided POST omits catalog and GitOps deploy knobs; defaults still apply."""
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "helm-chart-generic",
            "dry_run": "true",
            "image_repository": "ghcr.io/example/checkout-api",
            "owner": "platform-engineering",
            "environment": "dev",
            "service_type": "ClusterIP",
            "service_port": "8080",
            "enable_ingress": "false",
        },
    )
    assert response.status_code == 200
    assert "Plan only" in response.text
    assert "Generated files" in response.text


def test_gitops_guided_only_generate_uses_defaults(repo_root, output_config) -> None:
    """Guided POST omits cluster/project fields; defaults still apply."""
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "gitops-deployment-generic",
            "dry_run": "true",
            "environment": "dev",
            "gitops_engine": "argocd",
            "chart_repo_url": "https://charts.example.com",
            "chart_name": "checkout-api",
            "chart_version": "1.2.3",
            "target_namespace": "checkout",
            "sync_policy": "manual",
        },
    )
    assert response.status_code == 200
    assert "Plan only" in response.text
    assert "Generated files" in response.text


def test_checkov_guided_only_generate_uses_defaults(repo_root, output_config) -> None:
    """Guided POST omits pack/profile/rules; defaults and identity fill still apply."""
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "checkov-policy-generic",
            "dry_run": "true",
            "organization": "acme",
        },
    )
    assert response.status_code == 200
    assert "Plan only" in response.text
    assert "Generated files" in response.text


def test_app_service_form_guided_advanced_mode(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/app-service-generic")

    assert response.status_code == 200
    assert 'data-form-mode="guided"' in response.text
    assert 'id="form-mode-toggle"' in response.text
    assert "Generated from your selections" in response.text
    assert 'data-guided-from="{runtime}-{layout}"' in response.text
    assert "data-form-advanced" in response.text
    assert 'id="app-service-catalog"' in response.text
    assert 'name="enable_deploy_pipeline"' in response.text
    assert 'name="runtime"' in response.text


def test_ansible_collection_form_guided_advanced_mode(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/ansible-collection-generic")

    assert response.status_code == 200
    assert 'data-form-mode="guided"' in response.text
    assert "Generated from your selections" in response.text
    assert 'data-guided-from="{sample_role_pattern_source}"' in response.text
    assert "data-form-advanced" in response.text
    assert 'id="ansible-collection-sample-pattern-block"' in response.text
    assert 'name="min_ansible_version"' in response.text
    assert 'name="namespace"' in response.text


def test_ansible_playbook_form_guided_advanced_mode(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/ansible-playbook-project")

    assert response.status_code == 200
    assert 'data-form-mode="guided"' in response.text
    assert "Generated from your selections" in response.text
    assert 'data-guided-from="{environment}-{playbook_pattern_source}"' in response.text
    assert "data-form-advanced" in response.text
    assert 'id="ansible-playbook-pattern-block"' in response.text
    assert 'name="min_ansible_version"' in response.text
    assert 'name="pinned_roles"' in response.text


def test_env_stack_form_guided_advanced_mode(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/terraform-environment-stack")

    assert response.status_code == 200
    assert 'data-form-mode="guided"' in response.text
    assert "Generated from your selections" in response.text
    assert 'data-guided-from="{environment}-{cloud_provider}"' in response.text
    assert "data-form-advanced" in response.text
    assert 'name="cost_center"' in response.text
    assert 'id="policy-customization"' in response.text
    assert 'name="pinned_modules"' in response.text


def test_app_service_guided_only_generate_uses_defaults(repo_root, output_config) -> None:
    """Guided POST omits catalog and deploy knobs; defaults still apply."""
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "app-service-generic",
            "dry_run": "true",
            "owner": "group:platform",
            "runtime": "python",
            "layout": "http-api",
            "port": "8080",
        },
    )
    assert response.status_code == 200
    assert "Plan only" in response.text
    assert "Generated files" in response.text


def test_ansible_collection_guided_only_generate_uses_defaults(repo_root, output_config) -> None:
    """Guided POST omits pattern and min version; defaults still apply."""
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "ansible-collection-generic",
            "dry_run": "true",
            "namespace": "acme",
            "collection_name": "platform",
            "description": "Guided-only collection generate",
            "sample_role_name": "sample",
            "support_linux": "true",
            "support_windows": "false",
        },
    )
    assert response.status_code == 200
    assert "Plan only" in response.text
    assert "Generated files" in response.text


def test_ansible_playbook_guided_only_generate_uses_defaults(repo_root, output_config) -> None:
    """Guided POST omits pattern and min version; defaults still apply."""
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "ansible-playbook-project",
            "dry_run": "true",
            "project_name": "baseline",
            "description": "Guided-only playbook generate",
            "environment": "dev",
            "support_linux": "true",
            "support_windows": "false",
        },
    )
    assert response.status_code == 200
    assert "Plan only" in response.text
    assert "Generated files" in response.text


def test_env_stack_guided_only_generate_uses_defaults(repo_root, output_config) -> None:
    """Guided POST omits cost center and policy; defaults still apply."""
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "terraform-environment-stack",
            "dry_run": "true",
            "cloud_provider": "aws",
            "environment": "dev",
            "owner": "platform-engineering",
        },
    )
    assert response.status_code == 200
    assert "Plan only" in response.text
    assert "Generated files" in response.text


def test_static_repave_css_served(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/static/repave.css")

    assert response.status_code == 200
    assert "--accent" in response.text
    assert "--brand-primary" in response.text
    assert "--teal-500" in response.text
    assert "--dur-fast" in response.text
    assert "--btn-primary-fg" in response.text
    assert "@layer tokens, base, components, pages, utilities;" in response.text
    assert '[data-theme="dark"]' in response.text
    assert ".shell__wordmark" in response.text
    assert ".shell__edition" in response.text
    assert ".home-console" in response.text
    assert ".home-catalog-column" in response.text
    assert ".catalog-inventory--browse" in response.text
    assert "color-scheme: dark" in response.text
    assert ".shell__atmosphere" in response.text
    assert ".alert--fail" in response.text
    assert ".gate-table-wrap" in response.text
    assert 'form[data-form-mode="guided"]' in response.text
    assert "[data-form-identity]" in response.text
    assert ".identity-preview" in response.text
    assert ".gate-list" not in response.text


def test_brand_static_assets_served(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    mark = client.get("/static/brand/svg/repave-mark-dark.svg")
    favicon = client.get("/static/brand/favicon.svg")
    social = client.get("/static/brand/social/repave-social-card.png")
    assert mark.status_code == 200
    assert "platform layer" in mark.text.lower() or 'viewBox="0 0 80 80"' in mark.text
    assert favicon.status_code == 200
    assert favicon.headers["content-type"].startswith("image/")
    assert 'fill="#0F172A"' in favicon.text
    assert 'stroke="#F59E0B"' in favicon.text
    assert "stroke-dasharray" not in favicon.text
    assert social.status_code == 200


def test_portal_white_label_logo_and_accent(
    repo_root, output_config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REPAVE_PORTAL_LOGO_URL", "/static/brand/svg/repave-mark-monochrome.svg")
    monkeypatch.setenv("REPAVE_PORTAL_ACCENT_COLOR", "#0ea5e9")
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/")
    assert response.status_code == 200
    assert '/static/brand/svg/repave-mark-monochrome.svg"' in response.text
    assert "--brand-primary: #0ea5e9" in response.text
    assert 'content="#0ea5e9"' in response.text


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
    assert "Plan (validate only)" not in response.text
    assert "Apply (publish to GitHub)" not in response.text
    assert "chip" in response.text
    assert "service-presets" in response.text
    assert "form-validation" in response.text
    assert (
        'providerSelect.addEventListener("change", () => renderServices(providerSelect.value))'
        in response.text
    )
    assert "scope-resource-filter" in response.text
    assert "policy-rules-list" in response.text
    assert 'id="policy-rules-advanced"' in response.text
    assert 'id="policy-rules-advanced" class="policy-rules-advanced" open' not in response.text
    assert "policy-compact-summary" in response.text
    assert "policy-catalog" in response.text
    assert "data-repave-busy-form" in response.text
    assert "data-portal-submit-error" in response.text
    assert "form-actions--sticky" in response.text
    assert "Pin drift" in response.text
    assert "data-form-stepper" not in response.text
    assert "form-stepper" not in response.text
    assert "governance-meter" in response.text
    assert "data-dry-run-run" in response.text
    assert "data-dry-run-force" in response.text
    assert "Plan preview" in response.text
    assert ">Apply<" in response.text or ">Apply</button>" in response.text
    assert "form-actions__preflight-details" in response.text
    assert "form-actions__toolbar--solo" in response.text
    assert 'name="dry_run" value="true"' in response.text
    assert 'name="dry_run" value="false"' in response.text
    assert "form-actions__delivery--wire" in response.text
    assert "Stream gates" not in response.text
    assert "governance-card__gates-details" in response.text
    assert "receipt in" not in response.text.lower()
    assert "form-actions__buttons--stack" in response.text
    apply_pos = response.text.find('class="btn btn--secondary" type="submit"')
    hidden_pos = response.text.find("data-dry-run-submit")
    assert 0 <= hidden_pos < apply_pos
    assert "repave.yaml" in response.text


def test_blueprint_form_prefills_allowlisted_query_params(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get(
        "/blueprints/terraform-module-generic",
        params={
            "cloud_provider": "gcp",
            "module_name": "vpc-core",
            "dry_run": "false",
            "secret": "nope",
            "unknown_field": "x",
        },
    )
    html = response.text
    assert 'value="gcp" selected' in html or 'value="gcp" selected="selected"' in html
    assert 'id="module_name"' in response.text
    assert 'value="vpc-core"' in response.text
    assert "data-assistant-prefill" in html
    assert 'name="secret"' not in response.text
    assert 'name="unknown_field"' not in response.text
    assert 'name="dry_run" value="false"' in response.text
    # Plan/Apply radios still present; query dry_run does not select Apply
    assert 'name="dry_run" value="true"' in response.text


def test_blueprint_form_ignores_invalid_enum_prefill(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get(
        "/blueprints/terraform-module-generic",
        params={"cloud_provider": "nope"},
    )
    html = response.text
    assert 'value="nope"' not in html
    assert 'value="aws" selected' in html or 'value="aws" selected="selected"' in html


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
    assert "data-assistant-prefill" in body
    assert "Lineage summary copied" in body
    assert "Lineage receipt" not in body
    assert 'dryRun ? "Plan" : "Applied"' in body
    assert 'streamBox.type === "checkbox"' in body
    assert "hidden stream=1 always forces" in body

    home = client.get("/static/repave-home.mjs")
    assert home.status_code == 200
    assert "syncHomeQuickVisibility" in home.text
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
    install_repave_license(monkeypatch, tmp_path)

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
    install_repave_license(monkeypatch, tmp_path)

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
            "catalog_depends_on",
            "catalog_provides_apis",
            "catalog_kubernetes_id",
            "catalog_kubernetes_namespace",
            "catalog_consumes_apis",
            "catalog_subcomponent_of",
            "catalog_tags",
            "catalog_links",
            "catalog_github_slug",
            "catalog_domain",
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


def test_terraform_guided_generate_derives_name_and_description(
    repo_root, output_config, sample_inputs
) -> None:
    """Guided POST omits module_name and description; selections fill them."""
    guided = {
        key: value
        for key, value in sample_inputs.items()
        if key
        not in {
            "module_name",
            "description",
            "cost_center",
            "policy_pack_source",
            "policy_profile",
            "policy_rules",
            "include_backstage_catalog",
            "system",
            "catalog_lifecycle",
            "catalog_depends_on",
            "catalog_provides_apis",
            "catalog_kubernetes_id",
            "catalog_kubernetes_namespace",
            "catalog_consumes_apis",
            "catalog_subcomponent_of",
            "catalog_tags",
            "catalog_links",
            "catalog_github_slug",
            "catalog_domain",
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
    assert "ec2-s3" in response.text
    assert "aws Terraform module covering" in response.text


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
    assert "Apply (publish to GitHub)" not in response.text
    assert "form-actions__delivery--wire" in response.text
    assert "form-actions__toolbar--solo" in response.text
    assert "Plan preview" in response.text
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


def test_ansible_guided_generate_derives_name_and_description(repo_root, output_config) -> None:
    """Guided POST omits role_name and description; pattern and namespace fill them."""
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "ansible-role-generic",
            "dry_run": "true",
            "namespace": "acme",
            "support_linux": "true",
            "support_windows": "false",
            "windows_server_generation": "2022",
        },
    )
    assert response.status_code == 200
    assert "Plan only" in response.text
    assert "Generated files" in response.text
    assert "linux_service" in response.text
    assert "acme Ansible role" in response.text


def test_observability_form_single_page(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/observability-as-code-generic")
    assert response.status_code == 200
    assert "data-form-stepper" not in response.text
    assert "Alert routing" in response.text
    assert "Legacy umbrella path" in response.text
    assert 'id="enable_policy_toggle"' in response.text
    assert "governance-drift-details" in response.text or "Pin drift" in response.text
    assert "Could not load service inventory" in response.text


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
    assert "Could not load module inventory" in response.text
    assert 'name="pinned_modules"' in response.text
    assert "form-layout--split" in response.text


def test_ansible_playbook_form_renders_role_inventory_picker(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/blueprints/ansible-playbook-project")

    assert response.status_code == 200
    assert 'id="pinned-roles-rows"' in response.text
    assert 'id="add-pinned-role"' in response.text
    assert "role-inventory" in response.text
    assert "if (!response.ok)" in response.text
    assert "Could not load role inventory" in response.text
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
    assert 'id="github-team-picker"' in response.text
    assert 'id="github-team-filter"' in response.text
    assert 'id="github-team-slugs-extra"' in response.text
    assert 'id="team_slugs"' in response.text
    assert 'id="github-teams-hint"' in response.text
    assert 'id="github-team-slugs"' in response.text
    assert 'id="sync_team_membership_toggle"' in response.text
    assert 'id="sync_team_membership"' in response.text
    assert 'name="sync_team_membership"' in response.text
    assert 'id="membership_source_team"' in response.text
    assert 'id="github-source-team-select"' in response.text
    assert "fillSourceSelect" in response.text
    assert 'id="github-source-team-members"' in response.text
    assert 'id="github-source-team-members-list"' in response.text
    assert 'id="ruleset_profile"' in response.text
    assert "default-pr — require PRs" in response.text
    assert "/api/v2/github/teams" in response.text
    assert "/api/v2/github/teams/${encodeURIComponent(slug)}/members" in response.text
    assert "you can add to this repository" in response.text
    assert "renderTeamPicker" in response.text
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
    assert "Plan (validate only)" not in response.text
    assert "Plan preview" in response.text
    assert "data-dry-run-run" in response.text
    assert 'id="catalog_lifecycle"' in response.text
    assert 'id="catalog_depends_on"' in response.text
    assert 'id="catalog_provides_apis"' in response.text
    assert 'id="catalog_kubernetes_id"' in response.text
    assert 'id="catalog_kubernetes_namespace"' in response.text
    assert 'id="catalog_consumes_apis"' in response.text
    assert 'id="catalog_subcomponent_of"' in response.text
    assert 'id="catalog_tags"' in response.text
    assert 'id="catalog_links"' in response.text
    assert 'id="catalog_github_slug"' in response.text
    assert 'id="catalog_domain"' in response.text
    assert 'id="runtime"' in response.text
    assert ">go</option>" in response.text
    assert 'data-form-mode="guided"' in response.text
    assert 'data-guided-from="{runtime}-{layout}"' in response.text
    assert "data-form-advanced" in response.text


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


def test_plan_preview_with_files_surfaces_copyable_explorer(
    repo_root,
    output_config,
    sample_inputs,
    monkeypatch,
) -> None:
    """Plan preview with rendered files must not look like a dead-end failure."""

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
                GateResult("terraform-fmt", False, False, "terraform not available"),
            ],
            module_repository=None,
            pr_plan=None,
            pr_message="",
            dry_run=True,
            rendered_files=(
                RenderedFile(path="README.md", content="# demo module\n", truncated=False),
                RenderedFile(
                    path="main.tf",
                    content='resource "null_resource" "x" {}\n',
                    truncated=False,
                ),
            ),
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
    assert "Plan preview ready" in response.text
    assert "Browse and copy generated files below" in response.text
    assert "result-hero--preview" in response.text
    assert "Generation failed" not in response.text
    assert "Generated files" in response.text
    assert 'data-copy-target="#file-explorer-content-0"' in response.text
    assert "# demo module" in response.text
    files_idx = response.text.index("Generated files")
    gates_idx = response.text.index('aria-labelledby="gates-heading"')
    assert files_idx < gates_idx


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
    assert "Auto-merge" in response.text
    assert "Review required" in response.text
    assert "v3.enabled" in response.text
    assert "Opening the upgrade pull request merges Allowed" in response.text


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
    assert "data-run-file-preview" in page.text
    assert "Browse generated files" in page.text


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
    assert "Generated files" in page.text
    assert "data-copy-target" in page.text
    assert "Browse and copy generated files below" in page.text
