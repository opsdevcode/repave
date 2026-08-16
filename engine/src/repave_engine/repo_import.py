"""Import an existing repository into a golden path layout and open a pull request.

Import differs from upgrade: upgrade re-renders a repo that already carries
``repave.yaml`` provenance, while import adopts an ungoverned repo by moving its files to
where the chosen blueprint would have put them. Moved content is never rewritten, so the
layout commit is mechanically verifiable as byte-identical.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from repave_engine.audit import AuditRecord, acting_user_from_env, append_audit_record
from repave_engine.audit_history import AuditHistoryEntry
from repave_engine.blueprint import (
    Blueprint,
    artifact_family,
    blueprint_dir,
    blueprints_dir,
    group_blueprints_by_artifact,
    list_catalog_blueprints,
    load_blueprint,
    validate_inputs,
)
from repave_engine.cost_estimate import (
    CostEstimateDelta,
    audit_extra_for_cost_estimate,
    cost_estimate_from_gates,
    diff_cost_estimates,
    load_cost_estimate_file,
)
from repave_engine.entity_catalog import ScorecardDimension, build_scorecard
from repave_engine.fleet import FleetEntry, FleetError, normalize_repo_url, register_repo
from repave_engine.gate_registry import GateResult
from repave_engine.gates import all_gates_passed, is_gate_artifact_path, run_gates
from repave_engine.git_clone import (
    CloneError,
    ephemeral_clone,
    is_shallow_update_rejection,
    redact_secrets,
    resolve_git_token,
    unshallow,
)
from repave_engine.github import (
    add_pull_request_labels,
    can_push_to_repository,
    create_github_pull_request,
    default_branch,
    find_open_pull_request,
    push_git_branch,
)
from repave_engine.github_auth import resolve_github_access_token
from repave_engine.github_client import GitHubError
from repave_engine.github_inventory import (
    GitHubInventoryError,
    fetch_github_file_text,
    inventory_github_paths,
    parse_github_repository,
    remote_has_provenance,
    resolve_batch_targets,
    validate_pushed_since,
)
from repave_engine.github_rate_limit import wait_before_github_request
from repave_engine.import_detect import (
    BlueprintCandidate,
    best_candidate,
    detect_blueprint_candidates,
    inventory_relative_paths,
)
from repave_engine.import_rules import (
    UNMAPPED_QUARANTINE,
    classify_path,
    matches_any,
    parse_path_overrides,
    quarantine_path,
)
from repave_engine.infracost_policy import effective_gate_names
from repave_engine.pr_conventions import (
    PullRequestConventions,
    append_evidence_section,
    branch_name,
    import_pull_request_title,
    load_pull_request_conventions,
)
from repave_engine.provider_catalog import load_provider_catalog
from repave_engine.render import render_blueprint
from repave_engine.settings import load_audit_config, load_fleet_config, load_gate_overrides
from repave_engine.subprocess_run import run_subprocess
from repave_engine.target_repo import (
    ModuleRepository,
    _git_executable,
    resolve_module_repository_from_git,
)

PROVENANCE_FILENAME = "repave.yaml"
BLAME_IGNORE_FILENAME = ".git-blame-ignore-revs"
_NAME_PREFIXES = ("tf-", "tfm-", "terraform-", "ansible-role-", "ansible-", "helm-", "chart-")
_SAFE_NAME = re.compile(r"[^a-z0-9_]+")


class RepoImportError(ValueError):
    """Invalid import input or target."""


class AlreadyGovernedError(RepoImportError):
    """Target already carries repave.yaml, so it belongs in the upgrade flow."""


class ImportCloneError(RepoImportError):
    """Remote clone failed before the import could be planned."""


@dataclass(frozen=True)
class FileMove:
    source: str
    destination: str
    reason: str

    @property
    def is_rename(self) -> bool:
        return self.source != self.destination

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "destination": self.destination,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ScorecardDelta:
    before: tuple[ScorecardDimension, ...] = ()
    after: tuple[ScorecardDimension, ...] = ()

    @staticmethod
    def _passing(dims: tuple[ScorecardDimension, ...]) -> int:
        return sum(1 for dim in dims if dim.level == "pass")

    @property
    def passing_before(self) -> int:
        return self._passing(self.before)

    @property
    def passing_after(self) -> int:
        return self._passing(self.after)

    @property
    def total(self) -> int:
        return max(len(self.before), len(self.after))

    @property
    def improved(self) -> bool:
        return self.passing_after > self.passing_before

    def to_json_dict(self) -> dict[str, Any]:
        def rows(dims: tuple[ScorecardDimension, ...]) -> list[dict[str, str]]:
            return [
                {"key": d.key, "label": d.label, "level": d.level, "detail": d.detail} for d in dims
            ]

        return {
            "before": rows(self.before),
            "after": rows(self.after),
            "passing_before": self.passing_before,
            "passing_after": self.passing_after,
            "total": self.total,
            "improved": self.improved,
        }


@dataclass(frozen=True)
class ImportPlan:
    target: str
    blueprint_name: str
    blueprint_version: str
    standard_source: str = ""
    standard_version: str = ""
    moves: tuple[FileMove, ...] = ()
    unchanged: tuple[str, ...] = ()
    scaffold_added: tuple[str, ...] = ()
    unmapped: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    candidates: tuple[BlueprintCandidate, ...] = ()
    scorecard: ScorecardDelta = field(default_factory=ScorecardDelta)
    gates: tuple[GateResult, ...] = ()
    cost_delta: CostEstimateDelta | None = None
    values: dict[str, Any] = field(default_factory=dict)
    path_overrides: dict[str, str] = field(default_factory=dict)
    remote: bool = False
    detected: bool = False
    source_layout_hash: str = ""
    preview_limited: bool = False

    @property
    def renames(self) -> tuple[FileMove, ...]:
        return tuple(move for move in self.moves if move.is_rename)

    @property
    def is_noop(self) -> bool:
        return not self.renames and not self.scaffold_added

    @property
    def gates_passed(self) -> bool:
        return all_gates_passed(list(self.gates))

    @property
    def ok(self) -> bool:
        return not self.conflicts

    @property
    def summary(self) -> str:
        if self.is_noop:
            return f"Already conforms to {self.blueprint_name} v{self.blueprint_version}"
        return (
            f"{len(self.renames)} file(s) moved, "
            f"{len(self.scaffold_added)} scaffold file(s) added, "
            f"{len(self.unmapped)} unmapped"
        )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "remote": self.remote,
            "blueprint_name": self.blueprint_name,
            "blueprint_version": self.blueprint_version,
            "detected": self.detected,
            "ok": self.ok,
            "is_noop": self.is_noop,
            "gates_passed": self.gates_passed,
            "summary": self.summary,
            "path_overrides": dict(self.path_overrides),
            "preview_limited": self.preview_limited,
            "moves": [move.to_json_dict() for move in self.renames],
            "unchanged": list(self.unchanged),
            "scaffold_added": list(self.scaffold_added),
            "unmapped": list(self.unmapped),
            "conflicts": list(self.conflicts),
            "candidates": [item.to_json_dict() for item in self.candidates],
            "scorecard": self.scorecard.to_json_dict(),
            "gates": [
                {
                    "name": gate.name,
                    "passed": gate.passed,
                    "skipped": gate.skipped,
                    "message": gate.message,
                }
                for gate in self.gates
            ],
            "cost_delta": (None if self.cost_delta is None else self.cost_delta.to_public_dict()),
        }


@dataclass(frozen=True)
class ImportBatchPlan:
    """A batch of import plans. Single-repo import is a batch of one."""

    items: tuple[ImportPlan, ...] = ()
    failures: tuple[tuple[str, str], ...] = ()

    @property
    def ok(self) -> bool:
        return not self.failures and all(item.ok for item in self.items)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "count": len(self.items),
            "ok": self.ok,
            "items": [item.to_json_dict() for item in self.items],
            "failures": [{"target": target, "error": error} for target, error in self.failures],
        }


@dataclass(frozen=True)
class ImportApplyResult:
    plan: ImportPlan
    git_branch: str
    move_commit_sha: str = ""
    scaffold_commit_sha: str = ""
    verified_moves: int = 0

    @property
    def summary(self) -> str:
        return self.plan.summary

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_json_dict(),
            "git_branch": self.git_branch,
            "move_commit_sha": self.move_commit_sha,
            "scaffold_commit_sha": self.scaffold_commit_sha,
            "verified_moves": self.verified_moves,
        }


@dataclass(frozen=True)
class ImportPublishResult:
    apply: ImportApplyResult
    pull_request_url: str
    pull_request_number: int
    draft: bool = False

    def to_json_dict(self) -> dict[str, Any]:
        payload = self.apply.to_json_dict()
        payload["pull_request_url"] = self.pull_request_url
        payload["pull_request_number"] = self.pull_request_number
        payload["draft"] = self.draft
        return payload


def looks_like_remote_url(raw: str) -> bool:
    lowered = raw.strip().lower()
    return lowered.startswith(("http://", "https://", "git@", "ssh://", "file://"))


@contextmanager
def materialize_import_target(
    raw: str,
    *,
    git_token: str | None = None,
    ref: str | None = None,
) -> Iterator[tuple[Path, bool, str]]:
    """Yield (repo_path, is_remote, display_target) for a local path or remote URL."""
    text = raw.strip()
    if not text:
        raise RepoImportError("target path or repository URL is required")
    if looks_like_remote_url(text):
        token = resolve_git_token(git_token)
        try:
            with ephemeral_clone(text, token=token, ref=ref, prefix="repave-import-") as clone:
                yield clone, True, normalize_repo_url(text)
        except CloneError as exc:
            raise ImportCloneError(str(exc)) from exc
    else:
        path = Path(text).expanduser().resolve()
        if not path.is_dir():
            raise RepoImportError(f"{path} is not a directory")
        yield path, False, str(path)


def assert_not_governed(repo_dir: Path) -> None:
    """Reject a repo that already has provenance; those belong in the upgrade flow."""
    if (repo_dir / PROVENANCE_FILENAME).is_file():
        raise AlreadyGovernedError(
            f"{PROVENANCE_FILENAME} already present — this repository is governed. "
            "Use the upgrade flow (/update) to re-render it against a newer blueprint."
        )


def infer_repo_name(repo_dir: Path, target: str) -> str:
    raw = (
        Path(target).name
        if not looks_like_remote_url(target)
        else target.rstrip("/").split("/")[-1]
    )
    raw = raw or repo_dir.name
    if raw.endswith(".git"):
        raw = raw[:-4]
    return raw


def _slug(value: str) -> str:
    lowered = value.strip().lower().replace("-", "_").replace(".", "_")
    cleaned = _SAFE_NAME.sub("_", lowered).strip("_")
    return cleaned or "imported"


def artifact_name_from_repo(repo_name: str) -> str:
    stripped = repo_name.strip().lower()
    for prefix in _NAME_PREFIXES:
        if stripped.startswith(prefix) and len(stripped) > len(prefix):
            stripped = stripped[len(prefix) :]
            break
    return _slug(stripped)


def _readme_summary(repo_dir: Path) -> str:
    for name in ("README.md", "README.rst", "README.txt", "README"):
        path = repo_dir / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.strip().lstrip("#").strip()
            if stripped and not stripped.startswith(("!", "[", "<", "=", "-")):
                return stripped[:160]
    return ""


_NAME_INPUTS = (
    "module_name",
    "role_name",
    "collection_name",
    "project_name",
    "stack_name",
    "chart_name",
    "service_name",
    "policy_name",
)

_TF_RESOURCE = re.compile(r'resource\s+"([a-z0-9]+_[a-z0-9_]+)"')
_TF_PROVIDER_PREFIX = {
    "aws": "aws",
    "azurerm": "azure",
    "azuread": "azure",
    "google": "gcp",
    "google-beta": "gcp",
}
MAX_INFERRED_SERVICES = 6


def _terraform_resource_types_from_texts(texts: Mapping[str, str]) -> list[str]:
    types: list[str] = []
    for text in texts.values():
        types.extend(_TF_RESOURCE.findall(text))
    return types


def infer_terraform_scope_from_texts(
    blueprint: Blueprint,
    texts: Mapping[str, str],
) -> tuple[str, list[str]]:
    """Guess cloud provider and services from fetched ``.tf`` file bodies."""
    catalog = load_provider_catalog(blueprint.path)
    if not catalog:
        return "", []

    hits: dict[str, list[str]] = {}
    for resource_type in _terraform_resource_types_from_texts(texts):
        prefix, _, remainder = resource_type.partition("_")
        provider = _TF_PROVIDER_PREFIX.get(prefix)
        if provider is None or provider not in catalog:
            continue
        for service, definition in catalog[provider].items():
            if not remainder.startswith(f"{service}_"):
                continue
            if remainder[len(service) + 1 :] not in definition["resources"]:
                continue
            services = hits.setdefault(provider, [])
            if service not in services:
                services.append(service)

    if hits:
        provider = max(hits, key=lambda key: len(hits[key]))
        return provider, sorted(hits[provider])[:MAX_INFERRED_SERVICES]

    provider = next((key for key in ("aws", "azure", "gcp") if key in catalog), next(iter(catalog)))
    fallback = next(
        (
            service
            for service, definition in sorted(catalog[provider].items())
            if definition["basic"]
        ),
        "",
    )
    return provider, [fallback] if fallback else []


def _terraform_resource_types(repo_dir: Path, rel_paths: tuple[str, ...]) -> list[str]:
    types: list[str] = []
    for rel in rel_paths:
        if not rel.endswith(".tf"):
            continue
        try:
            text = (repo_dir / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        types.extend(_TF_RESOURCE.findall(text))
    return types


def infer_terraform_scope(
    blueprint: Blueprint,
    repo_dir: Path,
    rel_paths: tuple[str, ...],
) -> tuple[str, list[str]]:
    """Read the repo's own ``resource`` blocks to guess cloud provider and services."""
    catalog = load_provider_catalog(blueprint.path)
    if not catalog:
        return "", []

    hits: dict[str, list[str]] = {}
    for resource_type in _terraform_resource_types(repo_dir, rel_paths):
        prefix, _, remainder = resource_type.partition("_")
        provider = _TF_PROVIDER_PREFIX.get(prefix)
        if provider is None or provider not in catalog:
            continue
        for service, definition in catalog[provider].items():
            if not remainder.startswith(f"{service}_"):
                continue
            if remainder[len(service) + 1 :] not in definition["resources"]:
                continue
            services = hits.setdefault(provider, [])
            if service not in services:
                services.append(service)

    if hits:
        provider = max(hits, key=lambda key: len(hits[key]))
        return provider, sorted(hits[provider])[:MAX_INFERRED_SERVICES]

    provider = next((key for key in ("aws", "azure", "gcp") if key in catalog), next(iter(catalog)))
    fallback = next(
        (
            service
            for service, definition in sorted(catalog[provider].items())
            if definition["basic"]
        ),
        "",
    )
    return provider, [fallback] if fallback else []


