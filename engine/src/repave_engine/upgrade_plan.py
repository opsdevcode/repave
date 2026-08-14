from __future__ import annotations

import difflib
import hashlib
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repave_engine.auto_merge import AutoMergeDecision, decide_auto_merge_for_plan
from repave_engine.blueprint import blueprint_dir, load_blueprint, validate_inputs
from repave_engine.cost_estimate import (
    CostEstimateDelta,
    cost_estimate_from_gates,
    diff_cost_estimates,
    load_cost_estimate_file,
)
from repave_engine.gate_registry import GateResult
from repave_engine.gates import run_gates
from repave_engine.github import (
    add_pull_request_labels,
    create_github_pull_request,
    push_git_branch,
)
from repave_engine.policy_selection import diff_policy_provenance
from repave_engine.pr_conventions import (
    append_evidence_section,
    load_pull_request_conventions,
    upgrade_pull_request_title,
)
from repave_engine.provenance_inputs import (
    blueprint_name_from_provenance,
    inputs_from_provenance,
    load_provenance_document,
)
from repave_engine.render import render_blueprint
from repave_engine.settings import load_gate_overrides
from repave_engine.standards_diff import PinChange, StandardsDiffFile, diff_observed_vs_catalog_pins
from repave_engine.subprocess_run import run_subprocess
from repave_engine.target_repo import _git_executable, _run_git, resolve_module_repository_from_git

_SKIP_DIR_NAMES = frozenset({".git", "__pycache__", ".terraform", ".pytest_cache", ".ruff_cache"})
_MAX_UPGRADE_DIFF_FILES = 12
_MAX_UPGRADE_DIFF_BYTES = 120_000
_TEXT_DIFF_SUFFIXES = frozenset(
    {
        ".md",
        ".yaml",
        ".yml",
        ".json",
        ".tf",
        ".hcl",
        ".rego",
        ".txt",
        ".sh",
        ".py",
        ".toml",
        ".ini",
        ".tpl",
        ".html",
        ".css",
        ".js",
        ".mjs",
        ".cjs",
        ".xml",
        ".properties",
    }
)


@dataclass(frozen=True)
class UpgradePlanResult:
    added: tuple[str, ...]
    modified: tuple[str, ...]
    removed: tuple[str, ...]
    blueprint_name: str
    blueprint_version: str
    policy_changes: tuple[str, ...] = ()
    pin_changes: tuple[PinChange, ...] = ()
    file_diffs: tuple[StandardsDiffFile, ...] = ()
    cost_delta: CostEstimateDelta | None = None
    gates: tuple[GateResult, ...] = ()
    auto_merge: AutoMergeDecision | None = None

    @property
    def changed_file_count(self) -> int:
        return len(self.added) + len(self.modified) + len(self.removed)

    @property
    def summary(self) -> str:
        base = (
            f"{self.changed_file_count} file(s) differ "
            f"({len(self.added)} added, {len(self.modified)} modified, "
            f"{len(self.removed)} removed) "
            f"for blueprint {self.blueprint_name}@{self.blueprint_version}"
        )
        if self.policy_changes:
            return f"{base}; {len(self.policy_changes)} policy change(s)"
        return base

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "blueprint_name": self.blueprint_name,
            "blueprint_version": self.blueprint_version,
            "changed_file_count": self.changed_file_count,
            "added": list(self.added),
            "modified": list(self.modified),
            "removed": list(self.removed),
            "policy_changes": list(self.policy_changes),
            "pin_changes": [row.to_dict() for row in self.pin_changes],
            "file_diffs": [{"path": item.path, "patch": item.patch} for item in self.file_diffs],
            "cost_delta": (None if self.cost_delta is None else self.cost_delta.to_public_dict()),
            "gates": [
                {
                    "name": gate.name,
                    "passed": gate.passed,
                    "skipped": gate.skipped,
                    "message": gate.message,
                }
                for gate in self.gates
            ],
            "auto_merge": (
                None
                if self.auto_merge is None
                else {"allowed": self.auto_merge.allowed, "reason": self.auto_merge.reason}
            ),
            "summary": self.summary,
        }


