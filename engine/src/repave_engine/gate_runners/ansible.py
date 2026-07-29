from __future__ import annotations

from pathlib import Path

import repave_engine.gate_runners as _gr
from repave_engine.gate_registry import GateContext, GateResult


def run_ansible_lint(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if not _gr.tool_available("ansible-lint"):
        return GateResult("ansible-lint", True, True, "ansible-lint not installed; skipped")

    result = _gr.run_command(["ansible-lint"], output_dir)
    if result.returncode == 0:
        return GateResult("ansible-lint", True, False, "ansible-lint passed")
    return GateResult(
        "ansible-lint",
        False,
        False,
        result.stderr.strip() or result.stdout.strip() or "ansible-lint failed",
    )


def _syntax_check_playbook(output_dir: Path) -> Path | None:
    candidates = (
        output_dir / "site.yml",
        output_dir / "playbooks" / "site.yml",
        output_dir / "molecule" / "default" / "converge.yml",
        output_dir / "molecule" / "default" / "playbook.yml",
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def run_ansible_syntax_check(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if not _gr.tool_available("ansible-playbook"):
        return GateResult(
            "ansible-syntax-check",
            True,
            True,
            "ansible-playbook not installed; skipped",
        )

    playbook = _syntax_check_playbook(output_dir)
    if playbook is None:
        return GateResult(
            "ansible-syntax-check",
            True,
            True,
            "no playbook found for syntax check; skipped",
        )

    result = _gr.run_command(
        ["ansible-playbook", "--syntax-check", str(playbook.relative_to(output_dir))],
        output_dir,
    )
    if result.returncode == 0:
        return GateResult("ansible-syntax-check", True, False, "ansible syntax check passed")
    return GateResult(
        "ansible-syntax-check",
        False,
        False,
        result.stderr.strip() or result.stdout.strip() or "ansible syntax check failed",
    )


def run_molecule(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    molecule_config = output_dir / "molecule" / "default" / "molecule.yml"
    if not molecule_config.is_file():
        return GateResult("molecule", True, True, "no molecule scenario; skipped")

    if not _gr.tool_available("molecule"):
        return GateResult("molecule", True, True, "molecule not installed; skipped")

    result = _gr.run_command(["molecule", "test"], output_dir)
    if result.returncode == 0:
        return GateResult("molecule", True, False, "molecule test passed")
    return GateResult(
        "molecule",
        False,
        False,
        result.stderr.strip() or result.stdout.strip() or "molecule test failed",
    )
