from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import jsonschema

from repave_engine.blueprint import CheckovGateConfig, TflintGateConfig, _find_repo_root
from repave_engine.gate_registry import GateContext, GateResult
from repave_engine.provenance import validate_provenance_file


def tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def run_command(
    cmd: list[str],
    cwd: Path,
    *,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = None
    if extra_env is not None:
        import os

        env = os.environ.copy()
        env.update(extra_env)
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def terraform_usable(output_dir: Path) -> bool:
    if not tool_available("terraform"):
        return False
    result = run_command(["terraform", "version"], output_dir)
    return result.returncode == 0


def tflint_config_args(output_dir: Path, config: TflintGateConfig) -> list[str]:
    config_path = output_dir / config.config_file
    if config_path.is_file():
        return ["--config", config.config_file]
    return []


def run_terraform_fmt(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if not terraform_usable(output_dir):
        return GateResult("terraform-fmt", True, True, "terraform not available; skipped")

    result = run_command(["terraform", "fmt", "-check", "-recursive"], output_dir)
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
    if not terraform_usable(output_dir):
        return GateResult("terraform-validate", True, True, "terraform not available; skipped")

    init = run_command(["terraform", "init", "-backend=false"], output_dir)
    if init.returncode != 0:
        return GateResult(
            "terraform-validate",
            False,
            False,
            init.stderr.strip() or init.stdout.strip() or "terraform init failed",
        )

    validate = run_command(["terraform", "validate"], output_dir)
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
    if not terraform_usable(output_dir):
        return GateResult("terraform-test", True, True, "terraform not available; skipped")

    raw = ctx.config("terraform-test")
    test_directory = str(raw.get("test_directory", "tests"))
    test_dir = output_dir / test_directory
    if not test_dir.is_dir() or not any(test_dir.rglob("*.tftest.hcl")):
        return GateResult("terraform-test", True, True, "no terraform tests; skipped")

    init = run_command(["terraform", "init", "-backend=false"], output_dir)
    if init.returncode != 0:
        return GateResult(
            "terraform-test",
            False,
            False,
            init.stderr.strip() or init.stdout.strip() or "terraform init failed",
        )

    result = run_command(["terraform", "test"], output_dir)
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
    if not tool_available("tflint"):
        return GateResult("tflint", True, True, "tflint not installed; skipped")

    config = ctx.blueprint.tflint_gate if ctx.blueprint is not None else TflintGateConfig()
    config_args = tflint_config_args(output_dir, config)

    result = run_command(["tflint", "--init", *config_args], output_dir)
    if result.returncode != 0:
        return GateResult("tflint", False, False, result.stderr.strip() or "tflint init failed")

    result = run_command(["tflint", *config_args], output_dir)
    if result.returncode == 0:
        return GateResult("tflint", True, False, "tflint passed")
    return GateResult("tflint", False, False, result.stderr.strip() or "tflint failed")


def build_checkov_command(
    output_dir: Path,
    config: CheckovGateConfig,
    *,
    extra_skip_checks: tuple[str, ...] = (),
) -> list[str]:
    cmd = ["checkov", "-d", str(output_dir)]
    config_path = output_dir / config.config_file
    if config_path.is_file():
        cmd.extend(["--config-file", str(config_path)])

    checks_dir = output_dir / config.external_checks_dir
    if checks_dir.is_dir():
        cmd.extend(["--external-checks-dir", str(checks_dir)])

    skip_checks = {*config.skip_checks, *extra_skip_checks}
    for check_id in sorted(skip_checks):
        cmd.extend(["--skip-check", check_id])

    if config.soft_fail:
        cmd.append("--soft-fail")
    return cmd


def build_secrets_scan_command(output_dir: Path) -> list[str]:
    return [
        "checkov",
        "-d",
        str(output_dir),
        "--framework",
        "secrets",
        "--enable-secret-scan-all-files",
    ]


def run_secrets(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if not tool_available("checkov"):
        return GateResult("secrets", True, True, "checkov not installed; skipped")

    cmd = build_secrets_scan_command(output_dir)
    result = run_command(cmd, output_dir)
    if result.returncode == 0:
        return GateResult("secrets", True, False, "secrets scan passed")
    return GateResult("secrets", False, False, result.stderr.strip() or "secrets scan failed")


def run_checkov(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if not tool_available("checkov"):
        return GateResult("checkov", True, True, "checkov not installed; skipped")

    config = ctx.blueprint.checkov_gate if ctx.blueprint is not None else CheckovGateConfig()
    extra_skip = ctx.gate_overrides.checkov_skip_checks if ctx.gate_overrides is not None else ()
    cmd = build_checkov_command(output_dir, config, extra_skip_checks=extra_skip)
    result = run_command(
        cmd,
        output_dir,
        extra_env={"REPAVE_CHECKOV_SCAN_ROOT": str(output_dir.resolve())},
    )
    if result.returncode == 0:
        return GateResult("checkov", True, False, "checkov passed")
    return GateResult("checkov", False, False, result.stderr.strip() or "checkov failed")


def run_docs_drift(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    readme = output_dir / "README.md"
    if not readme.exists():
        return GateResult("docs-drift", False, False, "README.md missing")

    content = readme.read_text(encoding="utf-8")
    placeholders = [match for match in re.findall(r"\{\{[^}]+\}\}", content)]
    if placeholders:
        return GateResult(
            "docs-drift",
            False,
            False,
            f"README contains unresolved template placeholders: {', '.join(placeholders)}",
        )

    if "## Usage" not in content:
        return GateResult("docs-drift", False, False, "README missing Usage section")

    return GateResult("docs-drift", True, False, "README present and rendered")


def run_provenance_drift(ctx: GateContext) -> GateResult:
    blueprint = ctx.blueprint
    if blueprint is None or not blueprint.provenance_file:
        return GateResult("provenance-drift", True, True, "provenance not configured; skipped")

    provenance_path = ctx.output_dir / blueprint.provenance_file
    try:
        repo_root = _find_repo_root(blueprint.path)
        validate_provenance_file(provenance_path, repo_root)
    except FileNotFoundError as exc:
        return GateResult("provenance-drift", False, False, str(exc))
    except jsonschema.ValidationError as exc:
        return GateResult(
            "provenance-drift",
            False,
            False,
            f"Invalid provenance file: {exc.message}",
        )
    except Exception as exc:
        return GateResult("provenance-drift", False, False, str(exc))

    return GateResult("provenance-drift", True, False, "Provenance file present and valid")
