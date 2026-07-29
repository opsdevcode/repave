from __future__ import annotations

from repave_engine.run_store import RunStatus, RunStore


def test_run_store_create_and_update(tmp_path) -> None:
    store = RunStore(tmp_path / "runs.sqlite")
    record = store.create_run(
        blueprint_name="terraform-module-generic",
        dry_run=True,
        payload={"blueprint": "terraform-module-generic", "inputs": {}, "dry_run": True},
        acting_user="tester",
        client_request_id="req-1",
    )
    assert record.status == RunStatus.QUEUED
    assert record.client_request_id == "req-1"

    again = store.create_run(
        blueprint_name="terraform-module-generic",
        dry_run=True,
        payload={"blueprint": "terraform-module-generic", "inputs": {}, "dry_run": True},
        acting_user="tester",
        client_request_id="req-1",
    )
    assert again.run_id == record.run_id

    store.update_status(record.run_id, RunStatus.SUCCEEDED, result={"gates_outcome": "passed"})
    loaded = store.get(record.run_id)
    assert loaded is not None
    assert loaded.status == RunStatus.SUCCEEDED
    assert loaded.result == {"gates_outcome": "passed"}
