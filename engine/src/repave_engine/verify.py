"""Verify governance of an existing repository without rendering or publishing."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from repave_engine.artifact_blueprint import blueprint_from_repave_file
from repave_engine.blueprint import Blueprint, blueprint_dir, blueprints_dir, load_blueprint
from repave_engine.fleet import normalize_repo_url
from repave_engine.gate_registry import GateResult
from repave_engine.gates import all_gates_passed, run_gates
from repave_engine.git_clone import CloneError, ephemeral_clone, resolve_git_token
from repave_engine.provenance_inputs import blueprint_name_from_provenance, load_provenance_document
from repave_engine.settings import load_gate_overrides
from repave_engine.standards_diff import PinChange, diff_observed_vs_catalog_pins


class VerifyError(ValueError):
    """Invalid verify input or target."""


class VerifyCloneError(VerifyError):
    """Remote clone failed before verify could run."""


@dataclass(frozen=True)
class VerifyResult:
    target: str
    catalog_blueprint_name: str
    catalog_blueprint_version: str
    provenance_present: bool
    gates: tuple[GateResult, ...]
    pin_changes: tuple[PinChange, ...]
    remote: bool = False

    @property
    def gates_passed(self) -> bool:
        return all_gates_passed(list(self.gates))

    @property
    def pins_aligned(self) -> bool:
        return not self.pin_changes

    @property
    def ok(self) -> bool:
        return self.gates_passed and self.pins_aligned

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "remote": self.remote,
            "catalog_blueprint_name": self.catalog_blueprint_name,
            "catalog_blueprint_version": self.catalog_blueprint_version,
            "provenance_present": self.provenance_present,
            "ok": self.ok,
            "gates_passed": self.gates_passed,
            "pins_aligned": self.pins_aligned,
            "gates": [
                {
                    "name": gate.name,
                    "passed": gate.passed,
                    "skipped": gate.skipped,
                    "message": gate.message,
                }
                for gate in self.gates
            ],
            "pin_changes": [row.to_dict() for row in self.pin_changes],
        }


def _looks_like_remote_url(raw: str) -> bool:
    lowered = raw.strip().lower()
    return lowered.startswith(("http://", "https://", "git@", "ssh://", "file://"))


def _gate_blueprint_from_repo(
    target_repo: Path,
    catalog_blueprint: Blueprint,
    *,
    provenance_path: Path,
) -> Blueprint:
    try:
        return blueprint_from_repave_file(provenance_path)
    except ValueError as exc:
        if "ci.gates" in str(exc):
            return catalog_blueprint
        raise VerifyError(str(exc)) from exc


def verify_repository(
    target_repo: Path,
    repo_root: Path,
    *,
    blueprint_name: str | None = None,
    require_run: bool = False,
) -> VerifyResult:
    """Run blueprint gates and compare provenance pins to the catalog blueprint."""
    target_repo = target_repo.resolve()
    repo_root = repo_root.resolve()

    if not target_repo.is_dir():
        raise VerifyError(f"not a directory: {target_repo}")

    provenance_path = target_repo / "repave.yaml"
    provenance_present = provenance_path.is_file()
    doc: dict[str, Any] = {}

    if provenance_present:
        doc = load_provenance_document(provenance_path)
        resolved_name = (blueprint_name or blueprint_name_from_provenance(doc)).strip()
    elif blueprint_name:
        resolved_name = blueprint_name.strip()
    else:
        raise VerifyError(
            "repave.yaml is missing; pass --blueprint to select a catalog golden path"
        )

    catalog_path = blueprint_dir(repo_root, resolved_name)
    if not catalog_path.is_dir():
        raise VerifyError(f"unknown blueprint {resolved_name!r} under {blueprints_dir(repo_root)}")

    catalog_blueprint = load_blueprint(catalog_path, repo_root)
    if provenance_present:
        gate_blueprint = _gate_blueprint_from_repo(
            target_repo, catalog_blueprint, provenance_path=provenance_path
        )
        pin_changes = diff_observed_vs_catalog_pins(doc, catalog_blueprint)
    else:
        gate_blueprint = catalog_blueprint
        pin_changes = ()

    gate_overrides = load_gate_overrides(repo_root)
    gates = tuple(
        run_gates(
            target_repo,
            gate_blueprint.gates,
            blueprint=gate_blueprint,
            gate_overrides=gate_overrides,
            require_run=require_run,
        )
    )

    return VerifyResult(
        target=str(target_repo),
        catalog_blueprint_name=catalog_blueprint.name,
        catalog_blueprint_version=catalog_blueprint.version,
        provenance_present=provenance_present,
        gates=gates,
        pin_changes=pin_changes,
    )


@contextmanager
def _materialize_target(
    raw: str,
    *,
    git_token: str | None = None,
    ref: str | None = None,
) -> Iterator[tuple[Path, bool, str]]:
    """Yield (repo_path, is_remote, display_target)."""
    text = raw.strip()
    if not text:
        raise VerifyError("target path or repository URL is required")
    if _looks_like_remote_url(text):
        token = resolve_git_token(git_token)
        try:
            with ephemeral_clone(text, token=token, ref=ref) as clone_dir:
                display = normalize_repo_url(text)
                yield clone_dir, True, display
        except CloneError as exc:
            raise VerifyCloneError(str(exc)) from exc
    else:
        path = Path(text).expanduser().resolve()
        yield path, False, str(path)


def verify_target(
    raw: str,
    repo_root: Path,
    *,
    blueprint_name: str | None = None,
    require_run: bool = False,
    git_token: str | None = None,
    ref: str | None = None,
) -> VerifyResult:
    """Verify a local path or shallow-cloned remote URL."""
    with _materialize_target(raw, git_token=git_token, ref=ref) as (path, is_remote, display):
        result = verify_repository(
            path,
            repo_root,
            blueprint_name=blueprint_name,
            require_run=require_run,
        )
    if is_remote:
        return replace(result, target=display, remote=True)
    return result
