from __future__ import annotations

from pathlib import Path

import yaml

from repave_engine.backstage_catalog import (
    TECHDOCS_REF_DIR,
    build_catalog_document,
    catalog_component_name,
    catalog_entity_refs,
    catalog_github_slug,
    catalog_links,
    catalog_optional_text,
    catalog_techdocs_ref,
    enrich_catalog_values,
    should_emit_catalog,
    write_backstage_catalog_if_enabled,
)
from repave_engine.blueprint import Blueprint


def _bp(artifact_type: str) -> Blueprint:
    return Blueprint(
        path=Path("/tmp/test-blueprint"),
        name="test-blueprint",
        version="1.0.0",
        description="Test blueprint",
        artifact_type=artifact_type,
        standard_source="standards/test",
        standard_version="1.0.0",
        inputs=(),
        template_engine="copier",
        template_path="template",
        gates=(),
        output_type="pull_request",
        output_repo_name_template="test-{name}",
        output_title_template="Test",
    )


def test_should_emit_catalog_app_service_always() -> None:
    bp = _bp("app-service")
    assert should_emit_catalog(bp, {}) is True
    assert should_emit_catalog(bp, {"include_backstage_catalog": "false"}) is True


def test_should_emit_catalog_optional_flag() -> None:
    bp = _bp("helm-chart")
    assert should_emit_catalog(bp, {}) is False
    assert should_emit_catalog(bp, {"include_backstage_catalog": "true"}) is True


def test_build_catalog_document_annotations() -> None:
    bp = _bp("app-service")
    doc = build_catalog_document(
        bp,
        {
            "service_name": "checkout",
            "description": "Checkout API",
            "owner": "group:payments",
            "system": "commerce",
            "catalog_lifecycle": "production",
            "_repave_blueprint_name": "app-service-generic",
            "_repave_blueprint_version": "0.3.0",
            "_repave_standard_source": "standards/app/service-standard.md",
            "_repave_standard_version": "1.0.0",
            "_repave_engine_version": "1.43.0",
        },
    )
    assert doc["kind"] == "Component"
    assert doc["metadata"]["name"] == "checkout"
    assert doc["spec"]["owner"] == "group:payments"
    assert doc["spec"]["system"] == "commerce"
    assert doc["spec"]["lifecycle"] == "production"
    assert doc["spec"]["type"] == "service"
    annotations = doc["metadata"]["annotations"]
    assert annotations["repave.dev/blueprint"] == "app-service-generic"
    assert annotations["repave.dev/engine-version"] == "1.43.0"
    assert "dependsOn" not in doc["spec"]
    assert "providesApis" not in doc["spec"]
    assert "consumesApis" not in doc["spec"]
    assert "subcomponentOf" not in doc["spec"]
    assert "tags" not in doc["metadata"]
    assert "links" not in doc["metadata"]
    assert "github.com/project-slug" not in annotations
    assert "backstage.io/kubernetes-id" not in annotations
    assert "backstage.io/kubernetes-namespace" not in annotations


def test_catalog_entity_refs_splits_comma_and_newlines() -> None:
    assert catalog_entity_refs("component:default/api, resource:default/bucket") == (
        "component:default/api",
        "resource:default/bucket",
    )
    assert catalog_entity_refs("component:default/api\nresource:default/bucket") == (
        "component:default/api",
        "resource:default/bucket",
    )
    assert catalog_entity_refs("  ") == ()
    assert catalog_entity_refs(None) == ()


def test_build_catalog_document_relations() -> None:
    bp = _bp("app-service")
    doc = build_catalog_document(
        bp,
        {
            "service_name": "checkout",
            "owner": "group:payments",
            "catalog_depends_on": "component:default/tf-aws-demo, resource:default/db",
            "catalog_provides_apis": "api:default/checkout",
        },
    )
    assert doc["spec"]["dependsOn"] == [
        "component:default/tf-aws-demo",
        "resource:default/db",
    ]
    assert doc["spec"]["providesApis"] == ["api:default/checkout"]


def test_catalog_optional_text_strips() -> None:
    assert catalog_optional_text("  ns  ") == "ns"
    assert catalog_optional_text(None) == ""
    assert catalog_optional_text("  ") == ""


def test_build_catalog_document_kubernetes_annotations() -> None:
    bp = _bp("app-service")
    doc = build_catalog_document(
        bp,
        {
            "service_name": "checkout",
            "owner": "group:payments",
            "catalog_kubernetes_id": "checkout",
            "catalog_kubernetes_namespace": "prod",
        },
    )
    annotations = doc["metadata"]["annotations"]
    assert annotations["backstage.io/kubernetes-id"] == "checkout"
    assert annotations["backstage.io/kubernetes-namespace"] == "prod"


def test_catalog_github_slug_from_parts_and_rejects_invalid() -> None:
    assert catalog_github_slug({"catalog_github_slug": "acme/checkout"}) == "acme/checkout"
    assert catalog_github_slug({"github_org": "acme", "github_repo": "app-checkout"}) == (
        "acme/app-checkout"
    )
    assert catalog_github_slug({"catalog_github_slug": "not-a-slug"}) == ""
    assert catalog_github_slug({"catalog_github_slug": "acme/has space"}) == ""


