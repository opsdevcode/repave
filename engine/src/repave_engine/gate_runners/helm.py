from __future__ import annotations

from pathlib import Path

import repave_engine.gate_runners as _gr
from repave_engine.gate_registry import GateContext, GateResult


def _helm_chart_dir(output_dir: Path, ctx: GateContext, gate: str) -> Path:
    raw = ctx.config(gate)
    rel = str(raw.get("chart_path", ".")).strip() or "."
    return (output_dir / rel).resolve()


def run_helm_lint(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "helm-chart":
        return GateResult("helm-lint", True, True, "helm-lint gate not applicable; skipped")

    if not _gr.tool_available("helm"):
        return GateResult("helm-lint", True, True, "helm not installed; skipped")

    chart_dir = _helm_chart_dir(output_dir, ctx, "helm-lint")
    chart_yaml = chart_dir / "Chart.yaml"
    if not chart_yaml.is_file():
        return GateResult("helm-lint", True, True, "no Chart.yaml found; skipped")

    result = _gr.run_command(
        ["helm", "lint", str(chart_dir.resolve().relative_to(output_dir.resolve()))],
        output_dir.resolve(),
    )
    if result.returncode == 0:
        return GateResult("helm-lint", True, False, "helm lint passed")
    detail = result.stderr.strip() or result.stdout.strip() or "helm lint failed"
    return GateResult("helm-lint", False, False, detail)


def run_helm_template(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "helm-chart":
        return GateResult("helm-template", True, True, "helm-template gate not applicable; skipped")

    if not _gr.tool_available("helm"):
        return GateResult("helm-template", True, True, "helm not installed; skipped")

    chart_dir = _helm_chart_dir(output_dir, ctx, "helm-template")
    if not (chart_dir / "Chart.yaml").is_file():
        return GateResult("helm-template", True, True, "no Chart.yaml found; skipped")

    cfg = ctx.config("helm-template")
    release = str(cfg.get("release_name", "repave-test"))
    resolved_out = output_dir.resolve()
    resolved_chart = chart_dir.resolve()
    result = _gr.run_command(
        [
            "helm",
            "template",
            release,
            str(resolved_chart.relative_to(resolved_out)),
        ],
        resolved_out,
    )
    if result.returncode == 0:
        return GateResult("helm-template", True, False, "helm template passed")
    detail = result.stderr.strip() or result.stdout.strip() or "helm template failed"
    return GateResult("helm-template", False, False, detail)
