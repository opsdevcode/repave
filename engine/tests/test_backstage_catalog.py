from __future__ import annotations

from pathlib import Path

import yaml

from repave_engine.backstage_catalog import (
    TECHDOCS_REF_DIR,
    build_catalog_document,
    catalog_component_name,
    catalog_entity_refs,
    catalog_techdocs_ref,
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