@dataclass(frozen=True)
class ApplyUpgradeResult:
    plan: UpgradePlanResult
    git_branch: str = ""
    commit_sha: str = ""
    preserved_local: tuple[str, ...] = ()

    def to_json_dict(self) -> dict[str, Any]:
        payload = self.plan.to_json_dict()
        payload["git_branch"] = self.git_branch
        payload["commit_sha"] = self.commit_sha
        if self.preserved_local:
            payload["preserved_local"] = list(self.preserved_local)
        return payload

    @property
    def summary(self) -> str:
        return self.plan.summary


@dataclass(frozen=True)
class UpgradePublishResult:
    apply: ApplyUpgradeResult
    pull_request_url: str
    pull_request_number: int

    def to_json_dict(self) -> dict[str, Any]:
        payload = self.apply.to_json_dict()
        payload["pull_request_url"] = self.pull_request_url
        payload["pull_request_number"] = self.pull_request_number
        return payload

    @property
    def summary(self) -> str:
        return self.apply.summary


def build_upgrade_pull_request_title(blueprint_name: str, blueprint_version: str) -> str:
    return upgrade_pull_request_title(blueprint_name, blueprint_version)


def build_upgrade_pull_request_body(plan: UpgradePlanResult) -> str:
    lines = [
        "## Summary",
        (
            f"Blueprint upgrade for `{plan.blueprint_name}` "
            f"v{plan.blueprint_version} (via `repave update`)."
        ),
        "",
        plan.summary,
        "",
        "### File changes",
    ]
    if plan.added:
        lines.append("")
        lines.append("Added:")
        lines.extend(f"- `{path}`" for path in plan.added)
    if plan.modified:
        lines.append("")
        lines.append("Modified:")
        lines.extend(f"- `{path}`" for path in plan.modified)
    if plan.removed:
        lines.append("")
        lines.append("Removed:")
        lines.extend(f"- `{path}`" for path in plan.removed)
    if plan.policy_changes:
        lines.append("")
        lines.append("### Policy changes")
        lines.extend(f"- {note}" for note in plan.policy_changes)
    if plan.cost_delta is not None:
        lines.extend(["", "### Cost estimate", plan.cost_delta.detail])
    lines.extend(
        [
            "",
            "Review the diff before merging; close this PR to abandon the upgrade branch.",
        ]
    )
    return "\n".join(lines) + "\n"


def open_upgrade_pull_request(
    target_repo: Path,
    repo_root: Path,
    *,
    github_token: str,
    blueprint_name: str | None = None,
    staging_root: Path | None = None,
    git_branch: str,
    base_branch: str = "main",
    commit_message: str,
) -> UpgradePublishResult:
    apply_result = apply_upgrade(
        target_repo,
        repo_root,
        blueprint_name=blueprint_name,
        staging_root=staging_root,
        git_branch=git_branch,
        commit_message=commit_message,
    )
    repository = resolve_module_repository_from_git(target_repo)
    push_git_branch(
        target_repo,
        owner=repository.owner,
        name=repository.name,
        token=github_token,
        branch=git_branch,
    )
    title = build_upgrade_pull_request_title(
        apply_result.plan.blueprint_name,
        apply_result.plan.blueprint_version,
    )
    conventions = load_pull_request_conventions(repo_root)
    body = append_evidence_section(
        build_upgrade_pull_request_body(apply_result.plan),
        apply_result.plan.gates,
        enabled=conventions.evidence_checklist,
    )
    pr = create_github_pull_request(
        repository.owner,
        repository.name,
        title=title,
        body=body,
        head=git_branch,
        base=base_branch,
        token=github_token,
    )
    pr_number = int(pr.get("number", 0))
    if pr_number and conventions.labels:
        add_pull_request_labels(
            repository.owner,
            repository.name,
            pr_number,
            conventions.labels,
            github_token,
        )
    return UpgradePublishResult(
        apply=apply_result,
        pull_request_url=str(pr.get("html_url", "")),
        pull_request_number=int(pr.get("number", 0)),
    )


def _iter_relative_files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    if not root.is_dir():
        return files
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        parts = path.relative_to(root).parts
        if any(part in _SKIP_DIR_NAMES for part in parts):
            continue
        files[rel] = path
    return files


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _is_text_diff_candidate(relative_path: str) -> bool:
    suffix = Path(relative_path).suffix.lower()
    if suffix in _TEXT_DIFF_SUFFIXES:
        return True
    name = Path(relative_path).name.lower()
    return name in {"dockerfile", "makefile", "license", "readme"}