def infer_import_values(
    blueprint: Blueprint,
    repo_dir: Path | None,
    *,
    repo_name: str,
    rel_paths: tuple[str, ...] = (),
    overrides: Mapping[str, Any] | None = None,
    file_texts: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Seed blueprint inputs from the source repo, letting caller overrides win."""
    inferred: dict[str, Any] = {}
    artifact_name = artifact_name_from_repo(repo_name)
    description = _readme_summary(repo_dir) if repo_dir is not None else ""
    if not description:
        for rel in rel_paths:
            if rel.lower().startswith("readme"):
                if file_texts and rel in file_texts:
                    for line in file_texts[rel].splitlines():
                        stripped = line.strip().lstrip("#").strip()
                        if stripped and not stripped.startswith(("!", "[", "<", "=", "-")):
                            description = stripped[:160]
                            break
                elif repo_dir is not None:
                    description = _readme_summary(repo_dir)
                if description:
                    break
    if not description:
        description = f"Imported from {repo_name}"
    input_names = {item.name for item in blueprint.inputs}

    provider = ""
    services: list[str] = []
    if {"cloud_provider", "provider_services"} <= input_names:
        if file_texts:
            provider, services = infer_terraform_scope_from_texts(blueprint, file_texts)
        elif repo_dir is not None:
            provider, services = infer_terraform_scope(blueprint, repo_dir, rel_paths)

    for item in blueprint.inputs:
        if item.name in _NAME_INPUTS:
            inferred[item.name] = artifact_name
        elif item.name == "description":
            inferred[item.name] = description
        elif item.name == "cloud_provider" and provider:
            inferred[item.name] = provider
        elif item.name == "provider_services" and services:
            inferred[item.name] = ",".join(services)
        elif item.name == "namespace":
            inferred[item.name] = _slug(repo_name.split("-")[0]) if "-" in repo_name else "acme"
        elif item.default is not None:
            inferred[item.name] = item.default
        elif item.enum:
            inferred[item.name] = item.enum[0]
        elif item.required:
            inferred[item.name] = artifact_name if item.type == "string" else ""

    for key, value in (overrides or {}).items():
        if value not in (None, ""):
            inferred[key] = value
    return inferred


def resolve_import_blueprint(
    repo_root: Path,
    *,
    blueprint_name: str | None,
    candidates: tuple[BlueprintCandidate, ...],
) -> tuple[Blueprint, bool]:
    """Load the requested blueprint, or the best detected one. Returns (blueprint, detected)."""
    if blueprint_name:
        path = blueprint_dir(repo_root, blueprint_name)
        if not path.is_dir():
            raise RepoImportError(
                f"unknown blueprint {blueprint_name!r}; add it under a configured "
                f"catalog root (default {blueprints_dir(repo_root)})"
            )
        return load_blueprint(path, repo_root=repo_root), False
    if not candidates:
        raise RepoImportError(
            "could not detect a golden path for this repository — pass a blueprint explicitly"
        )
    top = candidates[0]
    return load_blueprint(blueprint_dir(repo_root, top.blueprint_name), repo_root=repo_root), True


FAMILY_BLUEPRINT_MAP_SENTINEL = "__family_map__"


def parse_family_blueprints(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in raw.items():
        family = str(key).strip()
        blueprint = str(value).strip()
        if family and blueprint:
            result[family] = blueprint
    return result


def parse_target_blueprints(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in raw.items():
        target = str(key).strip()
        blueprint = str(value).strip()
        if not target or not blueprint:
            continue
        if looks_like_remote_url(target):
            result[normalize_repo_url(target)] = blueprint
        else:
            result[target] = blueprint
    return result


def target_blueprints_from_org_scan(summary: Mapping[str, Any]) -> dict[str, str]:
    repos = summary.get("repos")
    if not isinstance(repos, list):
        return {}
    result: dict[str, str] = {}
    for item in repos:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        candidate = item.get("top_candidate")
        if not url or not isinstance(candidate, dict):
            continue
        blueprint_name = str(candidate.get("blueprint_name", "")).strip()
        if blueprint_name:
            result[normalize_repo_url(url)] = blueprint_name
    return result


def build_default_family_blueprint_map(repo_root: Path) -> dict[str, str]:
    groups = group_blueprints_by_artifact(list_catalog_blueprints(repo_root))
    return {group.family: group.blueprints[0].name for group in groups if group.blueprints}


def _detect_candidates_for_target(
    raw_target: str,
    repo_root: Path,
    *,
    git_token: str | None = None,
    ref: str | None = None,
) -> tuple[BlueprintCandidate, ...]:
    text = raw_target.strip()
    catalog = list_catalog_blueprints(repo_root)
    if looks_like_remote_url(text):
        token = resolve_git_token(git_token) or resolve_github_access_token(git_token)
        if token and "github.com" in text.lower():
            try:
                owner, name = parse_github_repository(text)
                if remote_has_provenance(owner, name, token, ref=ref):
                    return ()
                rel_paths = inventory_github_paths(owner, name, token, ref=ref)
                return detect_blueprint_candidates(
                    Path("."),
                    catalog,
                    rel_paths=rel_paths,
                )
            except (GitHubInventoryError, ValueError):
                pass
    try:
        with materialize_import_target(text, git_token=git_token, ref=ref) as (
            repo_dir,
            _,
            _,
        ):
            assert_not_governed(repo_dir)
            return detect_blueprint_candidates(repo_dir, catalog)
    except (AlreadyGovernedError, RepoImportError, CloneError):
        return ()


def resolve_batch_target_blueprint(
    target: str,
    candidates: tuple[BlueprintCandidate, ...],
    *,
    blueprint_name: str | None,
    family_blueprints: Mapping[str, str] | None,
    target_blueprints: Mapping[str, str] | None,
) -> str | None:
    if blueprint_name and blueprint_name != FAMILY_BLUEPRINT_MAP_SENTINEL:
        return blueprint_name
    normalized = normalize_repo_url(target) if looks_like_remote_url(target) else target.strip()
    if target_blueprints:
        direct = target_blueprints.get(normalized) or target_blueprints.get(target.strip())
        if direct:
            return direct
    if family_blueprints:
        top = best_candidate(candidates)
        if top is not None:
            mapped = family_blueprints.get(top.family)
            if mapped:
                return mapped
    return None


def resolve_batch_import_blueprint_options(
    repo_root: Path,
    *,
    blueprint: str | None,
    family_blueprints_raw: object = None,
    use_family_blueprints: bool = False,
) -> tuple[str | None, dict[str, str] | None]:
    parsed_family_blueprints = parse_family_blueprints(family_blueprints_raw)
    blueprint_name = blueprint
    family_blueprints: dict[str, str] | None
    if blueprint == FAMILY_BLUEPRINT_MAP_SENTINEL:
        blueprint_name = FAMILY_BLUEPRINT_MAP_SENTINEL
        defaults = build_default_family_blueprint_map(repo_root)
        defaults.update(parsed_family_blueprints)
        family_blueprints = defaults
    elif use_family_blueprints:
        defaults = build_default_family_blueprint_map(repo_root)
        defaults.update(parsed_family_blueprints)
        family_blueprints = defaults
    elif parsed_family_blueprints:
        family_blueprints = parsed_family_blueprints
    else:
        family_blueprints = None
    return blueprint_name, family_blueprints


def _reference_tree(
    blueprint: Blueprint,
    values: dict[str, Any],
    dest: Path,
) -> tuple[str, ...]:
    """Render the blueprint to dest and return its relative file paths."""
    render_blueprint(blueprint, values, dest)
    rendered: list[str] = []
    for path in sorted(dest.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(dest).as_posix()
        if is_gate_artifact_path(rel, artifact_type=blueprint.artifact_type):
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        rendered.append(rel)
    return tuple(rendered)


def layout_hash(repo_dir: Path, rel_paths: tuple[str, ...]) -> str:
    """Hash the pre-import tree (paths plus content) as a drift baseline."""
    digest = hashlib.sha256()
    for rel in sorted(rel_paths):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        path = repo_dir / rel
        if path.is_file():
            digest.update(_file_digest(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def path_only_layout_hash(rel_paths: tuple[str, ...]) -> str:
    """Hash only path names when file content is unavailable (trees-API preview)."""
    digest = hashlib.sha256()
    for rel in sorted(rel_paths):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _classify_sources(
    rel_paths: tuple[str, ...],
    blueprint: Blueprint,
    *,
    path_overrides: Mapping[str, str] | None = None,
) -> tuple[list[FileMove], list[str], list[str], list[str]]:
    rules = blueprint.import_rules
    moves: list[FileMove] = []
    unchanged: list[str] = []
    unmapped: list[str] = []
    claimed: dict[str, str] = {}
    conflicts: list[str] = []

    for rel in rel_paths:
        outcome = classify_path(rel, rules, path_overrides=path_overrides)
        destination = outcome.destination
        if destination is None:
            unmapped.append(rel)
            # Unmapped files still occupy their own path, so they must appear in the plan:
            # otherwise scaffold would claim their destination and the "after" tree used for
            # gates and the scorecard would be missing them.
            destination = quarantine_path(rel) if rules.unmapped == UNMAPPED_QUARANTINE else rel

        previous = claimed.get(destination)
        if previous is not None and previous != rel:
            conflicts.append(
                f"`{rel}` and `{previous}` both map to `{destination}` — "
                "resolve one of them before importing"
            )
            continue
        claimed[destination] = rel

        if destination == rel:
            unchanged.append(rel)
        moves.append(FileMove(source=rel, destination=destination, reason=outcome.reason))

    return moves, unchanged, unmapped, conflicts


# Reference files matching these globs are the artifact's own source code, not governance
# scaffolding. When the repo already supplies files in one of these groups, the repo's
# content wins wholesale — import never grafts generated resources onto working code.
_PRIMARY_CONTENT_GLOBS: dict[str, tuple[tuple[str, ...], ...]] = {
    "terraform": (("*.tf", "*.tfvars"),),
    "ansible": (
        ("tasks/**",),
        ("handlers/**",),
        ("defaults/**",),
        ("vars/**",),
        ("plugins/**",),
        ("playbooks/**",),
    ),
    "helm": (("templates/**",), ("Chart.yaml", "values.yaml")),
    "app": (("src/**",), ("Dockerfile",)),
    "policy": (("**/*.rego",), ("policy/checkov/**",), ("policy/definitions/**",)),
    "observability": (("dashboards/**",), ("monitors/**",), ("rules/**",), ("alerts/**",)),
}


def _scaffold_gaps(
    reference_paths: tuple[str, ...],
    occupied: set[str],
    *,
    family: str,
) -> tuple[str, ...]:
    """Reference files with no occupant, minus generated content the repo already owns."""
    suppressed: set[str] = set()
    for group in _PRIMARY_CONTENT_GLOBS.get(family, ()):
        if any(matches_any(rel, group) for rel in occupied):
            suppressed.update(rel for rel in reference_paths if matches_any(rel, group))
    return tuple(rel for rel in reference_paths if rel not in occupied and rel not in suppressed)


def materialize_reorganized_tree(
    repo_dir: Path,
    plan: ImportPlan,
    reference_dir: Path,
    dest: Path,
) -> None:
    """Build the post-import tree in dest: moved sources plus scaffold additions."""
    dest.mkdir(parents=True, exist_ok=True)
    for move in plan.moves:
        source = repo_dir / move.source
        if not source.is_file():
            continue
        target = dest / move.destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for rel in plan.scaffold_added:
        source = reference_dir / rel
        if not source.is_file():
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def synthetic_fleet_entry(blueprint: Blueprint, target: str) -> FleetEntry:
    """The pins registration will record, so the "after" scorecard reflects the merged state."""
    return FleetEntry(
        repo_url=target if looks_like_remote_url(target) else f"local://{Path(target).name}",
        blueprint_name=blueprint.name,
        blueprint_version=blueprint.version,
        standard_source=blueprint.standard_source,
        standard_version=blueprint.standard_version,
    )


def _score_tree(
    repo_dir: Path,
    *,
    fleet_entry: FleetEntry | None,
    audit: AuditHistoryEntry | None = None,
) -> tuple[ScorecardDimension, ...]:
    return build_scorecard(
        repo_dir=repo_dir,
        fleet_entry=fleet_entry,
        operator=None,
        audit=audit,
    )


def build_import_plan(
    repo_dir: Path | None,
    repo_root: Path,
    *,
    target: str,
    blueprint_name: str | None = None,
    values: Mapping[str, Any] | None = None,
    rel_paths: tuple[str, ...] | None = None,
    path_overrides: Mapping[str, str] | None = None,
    file_texts: Mapping[str, str] | None = None,
    remote: bool = False,
    with_gates: bool = True,
    preview_limited: bool = False,
) -> ImportPlan:
    """Plan an import. Performs no writes to repo_dir when it is present."""
    if repo_dir is not None:
        assert_not_governed(repo_dir)

    normalized_overrides = parse_path_overrides(path_overrides or {})
    paths = rel_paths if rel_paths is not None else inventory_relative_paths(repo_dir)  # type: ignore[arg-type]
    if not paths:
        raise RepoImportError(f"{target} has no files to import")

    catalog = list_catalog_blueprints(repo_root)
    candidates = detect_blueprint_candidates(
        repo_dir or Path("."),
        catalog,
        rel_paths=paths,
    )
    blueprint, detected = resolve_import_blueprint(
        repo_root,
        blueprint_name=blueprint_name,
        candidates=candidates,
    )

    repo_name = infer_repo_name(repo_dir or Path("."), target)
    inferred = infer_import_values(
        blueprint,
        repo_dir,
        repo_name=repo_name,
        rel_paths=paths,
        overrides=values,
        file_texts=file_texts,
    )
    normalized = validate_inputs(blueprint, inferred, repo_root=repo_root)

    moves, unchanged, unmapped, conflicts = _classify_sources(
        paths,
        blueprint,
        path_overrides=normalized_overrides,
    )

    with tempfile.TemporaryDirectory(prefix="repave-import-ref-") as tmp:
        reference_dir = Path(tmp) / "reference"
        reference_paths = _reference_tree(blueprint, normalized, reference_dir)
        occupied = {move.destination for move in moves}
        scaffold = _scaffold_gaps(
            reference_paths,
            occupied,
            family=artifact_family(blueprint.artifact_type),
        )

        layout = (
            path_only_layout_hash(paths)
            if preview_limited or repo_dir is None
            else layout_hash(repo_dir, paths)
        )

        plan = ImportPlan(
            target=target,
            blueprint_name=blueprint.name,
            blueprint_version=blueprint.version,
            standard_source=blueprint.standard_source,
            standard_version=blueprint.standard_version,
            moves=tuple(moves),
            unchanged=tuple(sorted(set(unchanged))),
            scaffold_added=scaffold,
            unmapped=tuple(unmapped),
            conflicts=tuple(conflicts),
            candidates=candidates,
            values=normalized,
            path_overrides=dict(normalized_overrides),
            remote=remote,
            detected=detected,
            source_layout_hash=layout,
            preview_limited=preview_limited,
        )

        if conflicts or preview_limited or repo_dir is None:
            return plan

        with tempfile.TemporaryDirectory(prefix="repave-import-after-") as after_tmp:
            after_dir = Path(after_tmp) / "after"
            materialize_reorganized_tree(repo_dir, plan, reference_dir, after_dir)
            gates: tuple[GateResult, ...] = ()
            cost_delta: CostEstimateDelta | None = None
            if with_gates:
                gate_overrides = load_gate_overrides(repo_root)
                gates = tuple(
                    run_gates(
                        after_dir,
                        effective_gate_names(blueprint, gate_overrides),
                        blueprint=blueprint,
                        gate_overrides=gate_overrides,
                        require_run=False,
                        repo_root=repo_root,
                    )
                )
                before_est = load_cost_estimate_file(repo_dir)
                after_est = load_cost_estimate_file(after_dir) or cost_estimate_from_gates(
                    list(gates)
                )
                cost_delta = diff_cost_estimates(before_est, after_est)
            scorecard = ScorecardDelta(
                before=_score_tree(repo_dir, fleet_entry=None),
                after=_score_tree(
                    after_dir,
                    fleet_entry=synthetic_fleet_entry(blueprint, target),
                    audit=_gate_audit_entry(blueprint, gates),
                ),
            )
        return replace(plan, gates=gates, scorecard=scorecard, cost_delta=cost_delta)


def _gate_audit_entry(
    blueprint: Blueprint,
    gates: tuple[GateResult, ...],
) -> AuditHistoryEntry | None:
    if not gates:
        return None
    return AuditHistoryEntry(
        timestamp="",
        event="import",
        module_name=blueprint.name,
        blueprint_name=blueprint.name,
        blueprint_version=blueprint.version,
        gates_outcome="passed" if all_gates_passed(list(gates)) else "failed",
        dry_run=True,
        acting_user="",
        repository_url="",
        extra={},
    )


def _fetch_terraform_texts(
    owner: str,
    repo: str,
    rel_paths: tuple[str, ...],
    token: str,
    *,
    ref: str | None,
) -> dict[str, str]:
    texts: dict[str, str] = {}
    for rel in rel_paths:
        if not rel.endswith(".tf"):
            continue
        text = fetch_github_file_text(owner, repo, rel, token, ref=ref)
        if text:
            texts[rel] = text
    return texts


def plan_import_remote(
    raw_target: str,
    repo_root: Path,
    *,
    blueprint_name: str | None = None,
    values: Mapping[str, Any] | None = None,
    path_overrides: Mapping[str, str] | None = None,
    git_token: str | None = None,
    ref: str | None = None,
) -> ImportPlan:
    """Plan a remote import from the GitHub trees API without cloning."""
    token = resolve_git_token(git_token) or resolve_github_access_token(git_token)
    if not token:
        raise RepoImportError(
            "a GitHub token is required to preview a remote repository without cloning"
        )
    owner, name = parse_github_repository(raw_target)
    display = normalize_repo_url(raw_target)
    if remote_has_provenance(owner, name, token, ref=ref):
        raise AlreadyGovernedError(
            f"{PROVENANCE_FILENAME} already present — this repository is governed. "
            "Use the upgrade flow (/update) to re-render it against a newer blueprint."
        )
    try:
        rel_paths = inventory_github_paths(owner, name, token, ref=ref)
    except GitHubInventoryError as exc:
        raise RepoImportError(str(exc)) from exc
    file_texts = _fetch_terraform_texts(owner, name, rel_paths, token, ref=ref)
    return build_import_plan(
        None,
        repo_root,
        target=display,
        blueprint_name=blueprint_name,
        values=values,
        rel_paths=rel_paths,
        path_overrides=path_overrides,
        file_texts=file_texts,
        remote=True,
        with_gates=False,
        preview_limited=True,
    )


def plan_import(
    raw_target: str,
    repo_root: Path,
    *,
    blueprint_name: str | None = None,
    values: Mapping[str, Any] | None = None,
    path_overrides: Mapping[str, str] | None = None,
    git_token: str | None = None,
    ref: str | None = None,
    with_gates: bool = True,
    force_clone: bool = False,
) -> ImportPlan:
    """Plan an import for a local path or remote URL.

    Remote HTTPS GitHub URLs use the trees API for preview by default; pass
    ``force_clone=True`` to shallow-clone for a full scorecard and gate run.
    Apply always clones regardless of how the plan was built.
    """
    text = raw_target.strip()
    if looks_like_remote_url(text) and not force_clone:
        token = resolve_git_token(git_token) or resolve_github_access_token(git_token)
        if token and "github.com" in text.lower():
            try:
                return plan_import_remote(
                    text,
                    repo_root,
                    blueprint_name=blueprint_name,
                    values=values,
                    path_overrides=path_overrides,
                    git_token=token,
                    ref=ref,
                )
            except AlreadyGovernedError:
                raise
            except RepoImportError:
                pass

    with materialize_import_target(text, git_token=git_token, ref=ref) as (
        repo_dir,
        remote,
        display,
    ):
        return build_import_plan(
            repo_dir,
            repo_root,
            target=display,
            blueprint_name=blueprint_name,
            values=values,
            path_overrides=path_overrides,
            remote=remote,
            with_gates=with_gates,
        )


def plan_import_batch(
    targets: list[str],
    repo_root: Path,
    *,
    blueprint_name: str | None = None,
    family_blueprints: Mapping[str, str] | None = None,
    target_blueprints: Mapping[str, str] | None = None,
    values: Mapping[str, Any] | None = None,
    path_overrides: Mapping[str, str] | None = None,
    git_token: str | None = None,
    org: str = "",
    topic: str = "",
    language: str = "",
    pushed_since: str = "",
    exclude_archived: bool = True,
    exclude_forks: bool = True,
    with_gates: bool = True,
    limit: int = 30,
) -> ImportBatchPlan:
    """Plan several imports, collecting per-target failures instead of aborting."""
    token = resolve_git_token(git_token) or resolve_github_access_token(git_token)
    pushed = validate_pushed_since(pushed_since)
    resolved = resolve_batch_targets(
        targets,
        org=org,
        topic=topic,
        language=language,
        pushed_since=pushed,
        exclude_archived=exclude_archived,
        exclude_forks=exclude_forks,
        token=token,
        limit=limit,
    )
    if not resolved:
        raise RepoImportError("at least one repository target is required")

    items: list[ImportPlan] = []
    failures: list[tuple[str, str]] = []
    for target in resolved:
        wait_before_github_request()
        try:
            candidates = _detect_candidates_for_target(
                target,
                repo_root,
                git_token=token,
            )
            blueprint_for_target = resolve_batch_target_blueprint(
                target,
                candidates,
                blueprint_name=blueprint_name,
                family_blueprints=family_blueprints,
                target_blueprints=target_blueprints,
            )
            items.append(
                plan_import(
                    target,
                    repo_root,
                    blueprint_name=blueprint_for_target,
                    values=values,
                    path_overrides=path_overrides,
                    git_token=token,
                    with_gates=with_gates,
                )
            )
        except (RepoImportError, OSError, ValueError) as exc:
            failures.append((target, str(exc)))
    return ImportBatchPlan(items=tuple(items), failures=tuple(failures))


def suggested_import_branch(plan: ImportPlan, repo_root: Path | None = None) -> str:
    conventions = (
        load_pull_request_conventions(repo_root)
        if repo_root is not None
        else PullRequestConventions()
    )
    return branch_name(
        conventions.branch_prefix_import, plan.blueprint_name, plan.blueprint_version
    )


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_git(args: list[str], *, cwd: Path, token: str | None = None) -> str:
    try:
        result = run_subprocess([_git_executable(), *args], cwd=cwd, check=True, git=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RepoImportError(redact_secrets(detail, token) or f"git {args[0]} failed") from exc
    except FileNotFoundError as exc:
        raise RepoImportError("git executable not found") from exc
    return result.stdout.strip()


def _ensure_git_identity(repo_dir: Path) -> None:
    for key, value in (("user.email", "repave@local.dev"), ("user.name", "repave")):
        existing = run_subprocess(
            [_git_executable(), "config", "--get", key],
            cwd=repo_dir,
            git=True,
        )
        if not existing.stdout.strip():
            _run_git(["config", key, value], cwd=repo_dir)


def _git_move(repo_dir: Path, move: FileMove) -> None:
    destination = repo_dir / move.destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run_git(["mv", "-f", move.source, move.destination], cwd=repo_dir)


def _prune_empty_dirs(repo_dir: Path, moves: tuple[FileMove, ...]) -> None:
    """Remove source directories left empty by the moves.

    Git tracks files, not directories, so ``git mv`` leaves the vacated parent behind as
    working-tree cruft the reviewer would have to delete by hand.
    """
    candidates = {
        repo_dir / parent
        for move in moves
        for parent in Path(move.source).parents
        if parent != Path(".")
    }
    for path in sorted(candidates, key=lambda item: len(item.parts), reverse=True):
        if path == repo_dir or not path.is_dir():
            continue
        try:
            next(path.iterdir())
        except StopIteration:
            path.rmdir()
        except OSError:
            continue


def apply_import(
    repo_dir: Path,
    plan: ImportPlan,
    repo_root: Path,
    *,
    git_branch: str,
    move_commit_message: str = "",
    scaffold_commit_message: str = "",
) -> ImportApplyResult:
    """Rearrange repo_dir on a new branch as two commits: pure moves, then scaffold.

    The move commit changes no file content, so a reviewer can verify it mechanically.
    """
    if not plan.ok:
        raise RepoImportError("cannot apply an import plan with conflicts")
    if plan.is_noop:
        raise RepoImportError("nothing to import — the repository already conforms")

    _ensure_git_identity(repo_dir)
    _run_git(["checkout", "-B", git_branch], cwd=repo_dir)

    digests_before = {
        move.source: _file_digest(repo_dir / move.source)
        for move in plan.renames
        if (repo_dir / move.source).is_file()
    }

    for move in plan.renames:
        if (repo_dir / move.source).is_file():
            _git_move(repo_dir, move)

    _prune_empty_dirs(repo_dir, plan.renames)

    verified = 0
    for move in plan.renames:
        target = repo_dir / move.destination
        expected = digests_before.get(move.source)
        if expected is None or not target.is_file():
            continue
        if _file_digest(target) != expected:
            raise RepoImportError(
                f"content changed while moving `{move.source}` to `{move.destination}`"
            )
        verified += 1

    move_message = move_commit_message or (
        f"refactor(repave): move files into {plan.blueprint_name} layout\n\n"
        f"Pure file moves, no content changes. {verified} file(s) verified byte-identical."
    )
    _run_git(["add", "-A"], cwd=repo_dir)
    move_sha = _commit_if_changed(repo_dir, move_message)

    if move_sha:
        _append_blame_ignore(repo_dir, move_sha)

    with tempfile.TemporaryDirectory(prefix="repave-import-scaffold-") as tmp:
        reference_dir = Path(tmp) / "reference"
        blueprint = load_blueprint(
            blueprint_dir(repo_root, plan.blueprint_name),
            repo_root=repo_root,
        )
        _reference_tree(blueprint, dict(plan.values), reference_dir)
        for rel in plan.scaffold_added:
            source = reference_dir / rel
            if not source.is_file():
                continue
            target = repo_dir / rel
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    annotate_import_provenance(repo_dir, plan)

    scaffold_message = scaffold_commit_message or (
        f"feat(repave): add {plan.blueprint_name} scaffold\n\n"
        f"Adds {len(plan.scaffold_added)} golden path file(s) that were missing, "
        f"including {PROVENANCE_FILENAME} provenance."
    )
    _run_git(["add", "-A"], cwd=repo_dir)
    scaffold_sha = _commit_if_changed(repo_dir, scaffold_message)

    return ImportApplyResult(
        plan=plan,
        git_branch=git_branch,
        move_commit_sha=move_sha,
        scaffold_commit_sha=scaffold_sha,
        verified_moves=verified,
    )


def annotate_import_provenance(repo_dir: Path, plan: ImportPlan) -> None:
    """Record in repave.yaml that the repo arrived by import, plus its pre-import baseline.

    Later drift detection compares against ``pre_import_layout_hash`` rather than assuming
    the tree was generated from the blueprint.
    """
    path = repo_dir / PROVENANCE_FILENAME
    if not path.is_file() or not plan.source_layout_hash:
        return
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        return
    spec = document.get("spec")
    if not isinstance(spec, dict):
        return
    spec["import"] = {
        "source": plan.target,
        "imported_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "pre_import_layout_hash": plan.source_layout_hash,
        "moved_files": len(plan.renames),
        "scaffold_files": len(plan.scaffold_added),
        "unmapped_files": list(plan.unmapped),
    }
    if plan.path_overrides:
        spec["import"]["overrides"] = dict(plan.path_overrides)
    path.write_text(
        yaml.safe_dump(document, sort_keys=False, default_flow_style=False, width=4096),
        encoding="utf-8",
    )


def _commit_if_changed(repo_dir: Path, message: str) -> str:
    status = run_subprocess(
        [_git_executable(), "status", "--porcelain"],
        cwd=repo_dir,
        git=True,
    )
    if not status.stdout.strip():
        return ""
    _run_git(["commit", "-m", message], cwd=repo_dir)
    return _run_git(["rev-parse", "HEAD"], cwd=repo_dir)


def _append_blame_ignore(repo_dir: Path, commit_sha: str) -> None:
    """Keep git blame useful after a mass move."""
    path = repo_dir / BLAME_IGNORE_FILENAME
    header = "# Bulk file moves from repave import; ignored by git blame.\n"
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if commit_sha in existing:
        return
    body = existing if existing.endswith("\n") or not existing else existing + "\n"
    if not existing:
        body = header
    path.write_text(f"{body}{commit_sha}\n", encoding="utf-8")


def build_import_pull_request_title(plan: ImportPlan) -> str:
    return import_pull_request_title(plan.blueprint_name, plan.blueprint_version)


def build_import_pull_request_body(result: ImportApplyResult) -> str:
    plan = result.plan
    lines = [
        "## Summary",
        (
            f"Adopts the `{plan.blueprint_name}` v{plan.blueprint_version} golden path "
            "layout for this repository (via `repave import`)."
        ),
        "",
        plan.summary,
        "",
        "### Content safety",
        (
            f"All {result.verified_moves} moved file(s) are byte-identical; SHA-256 verified "
            "before and after the move."
        ),
        (
            f"Commit `{result.move_commit_sha[:12]}` contains **only** file moves. "
            f"Commit `{result.scaffold_commit_sha[:12]}` adds the missing scaffold."
            if result.move_commit_sha and result.scaffold_commit_sha
            else "Review each commit independently."
        ),
    ]

    if plan.renames:
        lines.extend(["", "### Moved files"])
        lines.extend(f"- `{move.source}` -> `{move.destination}`" for move in plan.renames[:100])
        if len(plan.renames) > 100:
            lines.append(f"- ...and {len(plan.renames) - 100} more")

    if plan.scaffold_added:
        lines.extend(["", "### Added files"])
        lines.extend(f"- `{rel}`" for rel in plan.scaffold_added[:100])
        if len(plan.scaffold_added) > 100:
            lines.append(f"- ...and {len(plan.scaffold_added) - 100} more")

    if plan.unmapped:
        lines.extend(["", "### Left in place (no rule matched)"])
        lines.extend(f"- `{rel}`" for rel in plan.unmapped[:50])

    scorecard = plan.scorecard
    if scorecard.total:
        lines.extend(
            [
                "",
                "### Scorecard",
                (
                    f"{scorecard.passing_before} of {scorecard.total} passing before, "
                    f"{scorecard.passing_after} of {scorecard.total} after."
                ),
            ]
        )

    failing = [gate for gate in plan.gates if not gate.passed and not gate.skipped]
    if failing:
        lines.extend(["", "### Failing gates"])
        lines.extend(f"- `{gate.name}`: {gate.message}" for gate in failing)

    if plan.cost_delta is not None:
        lines.extend(["", "### Cost estimate", plan.cost_delta.detail])

    lines.extend(
        [
            "",
            f"`{BLAME_IGNORE_FILENAME}` records the move commit so `git blame` stays useful.",
            "Close this PR to abandon the import branch.",
        ]
    )
    return "\n".join(lines) + "\n"


def push_import_branch(
    repo_dir: Path,
    repository: ModuleRepository,
    *,
    token: str,
    branch: str,
) -> None:
    """Push the import branch, unshallowing once if the remote rejects a shallow update."""
    try:
        push_git_branch(
            repo_dir,
            owner=repository.owner,
            name=repository.name,
            token=token,
            branch=branch,
        )
        return
    except subprocess.CalledProcessError as exc:
        detail = redact_secrets((exc.stderr or exc.stdout or str(exc)).strip(), token)
        if not is_shallow_update_rejection(detail):
            raise RepoImportError(detail or "git push failed") from exc

    unshallow(repo_dir)
    try:
        push_git_branch(
            repo_dir,
            owner=repository.owner,
            name=repository.name,
            token=token,
            branch=branch,
        )
    except subprocess.CalledProcessError as exc:
        detail = redact_secrets((exc.stderr or exc.stdout or str(exc)).strip(), token)
        raise RepoImportError(detail or "git push failed after unshallow") from exc


@dataclass(frozen=True)
class ImportPreflight:
    """Outcome of the cheap checks that run before any cloning or rendering."""

    repository: ModuleRepository
    base_branch: str
    existing_pull_request_url: str = ""
    existing_pull_request_number: int = 0

    @property
    def has_existing_pull_request(self) -> bool:
        return bool(self.existing_pull_request_url)


def preflight_import(
    repo_dir: Path,
    *,
    github_token: str,
    git_branch: str,
) -> ImportPreflight:
    """Check push access, resolve the base branch, and detect a duplicate import PR."""
    repository = resolve_module_repository_from_git(repo_dir)
    allowed, reason = can_push_to_repository(repository.owner, repository.name, github_token)
    if not allowed:
        raise RepoImportError(reason)

    base = default_branch(repository.owner, repository.name, github_token)
    existing = find_open_pull_request(
        repository.owner,
        repository.name,
        github_token,
        head_branch=git_branch,
    )
    if existing is None:
        return ImportPreflight(repository=repository, base_branch=base)
    return ImportPreflight(
        repository=repository,
        base_branch=base,
        existing_pull_request_url=str(existing.get("html_url", "")),
        existing_pull_request_number=int(existing.get("number", 0)),
    )


def open_import_pull_request(
    repo_dir: Path,
    plan: ImportPlan,
    repo_root: Path,
    *,
    github_token: str,
    git_branch: str,
    base_branch: str = "",
) -> ImportPublishResult:
    """Apply the plan on a branch, push it, and open a PR on the source repository."""
    preflight = preflight_import(repo_dir, github_token=github_token, git_branch=git_branch)
    if preflight.has_existing_pull_request:
        raise RepoImportError(
            f"an import pull request is already open for `{git_branch}`: "
            f"{preflight.existing_pull_request_url}"
        )

    apply_result = apply_import(repo_dir, plan, repo_root, git_branch=git_branch)
    push_import_branch(
        repo_dir,
        preflight.repository,
        token=github_token,
        branch=git_branch,
    )

    draft = not plan.gates_passed
    conventions = load_pull_request_conventions(repo_root)
    body = append_evidence_section(
        build_import_pull_request_body(apply_result),
        plan.gates,
        enabled=conventions.evidence_checklist,
    )
    payload = create_github_pull_request(
        preflight.repository.owner,
        preflight.repository.name,
        title=build_import_pull_request_title(plan),
        body=body,
        head=git_branch,
        base=base_branch or preflight.base_branch,
        token=github_token,
        draft=draft,
    )
    pr_number = int(payload.get("number", 0))
    if pr_number and conventions.labels:
        add_pull_request_labels(
            preflight.repository.owner,
            preflight.repository.name,
            pr_number,
            conventions.labels,
            github_token,
        )
    return ImportPublishResult(
        apply=apply_result,
        pull_request_url=str(payload.get("html_url", "")),
        pull_request_number=int(payload.get("number", 0)),
        draft=draft,
    )


IMPORT_AUDIT_EVENT = "import"


def record_import(
    repo_root: Path,
    result: ImportPublishResult,
    *,
    acting_user: str = "",
) -> bool:
    """Log the import to the audit sink and register the repo. Returns True when registered.

    Both writes are best effort: audit and fleet are optional deployment features, and a
    successful pull request should not be reported as a failure because they are off.
    """
    plan = result.apply.plan
    audit_config = load_audit_config(repo_root)
    if audit_config is not None and audit_config.enabled:
        append_audit_record(
            audit_config.file,
            AuditRecord(
                event=IMPORT_AUDIT_EVENT,
                blueprint_name=plan.blueprint_name,
                blueprint_version=plan.blueprint_version,
                module_name=artifact_name_from_repo(infer_repo_name(Path("."), plan.target)),
                dry_run=False,
                gates_outcome="passed" if plan.gates_passed else "failed",
                repository_url=plan.target if plan.remote else None,
                acting_user=acting_user or acting_user_from_env(),
                extra={
                    "moved_files": len(plan.renames),
                    "scaffold_files": len(plan.scaffold_added),
                    "unmapped_files": len(plan.unmapped),
                    "git_branch": result.apply.git_branch,
                    "move_commit_sha": result.apply.move_commit_sha,
                    "pull_request_url": result.pull_request_url,
                    "draft": result.draft,
                    "source_layout_hash": plan.source_layout_hash,
                    **audit_extra_for_cost_estimate(
                        None
                        if plan.cost_delta is None
                        else plan.cost_delta.after or plan.cost_delta.before
                    ),
                },
            ),
            repo_root=repo_root,
        )

    if not plan.remote:
        return False
    fleet_config = load_fleet_config(repo_root)
    if fleet_config is None or not fleet_config.enabled:
        return False
    try:
        register_repo(
            fleet_config.file,
            FleetEntry(
                repo_url=plan.target,
                blueprint_name=plan.blueprint_name,
                blueprint_version=plan.blueprint_version,
                standard_source=plan.standard_source,
                standard_version=plan.standard_version,
            ),
            repo_root=repo_root,
        )
    except (FleetError, OSError):
        return False
    return True


def import_repository(
    raw_target: str,
    repo_root: Path,
    *,
    github_token: str,
    blueprint_name: str | None = None,
    values: Mapping[str, Any] | None = None,
    path_overrides: Mapping[str, str] | None = None,
    ref: str | None = None,
    git_branch: str = "",
    base_branch: str = "",
    with_gates: bool = True,
) -> ImportPublishResult:
    """Plan and publish an import in one materialized checkout."""
    with materialize_import_target(raw_target, git_token=github_token, ref=ref) as (
        repo_dir,
        remote,
        display,
    ):
        plan = build_import_plan(
            repo_dir,
            repo_root,
            target=display,
            blueprint_name=blueprint_name,
            values=values,
            path_overrides=path_overrides,
            remote=remote,
            with_gates=with_gates,
        )
        branch = git_branch or suggested_import_branch(plan)
        return open_import_pull_request(
            repo_dir,
            plan,
            repo_root,
            github_token=github_token,
            git_branch=branch,
            base_branch=base_branch,
        )


@dataclass(frozen=True)
class ImportBatchPublishResult:
    items: tuple[ImportPublishResult, ...] = ()
    failures: tuple[tuple[str, str], ...] = ()

    @property
    def ok(self) -> bool:
        return not self.failures and bool(self.items)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "count": len(self.items),
            "ok": self.ok,
            "items": [item.to_json_dict() for item in self.items],
            "failures": [{"target": target, "error": error} for target, error in self.failures],
        }


def import_repository_batch(
    targets: list[str],
    repo_root: Path,
    *,
    github_token: str,
    blueprint_name: str | None = None,
    family_blueprints: Mapping[str, str] | None = None,
    target_blueprints: Mapping[str, str] | None = None,
    values: Mapping[str, Any] | None = None,
    org: str = "",
    topic: str = "",
    language: str = "",
    pushed_since: str = "",
    exclude_archived: bool = True,
    exclude_forks: bool = True,
    with_gates: bool = True,
    limit: int = 30,
) -> ImportBatchPublishResult:
    """Apply imports for many repositories, opening one pull request per repo."""
    batch = plan_import_batch(
        targets,
        repo_root,
        blueprint_name=blueprint_name,
        family_blueprints=family_blueprints,
        target_blueprints=target_blueprints,
        values=values,
        git_token=github_token,
        org=org,
        topic=topic,
        language=language,
        pushed_since=pushed_since,
        exclude_archived=exclude_archived,
        exclude_forks=exclude_forks,
        with_gates=with_gates,
        limit=limit,
    )
    published: list[ImportPublishResult] = []
    failures = list(batch.failures)
    for plan in batch.items:
        if not plan.ok or plan.is_noop:
            failures.append((plan.target, "nothing to import or plan has conflicts"))
            continue
        wait_before_github_request()
        try:
            published.append(
                import_repository(
                    plan.target,
                    repo_root,
                    github_token=github_token,
                    blueprint_name=plan.blueprint_name,
                    values=plan.values,
                    path_overrides=plan.path_overrides,
                    with_gates=with_gates,
                    git_branch=suggested_import_branch(plan),
                )
            )
        except (RepoImportError, GitHubError, OSError, ValueError) as exc:
            failures.append((plan.target, str(exc)))
    return ImportBatchPublishResult(
        items=tuple(published),
        failures=tuple(failures),
    )
