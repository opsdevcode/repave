"""Backstage Software Catalog metadata for generated golden-path repositories."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from repave_engine import __version__
from repave_engine.blueprint import Blueprint

CATALOG_FILENAME = "catalog-info.yaml"
TECHDOCS_REF_DIR = "dir:."
ALWAYS_EMIT_ARTIFACT_TYPES = frozenset({"app-service"})


def should_emit_catalog(blueprint: Blueprint, values: dict[str, Any]) -> bool:
    if blueprint.artifact_type in ALWAYS_EMIT_ARTIFACT_TYPES:
        return True
    return str(values.get("include_backstage_catalog", "false")).lower() == "true"


def catalog_component_name(blueprint: Blueprint, values: dict[str, Any]) -> str:
    artifact = blueprint.artifact_type
    if artifact == "app-service":
        return str(values.get("service_name", blueprint.name)).strip()
    if artifact == "helm-chart":
        return str(values.get("chart_name", values.get("app_name", blueprint.name))).strip()
    if artifact.startswith("terraform-"):
        return str(values.get("module_name", blueprint.name)).strip()
    for key in ("module_name", "service_name", "chart_name", "app_name"):
        if values.get(key):
            return str(values[key]).strip()
    return blueprint.name


def catalog_component_type(artifact_type: str) -> str:
    if artifact_type == "app-service":
        return "service"
    if artifact_type == "helm-chart":
        return "service"
    if artifact_type.startswith("terraform-"):
        return "library"
    return "service"


def catalog_techdocs_ref(output_dir: Path) -> str | None:
    """Return dir:. when the generated repo has MkDocs source."""
    if (output_dir / "mkdocs.yml").is_file() or (output_dir / "docs").is_dir():
        return TECHDOCS_REF_DIR
    return None


def catalog_entity_refs(raw: Any) -> tuple[str, ...]:
    """Split comma or newline entity refs (component:default/foo)."""
    if raw is None:
        return ()
    text = str(raw).strip()
    if not text:
        return ()
    parts = (part.strip() for part in text.replace("\n", ",").split(","))
    return tuple(part for part in parts if part)


def catalog_optional_text(raw: Any) -> str:
    if raw is None:
        return ""
    return str(raw).strip()


def catalog_github_slug(values: dict[str, Any]) -> str:
    """Return org/repo for github.com/project-slug, or empty when unset/invalid."""
    raw = catalog_optional_text(values.get("catalog_github_slug") or values.get("github_slug"))
    if not raw:
        org = catalog_optional_text(values.get("catalog_github_org") or values.get("github_org"))
        repo = catalog_optional_text(values.get("catalog_github_repo") or values.get("github_repo"))
        raw = f"{org}/{repo}" if org and repo else ""
    if raw.count("/") != 1 or " " in raw:
        return ""
    org, repo = raw.split("/", 1)
    if not org or not repo:
        return ""
    return raw


def catalog_links(raw: Any) -> tuple[dict[str, str], ...]:
    """Parse Title|https://url or bare https://url entries."""
    links: list[dict[str, str]] = []
    for part in catalog_entity_refs(raw):
        title = ""
        url = part
        if "|" in part:
            title, url = (piece.strip() for piece in part.split("|", 1))
        if not url.startswith(("http://", "https://")):
            continue
        item = {"url": url}
        if title:
            item["title"] = title
        links.append(item)
    return tuple(links)


def catalog_description(blueprint: Blueprint, values: dict[str, Any]) -> str:
    raw = values.get("description") or values.get("catalog_description")
    if raw:
        return str(raw).strip()
    return blueprint.description or f"Golden path {blueprint.name}"


def build_catalog_document(blueprint: Blueprint, values: dict[str, Any]) -> dict[str, Any]:
    name = catalog_component_name(blueprint, values)
    owner = str(values.get("owner", "group:default/unknown")).strip()
    lifecycle = str(values.get("catalog_lifecycle", "experimental")).strip()
    system = str(values.get("system", "")).strip()

    blueprint_name = str(values.get("_repave_blueprint_name", blueprint.name))
    blueprint_version = str(values.get("_repave_blueprint_version", blueprint.version))
    standard_source = str(values.get("_repave_standard_source", blueprint.standard_source))
    standard_version = str(values.get("_repave_standard_version", blueprint.standard_version))
    engine_version = str(values.get("_repave_engine_version", __version__))

    annotations: dict[str, str] = {
        "repave.dev/blueprint": blueprint_name,
        "repave.dev/blueprint-version": blueprint_version,
        "repave.dev/standard-source": standard_source,
        "repave.dev/standard-version": standard_version,
        "repave.dev/engine-version": engine_version,
        "repave.dev/artifact-type": blueprint.artifact_type,
    }

    spec: dict[str, Any] = {
        "type": catalog_component_type(blueprint.artifact_type),
        "lifecycle": lifecycle,
        "owner": owner,
    }
    if system:
        spec["system"] = system
    depends_on = catalog_entity_refs(values.get("catalog_depends_on") or values.get("depends_on"))
    if depends_on:
        spec["dependsOn"] = list(depends_on)
    provides_apis = catalog_entity_refs(
        values.get("catalog_provides_apis") or values.get("provides_apis")
    )
    if provides_apis:
        spec["providesApis"] = list(provides_apis)
    consumes_apis = catalog_entity_refs(
        values.get("catalog_consumes_apis") or values.get("consumes_apis")
    )
    if consumes_apis:
        spec["consumesApis"] = list(consumes_apis)
    subcomponent_of = catalog_optional_text(
        values.get("catalog_subcomponent_of") or values.get("subcomponent_of")
    )
    if subcomponent_of:
        spec["subcomponentOf"] = subcomponent_of

    tags = catalog_entity_refs(values.get("catalog_tags") or values.get("tags"))
    links = catalog_links(values.get("catalog_links") or values.get("links"))
    github_slug = catalog_github_slug(values)
    if github_slug:
        annotations["github.com/project-slug"] = github_slug
        annotations["backstage.io/source-location"] = f"url:https://github.com/{github_slug}"

    kubernetes_id = catalog_optional_text(
        values.get("catalog_kubernetes_id") or values.get("kubernetes_id")
    )
    if kubernetes_id:
        annotations["backstage.io/kubernetes-id"] = kubernetes_id
    kubernetes_namespace = catalog_optional_text(
        values.get("catalog_kubernetes_namespace") or values.get("kubernetes_namespace")
    )
    if kubernetes_namespace:
        annotations["backstage.io/kubernetes-namespace"] = kubernetes_namespace

    metadata: dict[str, Any] = {
        "name": name,
        "description": catalog_description(blueprint, values),
        "annotations": annotations,
    }
    if tags:
        metadata["tags"] = list(tags)
    if links:
        metadata["links"] = [dict(item) for item in links]

    return {
        "apiVersion": "backstage.io/v1alpha1",
        "kind": "Component",
        "metadata": metadata,
        "spec": spec,
    }


def write_backstage_catalog_if_enabled(
    output_dir: Path,
    blueprint: Blueprint,
    values: dict[str, Any],
) -> bool:
    if not should_emit_catalog(blueprint, values):
        return False
    document = build_catalog_document(blueprint, values)
    techdocs_ref = catalog_techdocs_ref(output_dir)
    if techdocs_ref:
        annotations = document["metadata"]["annotations"]
        annotations["backstage.io/techdocs-ref"] = techdocs_ref
    path = output_dir / CATALOG_FILENAME
    path.write_text(
        yaml.safe_dump(document, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return True
