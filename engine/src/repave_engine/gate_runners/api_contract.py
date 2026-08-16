from __future__ import annotations

from pathlib import Path

import repave_engine.gate_runners as _gr
from repave_engine.gate_registry import GateContext, GateResult

_SPEC_CANDIDATES: tuple[str, ...] = (
    "openapi.yaml",
    "openapi.yml",
    "asyncapi.yaml",
    "asyncapi.yml",
    "spec.yaml",
)


def _is_asyncapi(path: Path) -> bool:
    name = path.name.lower()
    if name.startswith("asyncapi"):
        return True
    try:
        first = path.read_text(encoding="utf-8").lstrip()[:80].lower()
    except OSError:
        return False
    return first.startswith("asyncapi:")


def _resolve_spec_file(output_dir: Path, ctx: GateContext, gate: str) -> Path | None:
    raw = str(ctx.config(gate).get("spec_file", "")).strip()
    if raw:
        candidate = (output_dir / raw).resolve()
        return candidate if candidate.is_file() else None
    for name in _SPEC_CANDIDATES:
        candidate = output_dir / name
        if candidate.is_file():
            return candidate
    return None


def _resolve_baseline(output_dir: Path, ctx: GateContext, spec_file: Path) -> Path | None:
    raw = str(ctx.config("oasdiff").get("baseline", "")).strip()
    if raw:
        candidate = (output_dir / raw).resolve()
        return candidate if candidate.is_file() else None
    sibling = output_dir / "baseline" / spec_file.name
    if sibling.is_file():
        return sibling
    return None


def _rel(output_dir: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(output_dir.resolve()))
    except ValueError:
        return str(path)


def run_spectral(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "api-contract":
        return GateResult("spectral", True, True, "spectral gate not applicable; skipped")

    if not _gr.tool_available("spectral"):
        return GateResult("spectral", True, True, "spectral not installed; skipped")

    spec_file = _resolve_spec_file(output_dir, ctx, "spectral")
    if spec_file is None:
        return GateResult(
            "spectral",
            False,
            False,
            "API spec not found; set gate_config.spectral.spec_file "
            "(openapi.yaml, asyncapi.yaml, or spec.yaml)",
        )

    cmd = ["spectral", "lint", "--fail-severity=error", _rel(output_dir, spec_file)]
    ruleset = str(ctx.config("spectral").get("ruleset", ".spectral.yaml")).strip()
    ruleset_path = output_dir / ruleset
    if ruleset_path.is_file():
        cmd.extend(["--ruleset", ruleset])

    result = _gr.run_command(cmd, output_dir)
    return _gr.gate_result_from_command(
        "spectral",
        result,
        ok_message="spectral lint passed",
        fail_message="spectral lint failed",
    )


def run_oasdiff(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "api-contract":
        return GateResult("oasdiff", True, True, "oasdiff gate not applicable; skipped")

    spec_file = _resolve_spec_file(output_dir, ctx, "oasdiff")
    if spec_file is None:
        return GateResult(
            "oasdiff",
            False,
            False,
            "API spec not found; set gate_config.oasdiff.spec_file (openapi.yaml or spec.yaml)",
        )
    if _is_asyncapi(spec_file):
        return GateResult(
            "oasdiff",
            True,
            True,
            "oasdiff applies to OpenAPI specs only; skipped",
        )

    if not _gr.tool_available("oasdiff"):
        return GateResult("oasdiff", True, True, "oasdiff not installed; skipped")

    baseline = _resolve_baseline(output_dir, ctx, spec_file)
    if baseline is None:
        return GateResult(
            "oasdiff",
            False,
            False,
            "baseline spec not found; set gate_config.oasdiff.baseline "
            f"(expected baseline/{spec_file.name})",
        )

    result = _gr.run_command(
        [
            "oasdiff",
            "breaking",
            _rel(output_dir, baseline),
            _rel(output_dir, spec_file),
        ],
        output_dir,
    )
    return _gr.gate_result_from_command(
        "oasdiff",
        result,
        ok_message="oasdiff found no breaking changes",
        fail_message="oasdiff reported breaking changes versus the baseline spec",
    )
