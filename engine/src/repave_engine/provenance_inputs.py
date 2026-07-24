from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml


def load_provenance_document(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected mapping at document root")
    return cast(dict[str, Any], data)


def blueprint_name_from_provenance(doc: dict[str, Any]) -> str:
    spec = doc.get("spec")
    if not isinstance(spec, dict):
        raise ValueError("provenance spec missing")
    blueprint = spec.get("blueprint")
    if not isinstance(blueprint, dict):
        raise ValueError("provenance spec.blueprint missing")
    name = str(blueprint.get("name", "")).strip()
    if not name:
        raise ValueError("provenance spec.blueprint.name is empty")
    return name


def _join_provider_services(raw: object) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, list):
        return ",".join(str(item).strip() for item in raw if str(item).strip())
    return ""


def inputs_from_provenance(doc: dict[str, Any]) -> dict[str, Any]:
    """Build blueprint render inputs from an on-disk GoldenPathArtifact document."""
    spec = doc.get("spec")
    if not isinstance(spec, dict):
        raise ValueError("provenance spec missing")

    metadata = doc.get("metadata")
    artifact_name = "artifact"
    if isinstance(metadata, dict) and metadata.get("name"):
        artifact_name = str(metadata["name"])

    artifact_type = str(spec.get("artifactType", "")).strip()
    if artifact_type == "terraform-module":
        module = spec.get("terraformModule")
        if not isinstance(module, dict):
            raise ValueError("terraform-module provenance missing spec.terraformModule")
        module_name = str(module.get("module_name", artifact_name)).strip()
        return {
            "module_name": module_name,
            "description": f"Repave upgrade plan for {module_name}",
            "cloud_provider": str(module.get("cloud_provider", "aws")).strip(),
            "provider_services": _join_provider_services(module.get("provider_services")),
        }

    if artifact_type == "ansible-role":
        role = spec.get("ansibleRole")
        if not isinstance(role, dict):
            raise ValueError("ansible-role provenance missing spec.ansibleRole")
        role_name = str(role.get("role_name", artifact_name)).strip()
        values: dict[str, Any] = {
            "role_name": role_name,
            "namespace": str(role.get("namespace", "")).strip(),
            "description": f"Repave upgrade plan for {role_name}",
        }
        if role.get("min_ansible_version"):
            values["min_ansible_version"] = str(role["min_ansible_version"]).strip()
        return values

    raise ValueError(f"unsupported artifactType {artifact_type!r}")
