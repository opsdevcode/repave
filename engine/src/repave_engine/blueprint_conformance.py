"""Render and gate every shipped blueprint using checked-in fixture inputs."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from repave_engine.blueprint import blueprints_dir, load_blueprint
from repave_engine.pipeline import generate_from_blueprint
from repave_engine.settings import OutputConfig

CONFORMANCE_FILE = "conformance.yaml"
MANIFEST_FILE = "conformance.manifest.json"
TEXT_SUFFIXES = {
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".tf",
    ".hcl",
    ".rego",
    ".py",
    ".toml",
    ".txt",
    ".tpl",
    ".sh",
    ".cfg",
    ".ini",
    ".dockerfile",
}
SKIP_DIR_NAMES = {".git", ".terraform", ".molecule", "__pycache__", ".repave"}
# Copier/Jinja leftovers vs Helm template syntax in rendered charts.
_JINJA_BLOCK = re.compile(r"\{%")
_Copier_VAR = re.compile(r"\{\{(?!\s*[\.\-$]|\s*include)")
_ENGINE_PIP_PIN = re.compile(r"repave-engine==[\d.]+(?:\.\w+)?")
_ENGINE_VERSION_YAML = re.compile(r"(?m)^(\s*engine_version:\s*)(['\"]?)[\d.]+(?:\.\w+)?\2\s*$")
_README_ENGINE_LINE = re.compile(r"(?m)^(- \*\*Engine:\*\* `)[\d.]+(?:\.\w+)?(`)")
_MANIFEST_ENGINE_NEUTRAL = b"SNAPSHOT"


@dataclass(frozen=True)
class ConformanceSpec:
    inputs: dict[str, Any]
    required_files: tuple[str, ...]
    snapshot: bool


@dataclass(frozen=True)
class ConformanceResult:
    blueprint_name: str
    output_dir: Path
    gate_failures: tuple[str, ...]
    missing_files: tuple[str, ...]
    placeholder_hits: tuple[str, ...]
    manifest_diff: str | None


def blueprint_dirs(repo_root: Path) -> tuple[Path, ...]:
    root = blueprints_dir(repo_root)
    return tuple(
        sorted(
            path for path in root.iterdir() if path.is_dir() and (path / "blueprint.yaml").is_file()
        )
    )


def load_conformance_spec(blueprint_dir: Path) -> ConformanceSpec | None:
    path = blueprint_dir / CONFORMANCE_FILE
    if not path.is_file():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: must be a mapping")
    inputs = raw.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError(f"{path}: inputs must be a mapping")
    required = raw.get("required_files", ["repave.yaml", "README.md"])
    if not isinstance(required, list):
        raise ValueError(f"{path}: required_files must be a list")
    snapshot = bool(raw.get("snapshot", False))
    return ConformanceSpec(
        inputs={str(k): v for k, v in inputs.items()},
        required_files=tuple(str(item) for item in required),
        snapshot=snapshot,
    )


def _is_text_artifact(path: Path) -> bool:
    if path.name.lower() == "dockerfile":
        return True
    return path.suffix.lower() in TEXT_SUFFIXES


def _should_skip_path(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def _text_has_unresolved_template(text: str) -> bool:
    if _JINJA_BLOCK.search(text):
        return True
    return _Copier_VAR.search(text) is not None


def _should_skip_placeholder_scan(path: Path, output_dir: Path) -> bool:
    rel = path.relative_to(output_dir).as_posix()
    if rel.startswith("templates/"):
        return True
    if rel.startswith(".github/workflows/"):
        return True
    return rel.endswith("_helpers.tpl") or rel.endswith("NOTES.txt")


def find_unresolved_placeholders(output_dir: Path) -> list[str]:
    hits: list[str] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or _should_skip_path(path):
            continue
        if _should_skip_placeholder_scan(path, output_dir):
            continue
        if not _is_text_artifact(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if _text_has_unresolved_template(text):
            rel = path.relative_to(output_dir).as_posix()
            hits.append(f"{rel} has unresolved template syntax")
    return hits


def _normalize_manifest_bytes(rel: str, data: bytes) -> bytes:
    """Drop engine-version pins from hashes so release bumps do not rewrite manifests."""
    if not _is_text_artifact(Path(rel)):
        return data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    if rel.startswith(".github/workflows/") and rel.endswith(".yml"):
        text = _ENGINE_PIP_PIN.sub("repave-engine==SNAPSHOT", text)
    elif rel == "repave.yaml":
        text = _ENGINE_VERSION_YAML.sub(
            rf"\1\2{_MANIFEST_ENGINE_NEUTRAL.decode()}\2",
            text,
        )
    elif rel == "README.md":
        text = _README_ENGINE_LINE.sub(rf"\1{_MANIFEST_ENGINE_NEUTRAL.decode()}\2", text)
    return text.encode("utf-8")


def _file_manifest_digest(rel: str, data: bytes) -> str:
    normalized = _normalize_manifest_bytes(rel, data)
    return hashlib.sha256(normalized).hexdigest()


def build_file_manifest(output_dir: Path) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or _should_skip_path(path):
            continue
        rel = path.relative_to(output_dir).as_posix()
        manifest[rel] = _file_manifest_digest(rel, path.read_bytes())
    return manifest


def compare_manifest(
    blueprint_dir: Path,
    output_dir: Path,
) -> str | None:
    manifest_path = blueprint_dir / MANIFEST_FILE
    if not manifest_path.is_file():
        return None
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(expected, dict):
        raise ValueError(f"{manifest_path}: must be a JSON object")
    actual = build_file_manifest(output_dir)
    expected_keys = set(expected)
    actual_keys = set(actual)
    if expected_keys != actual_keys:
        added = sorted(actual_keys - expected_keys)
        removed = sorted(expected_keys - actual_keys)
        parts = []
        if added:
            parts.append(f"added files: {', '.join(added)}")
        if removed:
            parts.append(f"removed files: {', '.join(removed)}")
        return "; ".join(parts)
    changed = sorted(rel for rel in expected_keys if expected[rel] != actual[rel])
    if changed:
        return f"content changed: {', '.join(changed)}"
    return None


def write_manifest_snapshot(blueprint_dir: Path, output_dir: Path) -> None:
    manifest = build_file_manifest(output_dir)
    path = blueprint_dir / MANIFEST_FILE
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


_CONFORMANCE_GENERATED_AT = "1970-01-01T00:00:00+00:00"


def run_blueprint_conformance(
    blueprint_dir: Path,
    *,
    repo_root: Path,
    output_config: OutputConfig,
    staging_root: Path,
    check_snapshot: bool = True,
) -> ConformanceResult:
    spec = load_conformance_spec(blueprint_dir)
    if spec is None:
        raise FileNotFoundError(f"Missing {blueprint_dir / CONFORMANCE_FILE}")

    blueprint = load_blueprint(blueprint_dir, repo_root=repo_root)
    values = {k: str(v) for k, v in spec.inputs.items()}

    prev_generated_at = os.environ.get("REPAVE_PROVENANCE_GENERATED_AT")
    if spec.snapshot:
        os.environ["REPAVE_PROVENANCE_GENERATED_AT"] = _CONFORMANCE_GENERATED_AT
    try:
        result = generate_from_blueprint(
            blueprint,
            values,
            output_config=output_config,
            dry_run=True,
            staging_root=staging_root / blueprint.name,
            repo_root=repo_root,
        )
    finally:
        if spec.snapshot:
            if prev_generated_at is None:
                os.environ.pop("REPAVE_PROVENANCE_GENERATED_AT", None)
            else:
                os.environ["REPAVE_PROVENANCE_GENERATED_AT"] = prev_generated_at
    output_dir = result.render.output_dir

    gate_failures = tuple(
        f"{gate.name}: {gate.message}"
        for gate in result.gates
        if not gate.passed and not gate.skipped
    )
    missing = tuple(rel for rel in spec.required_files if not (output_dir / rel).is_file())
    placeholders = tuple(find_unresolved_placeholders(output_dir))
    manifest_diff = None
    if check_snapshot and spec.snapshot:
        manifest_diff = compare_manifest(blueprint_dir, output_dir)

    return ConformanceResult(
        blueprint_name=blueprint.name,
        output_dir=output_dir,
        gate_failures=gate_failures,
        missing_files=missing,
        placeholder_hits=placeholders,
        manifest_diff=manifest_diff,
    )


def update_all_manifests(
    repo_root: Path,
    *,
    modules_root: Path,
    staging_root: Path,
) -> list[str]:
    output_config = OutputConfig(github_org="conformance", modules_root=modules_root)
    updated: list[str] = []
    for blueprint_dir in blueprint_dirs(repo_root):
        spec = load_conformance_spec(blueprint_dir)
        if spec is None or not spec.snapshot:
            continue
        outcome = run_blueprint_conformance(
            blueprint_dir,
            repo_root=repo_root,
            output_config=output_config,
            staging_root=staging_root,
            check_snapshot=False,
        )
        write_manifest_snapshot(blueprint_dir, outcome.output_dir)
        updated.append(blueprint_dir.name)
    return updated
