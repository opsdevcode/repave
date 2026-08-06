from __future__ import annotations

from repave_engine.blueprint import Blueprint, InputField
from repave_engine.provenance_components import (
    append_component_to_document,
    blueprint_names_from_provenance,
    build_component_record,
    default_component_id,
    list_provenance_components,
)
from repave_engine.provenance_inputs import inputs_from_provenance


def _sample_doc() -> dict:
    return {
        "apiVersion": "repave.dev/v1beta1",
        "kind": "GoldenPathArtifact",
        "metadata": {"name": "checkout-api"},
        "spec": {
            "artifactType": "app-service",
            "blueprint": {"name": "app-service-generic", "version": "0.4.1"},
            "standard": {"source": "standards/app-service", "version": "1.0.0"},
            "generation": {
                "engine_version": "2.0.0",
                "generated_at": "2026-08-03T12:00:00+00:00",
            },
            "governance": {"baseline_source": "standards", "baseline_version": "1.0.0"},
            "appService": {
                "service_name": "checkout-api",
                "owner": "team:payments",
                "port": "8080",
                "runtime": "python",
                "include_helm_reference": "false",
            },
            "ci": {
                "gates": ["docs-drift"],
                "workflow": ".github/workflows/repave-gates.yml",
                "toolchain": {
                    "terraform": "1.9.0",
                    "tflint": "0.50.0",
                    "checkov": "3.2.0",
                },
            },
        },
    }


def _helm_blueprint() -> Blueprint:
    return Blueprint(
        path=__file__,
        name="helm-chart-generic",
        version="0.3.1",
        description="Helm chart",
        artifact_type="helm-chart",
        standard_source="standards/helm-chart",
        standard_version="1.0.0",
        inputs=(InputField("chart_name", "string", True, "Chart name"),),
        template_engine="copier",
        template_path="template",
        gates=("helm-lint", "docs-drift"),
        output_type="pull_request",
        output_repo_name_template="chart-{chart_name}",
        output_title_template="Bootstrap {chart_name}",
    )


def test_list_provenance_components_primary_only() -> None:
    components = list_provenance_components(_sample_doc())
    assert len(components) == 1
    assert components[0].primary is True
    assert components[0].blueprint_name == "app-service-generic"


def test_append_component_records_blueprint_name() -> None:
    doc = _sample_doc()
    blueprint = _helm_blueprint()
    record = build_component_record(
        blueprint,
        {
            "chart_name": "checkout-api-chart",
            "app_name": "checkout-api",
            "owner": "platform-engineering",
            "description": "Chart",
            "image_repository": "ghcr.io/example/checkout-api",
            "image_tag": "latest",
            "service_type": "ClusterIP",
            "enable_ingress": "false",
        },
        component_id="helm",
    )
    updated = append_component_to_document(doc, record, blueprint=blueprint)
    names = blueprint_names_from_provenance(updated)
    assert names == frozenset({"app-service-generic", "helm-chart-generic"})
    assert default_component_id(blueprint) == "helm"
    assert len(list_provenance_components(updated)) == 2


def test_inputs_from_provenance_supports_app_service() -> None:
    values = inputs_from_provenance(_sample_doc())
    assert values["service_name"] == "checkout-api"
    assert values["runtime"] == "python"
