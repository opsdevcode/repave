"""Humanitec-style workload profiles and deployment sets for GitOps sandboxes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from repave_engine.yaml_util import load_yaml_mapping_soft


@dataclass(frozen=True)
class WorkloadProfile:
    id: str
    label: str
    blueprint: str
    description: str = ""
    policy_profile: str = ""
    default_inputs: dict[str, Any] = field(default_factory=dict)
    bundle: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "blueprint": self.blueprint,
            "description": self.description,
            "policy_profile": self.policy_profile,
            "default_inputs": dict(self.default_inputs),
            "bundle": self.bundle,
        }


@dataclass(frozen=True)
class DeploymentSet:
    id: str
    label: str
    workload_profile: str
    description: str = ""
    env_class: str = "sandbox"
    ttl_hours: int = 168
    pinned_modules: str = ""
    cloud_provider: str = "aws"
    environment: str = "dev"
    extra_inputs: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "workload_profile": self.workload_profile,
            "description": self.description,
            "class": self.env_class,
            "ttl_hours": self.ttl_hours,
            "pinned_modules": self.pinned_modules,
            "cloud_provider": self.cloud_provider,
            "environment": self.environment,
            "extra_inputs": dict(self.extra_inputs),
        }


def load_workload_profiles(path: Path | None) -> tuple[WorkloadProfile, ...]:
    if path is None or not path.is_file():
        return ()
    doc = load_yaml_mapping_soft(path)
    if doc is None:
        return ()
    raw_list = doc.get("profiles")
    if not isinstance(raw_list, list):
        return ()
    profiles: list[WorkloadProfile] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        profile_id = str(item.get("id", "")).strip()
        blueprint = str(item.get("blueprint", "")).strip()
        if not profile_id or not blueprint:
            continue
        inputs_raw = item.get("default_inputs", {})
        inputs = dict(inputs_raw) if isinstance(inputs_raw, dict) else {}
        profiles.append(
            WorkloadProfile(
                id=profile_id,
                label=str(item.get("label", profile_id)).strip() or profile_id,
                blueprint=blueprint,
                description=str(item.get("description", "")).strip(),
                policy_profile=str(item.get("policy_profile", "")).strip(),
                default_inputs=inputs,
                bundle=str(item.get("bundle", "")).strip(),
            )
        )
    return tuple(profiles)


def load_deployment_sets(path: Path | None) -> tuple[DeploymentSet, ...]:
    if path is None or not path.is_file():
        return ()
    doc = load_yaml_mapping_soft(path)
    if doc is None:
        return ()
    raw_list = doc.get("sets")
    if not isinstance(raw_list, list):
        return ()
    sets: list[DeploymentSet] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        set_id = str(item.get("id", "")).strip()
        profile = str(item.get("workload_profile", "")).strip()
        if not set_id or not profile:
            continue
        ttl_raw = item.get("ttl_hours", 168)
        try:
            ttl_hours = max(1, int(ttl_raw))
        except (TypeError, ValueError):
            ttl_hours = 168
        extras_raw = item.get("extra_inputs", {})
        extras = dict(extras_raw) if isinstance(extras_raw, dict) else {}
        sets.append(
            DeploymentSet(
                id=set_id,
                label=str(item.get("label", set_id)).strip() or set_id,
                workload_profile=profile,
                description=str(item.get("description", "")).strip(),
                env_class=str(item.get("class", "sandbox")).strip() or "sandbox",
                ttl_hours=ttl_hours,
                pinned_modules=str(item.get("pinned_modules", "")).strip(),
                cloud_provider=str(item.get("cloud_provider", "aws")).strip() or "aws",
                environment=str(item.get("environment", "dev")).strip() or "dev",
                extra_inputs=extras,
            )
        )
    return tuple(sets)


def find_workload_profile(
    profiles: tuple[WorkloadProfile, ...],
    profile_id: str,
) -> WorkloadProfile | None:
    needle = profile_id.strip()
    for item in profiles:
        if item.id == needle:
            return item
    return None


def find_deployment_set(
    sets: tuple[DeploymentSet, ...],
    set_id: str,
) -> DeploymentSet | None:
    needle = set_id.strip()
    for item in sets:
        if item.id == needle:
            return item
    return None


def build_vend_payload_from_deployment_set(
    deployment_set: DeploymentSet,
    profile: WorkloadProfile,
    *,
    stack_name: str,
    owner: str,
    gitops_repo: str = "",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Build an environment_vend request body from a named deployment set."""
    inputs: dict[str, Any] = dict(profile.default_inputs)
    inputs.update(deployment_set.extra_inputs)
    inputs["stack_name"] = stack_name.strip()
    if deployment_set.pinned_modules and "pinned_modules" not in inputs:
        inputs["pinned_modules"] = deployment_set.pinned_modules
    if deployment_set.cloud_provider:
        inputs.setdefault("cloud_provider", deployment_set.cloud_provider)
    if deployment_set.environment:
        inputs.setdefault("environment", deployment_set.environment)
    if owner.strip():
        inputs.setdefault("owner", owner.strip())
    if profile.policy_profile:
        inputs.setdefault("policy_profile", profile.policy_profile)
    inputs["workload_profile"] = profile.id
    inputs["deployment_set"] = deployment_set.id
    payload: dict[str, Any] = {
        "kind": "environment_vend",
        "blueprint": profile.blueprint,
        "class": deployment_set.env_class,
        "owner": owner.strip(),
        "dry_run": dry_run,
        "inputs": inputs,
    }
    if gitops_repo.strip():
        payload["gitops_repo"] = gitops_repo.strip()
    return payload
