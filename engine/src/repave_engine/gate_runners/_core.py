from __future__ import annotations

import os
import subprocess
from pathlib import Path

from repave_engine.blueprint import CheckovGateConfig, TflintGateConfig
from repave_engine.gate_registry import GateContext, GateResult
from repave_engine.gate_toolchain import (
    checkov_argv,
    ensure_gate_path,
    resolve_tool,
    subprocess_cwd,
)
from repave_engine.subprocess_run import (
    SUBPROCESS_TIMEOUT_RETURN_CODE,
    command_timed_out,
    run_subprocess,
    subprocess_timeout_seconds,
)


def run_command(
    cmd: list[str],
    cwd: Path,
    *,
    extra_env: dict[str, str] | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    ensure_gate_path()
    if cmd:
        resolved = resolve_tool(cmd[0])
        if resolved:
            cmd = [resolved, *cmd[1:]]
    env = os.environ.copy()
    if extra_env is not None:
        env.update(extra_env)
    run_cwd = subprocess_cwd(cwd)
    try:
        return run_subprocess(
            cmd,
            cwd=run_cwd,
            env=env,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode()
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode()
        budget = exc.timeout or timeout or subprocess_timeout_seconds()
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=SUBPROCESS_TIMEOUT_RETURN_CODE,
            stdout=stdout,
            stderr=f"{stderr}\ncommand timed out after {budget}s".strip(),
        )


def gate_timeout_seconds(ctx: GateContext, gate_name: str) -> int | None:
    raw = ctx.config(gate_name).get("timeout_seconds")
    if raw is None:
        return None
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return None


def gate_result_from_command(
    gate_name: str,
    result: subprocess.CompletedProcess[str],
    *,
    ok_message: str,
    fail_message: str,
) -> GateResult:
    if result.returncode == 0:
        return GateResult(gate_name, True, False, ok_message)
    if command_timed_out(result):
        detail = (result.stderr or result.stdout or "").strip()
        return GateResult(gate_name, False, False, detail or fail_message)
    detail = result.stderr.strip() or result.stdout.strip() or fail_message
    return GateResult(gate_name, False, False, detail)


def terraform_usable(output_dir: Path) -> bool:
    from repave_engine.gate_toolchain import terraform_cli_ready

    if not terraform_cli_ready():
        return False
    run_cwd = subprocess_cwd(output_dir)
    terraform_bin = resolve_tool("terraform")
    if not terraform_bin:
        return False
    result = run_subprocess(
        [terraform_bin, "version"],
        cwd=run_cwd,
        check=False,
        env=os.environ.copy(),
        timeout=15,
    )
    return result.returncode == 0


_DRY_RUN_TOOLCHAIN_HINT = (
    " Dry-run preview runs all blueprint gates; install the tool "
    "(see deploy/local) or use Docker compose for a full toolchain."
)


def _toolchain_skip(
    ctx: GateContext,
    gate_name: str,
    reason: str,
    *,
    benign: bool = False,
) -> GateResult:
    """SKIP when apply mode tolerates missing tools; FAIL on dry-run (require_run)."""
    if ctx.require_run and not benign:
        detail = reason.replace("; skipped", "").strip()
        if not detail.endswith("."):
            detail = f"{detail}."
        return GateResult(gate_name, False, False, f"{detail}{_DRY_RUN_TOOLCHAIN_HINT}")
    message = reason if reason.endswith("; skipped") else f"{reason}; skipped"
    return GateResult(gate_name, True, True, message)


def _checkov_command(cmd: list[str]) -> list[str]:
    prefix = checkov_argv()
    if prefix is None or not cmd or cmd[0] != "checkov":
        return cmd
    if len(prefix) == 1:
        return [prefix[0], *cmd[1:]]
    return [*prefix, *cmd[1:]]


def tflint_config_args(output_dir: Path, config: TflintGateConfig) -> list[str]:
    config_path = output_dir / config.config_file
    if config_path.is_file():
        return ["--config", config.config_file]
    return []


def build_checkov_command(
    output_dir: Path,
    config: CheckovGateConfig,
    *,
    extra_skip_checks: tuple[str, ...] = (),
) -> list[str]:
    scan_root = output_dir / config.scan_dir if config.scan_dir else output_dir
    cmd = ["checkov", "-d", str(scan_root)]
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
