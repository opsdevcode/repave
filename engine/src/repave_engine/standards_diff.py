"""Diff monorepo catalog pins (standards and policy packs) vs current HEAD."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repave_engine.blueprint import Blueprint
from repave_engine.governance import (
    GOVERNANCE_BASELINE_SOURCE,
    GOVERNANCE_BASELINE_VERSION,
)
from repave_engine.subprocess_run import run_subprocess
from repave_engine.target_repo import _git_executable


@dataclass(frozen=True)
class StandardsDiffFile:
    path: str
    patch: str


@dataclass(frozen=True)
class StandardsDiffResult:
    available: bool
    pinned_version: str
    standard_source: str
    baseline_commit: str
    baseline_ref: str
    reason: str
    files: tuple[StandardsDiffFile, ...]

    @property
    def has_changes(self) -> bool:
        return any(item.patch.strip() for item in self.files)


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run_subprocess(
        [_git_executable(), *args],
        cwd=repo_root,
        check=False,
        git=True,
    )


def _resolve_baseline_ref(
    repo_root: Path,
    rel_path: str,
    pinned_version: str,
    *,
    extra_refs: tuple[str, ...] = (),
) -> str | None:
    candidates = (
        *extra_refs,
        f"standards-v{pinned_version}",
        f"standards/{pinned_version}",
        f"policy-v{pinned_version}",
        f"policy/{pinned_version}",
        pinned_version,
    )
    for ref in candidates:
        result = _git(repo_root, "rev-parse", "--verify", ref)
        if result.returncode == 0:
            return result.stdout.strip()
    needle = f"Version: {pinned_version}"
    result = _git(
        repo_root,
        "log",
        "-1",
        "--format=%H",
        f"-G{needle}",
        "--",
        rel_path,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def _split_unified_diff(text: str) -> tuple[StandardsDiffFile, ...]:
    if not text.strip():
        return ()
    files: list[StandardsDiffFile] = []
    current_path = ""
    current_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("diff --git "):
            if current_path and current_lines:
                files.append(
                    StandardsDiffFile(path=current_path, patch="\n".join(current_lines) + "\n")
                )
            current_lines = [line]
            current_path = line.split(" b/", 1)[-1] if " b/" in line else line
            continue
        if line.startswith("+++ b/"):
            current_path = line.removeprefix("+++ b/").strip()
        current_lines.append(line)
    if current_path and current_lines:
        files.append(StandardsDiffFile(path=current_path, patch="\n".join(current_lines) + "\n"))
    return tuple(files)


def catalog_path_diff_for_pin(
    repo_root: Path,
    *,
    rel_path: str,
    pinned_version: str,
    path_kind: str = "standard",
    extra_refs: tuple[str, ...] = (),
) -> StandardsDiffResult:
    rel = rel_path.strip().strip("/")
    pinned = pinned_version.strip()
    kind = path_kind.strip() or "path"
    if not rel or not pinned:
        return StandardsDiffResult(
            available=False,
            pinned_version=pinned,
            standard_source=rel,
            baseline_commit="",
            baseline_ref="",
            reason=f"{kind.capitalize()} source or version is not configured on this blueprint.",
            files=(),
        )
    target = repo_root / rel
    if not target.exists():
        return StandardsDiffResult(
            available=False,
            pinned_version=pinned,
            standard_source=rel,
            baseline_commit="",
            baseline_ref="",
            reason=f"{kind.capitalize()} path `{rel}` was not found in the catalog root.",
            files=(),
        )
    if not (repo_root / ".git").exists():
        return StandardsDiffResult(
            available=False,
            pinned_version=pinned,
            standard_source=rel,
            baseline_commit="",
            baseline_ref="",
            reason=f"{kind.capitalize()} diff requires a git checkout of the repave catalog.",
            files=(),
        )

    baseline = _resolve_baseline_ref(repo_root, rel, pinned, extra_refs=extra_refs)
    if baseline is None:
        return StandardsDiffResult(
            available=False,
            pinned_version=pinned,
            standard_source=rel,
            baseline_commit="",
            baseline_ref="",
            reason=(
                f"No git ref found for {kind} version {pinned}. "
                "Tag the catalog release or ensure Version lines exist in the pinned files."
            ),
            files=(),
        )

    diff = _git(repo_root, "diff", f"{baseline}..HEAD", "--", rel)
    if diff.returncode not in (0, 1):
        return StandardsDiffResult(
            available=False,
            pinned_version=pinned,
            standard_source=rel,
            baseline_commit="",
            baseline_ref="",
            reason=f"Git diff failed for the {kind} path.",
            files=(),
        )
    files = _split_unified_diff(diff.stdout)
    return StandardsDiffResult(
        available=True,
        pinned_version=pinned,
        standard_source=rel,
        baseline_commit=baseline,
        baseline_ref=baseline[:12],
        reason="",
        files=files,
    )


def standards_diff_for_pin(
    repo_root: Path,
    *,
    standard_source: str,
    pinned_version: str,
) -> StandardsDiffResult:
    return catalog_path_diff_for_pin(
        repo_root,
        rel_path=standard_source,
        pinned_version=pinned_version,
        path_kind="standard",
    )


@dataclass(frozen=True)
class CatalogPinDiff:
    kind: str
    label: str
    result: StandardsDiffResult

    @property
    def has_changes(self) -> bool:
        return self.result.available and self.result.has_changes


def catalog_pin_diffs_for_blueprint(
    repo_root: Path,
    blueprint: Blueprint,
) -> tuple[CatalogPinDiff, ...]:
    """Standard plus Checkov/OPA/Azure/ansible-lint pack diffs vs HEAD."""
    diffs: list[CatalogPinDiff] = [
        CatalogPinDiff(
            kind="standard",
            label="Domain standard",
            result=standards_diff_for_pin(
                repo_root,
                standard_source=blueprint.standard_source,
                pinned_version=blueprint.standard_version,
            ),
        )
    ]
    if blueprint.checkov_policies is not None:
        diffs.append(
            CatalogPinDiff(
                kind="checkov",
                label="Checkov pack",
                result=catalog_path_diff_for_pin(
                    repo_root,
                    rel_path=blueprint.checkov_policies.policies_source,
                    pinned_version=blueprint.checkov_policies.policy_version,
                    path_kind="Checkov pack",
                    extra_refs=(f"checkov-v{blueprint.checkov_policies.policy_version}",),
                ),
            )
        )
    if blueprint.opa_policies is not None:
        diffs.append(
            CatalogPinDiff(
                kind="opa",
                label="OPA pack",
                result=catalog_path_diff_for_pin(
                    repo_root,
                    rel_path=blueprint.opa_policies.policies_source,
                    pinned_version=blueprint.opa_policies.policy_version,
                    path_kind="OPA pack",
                    extra_refs=(f"opa-v{blueprint.opa_policies.policy_version}",),
                ),
            )
        )
    if blueprint.azure_policy_pack is not None:
        diffs.append(
            CatalogPinDiff(
                kind="azure",
                label="Azure Policy pack",
                result=catalog_path_diff_for_pin(
                    repo_root,
                    rel_path=blueprint.azure_policy_pack.definitions_source,
                    pinned_version=blueprint.azure_policy_pack.policy_version,
                    path_kind="Azure Policy pack",
                    extra_refs=(f"azure-policy-v{blueprint.azure_policy_pack.policy_version}",),
                ),
            )
        )
    if blueprint.ansible_lint_pack is not None:
        diffs.append(
            CatalogPinDiff(
                kind="ansible-lint",
                label="ansible-lint pack",
                result=catalog_path_diff_for_pin(
                    repo_root,
                    rel_path=blueprint.ansible_lint_pack.pack_source,
                    pinned_version=blueprint.ansible_lint_pack.pack_version,
                    path_kind="ansible-lint pack",
                    extra_refs=(f"ansible-lint-v{blueprint.ansible_lint_pack.pack_version}",),
                ),
            )
        )
    return tuple(diffs)


def read_standard_file_pair(
    repo_root: Path,
    standards: StandardsDiffResult,
    diff_file: StandardsDiffFile,
) -> tuple[str, str]:
    """Return (pinned_at_baseline, at_head) text for a changed standard file."""
    rel = diff_file.path.replace("\\", "/").strip().lstrip("/")
    before = ""
    if standards.baseline_commit:
        show = _git(repo_root, "show", f"{standards.baseline_commit}:{rel}")
        if show.returncode == 0:
            before = show.stdout
    head_path = repo_root / rel
    if head_path.is_file():
        try:
            after = head_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            after = ""
    else:
        after = ""
    return before, after


@dataclass(frozen=True)
class PinChange:
    field: str
    before: str
    after: str

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "before": self.before, "after": self.after}


def _spec_str(spec: dict[str, Any], *keys: str) -> str:
    current: Any = spec
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    if current in (None, ""):
        return ""
    return str(current).strip()


def diff_observed_vs_catalog_pins(
    provenance_document: dict[str, Any],
    blueprint: Blueprint,
) -> tuple[PinChange, ...]:
    """Rows where repave.yaml pins differ from the target blueprint catalog."""
    spec = provenance_document.get("spec")
    if not isinstance(spec, dict):
        return ()

    changes: list[PinChange] = []

    def add(field: str, before: str, after: str) -> None:
        if before == after:
            return
        changes.append(PinChange(field=field, before=before or "(none)", after=after or "(none)"))

    bp_meta = spec.get("blueprint")
    if isinstance(bp_meta, dict):
        add("Blueprint name", _spec_str(spec, "blueprint", "name"), blueprint.name)
        add("Blueprint version", _spec_str(spec, "blueprint", "version"), blueprint.version)

    std = spec.get("standard")
    if isinstance(std, dict) or blueprint.standard_source:
        add("Standard source", _spec_str(spec, "standard", "source"), blueprint.standard_source)
        add("Standard version", _spec_str(spec, "standard", "version"), blueprint.standard_version)

    gov = spec.get("governance")
    if isinstance(gov, dict) or blueprint.artifact_type:
        add(
            "Governance baseline",
            _spec_str(spec, "governance", "baseline_source"),
            GOVERNANCE_BASELINE_SOURCE,
        )
        add(
            "Governance baseline version",
            _spec_str(spec, "governance", "baseline_version"),
            GOVERNANCE_BASELINE_VERSION,
        )

    if blueprint.checkov_policies is not None:
        add(
            "Checkov pack version",
            _spec_str(spec, "checkov", "policy_version"),
            blueprint.checkov_policies.policy_version,
        )

    if blueprint.opa_policies is not None:
        add(
            "OPA pack version",
            _spec_str(spec, "opa", "policy_version"),
            blueprint.opa_policies.policy_version,
        )

    if blueprint.azure_policy_pack is not None:
        add(
            "Azure Policy pack version",
            _spec_str(spec, "azurePolicy", "policy_version")
            or _spec_str(spec, "azure_policy", "policy_version"),
            blueprint.azure_policy_pack.policy_version,
        )

    if blueprint.ansible_lint_pack is not None:
        add(
            "ansible-lint pack version",
            _spec_str(spec, "ansibleLint", "pack_version")
            or _spec_str(spec, "ansible_lint", "pack_version"),
            blueprint.ansible_lint_pack.pack_version,
        )

    return tuple(changes)
