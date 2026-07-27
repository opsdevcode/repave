from __future__ import annotations

import json
from pathlib import Path

from repave_engine.monitor_pack_terraform import write_monitor_pack_terraform


def test_write_monitor_pack_terraform_datadog(tmp_path: Path) -> None:
    monitor_dir = tmp_path / "datadog" / "monitors"
    monitor_dir.mkdir(parents=True)
    (monitor_dir / "community-apm.json").write_text(
        json.dumps(
            [
                {
                    "name": "checkout APM error rate",
                    "type": "query alert",
                    "query": "avg(last_5m):avg:trace.errors{*} > 1",
                    "message": "errors high",
                    "tags": ["service:checkout"],
                    "options": {"notify_no_data": False, "include_tags": True},
                }
            ]
        ),
        encoding="utf-8",
    )

    write_monitor_pack_terraform(tmp_path, backend="datadog")

    content = (tmp_path / "monitor_packs.tf").read_text(encoding="utf-8")
    assert 'resource "datadog_monitor" "community_apm"' in content
    assert "checkout APM error rate" in content


def test_write_monitor_pack_terraform_prometheus(tmp_path: Path) -> None:
    rules_dir = tmp_path / "prometheus" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "community-host-cpu.yaml").write_text(
        "groups:\n- name: host\n  rules: []\n",
        encoding="utf-8",
    )

    write_monitor_pack_terraform(tmp_path, backend="prometheus")

    content = (tmp_path / "monitor_packs.tf").read_text(encoding="utf-8")
    assert 'resource "null_resource" "community_host_cpu"' in content
    assert "prometheus/rules/community-host-cpu.yaml" in content
