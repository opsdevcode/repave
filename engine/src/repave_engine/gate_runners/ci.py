from __future__ import annotations

from pathlib import Path

import repave_engine.gate_runners as _gr
from repave_engine.gate_registry import GateContext, GateResult

_WORKFLOW_ARTIFACT_TYPES = frozenset({"helm-chart", "app-service", "gitops-deployment"})


def _workflow_paths(ctx: GateContext, output_dir: Path) -> list[Path]:
    raw = ctx.config("actionlint")
    configured = raw.get("paths")
    if isinstance(configured, list) and configured:
        patterns = [str(item) for item in configured]
    else:
        patterns = [".github/workflows/*.yml", ".github/workflows/*.yaml"]
    targets: list[Path] = []
    for pattern in patterns:
        targets.extend(sorted(output_dir.glob(pattern)))
    return targets


def run_actionlint(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type not in _WORKFLOW_ARTIFACT_TYPES:
        return GateResult("actionlint", True, True, "actionlint gate not applicable; skipped")

    if not _gr.tool_available("actionlint"):
        return GateResult("actionlint", True, True, "actionlint not installed; skipped")

    targets = _workflow_paths(ctx, output_dir)
    if not targets:
        return GateResult("actionlint", True, True, "no workflow files for actionlint; skipped")

    result = _gr.run_command(
        ["actionlint", *[str(path.relative_to(output_dir)) for path in targets]],
        output_dir,
    )
    if result.returncode == 0:
        return GateResult(
            "actionlint",
            True,
            False,
            f"actionlint passed for {len(targets)} workflow file(s)",
        )
    detail = result.stderr.strip() or result.stdout.strip() or "actionlint failed"
    return GateResult("actionlint", False, False, detail)
