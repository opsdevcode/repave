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

from repave_engine.blueprint import blueprints_dir, load_blueprint, validate_inputs
from repave_engine.gates import is_gate_artifact_path
from repave_engine.pipeline import generate_from_blueprint
from repave_engine.render import render_blueprint
from repave_engine.settings import OutputConfig, load_gate_overrides

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
SKIP_DIR_NAMES = {
    ".git",
    ".terraform",
    ".molecule",
    "__pycache__",
    ".repave",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "target",
    "bin",
    "obj",
}
MANIFEST_SKIP_DIR_NAMES = SKIP_DIR_NAMES | {".gate-tools"}
MANIFEST_SKIP_FILE_NAMES = frozenset({"package-lock.json", "npm-shrinkwrap.yaml"})
# Copier/Jinja leftovers vs Helm template syntax in rendered charts.
_JINJA_BLOCK = re.compile(r"\{%")
_Copier_VAR = re.compile(r"\{\{(?!\s*[\.\-$]|\s*include)")
_ENGINE_PIP_PIN = re.compile(r"repave-engine==[\d.]+(?:\.\w+)?")
_ENGINE_VERSION_YAML = re.compile(r"(?m)^(\s*engine_version:\s*)(['\"]?)[\d.]+(?:\.\w+)?\2\s*$")
_README_ENGINE_LINE = re.compile(r"(?m)^(- \*\*Engine:\*\* `)[\d.]+(?:\.\w+)?(`)")
# Backstage annotations written by backstage_catalog.py — live pins, hash-neutral.
_CATALOG_REPAVE_VERSION_ANNOTATION = re.compile(
    r"(?m)^(\s*repave\.dev/(?:engine|blueprint|standard)-version:\s*)(['\"]?)[\d.]+(?:\.\w+)?\2\s*$"
)
_MANIFEST_ENGINE_NEUTRAL = b"SNAPSHOT"


@dataclass(frozen=True)
class ConformanceSpec:
    inputs: dict[str, Any]
    required_files: tuple[str, ...]
    snapshot: bool
    variant_id: str = ""
    run_gates: bool = True
    slow_harness: bool = True


@dataclass(frozen=True)
class ConformanceResult:
    blueprint_name: str
    output_dir: Path
    gate_failures: tuple[str, ...]
    missing_files: tuple[str, ...]
    placeholder_hits: tuple[str, ...]
    manifest_diff: str | None
    variant_id: str = ""


def blueprint_dirs(repo_root: Path) -> tuple[Path, ...]:
    root = blueprints_dir(repo_root)
    return tuple(
        sorted(
            path for path in root.iterdir() if path.is_dir() and (path / "blueprint.yaml").is_file()
        )
    )


def _manifest_filename(variant_id: str) -> str:
    if not variant_id:
        return MANIFEST_FILE
    return f"conformance.manifest.{variant_id}.json"


def manifest_path(blueprint_dir: Path, *, variant_id: str = "") -> Path:
    return blueprint_dir / _manifest_filename(variant_id)


def _parse_required_files(raw: object, *, label: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"{label}: required_files must be a list")
    return tuple(str(item) for item in raw)


