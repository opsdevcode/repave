from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.blueprint import load_blueprint, validate_inputs
from repave_engine.observability_catalog import (
    catalog_has_field_options,
    load_observability_catalog,
)


def test_catalog_has_field_options(repo_root) -> None:
    catalog = load_observability_catalog(repo_root)
    assert catalog.version == "1.3.0"
    assert catalog_has_field_options(catalog)
    assert len(catalog.services) >= 2


def test_validate_observability_catalog_fields_rejects_bad_team(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "dashboards-as-code-generic",
        repo_root,
    )
    with pytest.raises(ValueError, match="Invalid team"):
        validate_inputs(
            blueprint,
            {
                "configuration_mode": "custom",
                "service_name": "checkout",
                "organization": "platform",
                "team": "pipelines",
                "description": "x",
                "backend": "grafana",
                "environment": "prod",
                "output_mode": "native",
                "observability_focus": "dashboards",
                "dashboard_pack_source": "repave-red-starter",
                "datasource_uid": "prometheus",
                "notification_source": "repave-estate-oncall",
                "notification_target": "pagerduty-platform-primary",
            },
            repo_root=repo_root,
        )


def test_recommended_mode_applies_catalog_defaults(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "dashboards-as-code-generic",
        repo_root,
    )
    normalized = validate_inputs(
        blueprint,
        {
            "configuration_mode": "recommended",
            "service_name": "auth",
            "backend": "grafana",
            "dashboard_pack_source": "repave-red-starter",
        },
        repo_root=repo_root,
    )
    assert normalized["organization"] == "platform"
    assert normalized["team"] == "identity"
    assert normalized["description"]
    assert normalized["notification_source"] == "repave-estate-oncall"