def test_catalog_links_parses_title_and_bare_urls() -> None:
    assert catalog_links("Docs|https://docs.example, https://status.example") == (
        {"url": "https://docs.example", "title": "Docs"},
        {"url": "https://status.example"},
    )
    assert catalog_links("not-a-url, ftp://skip") == ()


def test_build_catalog_document_relations_tags_links_and_github() -> None:
    bp = _bp("app-service")
    doc = build_catalog_document(
        bp,
        {
            "service_name": "checkout",
            "owner": "group:payments",
            "catalog_consumes_apis": "api:default/payments",
            "catalog_subcomponent_of": "component:default/commerce",
            "catalog_tags": "payments, checkout",
            "catalog_links": "Runbook|https://runbooks.example/checkout",
            "catalog_github_slug": "acme/app-checkout",
        },
    )
    assert doc["spec"]["consumesApis"] == ["api:default/payments"]
    assert doc["spec"]["subcomponentOf"] == "component:default/commerce"
    assert doc["metadata"]["tags"] == ["payments", "checkout"]
    assert doc["metadata"]["links"] == [
        {"url": "https://runbooks.example/checkout", "title": "Runbook"}
    ]
    annotations = doc["metadata"]["annotations"]
    assert annotations["github.com/project-slug"] == "acme/app-checkout"
    assert annotations["backstage.io/source-location"] == (
        "url:https://github.com/acme/app-checkout"
    )


def test_enrich_catalog_values_auto_slug_and_kubernetes_id() -> None:
    bp = _bp("app-service")
    bp = Blueprint(
        path=bp.path,
        name=bp.name,
        version=bp.version,
        description=bp.description,
        artifact_type="app-service",
        standard_source=bp.standard_source,
        standard_version=bp.standard_version,
        inputs=bp.inputs,
        template_engine=bp.template_engine,
        template_path=bp.template_path,
        gates=bp.gates,
        output_type=bp.output_type,
        output_repo_name_template="app-{service_name}",
        output_title_template=bp.output_title_template,
    )
    enriched = enrich_catalog_values(
        bp,
        {"service_name": "checkout", "owner": "group:payments"},
        github_org="acme",
    )
    assert enriched["github_org"] == "acme"
    assert enriched["github_repo"] == "app-checkout"
    assert enriched["catalog_kubernetes_id"] == "checkout"
    doc = build_catalog_document(bp, enriched)
    slug = doc["metadata"]["annotations"]["github.com/project-slug"]
    assert slug == "acme/app-checkout"
    assert doc["metadata"]["annotations"]["backstage.io/kubernetes-id"] == "checkout"


def test_build_catalog_document_catalog_domain() -> None:
    bp = _bp("app-service")
    doc = build_catalog_document(
        bp,
        {
            "service_name": "checkout",
            "owner": "group:payments",
            "catalog_domain": "commerce",
        },
    )
    assert doc["metadata"]["annotations"]["repave.dev/catalog-domain"] == "commerce"


def test_catalog_component_name_terraform() -> None:
    bp = _bp("terraform-module")
    assert catalog_component_name(bp, {"module_name": "networking"}) == "networking"


def test_write_backstage_catalog(tmp_path) -> None:
    bp = _bp("helm-chart")
    written = write_backstage_catalog_if_enabled(
        tmp_path,
        bp,
        {
            "include_backstage_catalog": "true",
            "chart_name": "api",
            "description": "API chart",
            "owner": "group:platform",
        },
    )
    assert written is True
    payload = yaml.safe_load((tmp_path / "catalog-info.yaml").read_text(encoding="utf-8"))
    assert payload["metadata"]["name"] == "api"
    assert payload["spec"]["type"] == "service"
    assert "backstage.io/techdocs-ref" not in payload["metadata"]["annotations"]


def test_catalog_techdocs_ref_when_docs_dir(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    assert catalog_techdocs_ref(tmp_path) == TECHDOCS_REF_DIR


def test_catalog_techdocs_ref_when_mkdocs_yml(tmp_path: Path) -> None:
    (tmp_path / "mkdocs.yml").write_text("site_name: demo\n", encoding="utf-8")
    assert catalog_techdocs_ref(tmp_path) == TECHDOCS_REF_DIR


def test_catalog_techdocs_ref_absent_without_docs(tmp_path: Path) -> None:
    assert catalog_techdocs_ref(tmp_path) is None


def test_write_backstage_catalog_emits_techdocs_ref(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    bp = _bp("helm-chart")
    written = write_backstage_catalog_if_enabled(
        tmp_path,
        bp,
        {
            "include_backstage_catalog": "true",
            "chart_name": "api",
            "owner": "group:platform",
        },
    )
    assert written is True
    payload = yaml.safe_load((tmp_path / "catalog-info.yaml").read_text(encoding="utf-8"))
    assert payload["metadata"]["annotations"]["backstage.io/techdocs-ref"] == TECHDOCS_REF_DIR