def _merge_required_files(*groups: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    merged: list[str] = []
    for group in groups:
        for item in group:
            if item in seen:
                continue
            seen.add(item)
            merged.append(item)
    return tuple(merged)


def _variant_required_files(
    raw: dict[str, Any],
    *,
    runtime: str,
    layout: str,
    label: str,
) -> tuple[str, ...]:
    defaults = raw.get("defaults", {})
    default_required: tuple[str, ...] = ()
    if isinstance(defaults, dict):
        default_required = _parse_required_files(
            defaults.get("required_files"),
            label=f"{label} defaults",
        )
    runtime_map = raw.get("runtime_required_files", {})
    layout_map = raw.get("layout_required_files", {})
    layout_runtime_map = raw.get("layout_runtime_required_files", {})
    runtime_required: tuple[str, ...] = ()
    if isinstance(runtime_map, dict):
        runtime_required = _parse_required_files(
            runtime_map.get(runtime),
            label=f"{label} runtime_required_files[{runtime}]",
        )
    layout_required: tuple[str, ...] = ()
    if isinstance(layout_map, dict):
        layout_required = _parse_required_files(
            layout_map.get(layout),
            label=f"{label} layout_required_files[{layout}]",
        )
    layout_runtime_required: tuple[str, ...] = ()
    if isinstance(layout_runtime_map, dict):
        by_layout = layout_runtime_map.get(layout, {})
        if isinstance(by_layout, dict):
            layout_runtime_required = _parse_required_files(
                by_layout.get(runtime),
                label=f"{label} layout_runtime_required_files[{layout}][{runtime}]",
            )
    return _merge_required_files(
        default_required,
        runtime_required,
        layout_required,
        layout_runtime_required,
    )


def _load_variant_specs(raw: dict[str, Any], *, path: Path) -> tuple[ConformanceSpec, ...]:
    variants = raw.get("variants")
    if not isinstance(variants, list) or not variants:
        raise ValueError(f"{path}: variants must be a non-empty list when using variant mode")

    defaults = raw.get("defaults", {})
    default_inputs: dict[str, Any] = {}
    if isinstance(defaults, dict):
        inputs = defaults.get("inputs")
        if inputs is not None and not isinstance(inputs, dict):
            raise ValueError(f"{path}: defaults.inputs must be a mapping")
        if isinstance(inputs, dict):
            default_inputs = {str(k): v for k, v in inputs.items()}

    specs: list[ConformanceSpec] = []
    for index, entry in enumerate(variants):
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: variants[{index}] must be a mapping")
        runtime = str(entry.get("runtime", "")).strip()
        layout = str(entry.get("layout", "")).strip()
        if not runtime or not layout:
            raise ValueError(f"{path}: variants[{index}] requires runtime and layout")
        variant_id = str(entry.get("id", f"{runtime}-{layout}")).strip()
        variant_inputs = entry.get("inputs", {})
        if variant_inputs is not None and not isinstance(variant_inputs, dict):
            raise ValueError(f"{path}: variants[{index}].inputs must be a mapping")
        merged_inputs = {**default_inputs, **(variant_inputs or {})}
        merged_inputs.setdefault("runtime", runtime)
        merged_inputs.setdefault("layout", layout)
        explicit_required = entry.get("required_files")
        if explicit_required is not None:
            required_files = _parse_required_files(
                explicit_required,
                label=f"{path} variants[{index}]",
            )
        else:
            required_files = _variant_required_files(
                raw,
                runtime=runtime,
                layout=layout,
                label=str(path),
            )
        snapshot = bool(entry.get("snapshot", False))
        run_gates_raw = entry.get("run_gates")
        run_gates = snapshot if run_gates_raw is None else bool(run_gates_raw)
        slow_harness_raw = entry.get("slow_harness")
        slow_harness = snapshot if slow_harness_raw is None else bool(slow_harness_raw)
        specs.append(
            ConformanceSpec(
                inputs=merged_inputs,
                required_files=required_files,
                snapshot=snapshot,
                variant_id=variant_id,
                run_gates=run_gates,
                slow_harness=slow_harness,
            )
        )
    return tuple(specs)


def load_conformance_specs(blueprint_dir: Path) -> tuple[ConformanceSpec, ...]:
    path = blueprint_dir / CONFORMANCE_FILE
    if not path.is_file():
        return ()
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: must be a mapping")
    if "variants" in raw:
        return _load_variant_specs(raw, path=path)

    inputs = raw.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError(f"{path}: inputs must be a mapping")
    required = raw.get("required_files", ["repave.yaml", "README.md"])
    snapshot = bool(raw.get("snapshot", False))
    return (
        ConformanceSpec(
            inputs={str(k): v for k, v in inputs.items()},
            required_files=_parse_required_files(required, label=str(path)),
            snapshot=snapshot,
            variant_id="",
        ),
    )


def load_conformance_spec(blueprint_dir: Path) -> ConformanceSpec | None:
    specs = load_conformance_specs(blueprint_dir)
    if not specs:
        return None
    return specs[0]


def conformance_cases(
    repo_root: Path,
    *,
    slow: bool | None = None,
) -> tuple[tuple[str, str], ...]:
    cases: list[tuple[str, str]] = []
    for blueprint_dir in blueprint_dirs(repo_root):
        specs = load_conformance_specs(blueprint_dir)
        if not specs:
            continue
        for spec in specs:
            if slow is True and not spec.slow_harness:
                continue
            if slow is False and spec.slow_harness:
                continue
            cases.append((blueprint_dir.name, spec.variant_id))
    return tuple(cases)


def _is_text_artifact(path: Path) -> bool:
    if path.name.lower() == "dockerfile":
        return True
    return path.suffix.lower() in TEXT_SUFFIXES


def _should_skip_path(path: Path, *, manifest: bool = False) -> bool:
    skip = MANIFEST_SKIP_DIR_NAMES if manifest else SKIP_DIR_NAMES
    if any(part in skip for part in path.parts):
        return True
    if manifest and path.name in MANIFEST_SKIP_FILE_NAMES:
        return True
    return path.suffix == ".egg-info" or any(part.endswith(".egg-info") for part in path.parts)


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
    """Drop live version pins from hashes so release bumps do not rewrite manifests."""
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
    elif rel == "catalog-info.yaml" or rel.endswith("/catalog-info.yaml"):
        text = _CATALOG_REPAVE_VERSION_ANNOTATION.sub(
            rf"\1\2{_MANIFEST_ENGINE_NEUTRAL.decode()}\2",
            text,
        )
    return text.encode("utf-8")


def _file_manifest_digest(rel: str, data: bytes) -> str:
    normalized = _normalize_manifest_bytes(rel, data)
    return hashlib.sha256(normalized).hexdigest()


def build_file_manifest(
    output_dir: Path, *, artifact_type: str = "terraform-module"
) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or _should_skip_path(path, manifest=True):
            continue
        if path.stat().st_size == 0:
            continue
        rel = path.relative_to(output_dir).as_posix()
        if is_gate_artifact_path(rel, artifact_type=artifact_type):
            continue
        manifest[rel] = _file_manifest_digest(rel, path.read_bytes())
    return manifest


def compare_manifest(
    blueprint_dir: Path,
    output_dir: Path,
    *,
    variant_id: str = "",
    artifact_type: str = "terraform-module",
) -> str | None:
    manifest_file = manifest_path(blueprint_dir, variant_id=variant_id)
    if not manifest_file.is_file():
        return None
    expected = json.loads(manifest_file.read_text(encoding="utf-8"))
    if not isinstance(expected, dict):
        raise ValueError(f"{manifest_file}: must be a JSON object")
    actual = build_file_manifest(output_dir, artifact_type=artifact_type)
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


def write_manifest_snapshot(
    blueprint_dir: Path,
    output_dir: Path,
    *,
    variant_id: str = "",
    artifact_type: str = "terraform-module",
) -> None:
    manifest = build_file_manifest(output_dir, artifact_type=artifact_type)
    path = manifest_path(blueprint_dir, variant_id=variant_id)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


_CONFORMANCE_GENERATED_AT = "1970-01-01T00:00:00+00:00"


def _resolve_conformance_spec(
    blueprint_dir: Path,
    *,
    variant_id: str | None = None,
) -> ConformanceSpec:
    specs = load_conformance_specs(blueprint_dir)
    if not specs:
        raise FileNotFoundError(f"Missing {blueprint_dir / CONFORMANCE_FILE}")
    if variant_id is None:
        if len(specs) != 1:
            raise ValueError(
                f"{blueprint_dir.name}: multiple conformance variants; pass variant_id"
            )
        return specs[0]
    for spec in specs:
        if spec.variant_id == variant_id:
            return spec
    known = ", ".join(spec.variant_id for spec in specs)
    raise ValueError(f"{blueprint_dir.name}: unknown variant_id {variant_id!r} (known: {known})")


def run_blueprint_conformance(
    blueprint_dir: Path,
    *,
    repo_root: Path,
    output_config: OutputConfig,
    staging_root: Path,
    check_snapshot: bool = True,
    variant_id: str | None = None,
    render_only: bool = False,
) -> ConformanceResult:
    spec = _resolve_conformance_spec(blueprint_dir, variant_id=variant_id)

    blueprint = load_blueprint(blueprint_dir, repo_root=repo_root)
    values = {k: str(v) for k, v in spec.inputs.items()}

    staging_name = blueprint.name
    if spec.variant_id:
        staging_name = f"{blueprint.name}/{spec.variant_id}"

    staging_dir = staging_root / staging_name
    prev_generated_at = os.environ.get("REPAVE_PROVENANCE_GENERATED_AT")
    if spec.snapshot:
        os.environ["REPAVE_PROVENANCE_GENERATED_AT"] = _CONFORMANCE_GENERATED_AT
    gate_failures: tuple[str, ...]
    try:
        if spec.run_gates and not render_only:
            result = generate_from_blueprint(
                blueprint,
                values,
                output_config=output_config,
                dry_run=True,
                staging_root=staging_dir,
                repo_root=repo_root,
            )
            output_dir = result.render.output_dir
            gate_failures = tuple(
                f"{gate.name}: {gate.message}"
                for gate in result.gates
                if not gate.passed and not gate.skipped
            )
        else:
            gate_overrides = load_gate_overrides(repo_root)
            normalized = validate_inputs(
                blueprint,
                values,
                repo_root=repo_root,
                gate_overrides=gate_overrides,
            )
            staging_dir.mkdir(parents=True, exist_ok=True)
            render_result = render_blueprint(blueprint, normalized, staging_dir)
            output_dir = render_result.output_dir
            gate_failures = ()
    finally:
        if spec.snapshot:
            if prev_generated_at is None:
                os.environ.pop("REPAVE_PROVENANCE_GENERATED_AT", None)
            else:
                os.environ["REPAVE_PROVENANCE_GENERATED_AT"] = prev_generated_at
    missing = tuple(
        rel
        for rel in spec.required_files
        if not (output_dir / rel).is_file() or (output_dir / rel).stat().st_size == 0
    )
    placeholders = tuple(find_unresolved_placeholders(output_dir))
    manifest_diff = None
    if check_snapshot and spec.snapshot:
        manifest_diff = compare_manifest(
            blueprint_dir,
            output_dir,
            variant_id=spec.variant_id,
            artifact_type=blueprint.artifact_type,
        )

    return ConformanceResult(
        blueprint_name=blueprint.name,
        output_dir=output_dir,
        gate_failures=gate_failures,
        missing_files=missing,
        placeholder_hits=placeholders,
        manifest_diff=manifest_diff,
        variant_id=spec.variant_id,
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
        specs = load_conformance_specs(blueprint_dir)
        for spec in specs:
            if not spec.snapshot:
                continue
            outcome = run_blueprint_conformance(
                blueprint_dir,
                repo_root=repo_root,
                output_config=output_config,
                staging_root=staging_root,
                check_snapshot=False,
                variant_id=spec.variant_id or None,
            )
            blueprint = load_blueprint(blueprint_dir, repo_root=repo_root)
            write_manifest_snapshot(
                blueprint_dir,
                outcome.output_dir,
                variant_id=spec.variant_id,
                artifact_type=blueprint.artifact_type,
            )
            label = blueprint_dir.name
            if spec.variant_id:
                label = f"{label}/{spec.variant_id}"
            updated.append(label)
    return updated


def find_snapshot_manifest_drifts(
    repo_root: Path,
    *,
    modules_root: Path,
    staging_root: Path,
    render_only: bool = False,
) -> tuple[str, ...]:
    """Return human-readable drift labels for snapshot conformance manifests."""
    output_config = OutputConfig(github_org="conformance-check", modules_root=modules_root)
    drifts: list[str] = []
    for blueprint_dir in blueprint_dirs(repo_root):
        for spec in load_conformance_specs(blueprint_dir):
            if not spec.snapshot:
                continue
            outcome = run_blueprint_conformance(
                blueprint_dir,
                repo_root=repo_root,
                output_config=output_config,
                staging_root=staging_root,
                check_snapshot=True,
                variant_id=spec.variant_id or None,
                render_only=render_only,
            )
            if outcome.manifest_diff:
                label = blueprint_dir.name
                if spec.variant_id:
                    label = f"{label}/{spec.variant_id}"
                drifts.append(f"{label}: {outcome.manifest_diff}")
    return tuple(drifts)
