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


def test_run_store_schedule_retry_and_list(tmp_path) -> None:
    store = RunStore(tmp_path / "runs.sqlite")
    record = store.create_run(
        blueprint_name="terraform-module-generic",
        dry_run=True,
        payload={"blueprint": "terraform-module-generic", "inputs": {}, "dry_run": True},
        acting_user="tester",
    )
    store.schedule_retry(
        record.run_id,
        attempt_count=1,
        error="transient",
        next_attempt_at="2099-01-01T00:00:00+00:00",
    )
    loaded = store.get(record.run_id)
    assert loaded is not None
    assert loaded.status == RunStatus.QUEUED
    assert loaded.attempt_count == 1
    assert loaded.error == "transient"

    queued = store.list_runs(status=RunStatus.QUEUED, limit=10)
    assert any(item.run_id == record.run_id for item in queued)


def test_run_store_reclaim_stale_running(tmp_path) -> None:
    store = RunStore(tmp_path / "runs.sqlite")
    record = store.create_run(
        blueprint_name="terraform-module-generic",
        dry_run=True,
        payload={"blueprint": "terraform-module-generic", "inputs": {}, "dry_run": True},
        acting_user="tester",
    )
    store.update_status(record.run_id, RunStatus.RUNNING)
    with store._lock, store._connect() as conn:
        conn.execute(
            "UPDATE runs SET updated_at = ? WHERE run_id = ?",
            ("2000-01-01T00:00:00+00:00", record.run_id),
        )
        conn.commit()
    reclaimed = store.reclaim_stale_runs(stale_after_seconds=60, max_attempts=3)
    assert reclaimed == 1
    loaded = store.get(record.run_id)
    assert loaded is not None
    assert loaded.status == RunStatus.QUEUED
    assert loaded.attempt_count == 1