def _read_text_file(path: Path, *, max_bytes: int = _MAX_UPGRADE_DIFF_BYTES) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
    return raw.decode("utf-8", errors="replace")


def _unified_file_diff(relative_path: str, before: str, after: str) -> StandardsDiffFile | None:
    patch_lines = list(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
        )
    )
    if not patch_lines:
        return None
    return StandardsDiffFile(path=relative_path, patch="".join(patch_lines))


def build_upgrade_file_diffs(
    existing_root: Path,
    rendered_root: Path,
    *,
    modified: tuple[str, ...],
    added: tuple[str, ...],
    max_files: int = _MAX_UPGRADE_DIFF_FILES,
) -> tuple[StandardsDiffFile, ...]:
    diffs: list[StandardsDiffFile] = []
    for relative_path in modified:
        if not _is_text_diff_candidate(relative_path):
            continue
        left = existing_root / relative_path
        right = rendered_root / relative_path
        if not left.is_file() or not right.is_file():
            continue
        item = _unified_file_diff(
            relative_path,
            _read_text_file(left),
            _read_text_file(right),
        )
        if item is not None:
            diffs.append(item)
        if len(diffs) >= max_files:
            return tuple(diffs)
    for relative_path in added:
        if not _is_text_diff_candidate(relative_path):
            continue
        right = rendered_root / relative_path
        if not right.is_file():
            continue
        item = _unified_file_diff(relative_path, "", _read_text_file(right))
        if item is not None:
            diffs.append(item)
        if len(diffs) >= max_files:
            break
    return tuple(diffs)


def diff_directories(
    existing_root: Path,
    rendered_root: Path,
) -> tuple[list[str], list[str], list[str]]:
    left = _iter_relative_files(existing_root)
    right = _iter_relative_files(rendered_root)

    added = sorted(set(right) - set(left))
    removed = sorted(set(left) - set(right))
    modified: list[str] = []
    for rel in sorted(set(left) & set(right)):
        if _file_digest(left[rel]) != _file_digest(right[rel]):
            modified.append(rel)
    return added, modified, removed


def _apply_render_to_target(
    target_repo: Path,
    staging_dir: Path,
    removed: tuple[str, ...],
    modified: tuple[str, ...],
    *,
    preserve_local: bool,
) -> tuple[str, ...]:
    modified_set = set(modified)
    preserved: list[str] = []
    staging_hint_root = target_repo / ".repave" / "upgrade-staging"

    for rel in removed:
        dest = target_repo / rel
        if dest.is_file():
            dest.unlink()
        elif dest.is_dir():
            shutil.rmtree(dest)

    for rel, src in _iter_relative_files(staging_dir).items():
        if preserve_local and rel in modified_set:
            preserved.append(rel)
            hint_dest = staging_hint_root / rel
            hint_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, hint_dest)
            continue
        dest = target_repo / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    return tuple(sorted(preserved))


