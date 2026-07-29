from __future__ import annotations

import json
import os
from pathlib import Path

import repave_engine.gate_runners as _gr
from repave_engine.gate_registry import GateContext, GateResult


def _promtool_rule_files(output_dir: Path, ctx: GateContext) -> list[Path]:
    raw = ctx.config("promtool")
    glob_pattern = str(raw.get("rules_glob", "prometheus/rules/*.y*ml"))
    return sorted(output_dir.glob(glob_pattern))


def run_promtool(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "observability":
        return GateResult("promtool", True, True, "promtool gate not applicable; skipped")

    if not _gr.tool_available("promtool"):
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
        result = _gr.run_command(
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

    if not _gr.tool_available("amtool"):
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
        result = _gr.run_command(
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
    response = _gr.httpx.post(url, headers=headers, json=payload, timeout=30.0)
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
