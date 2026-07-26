from __future__ import annotations

from pathlib import Path

from repave_engine.dashboard_pack_terraform import write_dashboard_pack_terraform


def test_write_dashboard_pack_terraform_grafana(tmp_path: Path) -> None:
    dash_dir = tmp_path / "grafana" / "dashboards"
    dash_dir.mkdir(parents=True)
    (dash_dir / "service-overview.json").write_text('{"title": "x"}', encoding="utf-8")

    write_dashboard_pack_terraform(tmp_path, backend="grafana")

    content = (tmp_path / "dashboard_packs.tf").read_text(encoding="utf-8")
    assert 'resource "grafana_dashboard" "service_overview"' in content
    assert "grafana/dashboards/service-overview.json" in content
