from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from repave_engine.platform_runs import FleetDriftConfirmResult, run_fleet_drift_confirm
from repave_engine.standards_diff import PinChange
from repave_engine.verify import VerifyResult


def test_run_fleet_drift_confirm_counts_behind_and_current(repo_root: Path) -> None:
    outcomes = {
        "https://github.com/acme/current": VerifyResult(
            target="https://github.com/acme/current",
            catalog_blueprint_name="terraform-module-generic",
            catalog_blueprint_version="1.0.0",
            provenance_present=True,
            gates=(),
            pin_changes=(),
        ),
        "https://github.com/acme/behind": VerifyResult(
            target="https://github.com/acme/behind",
            catalog_blueprint_name="terraform-module-generic",
            catalog_blueprint_version="1.0.0",
            provenance_present=True,
            gates=(),
            pin_changes=(PinChange(field="blueprint_version", before="0.9.0", after="1.0.0"),),
        ),
    }

    def fake_verify(url: str, root: Path) -> VerifyResult:
        return outcomes[url]

    with patch("repave_engine.platform_runs.verify_target", side_effect=fake_verify):
        result = run_fleet_drift_confirm(
            repo_root,
            repo_urls=(
                "https://github.com/acme/current",
                "https://github.com/acme/behind",
            ),
        )
    assert isinstance(result, FleetDriftConfirmResult)
    assert result.confirmed_current == 1
    assert result.confirmed_behind == 1
    assert len(result.repos) == 2
