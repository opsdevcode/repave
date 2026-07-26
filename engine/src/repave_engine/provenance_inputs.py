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
        terraform_values: dict[str, Any] = {
            "module_name": module_name,
            "description": f"Repave upgrade plan for {module_name}",
            "cloud_provider": str(module.get("cloud_provider", "aws")).strip(),
            "provider_services": _join_provider_services(module.get("provider_services")),
        }
        if module.get("provider_service"):
            terraform_values["provider_service"] = str(module["provider_service"]).strip()
        if module.get("provider_resource"):
            terraform_values["provider_resource"] = str(module["provider_resource"]).strip()
        return terraform_values

    if artifact_type == "terraform-environment-stack":
        stack = spec.get("terraformEnvironmentStack")
        if not isinstance(stack, dict):
            raise ValueError(
                "terraform-environment-stack provenance missing spec.terraformEnvironmentStack"
            )
        stack_name = str(stack.get("stack_name", artifact_name)).strip()
        pinned = stack.get("pinned_modules")
        if not isinstance(pinned, list) or not pinned:
            raise ValueError("terraform-environment-stack provenance missing pinned_modules")
        primary = pinned[0]
        if not isinstance(primary, dict):
            raise ValueError("pinned_modules entry must be an object")
        stack_values: dict[str, Any] = {
            "stack_name": stack_name,
            "description": f"Repave upgrade plan for {stack_name}",
            "cloud_provider": str(stack.get("cloud_provider", "aws")).strip(),
            "environment": str(stack.get("environment", "dev")).strip(),
            "module_name": str(primary.get("name", "foundation")).strip(),
            "module_source": str(primary.get("source", "")).strip(),
            "module_version": str(primary.get("version", "")).strip(),
        }
        return stack_values

    if artifact_type == "ansible-playbook-project":
        project = spec.get("ansiblePlaybookProject")
        if not isinstance(project, dict):
            raise ValueError(
                "ansible-playbook-project provenance missing spec.ansiblePlaybookProject"
            )
        project_name = str(project.get("project_name", artifact_name)).strip()
        playbook_values: dict[str, Any] = {
            "project_name": project_name,
            "description": f"Repave upgrade plan for {project_name}",
            "environment": str(project.get("environment", "dev")).strip(),
        }
        if project.get("min_ansible_version"):
            playbook_values["min_ansible_version"] = str(project["min_ansible_version"]).strip()
        return playbook_values

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
