from __future__ import annotations

from repave_engine.fleet_operator_status import (
    FleetOperatorStatus,
    load_operator_status_file,
    parse_kubectl_gpr_list,
    write_operator_status_snapshot,
)


def test_parse_kubectl_gpr_list() -> None:
    payload = {
        "items": [
            {
                "metadata": {"name": "acme-tf-vpc", "namespace": "repave-system"},
                "spec": {"repoURL": "https://github.com/acme/tf-vpc.git"},
                "status": {
                    "phase": "OutOfDate",
                    "message": "pins differ",
                    "remediationPR": {"url": "https://github.com/acme/tf-vpc/pull/1"},
                },
            }
        ]
    }
    rows = parse_kubectl_gpr_list(payload)
    assert len(rows) == 1
    assert rows[0].phase == "OutOfDate"
    assert rows[0].remediation_pr_url.endswith("/pull/1")
    assert rows[0].resource_name == "acme-tf-vpc"


def test_operator_status_snapshot_round_trip(tmp_path) -> None:
    path = tmp_path / "status.json"
    write_operator_status_snapshot(
        path,
        [
            FleetOperatorStatus(
                repo_url="https://github.com/acme/tf-vpc",
                phase="Ready",
                resource_name="acme-tf-vpc",
                namespace="default",
            )
        ],
    )
    loaded = load_operator_status_file(path)
    assert "https://github.com/acme/tf-vpc" in loaded
    assert loaded["https://github.com/acme/tf-vpc"].phase == "Ready"
