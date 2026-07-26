from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.blueprint import load_blueprint, validate_inputs
from repave_engine.dashboard_pack import materialize_dashboard_pack
from repave_engine.observability_catalog import (
    catalog_for_api,
    dashboard_pack_by_id,
    dashboard_packs_for_backend,
    load_observability_catalog,
)


def test_load_observability_catalog(repo_root) -> None:
    catalog = load_observability_catalog(repo_root)
    assert catalog.version == "1.3.0"
    assert len(catalog.notification_sources) >= 2
    assert catalog.defaults["dashboard_pack_source"] == "repave-red-starter"
    assert len(catalog.dashboard_packs) >= 3


def test_dashboard_packs_for_backend(repo_root) -> None:
    catalog = load_observability_catalog(repo_root)
    grafana = dashboard_packs_for_backend(catalog, "grafana")
    assert any(p.id == "grafana-red-plus-node-exporter-1860" for p in grafana)
    datadog = dashboard_packs_for_backend(catalog, "datadog")
    assert any(p.id == "datadog-red-plus-apm-service" for p in datadog)
    assert all(p.backend in ("any", "datadog") for p in datadog)


def test_catalog_for_api_dashboard_packs(repo_root) -> None:
    catalog = load_observability_catalog(repo_root)
    payload = catalog_for_api(catalog, backend="grafana")
    pack_ids = {item["id"] for item in payload["dashboard_packs"]}
    assert len(pack_ids) >= 4
    assert "grafana-red-plus-node-exporter-1860" in pack_ids
    assert "datadog-red-plus-apm-service" in pack_ids
    grafana_pack = next(
        item
        for item in payload["dashboard_packs"]
        if item["id"] == "grafana-red-plus-node-exporter-1860"
    )
    assert grafana_pack["file_count"] == 1
    assert (
        grafana_pack["files"][0]["dest"] == "grafana/dashboards/community-node-exporter-1860.json"
    )


def test_materialize_dashboard_pack_writes_community_json(repo_root: Path, tmp_path: Path) -> None:
    values = {
        "service_name": "checkout",
        "organization": "platform",
        "team": "payments",
        "environment": "prod",
        "datasource_uid": "prometheus",
        "dashboard_pack_source": "grafana-red-plus-node-exporter-1860",
    }
    materialize_dashboard_pack(tmp_path, repo_root, values)
    out = tmp_path / "grafana" / "dashboards" / "community-node-exporter-1860.json"
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "community:grafana-1860" in text
    assert "checkout" in text


def test_validate_inputs_rejects_grafana_pack_on_datadog_backend(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "dashboards-as-code-generic",
        repo_root,
    )
    with pytest.raises(ValueError, match="Dashboard pack"):
        validate_inputs(
            blueprint,
            {
                "service_name": "checkout",
                "organization": "platform",
                "team": "payments",
                "description": "x",
                "backend": "datadog",
                "environment": "prod",
                "output_mode": "native",
                "observability_focus": "dashboards",
                "dashboard_pack_source": "grafana-red-plus-node-exporter-1860",
                "notification_source": "repave-estate-oncall",
                "notification_target": "pagerduty-platform-primary",
            },
            repo_root=repo_root,
        )


def test_dashboard_pack_by_id(repo_root) -> None:
    catalog = load_observability_catalog(repo_root)
    pack = dashboard_pack_by_id(catalog, "grafana-red-plus-node-exporter-1860")
    assert pack is not None
    assert len(pack.files) == 1
