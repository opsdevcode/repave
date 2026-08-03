"""Add a second golden-path component to an already-governed repository."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from repave_engine.audit import AuditRecord, acting_user_from_env, append_audit_record
from repave_engine.blueprint import (
    Blueprint,
    blueprint_dir,
    blueprints_dir,
    load_blueprint,
    validate_inputs,
)
from repave_engine.provenance_components import (
    append_component_to_document,
    blueprint_names_from_provenance,
    build_component_record,
    default_component_id,
    list_provenance_components,
)
from repave_engine.provenance_inputs import load_provenance_document
from repave_engine.render import render_blueprint
from repave_engine.repo_import import (
    PROVENANCE_FILENAME,
    infer_import_values,
    inventory_relative_paths,
)
from repave_engine.settings import load_audit_config
from repave_engine.upgrade_plan import _git_branch_commit

ADD_AUDIT_EVENT = "component_add"

_SHARED_GOVERNANCE_FILES = frozenset(
    {
        "README.md",
        "RUNBOOK.md",
        ".yamllint",
        ".github/workflows/repave-gates.yml",
    }
)


class RepoAddError(ValueError):
    """Invalid add input or target."""


class NotGovernedError(RepoAddError):
    """Target is missing repave.yaml; use import for ungoverned repos."""


@dataclass(frozen=True)
class AddPlan:
    target: str
    blueprint_name: str
    blueprint_version: str
    component_id: str
    files_added: tuple[str, ...]
    files_overwritten: tuple[str, ...]
    conflicts: tuple[str, ...]
    ok: bool
    summary: str
    component_record: dict[str, Any] = field(repr=False)
    input_values: dict[str, Any] = field(repr=False, default_factory=dict)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "blueprint_name": self.blueprint_name,
            "blueprint_version": self.blueprint_version,
            "component_id": self.component_id,
            "files_added": list(self.files_added),
            "files_overwritten": list(self.files_overwritten),
            "conflicts": list(self.conflicts),
            "ok": self.ok,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class AddApplyResult:
    plan: AddPlan
    git_branch: str
    commit_sha: str


def assert_governed(repo_dir: Path) -> None:
    if not (repo_dir / PROVENANCE_FILENAME).is_file():
        raise NotGovernedError(
            f"{repo_dir} is not governed (missing {PROVENANCE_FILENAME}); "
            "use `repave import` for ungoverned repositories"
        )


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _iter_relative_files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    if not root.is_dir():
        return files
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if ".git/" in path.as_posix():
            continue
        files[path.relative_to(root).as_posix()] = path
    return files


def infer_add_values(
    blueprint: Blueprint,
    repo_dir: Path,
    doc: dict[str, Any],
    *,
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rel_paths = tuple(inventory_relative_paths(repo_dir))
    repo_name = repo_dir.name
    inferred = infer_import_values(
        blueprint,
        repo_dir,
        repo_name=repo_name,
        rel_paths=rel_paths,
        overrides=overrides,
    )
    try:
        primary = list_provenance_components(doc)[0]
    except ValueError:
        primary = None
    if primary is not None and primary.artifact_type == "app-service":
        app = primary.record.get("appService")
        if isinstance(app, dict):
            service_name = str(app.get("service_name", "")).strip()
            owner = str(app.get("owner", "")).strip()
            if blueprint.artifact_type == "helm-chart" and service_name:
                inferred.setdefault("app_name", service_name)
                inferred.setdefault("chart_name", f"{service_name}-chart")
                inferred.setdefault(
                    "image_repository",
                    f"ghcr.io/example-org/{service_name}",
                )
                inferred.setdefault("image_tag", "latest")
            if blueprint.artifact_type == "gitops-deployment" and service_name:
                inferred.setdefault("service_name", service_name)
                inferred.setdefault("chart_name", f"{service_name}-chart")
            if owner and "owner" in {item.name for item in blueprint.inputs}:
                inferred.setdefault("owner", owner)
    return inferred


def build_add_plan(
    repo_dir: Path,
    repo_root: Path,
    *,
    target: str,
    blueprint_name: str,
    values: Mapping[str, Any] | None = None,
    component_id: str | None = None,
    force: bool = False,
) -> AddPlan:
    repo_dir = repo_dir.resolve()
    repo_root = repo_root.resolve()
    assert_governed(repo_dir)

    provenance_path = repo_dir / PROVENANCE_FILENAME
    doc = load_provenance_document(provenance_path)
    existing = blueprint_names_from_provenance(doc)

    catalog_path = blueprint_dir(repo_root, blueprint_name)
    if not catalog_path.is_dir():
        raise RepoAddError(
            f"unknown blueprint {blueprint_name!r} under {blueprints_dir(repo_root)}"
        )
    blueprint = load_blueprint(catalog_path, repo_root=repo_root)
    if blueprint.name in existing:
        raise RepoAddError(
            f"blueprint {blueprint.name!r} is already recorded in {PROVENANCE_FILENAME}; "
            "use `repave update` to bump pins"
        )

    normalized = validate_inputs(
        blueprint,
        infer_add_values(blueprint, repo_dir, doc, overrides=values),
        repo_root=repo_root,
    )
    resolved_id = (component_id or default_component_id(blueprint)).strip()
    if not resolved_id:
        raise RepoAddError("component_id must be a non-empty string")

    with tempfile.TemporaryDirectory(prefix="repave-add-") as temp_name:
        staging = Path(temp_name)
        render_blueprint(blueprint, normalized, staging)
        staged = _iter_relative_files(staging)
        occupied = _iter_relative_files(repo_dir)

        files_added: list[str] = []
        files_overwritten: list[str] = []
        conflicts: list[str] = []

        for rel, staged_path in sorted(staged.items()):
            if rel == PROVENANCE_FILENAME:
                continue
            if rel in occupied and rel in _SHARED_GOVERNANCE_FILES:
                continue
            dest = repo_dir / rel
            if rel not in occupied:
                files_added.append(rel)
                continue
            if _file_digest(staged_path) == _file_digest(dest):
                continue
            if force:
                files_overwritten.append(rel)
            else:
                conflicts.append(
                    f"{rel}: existing file differs from generated scaffold "
                    "(pass --force to overwrite)"
                )

        component_record = build_component_record(
            blueprint,
            normalized,
            component_id=resolved_id,
        )

    ok = not conflicts
    if conflicts:
        summary = f"Add blocked: {len(conflicts)} conflict(s) with existing files"
    elif not files_added and not files_overwritten:
        summary = "No new files to add; provenance would still gain a component record"
    else:
        parts: list[str] = []
        if files_added:
            parts.append(f"{len(files_added)} file(s) to add")
        if files_overwritten:
            parts.append(f"{len(files_overwritten)} file(s) to overwrite")
        summary = "; ".join(parts)

    return AddPlan(
        target=target,
        blueprint_name=blueprint.name,
        blueprint_version=blueprint.version,
        component_id=resolved_id,
        files_added=tuple(files_added),
        files_overwritten=tuple(files_overwritten),
        conflicts=tuple(conflicts),
        ok=ok,
        summary=summary,
        component_record=component_record,
        input_values=dict(normalized),
    )


def apply_add(
    repo_dir: Path,
    repo_root: Path,
    plan: AddPlan,
    *,
    staging_dir: Path,
    git_branch: str,
    commit_message: str,
) -> AddApplyResult:
    if not plan.ok:
        raise RepoAddError("cannot apply add plan with unresolved conflicts")

    repo_dir = repo_dir.resolve()
    repo_root = repo_root.resolve()
    assert_governed(repo_dir)

    blueprint = load_blueprint(blueprint_dir(repo_root, plan.blueprint_name), repo_root=repo_root)
    normalized = validate_inputs(blueprint, plan.input_values, repo_root=repo_root)
    render_blueprint(blueprint, normalized, staging_dir)

    for rel in (*plan.files_added, *plan.files_overwritten):
        src = staging_dir / rel
        if not src.is_file():
            continue
        dest = repo_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    provenance_path = repo_dir / PROVENANCE_FILENAME
    doc = load_provenance_document(provenance_path)
    updated = append_component_to_document(doc, plan.component_record, blueprint=blueprint)
    provenance_path.write_text(
        yaml.safe_dump(updated, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    commit_sha = _git_branch_commit(repo_dir, git_branch, commit_message)
    return AddApplyResult(plan=plan, git_branch=git_branch, commit_sha=commit_sha)


def plan_add(
    target: str,
    repo_root: Path,
    *,
    blueprint_name: str,
    values: Mapping[str, Any] | None = None,
    component_id: str | None = None,
    force: bool = False,
) -> AddPlan:
    path = Path(target).expanduser().resolve()
    if not path.is_dir():
        raise RepoAddError(f"not a directory: {target}")
    return build_add_plan(
        path,
        repo_root,
        target=str(path),
        blueprint_name=blueprint_name,
        values=values,
        component_id=component_id,
        force=force,
    )


def suggested_add_branch(plan: AddPlan, *, conventions_prefix: str) -> str:
    slug = plan.component_id.replace("_", "-")
    return f"{conventions_prefix}/{slug}-{plan.blueprint_version}"


def record_add(repo_root: Path, result: AddApplyResult, *, acting_user: str) -> None:
    audit_config = load_audit_config(repo_root)
    if audit_config is not None and audit_config.enabled:
        append_audit_record(
            audit_config.file,
            AuditRecord(
                event=ADD_AUDIT_EVENT,
                blueprint_name=result.plan.blueprint_name,
                blueprint_version=result.plan.blueprint_version,
                module_name=result.plan.component_id,
                dry_run=False,
                gates_outcome="not_run",
                repository_url=result.plan.target,
                acting_user=acting_user or acting_user_from_env(),
                extra={
                    "component_id": result.plan.component_id,
                    "files_added": list(result.plan.files_added),
                    "git_branch": result.git_branch,
                    "commit_sha": result.commit_sha,
                },
            ),
        )


def record_add_from_env(repo_root: Path, result: AddApplyResult) -> None:
    record_add(repo_root, result, acting_user=acting_user_from_env())
