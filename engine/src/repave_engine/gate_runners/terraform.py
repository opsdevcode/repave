from __future__ import annotations

from pathlib import Path

import repave_engine.gate_runners as _gr
from repave_engine.blueprint import TflintGateConfig
from repave_engine.gate_registry import GateContext, GateResult
from repave_engine.gate_runners._core import _toolchain_skip, tflint_config_args


def run_terraform_fmt(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if not _gr.terraform_usable(output_dir):
        return _toolchain_skip(ctx, "terraform-fmt", "terraform not available")

    result = _gr.run_command(["terraform", "fmt", "-check", "-recursive"], output_dir)
    if result.returncode == 0:
        return GateResult("terraform-fmt", True, False, "terraform fmt check passed")
    return GateResult(
        "terraform-fmt",
        False,
        False,
        result.stderr.strip() or result.stdout.strip() or "terraform fmt check failed",
    )


def run_terraform_validate(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if not _gr.terraform_usable(output_dir):
        return _toolchain_skip(ctx, "terraform-validate", "terraform not available")

    init = _gr.run_command(["terraform", "init", "-backend=false"], output_dir)
    if init.returncode != 0:
        return GateResult(
            "terraform-validate",
            False,
            False,
            init.stderr.strip() or init.stdout.strip() or "terraform init failed",
        )

    validate = _gr.run_command(["terraform", "validate"], output_dir)
    if validate.returncode == 0:
        return GateResult("terraform-validate", True, False, "terraform validate passed")
    return GateResult(
        "terraform-validate",
        False,
        False,
        validate.stderr.strip() or validate.stdout.strip() or "terraform validate failed",
    )


def run_terraform_test(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if not _gr.terraform_usable(output_dir):
        return _toolchain_skip(ctx, "terraform-test", "terraform not available")

    raw = ctx.config("terraform-test")
    test_directory = str(raw.get("test_directory", "tests"))
    test_dir = output_dir / test_directory
    if not test_dir.is_dir() or not any(test_dir.rglob("*.tftest.hcl")):
        return _toolchain_skip(ctx, "terraform-test", "no terraform tests", benign=True)

    init = _gr.run_command(["terraform", "init", "-backend=false"], output_dir)
    if init.returncode != 0:
        return GateResult(
            "terraform-test",
            False,
            False,
            init.stderr.strip() or init.stdout.strip() or "terraform init failed",
        )

    result = _gr.run_command(["terraform", "test"], output_dir)
    if result.returncode == 0:
        return GateResult("terraform-test", True, False, "terraform test passed")
    return GateResult(
        "terraform-test",
        False,
        False,
        result.stderr.strip() or result.stdout.strip() or "terraform test failed",
    )


def run_tflint(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if not _gr.tool_available("tflint"):
        return _toolchain_skip(ctx, "tflint", "tflint not installed")

    config = ctx.blueprint.tflint_gate if ctx.blueprint is not None else TflintGateConfig()
    config_args = tflint_config_args(output_dir, config)

    result = _gr.run_command(["tflint", "--init", *config_args], output_dir)
    if result.returncode != 0:
        return GateResult("tflint", False, False, result.stderr.strip() or "tflint init failed")

    result = _gr.run_command(["tflint", *config_args], output_dir)
    if result.returncode == 0:
        return GateResult("tflint", True, False, "tflint passed")
    return GateResult("tflint", False, False, result.stderr.strip() or "tflint failed")


def _terraform_plan_json(output_dir: Path, plan_subdir: str) -> Path | None:
    if not _gr.terraform_usable(output_dir):
        return None
    work = output_dir / plan_subdir
    work.mkdir(parents=True, exist_ok=True)
    plan_binary = work / "tfplan"
    plan_json = work / "tfplan.json"

    init = _gr.run_command(["terraform", "init", "-backend=false", "-input=false"], output_dir)
    if init.returncode != 0:
        return None

    plan = _gr.run_command(
        [
            "terraform",
            "plan",
            "-out",
            str(plan_binary.relative_to(output_dir)),
            "-input=false",
            "-lock=false",
        ],
        output_dir,
    )
    if plan.returncode != 0:
        return None

    show = _gr.run_command(
        ["terraform", "show", "-json", str(plan_binary.relative_to(output_dir))],
        output_dir,
    )
    if show.returncode != 0:
        return None
    plan_json.write_text(show.stdout, encoding="utf-8")
    return plan_json
