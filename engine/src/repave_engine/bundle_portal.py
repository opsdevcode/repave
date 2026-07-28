"""Portal helpers for composite bundle forms and results."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repave_engine import __version__
from repave_engine.blueprint import load_blueprint, primary_publish_name
from repave_engine.bundle import (
    Bundle,
    build_bundle_context,
    map_member_inputs,
    validate_bundle_inputs,
)
from repave_engine.gates import all_gates_passed
from repave_engine.governance import GOVERNANCE_BASELINE_SOURCE, GOVERNANCE_BASELINE_VERSION
from repave_engine.pipeline import BundleGenerationResult, BundleMemberResult
from repave_engine.portal_result import LineageRow
from repave_engine.settings import OutputConfig
from repave_engine.target_repo import resolve_module_repository


@dataclass(frozen=True)
class BundleMemberPreview:
    member_id: str
    blueprint_name: str
    blueprint_version: str
    repo_name: str
    web_url: str
    cross_ref: str


def bundle_member_previews(
    bundle: Bundle,
    shared_values: dict[str, Any],
    *,
    repo_root: Path,
    output_config: OutputConfig,
) -> tuple[BundleMemberPreview, ...]:
    shared = validate_bundle_inputs(bundle, shared_values)
    context = build_bundle_context(shared, github_org=output_config.github_org)
    previews: list[BundleMemberPreview] = []
    for member in bundle.members:
        blueprint = load_blueprint(repo_root / "blueprints" / member.blueprint_name, repo_root)
        mapped = map_member_inputs(member, context)
        module_name = primary_publish_name(blueprint, mapped)
        repository = resolve_module_repository(
            module_name=module_name,
            config=output_config,
            name_template=blueprint.output_repo_name_template,
            template_values=mapped,
        )
        cross_ref = _cross_ref_hint(member.member_id, context)
        previews.append(
            BundleMemberPreview(
                member_id=member.member_id,
                blueprint_name=blueprint.name,
                blueprint_version=blueprint.version,
                repo_name=repository.name,
                web_url=repository.web_url,
                cross_ref=cross_ref,
            )
        )
    return tuple(previews)


def _cross_ref_hint(member_id: str, context: dict[str, str]) -> str:
    if member_id == "app":
        return f"Links to Helm chart at {context.get('helm_chart_repo', '')}"
    if member_id == "helm":
        return f"Image {context.get('image_repository', '')}:1.0.0"
    if member_id == "dashboards":
        return f"Dashboards for service {context.get('service_name', '')}"
    return ""


def build_bundle_provenance_document(
    bundle: Bundle,
    shared: dict[str, str],
    member_results: tuple[BundleMemberResult, ...],
) -> dict[str, Any]:
    members: list[dict[str, Any]] = []
    for item in member_results:
        repo = item.result.module_repository
        members.append(
            {
                "id": item.member_id,
                "blueprint": item.result.blueprint.name,
                "blueprint_version": item.result.blueprint.version,
                "repository": repo.name if repo is not None else "",
                "repository_url": repo.web_url if repo is not None else "",
                "gates_passed": all_gates_passed(item.result.gates),
            }
        )
    return {
        "apiVersion": "repave.dev/v1alpha1",
        "kind": "BundleGeneration",
        "spec": {
            "bundle": bundle.name,
            "bundle_version": bundle.version,
            "engine_version": __version__,
            "shared_inputs": dict(shared),
            "members": members,
            "governance_baseline": {
                "source": GOVERNANCE_BASELINE_SOURCE,
                "version": GOVERNANCE_BASELINE_VERSION,
            },
        },
    }


def build_bundle_result_portal_context(
    bundle_result: BundleGenerationResult,
    *,
    shared_inputs: dict[str, str],
) -> dict[str, Any]:
    bundle = bundle_result.bundle
    lineage: list[LineageRow] = [
        LineageRow("Bundle", f"{bundle.name}@{bundle.version}"),
        LineageRow(
            "Governance baseline",
            f"{GOVERNANCE_BASELINE_SOURCE}@{GOVERNANCE_BASELINE_VERSION}",
        ),
        LineageRow("Engine", __version__),
        LineageRow("Members", str(len(bundle_result.members))),
    ]
    member_rows = []
    for item in bundle_result.members:
        repo = item.result.module_repository
        member_rows.append(
            {
                "member_id": item.member_id,
                "blueprint": f"{item.result.blueprint.name}@{item.result.blueprint.version}",
                "repo_name": repo.name if repo is not None else "",
                "web_url": repo.web_url if repo is not None else "",
                "gates_ok": all_gates_passed(item.result.gates),
            }
        )
    provenance = build_bundle_provenance_document(bundle, shared_inputs, bundle_result.members)
    return {
        "lineage": lineage,
        "member_rows": member_rows,
        "bundle_provenance": provenance,
        "shared_inputs": shared_inputs,
    }
