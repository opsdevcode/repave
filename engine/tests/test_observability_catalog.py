from __future__ import annotations

from repave_engine.observability_catalog import (
    catalog_for_api,
    load_observability_catalog,
    source_by_id,
    target_ids_for_source,
)


def test_load_observability_catalog(repo_root) -> None:
    catalog = load_observability_catalog(repo_root)
    assert catalog.version == "1.0.0"
    assert len(catalog.notification_sources) >= 2
    assert catalog.defaults["notification_source"] == "repave-estate-oncall"


def test_target_ids_for_source(repo_root) -> None:
    catalog = load_observability_catalog(repo_root)
    ids = target_ids_for_source(catalog, "repave-estate-oncall")
    assert "pagerduty-platform-primary" in ids
    assert "pagerduty-payments" in ids


def test_catalog_for_api_includes_defaults(repo_root) -> None:
    catalog = load_observability_catalog(repo_root)
    payload = catalog_for_api(
        catalog,
        defaults={
            "notification_source": "repave-slack-alerts",
            "notification_target": "slack-alerts-platform",
        },
    )
    assert payload["defaults"]["notification_source"] == "repave-slack-alerts"
    assert len(payload["notification_sources"]) >= 1
    first = payload["notification_sources"][0]
    assert first.get("targets")


def test_source_by_id(repo_root) -> None:
    catalog = load_observability_catalog(repo_root)
    source = source_by_id(catalog, "repave-slack-alerts")
    assert source is not None
    assert source.provider == "slack"
