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
    if blueprint.checkov_policies is not None:
        spec["checkov"] = {
            "policies_source": blueprint.checkov_policies.policies_source,
            "policy_version": blueprint.checkov_policies.policy_version,
        }
    return spec, module_name


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
    metadata_name = f"{namespace}.{role_name}" if namespace else role_name
    return spec, metadata_name


def build_provenance_document(blueprint: Blueprint, values: dict[str, Any]) -> dict[str, Any]:
    if blueprint.artifact_type == "ansible-role":
        artifact_spec, metadata_name = _build_ansible_spec(blueprint, values)
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
    path.write_text(
        yaml.safe_dump(document, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return path


def validate_provenance_file(path: Path, repo_root: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Provenance file missing: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    schema = load_artifact_schema(repo_root)
    jsonschema.validate(instance=data, schema=schema)
