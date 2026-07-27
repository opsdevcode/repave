"""Generate Terraform resources for materialized monitor pack files."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _terraform_resource_name(stem: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", stem)
    if cleaned and cleaned[0].isdigit():
        cleaned = f"m_{cleaned}"
    return cleaned or "monitor"


def _hcl_string(value: str) -> str:
    return json.dumps(value)


def _write_datadog_monitor_pack_terraform(output_dir: Path) -> None:
    json_dir = output_dir / "datadog" / "monitors"
    if not json_dir.is_dir():
        return
    lines = [
        "# Generated from materialized monitor pack JSON (datadog_monitor resources).",
        "",
    ]
    for path in sorted(json_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = payload if isinstance(payload, list) else [payload]
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            stem = path.stem if len(entries) == 1 else f"{path.stem}_{index}"
            resource = _terraform_resource_name(stem)
            name = str(entry.get("name", stem))
            monitor_type = str(entry.get("type", "query alert"))
            query = str(entry.get("query", ""))
            message = str(entry.get("message", ""))
            tags = entry.get("tags")
            options_raw = entry.get("options")
            options: dict[str, Any] = options_raw if isinstance(options_raw, dict) else {}
            lines.extend(
                [
                    f'resource "datadog_monitor" "{resource}" {{',
                    f"  name    = {_hcl_string(name)}",
                    f"  type    = {_hcl_string(monitor_type)}",
                    f"  query   = {_hcl_string(query)}",
                    f"  message = {_hcl_string(message)}",
                ]
            )
            if isinstance(tags, list) and tags:
                lines.append("  tags = [")
                for tag in tags:
                    lines.append(f"    {_hcl_string(str(tag))},")
                lines.append("  ]")
            if "notify_no_data" in options:
                lines.append(f"  notify_no_data = {str(options['notify_no_data']).lower()}")
            if "require_full_window" in options:
                lines.append(
                    f"  require_full_window = {str(options['require_full_window']).lower()}"
                )
            if "include_tags" in options:
                lines.append(f"  include_tags = {str(options['include_tags']).lower()}")
            lines.extend(["}", ""])
    if len(lines) <= 2:
        return
    (output_dir / "monitor_packs.tf").write_text("\n".join(lines), encoding="utf-8")


def _write_prometheus_monitor_pack_terraform(output_dir: Path) -> None:
    rules_dir = output_dir / "prometheus" / "rules"
    if not rules_dir.is_dir():
        return
    lines = [
        "# Generated from materialized monitor pack YAML (null_resource GitOps payloads).",
        "",
    ]
    for path in sorted(rules_dir.glob("*.yaml")):
        resource = _terraform_resource_name(path.stem)
        rel = path.relative_to(output_dir).as_posix()
        lines.extend(
            [
                f'resource "null_resource" "{resource}" {{',
                "  triggers = {",
                f'    rules_yaml = file("${{path.module}}/{rel}")',
                "  }",
                "",
                "  lifecycle {",
                "    ignore_changes = all",
                "  }",
                "}",
                "",
            ]
        )
    if len(lines) <= 2:
        return
    (output_dir / "monitor_packs.tf").write_text("\n".join(lines), encoding="utf-8")


def write_monitor_pack_terraform(output_dir: Path, *, backend: str) -> None:
    normalized = backend.strip().lower()
    if normalized == "datadog":
        _write_datadog_monitor_pack_terraform(output_dir)
        return
    if normalized == "prometheus":
        _write_prometheus_monitor_pack_terraform(output_dir)
