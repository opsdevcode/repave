"""Generate Terraform resources for materialized dashboard JSON files."""

from __future__ import annotations

import re
from pathlib import Path

from repave_engine.safe_paths import confined_join, trusted_path


def _terraform_resource_name(stem: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", stem)
    if cleaned and cleaned[0].isdigit():
        cleaned = f"d_{cleaned}"
    return cleaned or "dashboard"


def write_dashboard_pack_terraform(output_dir: Path, *, backend: str) -> None:
    output_dir = trusted_path(output_dir)
    normalized = backend.strip().lower()
    if normalized == "grafana":
        json_dir = confined_join(output_dir, "grafana", "dashboards")
        if not json_dir.is_dir():
            return
        lines = [
            "# Generated from materialized dashboard pack JSON (grafana_dashboard resources).",
            "",
        ]
        for path in sorted(json_dir.glob("*.json")):
            resource = _terraform_resource_name(path.stem)
            rel = path.relative_to(output_dir).as_posix()
            lines.extend(
                [
                    f'resource "grafana_dashboard" "{resource}" {{',
                    f'  config_json = file("${{path.module}}/{rel}")',
                    "}",
                    "",
                ]
            )
        if len(lines) <= 2:
            return
        confined_join(output_dir, "dashboard_packs.tf").write_text(
            "\n".join(lines), encoding="utf-8"
        )
        return

    if normalized == "datadog":
        json_dir = confined_join(output_dir, "datadog", "dashboards")
        if not json_dir.is_dir():
            return
        lines = [
            "# Generated from materialized dashboard pack JSON (datadog_dashboard_json resources).",
            "",
        ]
        for path in sorted(json_dir.glob("*.json")):
            resource = _terraform_resource_name(path.stem)
            rel = path.relative_to(output_dir).as_posix()
            lines.extend(
                [
                    f'resource "datadog_dashboard_json" "{resource}" {{',
                    f'  dashboard = file("${{path.module}}/{rel}")',
                    "}",
                    "",
                ]
            )
        if len(lines) <= 2:
            return
        confined_join(output_dir, "dashboard_packs.tf").write_text(
            "\n".join(lines), encoding="utf-8"
        )
