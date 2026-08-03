"""Multi-component provenance helpers for repave add (v1.82)."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from repave_engine.blueprint import Blueprint
from repave_engine.ci_workflow import build_ci_provenance_block
from repave_engine.provenance import build_provenance_document

_TYPED_BLOCKS_BY_ARTIFACT: dict[str, str] = {
    "terraform-module": "terraformModule",
    "terraform-environment-stack": "terraformEnvironmentStack",
    "ansible-role": "ansibleRole",
    "ansible-playbook-project": "ansiblePlaybookProject",
    "ansible-collection": "ansibleCollection",
    "observability": "observability",
    "helm-chart": "helmChart",
    "app-service": "appService",
    "gitops-deployment": "gitopsDeployment",
    "opa-policy": "opaPolicy",
    "azure-policy": "azurePolicy",
    "checkov-policy": "checkovPolicy",
}


@dataclass(frozen=True)
class ProvenanceComponent:
    id: str
    artifact_type: str
    blueprint_name: str
    blueprint_version: str
    record: dict[str, Any]
    primary: bool = False


class ProvenanceComponentError(ValueError):
    """Invalid multi-component provenance document."""


def _spec(doc: dict[str, Any]) -> dict[str, Any]:
    spec = doc.get("spec")
    if not isinstance(spec, dict):
        raise ProvenanceComponentError(
            "provenance spec missing; expected GoldenPathArtifact with a top-level 'spec' object"
        )
    return spec


def _primary_record(spec: dict[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": "primary",
        "artifactType": spec.get("artifactType"),
        "blueprint": spec.get("blueprint"),
        "standard": spec.get("standard"),
        "generation": spec.get("generation"),
    }
    for block in _TYPED_BLOCKS_BY_ARTIFACT.values():
        if block in spec:
            record[block] = spec[block]
    if isinstance(spec.get("policy"), dict):
        record["policy"] = spec["policy"]
    return record


def list_provenance_components(doc: dict[str, Any]) -> tuple[ProvenanceComponent, ...]:
    spec = _spec(doc)
    blueprint = spec.get("blueprint")
    if not isinstance(blueprint, dict):
        raise ProvenanceComponentError("provenance spec.blueprint missing")
    name = str(blueprint.get("name", "")).strip()
    version = str(blueprint.get("version", "")).strip()
    artifact_type = str(spec.get("artifactType", "")).strip()
    if not name or not artifact_type:
        raise ProvenanceComponentError("primary component missing artifactType or blueprint.name")

    primary = ProvenanceComponent(
        id="primary",
        artifact_type=artifact_type,
        blueprint_name=name,
        blueprint_version=version,
        record=_primary_record(spec),
        primary=True,
    )
    extras: list[ProvenanceComponent] = []
    raw_components = spec.get("components")
    if isinstance(raw_components, list):
        for entry in raw_components:
            if not isinstance(entry, dict):
                continue
            comp_id = str(entry.get("id", "")).strip()
            bp = entry.get("blueprint")
            if not comp_id or not isinstance(bp, dict):
                continue
            bp_name = str(bp.get("name", "")).strip()
            bp_version = str(bp.get("version", "")).strip()
            art = str(entry.get("artifactType", "")).strip()
            if not bp_name or not art:
                continue
            extras.append(
                ProvenanceComponent(
                    id=comp_id,
                    artifact_type=art,
                    blueprint_name=bp_name,
                    blueprint_version=bp_version,
                    record=entry,
                    primary=False,
                )
            )
    return (primary, *extras)


def blueprint_names_from_provenance(doc: dict[str, Any]) -> frozenset[str]:
    return frozenset(component.blueprint_name for component in list_provenance_components(doc))


def default_component_id(blueprint: Blueprint) -> str:
    if blueprint.artifact_type == "helm-chart":
        return "helm"
    if blueprint.artifact_type == "observability":
        return "observability"
    if blueprint.artifact_type == "gitops-deployment":
        return "gitops"
    slug = blueprint.name.removesuffix("-generic").replace("-", "_")
    return slug or blueprint.artifact_type.replace("-", "_")


def build_component_record(
    blueprint: Blueprint,
    values: dict[str, Any],
    *,
    component_id: str,
) -> dict[str, Any]:
    generated = build_provenance_document(blueprint, values)
    spec = generated["spec"]
    record: dict[str, Any] = {
        "id": component_id,
        "artifactType": spec["artifactType"],
        "blueprint": spec["blueprint"],
        "standard": spec["standard"],
        "generation": spec["generation"],
        "addedAt": spec["generation"]["generated_at"],
    }
    block = _TYPED_BLOCKS_BY_ARTIFACT.get(blueprint.artifact_type)
    if block and block in spec:
        record[block] = spec[block]
    if isinstance(spec.get("policy"), dict):
        record["policy"] = spec["policy"]
    return record


def merge_ci_blocks(existing: dict[str, Any], added: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(existing)
    existing_gates = merged.get("gates")
    added_gates = added.get("gates")
    gate_names: list[str] = []
    if isinstance(existing_gates, list):
        gate_names.extend(str(item) for item in existing_gates)
    if isinstance(added_gates, list):
        for item in added_gates:
            name = str(item)
            if name not in gate_names:
                gate_names.append(name)
    merged["gates"] = gate_names

    existing_cfg = merged.get("gate_config")
    added_cfg = added.get("gate_config")
    if isinstance(existing_cfg, dict) and isinstance(added_cfg, dict):
        cfg = copy.deepcopy(existing_cfg)
        for key, value in added_cfg.items():
            if key not in cfg:
                cfg[key] = value
        merged["gate_config"] = cfg
    elif isinstance(added_cfg, dict) and "gate_config" not in merged:
        merged["gate_config"] = copy.deepcopy(added_cfg)

    return merged


def append_component_to_document(
    doc: dict[str, Any],
    component_record: dict[str, Any],
    *,
    blueprint: Blueprint,
) -> dict[str, Any]:
    updated = copy.deepcopy(doc)
    spec = _spec(updated)
    components = spec.get("components")
    components = [] if not isinstance(components, list) else copy.deepcopy(components)
    components.append(component_record)
    spec["components"] = components

    ci = spec.get("ci")
    new_ci = build_ci_provenance_block(blueprint)
    if isinstance(ci, dict):
        spec["ci"] = merge_ci_blocks(ci, new_ci)
    else:
        spec["ci"] = new_ci
    updated["spec"] = spec
    return updated


def component_doc_for_inputs(component: ProvenanceComponent) -> dict[str, Any]:
    """Shape a component record like a full provenance document for input extraction."""
    record = component.record
    spec: dict[str, Any] = {
        "artifactType": record.get("artifactType"),
        "blueprint": record.get("blueprint"),
        "standard": record.get("standard"),
    }
    for block in _TYPED_BLOCKS_BY_ARTIFACT.values():
        if block in record:
            spec[block] = record[block]
    if isinstance(record.get("policy"), dict):
        spec["policy"] = record["policy"]
    metadata_name = "artifact"
    artifact_type = str(spec.get("artifactType", "")).strip()
    block_key = _TYPED_BLOCKS_BY_ARTIFACT.get(artifact_type)
    if block_key and isinstance(record.get(block_key), dict):
        typed = record[block_key]
        for key in ("service_name", "module_name", "chart_name", "role_name", "policy_name"):
            if typed.get(key):
                metadata_name = str(typed[key])
                break
    return {"metadata": {"name": metadata_name}, "spec": spec}
