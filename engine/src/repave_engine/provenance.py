from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import jsonschema
import yaml

from repave_engine import __version__
from repave_engine.blueprint import Blueprint


def load_artifact_schema(repo_root: Path) -> dict[str, Any]:
    schema_path = repo_root / "schemas" / "golden-path-artifact.schema.json"
    return cast(dict[str, Any], json.loads(schema_path.read_text(encoding="utf-8")))


def _parse_provider_services(values: dict[str, Any]) -> list[str]:
    provider_services = values.get("provider_services", "")
    if isinstance(provider_services, str):
        return [item.strip() for item in provider_services.split(",") if item.strip()]
    if isinstance(provider_services, list):
        return [str(item) for item in provider_services]
    return []


def _build_terraform_spec(
    blueprint: Blueprint,
    values: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    module_name = str(values.get("module_name", blueprint.name))
    spec: dict[str, Any] = {
        "artifactType": "terraform-module",
        "terraformModule": {
            "module_name": module_name,
            "cloud_provider": str(values.get("cloud_provider", "")),
            "provider_services": _parse_provider_services(values),
        },
    }
    if blueprint.terraform_layout == "single-resource":
        spec["terraformModule"]["provider_service"] = str(
            values.get("provider_service", "")
        ).strip()
        spec["terraformModule"]["provider_resource"] = str(
            values.get("provider_resource", "")
        ).strip()
    if blueprint.checkov_policies is not None:
        spec["checkov"] = {
            "policies_source": blueprint.checkov_policies.policies_source,
            "policy_version": blueprint.checkov_policies.policy_version,
        }
    return spec, module_name


def _build_environment_stack_spec(
    blueprint: Blueprint,
    values: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    stack_name = str(values.get("stack_name", blueprint.name))
    pinned_raw = values.get("pinned_modules")
    pinned_list: list[dict[str, Any]] = []
    if isinstance(pinned_raw, list):
        for item in pinned_raw:
            if not isinstance(item, dict):
                continue
            entry: dict[str, Any] = {
                "name": str(item.get("name", "")).strip(),
                "source": str(item.get("source", "")).strip(),
            }
            version = str(item.get("version", "")).strip()
            if version:
                entry["version"] = version
            repo_name = str(item.get("repo_name", "")).strip()
            if repo_name:
                entry["repo_name"] = repo_name
            if entry["name"] and entry["source"]:
                pinned_list.append(entry)
    spec: dict[str, Any] = {
        "artifactType": "terraform-environment-stack",
        "terraformEnvironmentStack": {
            "stack_name": stack_name,
            "cloud_provider": str(values.get("cloud_provider", "")),
            "environment": str(values.get("environment", "dev")),
            "pinned_modules": pinned_list,
        },
    }
    if blueprint.checkov_policies is not None:
        spec["checkov"] = {
            "policies_source": blueprint.checkov_policies.policies_source,
            "policy_version": blueprint.checkov_policies.policy_version,
        }
    return spec, stack_name


def _build_ansible_playbook_project_spec(
    blueprint: Blueprint,
    values: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    project_name = str(values.get("project_name", blueprint.name))
    spec: dict[str, Any] = {
        "artifactType": "ansible-playbook-project",
        "ansiblePlaybookProject": {
            "project_name": project_name,
            "environment": str(values.get("environment", "dev")),
        },
    }
    min_version = values.get("min_ansible_version")
    if min_version not in (None, ""):
        spec["ansiblePlaybookProject"]["min_ansible_version"] = str(min_version)
    pinned = values.get("pinned_roles")
    if isinstance(pinned, list) and pinned:
        spec["ansiblePlaybookProject"]["pinned_roles"] = [
            {
                "galaxy_name": str(item.get("galaxy_name", "")),
                "version": str(item.get("version", "")),
                "src": str(item.get("src", "")),
                **({"repo_name": str(item["repo_name"]).strip()} if item.get("repo_name") else {}),
            }
            for item in pinned
            if isinstance(item, dict)
        ]
    if blueprint.ansible_lint_pack is not None:
        spec["ansibleLint"] = {
            "pack_source": blueprint.ansible_lint_pack.pack_source,
            "pack_version": blueprint.ansible_lint_pack.pack_version,
        }
    return spec, project_name


def _build_ansible_spec(blueprint: Blueprint, values: dict[str, Any]) -> tuple[dict[str, Any], str]:
    role_name = str(values.get("role_name", blueprint.name))
    namespace = str(values.get("namespace", ""))
    spec: dict[str, Any] = {
        "artifactType": "ansible-role",
        "ansibleRole": {
            "role_name": role_name,
            "namespace": namespace,
        },
    }
    min_version = values.get("min_ansible_version")
    if min_version not in (None, ""):
        spec["ansibleRole"]["min_ansible_version"] = str(min_version)
    platforms = values.get("target_platforms")
    if isinstance(platforms, str) and platforms.strip():
        spec["ansibleRole"]["target_platforms"] = platforms.strip()
    elif isinstance(platforms, list) and platforms:
        spec["ansibleRole"]["target_platforms"] = ",".join(
            sorted(str(item).strip() for item in platforms if str(item).strip())
        )
    if blueprint.ansible_lint_pack is not None:
        spec["ansibleLint"] = {
            "pack_source": blueprint.ansible_lint_pack.pack_source,
            "pack_version": blueprint.ansible_lint_pack.pack_version,
        }
    metadata_name = f"{namespace}.{role_name}" if namespace else role_name
    return spec, metadata_name


def _build_ansible_collection_spec(
    blueprint: Blueprint,
    values: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    namespace = str(values.get("namespace", ""))
    collection_name = str(values.get("collection_name", blueprint.name))
    spec: dict[str, Any] = {
        "artifactType": "ansible-collection",
        "ansibleCollection": {
            "namespace": namespace,
            "collection_name": collection_name,
        },
    }
    min_version = values.get("min_ansible_version")
    if min_version not in (None, ""):
        spec["ansibleCollection"]["min_ansible_version"] = str(min_version)
    if blueprint.ansible_lint_pack is not None:
        spec["ansibleLint"] = {
            "pack_source": blueprint.ansible_lint_pack.pack_source,
            "pack_version": blueprint.ansible_lint_pack.pack_version,
        }
    metadata_name = f"{namespace}.{collection_name}" if namespace else collection_name
    return spec, metadata_name


def build_provenance_document(blueprint: Blueprint, values: dict[str, Any]) -> dict[str, Any]:
    if blueprint.artifact_type == "ansible-role":
        artifact_spec, metadata_name = _build_ansible_spec(blueprint, values)
    elif blueprint.artifact_type == "ansible-playbook-project":
        artifact_spec, metadata_name = _build_ansible_playbook_project_spec(blueprint, values)
    elif blueprint.artifact_type == "ansible-collection":
        artifact_spec, metadata_name = _build_ansible_collection_spec(blueprint, values)
    elif blueprint.artifact_type == "terraform-environment-stack":
        artifact_spec, metadata_name = _build_environment_stack_spec(blueprint, values)
    else:
        artifact_spec, metadata_name = _build_terraform_spec(blueprint, values)

    return {
        "apiVersion": "repave.dev/v1beta1",
        "kind": "GoldenPathArtifact",
        "metadata": {"name": metadata_name},
        "spec": {
            **artifact_spec,
            "blueprint": {
                "name": blueprint.name,
                "version": blueprint.version,
            },
            "standard": {
                "source": blueprint.standard_source,
                "version": blueprint.standard_version,
            },
            "generation": {
                "engine_version": __version__,
                "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            },
        },
    }


def write_provenance_file(
    output_dir: Path,
    blueprint: Blueprint,
    values: dict[str, Any],
    *,
    filename: str,
) -> Path:
    path = output_dir / filename
    document = build_provenance_document(blueprint, values)
    body = yaml.safe_dump(document, sort_keys=False, default_flow_style=False)
    path.write_text(f"---\n{body}", encoding="utf-8")
    return path


def validate_provenance_file(path: Path, repo_root: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Provenance file missing: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    schema = load_artifact_schema(repo_root)
    jsonschema.validate(instance=data, schema=schema)