def _git_branch_commit(repo: Path, branch: str, message: str) -> str:
    git_dir = repo / ".git"
    if not git_dir.exists():
        raise RuntimeError(f"{repo} is not a git repository (missing .git)")

    _run_git(["checkout", "-B", branch], cwd=repo)
    _run_git(["add", "-A"], cwd=repo)
    commit = run_subprocess(
        [_git_executable(), "commit", "-m", message],
        cwd=repo,
        check=False,
        git=True,
    )
    if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr):
        raise RuntimeError(commit.stderr.strip() or commit.stdout.strip() or "git commit failed")

    head = run_subprocess(
        [_git_executable(), "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        git=True,
    )
    return head.stdout.strip()


def _render_upgrade_staging(
    target_repo: Path,
    repo_root: Path,
    *,
    blueprint_name: str | None,
    staging_root: Path | None,
) -> tuple[UpgradePlanResult, Path, tempfile.TemporaryDirectory[str] | None, bool]:
    target_repo = target_repo.resolve()
    repo_root = repo_root.resolve()
    provenance_path = target_repo / "repave.yaml"
    if not provenance_path.is_file():
        raise FileNotFoundError(f"missing provenance file: {provenance_path}")

    doc = load_provenance_document(provenance_path)
    old_policy = doc.get("spec", {}).get("policy") if isinstance(doc.get("spec"), dict) else None
    resolved_blueprint = (blueprint_name or blueprint_name_from_provenance(doc)).strip()
    blueprint_path = blueprint_dir(repo_root, resolved_blueprint)
    blueprint = load_blueprint(blueprint_path, repo_root=repo_root)
    gate_overrides = load_gate_overrides(repo_root)
    values = validate_inputs(
        blueprint,
        inputs_from_provenance(doc),
        repo_root=repo_root,
        gate_overrides=gate_overrides,
    )

    owns_staging = staging_root is None
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if staging_root is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="repave-plan-")
        staging_dir = Path(temp_dir.name)
    else:
        staging_root.mkdir(parents=True, exist_ok=True)
        staging_dir = staging_root

    render_blueprint(blueprint, values, staging_dir)
    added, modified, removed = diff_directories(target_repo, staging_dir)
    new_policy: dict[str, Any] | None = None
    staged_prov = staging_dir / "repave.yaml"
    if staged_prov.is_file():
        import yaml

        staged_doc = yaml.safe_load(staged_prov.read_text(encoding="utf-8"))
        if isinstance(staged_doc, dict):
            spec = staged_doc.get("spec")
            if isinstance(spec, dict):
                raw_policy = spec.get("policy")
                if isinstance(raw_policy, dict):
                    new_policy = raw_policy
    policy_changes = diff_policy_provenance(
        old_policy if isinstance(old_policy, dict) else None,
        new_policy,
    )
    pin_changes = diff_observed_vs_catalog_pins(doc, blueprint)
    file_diffs = build_upgrade_file_diffs(
        target_repo,
        staging_dir,
        modified=tuple(modified),
        added=tuple(added),
    )
    # Cost preview: run infracost only when org floor requires it or a prior estimate exists
    # (delta vs previous pin). Avoids terraform plan on every upgrade when optional.
    before_est = load_cost_estimate_file(target_repo)
    want_estimate = gate_overrides.infracost.required or before_est is not None
    gates: tuple[GateResult, ...] = ()
    after_est = None
    if want_estimate:
        gates = tuple(
            run_gates(
                staging_dir,
                ("infracost",),
                blueprint=blueprint,
                gate_overrides=gate_overrides,
                require_run=False,
                repo_root=repo_root,
            )
        )
        after_est = load_cost_estimate_file(staging_dir) or cost_estimate_from_gates(list(gates))
    cost_delta = diff_cost_estimates(before_est, after_est)
    result = UpgradePlanResult(
        added=tuple(added),
        modified=tuple(modified),
        removed=tuple(removed),
        blueprint_name=blueprint.name,
        blueprint_version=blueprint.version,
        policy_changes=policy_changes,
        pin_changes=pin_changes,
        file_diffs=file_diffs,
        cost_delta=cost_delta,
        gates=gates,
        auto_merge=decide_auto_merge_for_plan(
            repo_root=repo_root,
            blueprint_name=blueprint.name,
            pin_changes=pin_changes,
            policy_changes=policy_changes,
            gates=gates,
        ),
    )
    return result, staging_dir, temp_dir, owns_staging


def plan_upgrade(
    target_repo: Path,
    repo_root: Path,
    *,
    blueprint_name: str | None = None,
    staging_root: Path | None = None,
) -> UpgradePlanResult:
    result, _, temp_dir, owns_staging = _render_upgrade_staging(
        target_repo,
        repo_root,
        blueprint_name=blueprint_name,
        staging_root=staging_root,
    )
    try:
        return result
    finally:
        if owns_staging and temp_dir is not None:
            temp_dir.cleanup()


def apply_upgrade(
    target_repo: Path,
    repo_root: Path,
    *,
    blueprint_name: str | None = None,
    staging_root: Path | None = None,
    git_branch: str,
    commit_message: str,
    preserve_local: bool = False,
) -> ApplyUpgradeResult:
    result, staging_dir, temp_dir, owns_staging = _render_upgrade_staging(
        target_repo,
        repo_root,
        blueprint_name=blueprint_name,
        staging_root=staging_root,
    )
    try:
        preserved = _apply_render_to_target(
            target_repo,
            staging_dir,
            result.removed,
            result.modified,
            preserve_local=preserve_local,
        )
        commit_sha = _git_branch_commit(target_repo, git_branch, commit_message)
        return ApplyUpgradeResult(
            plan=result,
            git_branch=git_branch,
            commit_sha=commit_sha,
            preserved_local=preserved,
        )
    finally:
        if owns_staging and temp_dir is not None:
            temp_dir.cleanup()
