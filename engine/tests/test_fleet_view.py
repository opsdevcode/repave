from __future__ import annotations

import pytest

from repave_engine.fleet import FleetEntry
from repave_engine.fleet_view import (
    fleet_blueprint_family,
    fleet_repo_display_name,
    fleet_row,
)


@pytest.mark.parametrize(
    ("repo_url", "expected"),
    [
        ("https://github.com/acme/tf-vpc", "tf-vpc"),
        ("https://github.com/acme/tf-vpc.git", "tf-vpc"),
        ("https://github.com/acme/tf-vpc.git/", "tf-vpc"),
        ("git@github.com:acme/tf-vpc.git", "tf-vpc"),
        ("tf-vpc", "tf-vpc"),
    ],
)
def test_fleet_repo_display_name(repo_url: str, expected: str) -> None:
    assert fleet_repo_display_name(repo_url) == expected


@pytest.mark.parametrize(
    ("blueprint_name", "expected"),
    [
        ("terraform-module-generic", "terraform"),
        ("tf-aws-vpc", "terraform"),
        ("ansible-collection-generic", "ansible"),
        ("opa-policy-generic", "policy"),
        ("checkov-policy-generic", "policy"),
        ("observability-dashboard-generic", "observability"),
        ("gitops-app-generic", "gitops"),
        ("helm-chart-generic", "helm"),
        ("app-service-generic", "app"),
        ("something-else", "other"),
        ("", "other"),
    ],
)
def test_fleet_blueprint_family(blueprint_name: str, expected: str) -> None:
    assert fleet_blueprint_family(blueprint_name) == expected


def test_fleet_row_adds_display_name_and_family() -> None:
    row = fleet_row(
        FleetEntry(
            repo_url="https://github.com/acme/tf-vpc.git",
            blueprint_name="terraform-module-generic",
            blueprint_version="0.9.0",
        )
    )
    assert row["display_name"] == "tf-vpc"
    assert row["family"] == "terraform"
