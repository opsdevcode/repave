"""Portal view models for generation results (lineage, policy, Backstage)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from repave_engine import __version__
from repave_engine.cost_estimate import CostEstimate, cost_estimate_for_result
from repave_engine.governance import GOVERNANCE_BASELINE_SOURCE, GOVERNANCE_BASELINE_VERSION
from repave_engine.pipeline import GenerationResult
from repave_engine.policy_catalog import load_policy_catalog, rules_for_artifact
from repave_engine.policy_selection import PolicySelection, blueprint_supports_policy_customization
from repave_engine.provenance import build_provenance_document


@dataclass(frozen=True)
class LineageRow:
    label: str
    value: str


@dataclass(frozen=True)
class PolicyRuleRow:
    rule_id: str
    title: str
    family: str
    enforced_by: str


@dataclass(frozen=True)
class BackstagePreview:
    path: str
    owner: str
    name: str
    repave_annotations: tuple[tuple[str, str], ...]
    tags: tuple[str, ...] = ()
    links: tuple[tuple[str, str], ...] = ()
    consumes_apis: tuple[str, ...] = ()
    subcomponent_of: str = ""
    github_slug: str = ""
    github_source_url: str = ""
    kubernetes_id: str = ""
    kubernetes_namespace: str = ""
    catalog_domain: str = ""


def _file_content(rendered_files: tuple[Any, ...], name: str) -> str | None:
    for item in rendered_files:
        path = str(getattr(item, "path", ""))
        if path == name or path.endswith(f"/{name}"):
            return str(getattr(item, "content", ""))
    return None


def _backstage_preview(content: str, path: str) -> BackstagePreview | None:
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        return None
    spec = data.get("spec")
    owner = ""
    if isinstance(spec, dict):
        owner = str(spec.get("owner", "")).strip()
    annotations = metadata.get("annotations")
    repave: list[tuple[str, str]] = []
    github_slug = ""
    github_source_url = ""
    kubernetes_id = ""
    kubernetes_namespace = ""
    catalog_domain = ""
    if isinstance(annotations, dict):
        for key, val in sorted(annotations.items()):
            key_str = str(key)
            if key_str == "repave.dev/catalog-domain":
                catalog_domain = str(val).strip()
            elif key_str.startswith("repave.dev/"):
                repave.append((key_str, str(val)))
            elif key_str == "github.com/project-slug":
                github_slug = str(val).strip()
            elif key_str == "backstage.io/source-location":
                loc = str(val).strip()
                if loc.startswith("url:"):
                    github_source_url = loc[4:].strip()
            elif key_str == "backstage.io/kubernetes-id":
                kubernetes_id = str(val).strip()
            elif key_str == "backstage.io/kubernetes-namespace":
                kubernetes_namespace = str(val).strip()
    if github_slug and not github_source_url:
        github_source_url = f"https://github.com/{github_slug}"

    tags: tuple[str, ...] = ()
    raw_tags = metadata.get("tags")
    if isinstance(raw_tags, list):
        tags = tuple(str(item).strip() for item in raw_tags if str(item).strip())

    links: tuple[tuple[str, str], ...] = ()
    raw_links = metadata.get("links")
    if isinstance(raw_links, list):
        parsed_links: list[tuple[str, str]] = []
        for item in raw_links:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", "")).strip()
            if not url:
                continue
            title = str(item.get("title", "")).strip()
            parsed_links.append((title, url))
        links = tuple(parsed_links)

    consumes_apis: tuple[str, ...] = ()
    subcomponent_of = ""
    if isinstance(spec, dict):
        raw_consumes = spec.get("consumesApis")
        if isinstance(raw_consumes, list):
            consumes_apis = tuple(str(item).strip() for item in raw_consumes if str(item).strip())
        subcomponent_of = str(spec.get("subcomponentOf", "")).strip()

    return BackstagePreview(
        path=path,
        owner=owner,
        name=str(metadata.get("name", "")).strip(),
        repave_annotations=tuple(repave),
        tags=tags,
        links=links,
        consumes_apis=consumes_apis,
        subcomponent_of=subcomponent_of,
        github_slug=github_slug,
        github_source_url=github_source_url,
        kubernetes_id=kubernetes_id,
        kubernetes_namespace=kubernetes_namespace,
        catalog_domain=catalog_domain,
    )


def build_result_portal_context(result: GenerationResult, repo_root: Path) -> dict[str, Any]:
    blueprint = result.blueprint
    values = result.render.values

    lineage: list[LineageRow] = [
        LineageRow("Blueprint", f"{blueprint.name}@{blueprint.version}"),
        LineageRow("Standard", f"{blueprint.standard_source}@{blueprint.standard_version}"),
        LineageRow(
            "Governance baseline",
            f"{GOVERNANCE_BASELINE_SOURCE}@{GOVERNANCE_BASELINE_VERSION}",
        ),
        LineageRow("Engine", __version__),
    ]

    policy_profile: str | None = None
    policy_profile_label: str | None = None
    policy_pack_source: str | None = None
    policy_rules: list[PolicyRuleRow] = []
    policy_gate_names: tuple[str, ...] = ()

    selection = values.get("_policy_selection")
    if isinstance(selection, PolicySelection):
        policy_profile = selection.profile
        policy_pack_source = selection.pack_source
        catalog = load_policy_catalog(repo_root)
        profile_meta = catalog.profiles.get(selection.profile, {})
        policy_profile_label = str(profile_meta.get("label", selection.profile))
        rule_by_id = {
            rule.id: rule for rule in rules_for_artifact(catalog, blueprint.artifact_type)
        }
        for rule_id in selection.enabled_rules:
            rule = rule_by_id.get(rule_id)
            if rule is None:
                continue
            enforced = rule.family
            if rule.checkov_id:
                enforced = "checkov"
            elif rule.rego_file:
                enforced = "opa"
            elif rule.definition_file:
                enforced = "azure-policy"
            policy_rules.append(
                PolicyRuleRow(
                    rule_id=rule.id,
                    title=rule.title,
                    family=rule.family,
                    enforced_by=enforced,
                )
            )
        policy_gate_names = tuple(
            gate.name
            for gate in result.gates
            if gate.name in {"checkov", "opa", "azure-policy"} and not gate.skipped
        )
    elif blueprint_supports_policy_customization(blueprint):
        policy_profile = str(values.get("policy_profile", "estate-default"))
        policy_pack_source = str(values.get("policy_pack_source", "repave-default"))

    provenance_filename = blueprint.provenance_file or "repave.yaml"

    repave_yaml = _file_content(result.rendered_files, provenance_filename)
    if repave_yaml is None and result.dry_run:
        try:
            doc = build_provenance_document(blueprint, values)
            repave_yaml = yaml.dump(doc, sort_keys=False, default_flow_style=False)
        except (TypeError, ValueError):
            repave_yaml = None

    backstage: BackstagePreview | None = None
    catalog_content = _file_content(result.rendered_files, "catalog-info.yaml")
    if catalog_content:
        backstage = _backstage_preview(catalog_content, "catalog-info.yaml")

    include_backstage_requested = str(values.get("include_backstage_catalog", "")).lower() in {
        "true",
        "1",
        "yes",
    }
    backstage_expected = blueprint.artifact_type == "app-service" or include_backstage_requested

    cost_estimate: CostEstimate | None = None
    if blueprint.artifact_type in {"terraform-module", "terraform-environment-stack"}:
        cost_estimate = cost_estimate_for_result(result)

    return {
        "lineage": lineage,
        "policy_profile": policy_profile,
        "policy_profile_label": policy_profile_label,
        "policy_pack_source": policy_pack_source,
        "policy_rules": policy_rules,
        "policy_gate_names": policy_gate_names,
        "repave_yaml_excerpt": repave_yaml,
        "provenance_filename": provenance_filename,
        "backstage": backstage,
        "backstage_expected": backstage_expected,
        "cost_estimate": cost_estimate,
    }
