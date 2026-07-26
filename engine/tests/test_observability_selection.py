from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.blueprint import load_blueprint, validate_inputs
from repave_engine.observability_selection import (
    blueprint_supports_observability_notifications,
    observability_input_defaults,
)


def test_blueprint_supports_observability_notifications(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "observability-as-code-generic",
        repo_root,
    )
    assert blueprint_supports_observability_notifications(blueprint)


def test_observability_input_defaults(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "observability-as-code-generic",
        repo_root,
    )
    defaults = observability_input_defaults(blueprint, repo_root)
    assert defaults["notification_source"] == "repave-estate-oncall"
    assert defaults["notification_target"] == "pagerduty-platform-primary"


def test_normalize_observability_inputs_rejects_bad_target(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "observability-as-code-generic",
        repo_root,
    )
    with pytest.raises(ValueError, match="notification_target"):
        validate_inputs(
            blueprint,
            {
                "configuration_mode": "custom",
                "service_name": "checkout",
                "organization": "platform",
                "team": "payments",
                "description": "x",
                "backend": "prometheus",
                "output_mode": "native",
                "notification_source": "repave-estate-oncall",
                "notification_target": "not-in-catalog",
                "runbook_url": "https://wiki.example.com/runbooks/checkout",
            },
            repo_root=repo_root,
        )


def test_normalize_observability_inputs_accepts_catalog_target(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "observability-as-code-generic",
        repo_root,
    )
    normalized = validate_inputs(
        blueprint,
        {
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "x",
            "backend": "prometheus",
            "output_mode": "native",
            "notification_source": "repave-slack-alerts",
            "notification_target": "slack-alerts-platform",
            "runbook_url": "https://wiki.example.com/runbooks/checkout",
        },
        repo_root=repo_root,
    )
    assert normalized["notification_target"] == "slack-alerts-platform"
