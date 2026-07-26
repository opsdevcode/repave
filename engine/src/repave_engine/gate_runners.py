from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import httpx
import jsonschema

from repave_engine.blueprint import CheckovGateConfig, TflintGateConfig, _find_repo_root
from repave_engine.gate_registry import GateContext, GateResult
from repave_engine.policy_selection import load_policy_selection_file
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
    extra_skip: tuple[str, ...] = ()
    if ctx.gate_overrides is not None:
        extra_skip = (*extra_skip, *ctx.gate_overrides.checkov_skip_checks)
    selection = load_policy_selection_file(output_dir)
    if selection is not None:
        extra_skip = (*extra_skip, *selection.checkov_skip_checks)
    cmd = build_checkov_command(output_dir, config, extra_skip_checks=extra_skip)
    scan_root = output_dir / config.scan_dir if config.scan_dir else output_dir
    result = run_command(
        cmd,
        output_dir,
        extra_env={"REPAVE_CHECKOV_SCAN_ROOT": str(scan_root.resolve())},
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

    if "## Provenance" not in content:
        return GateResult("docs-drift", False, False, "README missing Provenance section")

    if "repave.yaml" not in content:
        return GateResult("docs-drift", False, False, "README must reference repave.yaml")

    return GateResult("docs-drift", True, False, "README present and rendered")


def run_provenance_drift(ctx: GateContext) -> GateResult:
    blueprint = ctx.blueprint
    if blueprint is None or not blueprint.provenance_file:
        return GateResult("provenance-drift", True, True, "provenance not configured; skipped")

    provenance_path = ctx.output_dir / blueprint.provenance_file
    try:
        try:
            repo_root = _find_repo_root(blueprint.path)
        except FileNotFoundError:
            repo_root = None
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


def _yamllint_config_args(output_dir: Path) -> list[str]:
    config_path = output_dir / ".yamllint"
    if config_path.is_file():
        return ["-c", ".yamllint"]
    return []


def _yamllint_paths(ctx: GateContext) -> list[str]:
    raw = ctx.config("yamllint")
    paths = raw.get("paths")
    if isinstance(paths, list) and paths:
        return [str(path).strip() for path in paths if str(path).strip()]
    if ctx.blueprint is not None and ctx.blueprint.artifact_type == "helm-chart":
        return ["Chart.yaml", "values.yaml"]
    return ["."]


def run_yamllint(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if not tool_available("yamllint"):
        return GateResult("yamllint", True, True, "yamllint not installed; skipped")

    config_args = _yamllint_config_args(output_dir)
    targets = _yamllint_paths(ctx)
    result = run_command(["yamllint", *config_args, *targets], output_dir)
    if result.returncode == 0:
        return GateResult("yamllint", True, False, "yamllint passed")
    return GateResult(
        "yamllint",
        False,
        False,
        result.stderr.strip() or result.stdout.strip() or "yamllint failed",
    )


def _promtool_rule_files(output_dir: Path, ctx: GateContext) -> list[Path]:
    raw = ctx.config("promtool")
    glob_pattern = str(raw.get("rules_glob", "prometheus/rules/*.y*ml"))
    return sorted(output_dir.glob(glob_pattern))


def run_promtool(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "observability":
        return GateResult("promtool", True, True, "promtool gate not applicable; skipped")

    if not tool_available("promtool"):
        return GateResult("promtool", True, True, "promtool not installed; skipped")

    rule_files = _promtool_rule_files(output_dir, ctx)
    if not rule_files:
        return GateResult(
            "promtool",
            True,
            True,
            "no Prometheus rule files found; skipped",
        )

    errors: list[str] = []
    for path in rule_files:
        result = run_command(
            ["promtool", "check", "rules", str(path.relative_to(output_dir))], output_dir
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "check failed"
            errors.append(f"{path.name}: {detail}")
    if errors:
        return GateResult("promtool", False, False, "; ".join(errors))
    return GateResult("promtool", True, False, f"promtool validated {len(rule_files)} rule file(s)")


def _amtool_config_files(output_dir: Path, ctx: GateContext) -> list[Path]:
    raw = ctx.config("amtool")
    glob_pattern = str(raw.get("config_glob", "prometheus/alertmanager/*.y*ml"))
    return sorted(output_dir.glob(glob_pattern))


def run_amtool(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "observability":
        return GateResult("amtool", True, True, "amtool gate not applicable; skipped")

    if not tool_available("amtool"):
        return GateResult("amtool", True, True, "amtool not installed; skipped")

    config_files = _amtool_config_files(output_dir, ctx)
    if not config_files:
        return GateResult(
            "amtool",
            True,
            True,
            "no Alertmanager config files found; skipped",
        )

    errors: list[str] = []
    for path in config_files:
        result = run_command(
            ["amtool", "check-config", str(path.relative_to(output_dir))],
            output_dir,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "check failed"
            errors.append(f"{path.name}: {detail}")
    if errors:
        return GateResult("amtool", False, False, "; ".join(errors))
    return GateResult(
        "amtool",
        True,
        False,
        f"amtool validated {len(config_files)} Alertmanager config file(s)",
    )


def _grafana_dashboard_files(output_dir: Path, ctx: GateContext) -> list[Path]:
    raw = ctx.config("grafana-dashboard")
    glob_pattern = str(raw.get("dashboards_glob", "grafana/dashboards/*.json"))
    return sorted(output_dir.glob(glob_pattern))


def _validate_dashboard_tags(path: Path, tags: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(tags, list):
        if tags is not None:
            errors.append(f"{path.name}: tags must be a list")
        return errors
    tag_strings = {str(item) for item in tags}
    for prefix in ("service:", "team:", "org:", "env:", "managed-by:"):
        if not any(item.startswith(prefix) for item in tag_strings):
            errors.append(f"{path.name}: tags must include {prefix}{{value}}")
    return errors


def _validate_grafana_dashboard(path: Path, payload: dict[str, object]) -> list[str]:
    errors: list[str] = []
    for key in ("title", "uid", "tags", "schemaVersion"):
        if key not in payload:
            errors.append(f"{path.name}: missing {key!r}")
    errors.extend(_validate_dashboard_tags(path, payload.get("tags")))
    return errors


def run_grafana_dashboard(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "observability":
        return GateResult(
            "grafana-dashboard",
            True,
            True,
            "grafana-dashboard gate not applicable; skipped",
        )

    dashboard_files = _grafana_dashboard_files(output_dir, ctx)
    if not dashboard_files:
        return GateResult(
            "grafana-dashboard",
            True,
            True,
            "no Grafana dashboard JSON found; skipped",
        )

    errors: list[str] = []
    for path in dashboard_files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}: invalid JSON ({exc.msg})")
            continue
        if not isinstance(payload, dict):
            errors.append(f"{path.name}: dashboard root must be a JSON object")
            continue
        errors.extend(_validate_grafana_dashboard(path, payload))

    if errors:
        return GateResult("grafana-dashboard", False, False, "; ".join(errors))
    return GateResult(
        "grafana-dashboard",
        True,
        False,
        f"validated {len(dashboard_files)} Grafana dashboard(s)",
    )


def _datadog_dashboard_files(output_dir: Path, ctx: GateContext) -> list[Path]:
    raw = ctx.config("datadog-dashboard")
    glob_pattern = str(raw.get("dashboards_glob", "datadog/dashboards/*.json"))
    return sorted(output_dir.glob(glob_pattern))


def _validate_datadog_dashboard(path: Path, payload: dict[str, object]) -> list[str]:
    errors: list[str] = []
    for key in ("title", "layout_type", "widgets", "tags"):
        if key not in payload:
            errors.append(f"{path.name}: missing {key!r}")
    if payload.get("layout_type") not in (None, "ordered", "free"):
        errors.append(f"{path.name}: layout_type must be 'ordered' or 'free'")
    widgets = payload.get("widgets")
    if widgets is not None and not isinstance(widgets, list):
        errors.append(f"{path.name}: widgets must be a list")
    elif isinstance(widgets, list) and not widgets:
        errors.append(f"{path.name}: widgets must not be empty")
    errors.extend(_validate_dashboard_tags(path, payload.get("tags")))
    return errors


def run_datadog_dashboard(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "observability":
        return GateResult(
            "datadog-dashboard",
            True,
            True,
            "datadog-dashboard gate not applicable; skipped",
        )

    dashboard_files = _datadog_dashboard_files(output_dir, ctx)
    if not dashboard_files:
        return GateResult(
            "datadog-dashboard",
            True,
            True,
            "no Datadog dashboard JSON found; skipped",
        )

    errors: list[str] = []
    for path in dashboard_files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}: invalid JSON ({exc.msg})")
            continue
        if not isinstance(payload, dict):
            errors.append(f"{path.name}: dashboard root must be a JSON object")
            continue
        errors.extend(_validate_datadog_dashboard(path, payload))

    if errors:
        return GateResult("datadog-dashboard", False, False, "; ".join(errors))
    return GateResult(
        "datadog-dashboard",
        True,
        False,
        f"validated {len(dashboard_files)} Datadog dashboard(s)",
    )


def _datadog_monitor_files(output_dir: Path, ctx: GateContext) -> list[Path]:
    raw = ctx.config("datadog-monitor")
    glob_pattern = str(raw.get("monitors_glob", "datadog/monitors/*.json"))
    return sorted(output_dir.glob(glob_pattern))


def _monitor_payloads(path: Path, data: object) -> list[dict[str, object]]:
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _validate_datadog_monitor(path: Path, payload: dict[str, object]) -> list[str]:
    errors: list[str] = []
    for key in ("name", "type", "query", "message"):
        if key not in payload:
            errors.append(f"{path.name}: monitor missing {key!r}")
    tags = payload.get("tags")
    if tags is not None:
        errors.extend(_validate_dashboard_tags(path, tags))
    return errors


def run_datadog_monitor(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "observability":
        return GateResult(
            "datadog-monitor",
            True,
            True,
            "datadog-monitor gate not applicable; skipped",
        )

    monitor_files = _datadog_monitor_files(output_dir, ctx)
    if not monitor_files:
        return GateResult(
            "datadog-monitor",
            True,
            True,
            "no Datadog monitor JSON found; skipped",
        )

    errors: list[str] = []
    monitor_count = 0
    for path in monitor_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}: invalid JSON ({exc.msg})")
            continue
        payloads = _monitor_payloads(path, data)
        if not payloads:
            errors.append(f"{path.name}: expected a monitor object or array of monitors")
            continue
        for payload in payloads:
            monitor_count += 1
            errors.extend(_validate_datadog_monitor(path, payload))

    if errors:
        return GateResult("datadog-monitor", False, False, "; ".join(errors))
    return GateResult(
        "datadog-monitor",
        True,
        False,
        f"validated {monitor_count} Datadog monitor(s)",
    )


def _datadog_api_credentials() -> tuple[str, str, str] | None:
    api_key = os.environ.get("DD_API_KEY", "").strip()
    app_key = os.environ.get("DD_APP_KEY", "").strip()
    if not api_key or not app_key:
        return None
    site = os.environ.get("DD_SITE", "datadoghq.com").strip() or "datadoghq.com"
    return api_key, app_key, site


def _datadog_api_post(
    site: str,
    path: str,
    *,
    api_key: str,
    app_key: str,
    payload: object,
) -> tuple[int, str]:
    url = f"https://api.{site}{path}"
    headers = {
        "DD-API-KEY": api_key,
        "DD-APPLICATION-KEY": app_key,
        "Content-Type": "application/json",
    }
    response = httpx.post(url, headers=headers, json=payload, timeout=30.0)
    detail = response.text.strip()
    if len(detail) > 500:
        detail = detail[:500] + "..."
    return response.status_code, detail


def run_datadog_api_validate(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "observability":
        return GateResult(
            "datadog-api-validate",
            True,
            True,
            "datadog-api-validate gate not applicable; skipped",
        )

    creds = _datadog_api_credentials()
    if creds is None:
        return GateResult(
            "datadog-api-validate",
            True,
            True,
            "DD_API_KEY/DD_APP_KEY not set; skipped",
        )

    api_key, app_key, site = creds
    monitor_files = _datadog_monitor_files(output_dir, ctx)
    dashboard_files = _datadog_dashboard_files(output_dir, ctx)
    if not monitor_files and not dashboard_files:
        return GateResult(
            "datadog-api-validate",
            True,
            True,
            "no Datadog JSON to validate; skipped",
        )

    errors: list[str] = []
    validated = 0
    for path in monitor_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}: invalid JSON ({exc.msg})")
            continue
        for payload in _monitor_payloads(path, data):
            status, detail = _datadog_api_post(
                site,
                "/api/v1/monitor/validate",
                api_key=api_key,
                app_key=app_key,
                payload=payload,
            )
            validated += 1
            if status >= 400:
                errors.append(f"{path.name}: monitor validate HTTP {status}: {detail}")

    for path in dashboard_files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}: invalid JSON ({exc.msg})")
            continue
        if not isinstance(payload, dict):
            errors.append(f"{path.name}: dashboard root must be a JSON object")
            continue
        status, detail = _datadog_api_post(
            site,
            "/api/v1/dashboard/validate",
            api_key=api_key,
            app_key=app_key,
            payload=payload,
        )
        validated += 1
        if status >= 400:
            errors.append(f"{path.name}: dashboard validate HTTP {status}: {detail}")

    if errors:
        return GateResult("datadog-api-validate", False, False, "; ".join(errors))
    return GateResult(
        "datadog-api-validate",
        True,
        False,
        f"Datadog API validated {validated} artifact(s)",
    )


def _helm_chart_dir(output_dir: Path, ctx: GateContext, gate: str) -> Path:
    raw = ctx.config(gate)
    rel = str(raw.get("chart_path", ".")).strip() or "."
    return (output_dir / rel).resolve()


def run_helm_lint(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "helm-chart":
        return GateResult("helm-lint", True, True, "helm-lint gate not applicable; skipped")

    if not tool_available("helm"):
        return GateResult("helm-lint", True, True, "helm not installed; skipped")

    chart_dir = _helm_chart_dir(output_dir, ctx, "helm-lint")
    chart_yaml = chart_dir / "Chart.yaml"
    if not chart_yaml.is_file():
        return GateResult("helm-lint", True, True, "no Chart.yaml found; skipped")

    result = run_command(["helm", "lint", str(chart_dir.relative_to(output_dir))], output_dir)
    if result.returncode == 0:
        return GateResult("helm-lint", True, False, "helm lint passed")
    detail = result.stderr.strip() or result.stdout.strip() or "helm lint failed"
    return GateResult("helm-lint", False, False, detail)


def run_helm_template(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "helm-chart":
        return GateResult("helm-template", True, True, "helm-template gate not applicable; skipped")

    if not tool_available("helm"):
        return GateResult("helm-template", True, True, "helm not installed; skipped")

    chart_dir = _helm_chart_dir(output_dir, ctx, "helm-template")
    if not (chart_dir / "Chart.yaml").is_file():
        return GateResult("helm-template", True, True, "no Chart.yaml found; skipped")

    cfg = ctx.config("helm-template")
    release = str(cfg.get("release_name", "repave-test"))
    result = run_command(
        [
            "helm",
            "template",
            release,
            str(chart_dir.relative_to(output_dir)),
        ],
        output_dir,
    )
    if result.returncode == 0:
        return GateResult("helm-template", True, False, "helm template passed")
    detail = result.stderr.strip() or result.stdout.strip() or "helm template failed"
    return GateResult("helm-template", False, False, detail)


def _write_helm_rendered_manifest(output_dir: Path, ctx: GateContext) -> tuple[Path | None, str]:
    if not tool_available("helm"):
        return None, "helm not installed"
    chart_dir = _helm_chart_dir(output_dir, ctx, "opa")
    if not (chart_dir / "Chart.yaml").is_file():
        return None, "no Chart.yaml found"
    cfg = ctx.config("opa")
    release = str(cfg.get("helm_release_name", cfg.get("release_name", "repave-test")))
    result = run_command(
        [
            "helm",
            "template",
            release,
            str(chart_dir.relative_to(output_dir)),
        ],
        output_dir,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "helm template failed"
        return None, detail
    manifest_path = output_dir / ".repave" / "helm-rendered.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(result.stdout, encoding="utf-8")
    return manifest_path, ""


def _run_opa_helm_chart(
    ctx: GateContext,
    policies_dir: Path,
    output_dir: Path,
) -> GateResult:
    manifest_path, err = _write_helm_rendered_manifest(output_dir, ctx)
    if manifest_path is None:
        if err == "helm not installed":
            return GateResult("opa", True, True, "helm not installed; skipped")
        if err == "no Chart.yaml found":
            return GateResult("opa", True, True, "no Helm chart found; skipped")
        return GateResult("opa", False, False, err)
    cmd = [
        "conftest",
        "test",
        str(manifest_path.relative_to(output_dir)),
        "-p",
        str(policies_dir),
    ]
    result = run_command(cmd, output_dir)
    if result.returncode == 0:
        return GateResult("opa", True, False, "conftest passed on helm-rendered manifests")
    detail = result.stderr.strip() or result.stdout.strip() or "conftest failed"
    return GateResult("opa", False, False, detail)


def _ensure_python_project_installed(output_dir: Path) -> None:
    marker = output_dir / ".repave" / "python_dev_installed"
    if marker.is_file():
        return
    import sys

    install = run_command(
        [sys.executable, "-m", "pip", "install", "-e", ".[dev]"],
        output_dir,
    )
    if install.returncode == 0:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("ok", encoding="utf-8")


def run_dockerfile_lint(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "app-service":
        return GateResult(
            "dockerfile-lint",
            True,
            True,
            "dockerfile-lint gate not applicable; skipped",
        )

    if not tool_available("hadolint"):
        return GateResult("dockerfile-lint", True, True, "hadolint not installed; skipped")

    raw = ctx.config("dockerfile-lint")
    dockerfile = str(raw.get("dockerfile", "Dockerfile")).strip() or "Dockerfile"
    path = output_dir / dockerfile
    if not path.is_file():
        return GateResult("dockerfile-lint", True, True, "no Dockerfile found; skipped")

    result = run_command(["hadolint", dockerfile], output_dir)
    if result.returncode == 0:
        return GateResult("dockerfile-lint", True, False, "hadolint passed")
    detail = result.stderr.strip() or result.stdout.strip() or "hadolint failed"
    return GateResult("dockerfile-lint", False, False, detail)


def run_python_lint(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "app-service":
        return GateResult("python-lint", True, True, "python-lint gate not applicable; skipped")

    if not tool_available("ruff"):
        return GateResult("python-lint", True, True, "ruff not installed; skipped")

    pyproject = output_dir / "pyproject.toml"
    if not _pyproject_is_valid(pyproject):
        return GateResult("python-lint", True, True, "no pyproject.toml found; skipped")

    _ensure_python_project_installed(output_dir)

    result = run_command(["ruff", "check", "src", "tests"], output_dir)
    if result.returncode == 0:
        return GateResult("python-lint", True, False, "ruff check passed")
    detail = result.stderr.strip() or result.stdout.strip() or "ruff check failed"
    return GateResult("python-lint", False, False, detail)


def run_python_test(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "app-service":
        return GateResult("python-test", True, True, "python-test gate not applicable; skipped")

    if not tool_available("pytest"):
        return GateResult("python-test", True, True, "pytest not installed; skipped")

    raw = ctx.config("python-test")
    test_directory = str(raw.get("test_directory", "tests"))
    pyproject = output_dir / "pyproject.toml"
    if not _pyproject_is_valid(pyproject):
        return GateResult("python-test", True, True, "no pyproject.toml found; skipped")

    test_dir = output_dir / test_directory
    if not _has_python_tests(test_dir):
        return GateResult("python-test", True, True, "no python tests; skipped")

    _ensure_python_project_installed(output_dir)

    result = run_command(["pytest", test_directory], output_dir)
    if result.returncode == 0:
        return GateResult("python-test", True, False, "pytest passed")
    detail = result.stderr.strip() or result.stdout.strip() or "pytest failed"
    return GateResult("python-test", False, False, detail)


def _go_mod_is_valid(path: Path) -> bool:
    text = path.read_text(encoding="utf-8").strip()
    return text.startswith("module ")


def _pyproject_is_valid(path: Path) -> bool:
    return path.is_file() and bool(path.read_text(encoding="utf-8").strip())


def _has_python_tests(test_dir: Path) -> bool:
    if not test_dir.is_dir():
        return False
    for candidate in test_dir.glob("test_*.py"):
        if candidate.read_text(encoding="utf-8").strip():
            return True
    return False


def run_go_lint(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "app-service":
        return GateResult("go-lint", True, True, "go-lint gate not applicable; skipped")

    if not tool_available("go"):
        return GateResult("go-lint", True, True, "go not installed; skipped")

    go_mod = output_dir / "go.mod"
    if not go_mod.is_file() or not _go_mod_is_valid(go_mod):
        return GateResult("go-lint", True, True, "no go.mod found; skipped")

    vet = run_command(["go", "vet", "./..."], output_dir)
    if vet.returncode != 0:
        detail = vet.stderr.strip() or vet.stdout.strip() or "go vet failed"
        return GateResult("go-lint", False, False, detail)

    fmt = run_command(["gofmt", "-l", "."], output_dir)
    if fmt.returncode != 0:
        detail = fmt.stderr.strip() or fmt.stdout.strip() or "gofmt failed"
        return GateResult("go-lint", False, False, detail)
    if fmt.stdout.strip():
        detail = "gofmt would change: " + fmt.stdout.strip().replace("\n", ", ")
        return GateResult("go-lint", False, False, detail)

    return GateResult("go-lint", True, False, "go vet and gofmt passed")


def run_go_test(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "app-service":
        return GateResult("go-test", True, True, "go-test gate not applicable; skipped")

    if not tool_available("go"):
        return GateResult("go-test", True, True, "go not installed; skipped")

    go_mod = output_dir / "go.mod"
    if not go_mod.is_file() or not _go_mod_is_valid(go_mod):
        return GateResult("go-test", True, True, "no go.mod found; skipped")

    if not any(output_dir.rglob("*_test.go")):
        return GateResult("go-test", True, True, "no Go tests; skipped")

    result = run_command(["go", "test", "./..."], output_dir)
    if result.returncode == 0:
        return GateResult("go-test", True, False, "go test passed")
    detail = result.stderr.strip() or result.stdout.strip() or "go test failed"
    return GateResult("go-test", False, False, detail)


def _opa_native_globs(ctx: GateContext) -> list[str]:
    raw = ctx.config("opa")
    configured = raw.get("native_globs")
    if isinstance(configured, list) and configured:
        return [str(item) for item in configured]
    return [
        "datadog/monitors/*.json",
        "datadog/dashboards/*.json",
        "grafana/dashboards/*.json",
        "prometheus/rules/*.y*ml",
    ]


def _run_opa_native_observability(
    ctx: GateContext,
    policies_dir: Path,
    output_dir: Path,
) -> GateResult:
    targets: list[Path] = []
    for pattern in _opa_native_globs(ctx):
        targets.extend(sorted(output_dir.glob(pattern)))
    if not targets:
        return GateResult(
            "opa",
            True,
            True,
            "no native observability files for opa; skipped",
        )

    errors: list[str] = []
    for path in targets:
        parser = "yaml" if path.suffix in (".yaml", ".yml") else "json"
        cmd = [
            "conftest",
            "test",
            str(path.relative_to(output_dir)),
            "-p",
            str(policies_dir),
            "--parser",
            parser,
        ]
        result = run_command(cmd, output_dir)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "conftest failed"
            errors.append(f"{path.name}: {detail}")

    if errors:
        return GateResult("opa", False, False, "; ".join(errors))
    return GateResult(
        "opa",
        True,
        False,
        f"conftest passed for {len(targets)} native file(s)",
    )


def run_ansible_lint(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if not tool_available("ansible-lint"):
        return GateResult("ansible-lint", True, True, "ansible-lint not installed; skipped")

    result = run_command(["ansible-lint"], output_dir)
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
    if not tool_available("ansible-playbook"):
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

    result = run_command(
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

    if not tool_available("molecule"):
        return GateResult("molecule", True, True, "molecule not installed; skipped")

    result = run_command(["molecule", "test"], output_dir)
    if result.returncode == 0:
        return GateResult("molecule", True, False, "molecule test passed")
    return GateResult(
        "molecule",
        False,
        False,
        result.stderr.strip() or result.stdout.strip() or "molecule test failed",
    )


def _terraform_plan_json(output_dir: Path, plan_subdir: str) -> Path | None:
    if not terraform_usable(output_dir):
        return None
    work = output_dir / plan_subdir
    work.mkdir(parents=True, exist_ok=True)
    plan_binary = work / "tfplan"
    plan_json = work / "tfplan.json"

    init = run_command(["terraform", "init", "-backend=false", "-input=false"], output_dir)
    if init.returncode != 0:
        return None

    plan = run_command(
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

    show = run_command(
        ["terraform", "show", "-json", str(plan_binary.relative_to(output_dir))],
        output_dir,
    )
    if show.returncode != 0:
        return None
    plan_json.write_text(show.stdout, encoding="utf-8")
    return plan_json


def run_opa(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is None or ctx.blueprint.opa_policies is None:
        return GateResult("opa", True, True, "opa policy pack not configured; skipped")

    if not tool_available("conftest"):
        return GateResult("opa", True, True, "conftest not installed; skipped")

    cfg = ctx.blueprint.opa_gate
    policies_dir = output_dir / cfg.policies_dir
    selection = load_policy_selection_file(output_dir)
    if selection is not None and not selection.opa_rego_files:
        return GateResult("opa", True, True, "no OPA policies selected; skipped")

    if not policies_dir.is_dir():
        return GateResult(
            "opa",
            False,
            False,
            f"opa policies directory missing: {cfg.policies_dir}",
        )

    artifact = ctx.blueprint.artifact_type
    if artifact == "opa-policy":
        fixtures = output_dir / cfg.fixtures_dir
        if not fixtures.is_dir() or not any(fixtures.iterdir()):
            return GateResult(
                "opa",
                False,
                False,
                f"opa fixtures missing or empty: {cfg.fixtures_dir}",
            )
        target = str(fixtures)
    elif artifact.startswith("terraform-") or artifact == "observability":
        if artifact == "observability" and not any(output_dir.glob("*.tf")):
            return _run_opa_native_observability(ctx, policies_dir, output_dir)
        plan_json = _terraform_plan_json(output_dir, cfg.plan_subdir)
        if plan_json is None:
            return GateResult(
                "opa",
                False,
                False,
                "terraform plan JSON could not be produced for opa evaluation",
            )
        target = str(plan_json)
    elif artifact == "helm-chart":
        return _run_opa_helm_chart(ctx, policies_dir, output_dir)
    else:
        return GateResult("opa", True, True, "opa gate not applicable to this artifact type")

    cmd = ["conftest", "test", target, "-p", str(policies_dir)]
    result = run_command(cmd, output_dir)
    if result.returncode == 0:
        return GateResult("opa", True, False, "conftest passed")
    detail = result.stderr.strip() or result.stdout.strip() or "conftest failed"
    detail = _format_opa_failure(detail)
    return GateResult("opa", False, False, detail)


def _format_opa_failure(detail: str) -> str:
    lowered = detail.lower()
    if "destructive delete" in lowered:
        return (
            "Publish blocked: plan-time OPA rejected a destructive change "
            "(resource delete without replacement). Adjust the plan or use a profile "
            "that allows the change only after platform review.\n\n"
            f"{detail}"
        )
    return detail


_AZURE_POLICY_REQUIRED_PROPERTIES = frozenset(
    {"displayName", "policyType", "mode", "description", "policyRule"}
)
_AZURE_POLICY_MODES = frozenset({"All", "Indexed", "Microsoft.Kubernetes.Data"})


def _validate_azure_policy_definition(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return f"{path.name}: invalid JSON ({exc.msg})"
    if not isinstance(data, dict):
        return f"{path.name}: root must be a JSON object"
    properties = data.get("properties")
    if not isinstance(properties, dict):
        return f"{path.name}: missing properties object"
    missing = _AZURE_POLICY_REQUIRED_PROPERTIES - set(properties)
    if missing:
        missing_list = ", ".join(sorted(missing))
        return f"{path.name}: properties missing required fields: {missing_list}"
    mode = properties.get("mode")
    if mode not in _AZURE_POLICY_MODES:
        return f"{path.name}: invalid mode {mode!r}"
    if not isinstance(properties.get("policyRule"), dict):
        return f"{path.name}: policyRule must be an object"
    return None


def run_azure_policy(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is None or ctx.blueprint.artifact_type != "azure-policy":
        return GateResult("azure-policy", True, True, "azure-policy gate not applicable; skipped")

    cfg = ctx.blueprint.azure_policy_gate
    definitions_dir = output_dir / cfg.definitions_dir
    if not definitions_dir.is_dir():
        return GateResult(
            "azure-policy",
            False,
            False,
            f"azure policy definitions directory missing: {cfg.definitions_dir}",
        )

    json_files = sorted(definitions_dir.glob("*.json"))
    if not json_files:
        return GateResult(
            "azure-policy",
            False,
            False,
            f"no Azure Policy definition JSON files in {cfg.definitions_dir}",
        )

    errors: list[str] = []
    for path in json_files:
        problem = _validate_azure_policy_definition(path)
        if problem:
            errors.append(problem)
    if errors:
        return GateResult("azure-policy", False, False, "; ".join(errors))
    return GateResult("azure-policy", True, False, "azure policy definitions validated")
