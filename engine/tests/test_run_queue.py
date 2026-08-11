from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from repave_engine.audit_history import read_recent_audit_entries
from repave_engine.publish_idempotency import PublishIdempotencyStore
from repave_engine.run_queue import RunQueue, RunQueueConfig
from repave_engine.run_store import RunStatus, RunStore
from repave_engine.settings import OutputConfig


def _enable_audit(tmp_path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "audit:\n  enabled: true\n  file: audit/generation.jsonl\n",
        encoding="utf-8",
    )


def _wait_for_audit_entries(
    audit_path: Path,
    *,
    repo_root: Path,
    expected: int = 1,
    deadline_seconds: float = 15.0,
):
    deadline = time.time() + deadline_seconds
    while time.time() < deadline:
        entries = read_recent_audit_entries(audit_path, limit=5, repo_root=repo_root)
        if len(entries) >= expected:
            return entries
        time.sleep(0.05)
    entries = read_recent_audit_entries(audit_path, limit=5, repo_root=repo_root)
    assert len(entries) >= expected, f"expected >= {expected} audit entries, got {len(entries)}"
    return entries


def test_run_queue_executes_job(tmp_path) -> None:
    store = RunStore(tmp_path / "runs.sqlite")
    output = OutputConfig(
        github_org="example",
        modules_root=tmp_path / "modules",
    )
    queue = RunQueue(
        repo_root=tmp_path,
        output_config=output,
        store=store,
        config=RunQueueConfig(max_concurrent_runs=1, queue_max_depth=4),
    )
    fake_result = {
        "blueprint": "terraform-module-generic",
        "gates_outcome": "passed",
        "gates_passed": True,
        "gates": [],
        "rendered_files": 1,
        "output_dir": str(tmp_path / "out"),
    }
    with patch("repave_engine.run_queue.run_generate_api", return_value=fake_result):
        record = queue.submit(
            blueprint_name="terraform-module-generic",
            inputs={"module_name": "demo"},
            dry_run=True,
            acting_user="tester",
            client_request_id="job-1",
        )
        run_id = record.run_id
        deadline = time.time() + 5.0
        terminal = None
        while time.time() < deadline:
            terminal = store.get(run_id)
            if terminal and terminal.status in (
                RunStatus.SUCCEEDED,
                RunStatus.FAILED,
                RunStatus.DEAD_LETTER,
            ):
                break
            time.sleep(0.05)
        assert terminal is not None
        assert terminal.status == RunStatus.SUCCEEDED
        assert terminal.result is not None
        for key, value in fake_result.items():
            assert terminal.result.get(key) == value
        assert "artifact_root" in terminal.result
    queue.close()


def test_run_queue_passes_publish_idempotency_context(tmp_path) -> None:
    db_path = tmp_path / "runs.sqlite"
    store = RunStore(db_path)
    publish_store = PublishIdempotencyStore(db_path)
    output = OutputConfig(
        github_org="example",
        modules_root=tmp_path / "modules",
    )
    queue = RunQueue(
        repo_root=tmp_path,
        output_config=output,
        store=store,
        config=RunQueueConfig(max_concurrent_runs=1, queue_max_depth=4),
        publish_store=publish_store,
    )
    captured: list[tuple[str | None, str | None]] = []

    def fake_generate_api(**kwargs):  # type: ignore[no-untyped-def]
        ctx = kwargs.get("publish_idempotency")
        assert ctx is not None
        captured.append((ctx.run_id, ctx.client_request_id))
        return {
            "blueprint": "terraform-module-generic",
            "gates_outcome": "passed",
            "gates_passed": True,
            "gates": [],
            "rendered_files": 1,
            "output_dir": str(tmp_path / "out"),
        }

    with patch("repave_engine.run_queue.run_generate_api", side_effect=fake_generate_api):
        record = queue.submit(
            blueprint_name="terraform-module-generic",
            inputs={"module_name": "demo"},
            dry_run=False,
            acting_user="tester",
            client_request_id="publish-replay",
        )
        run_id = record.run_id
        deadline = time.time() + 5.0
        while time.time() < deadline:
            terminal = store.get(run_id)
            if terminal and terminal.status == RunStatus.SUCCEEDED:
                break
            time.sleep(0.05)
        assert captured == [(run_id, "publish-replay")]
    queue.close()


def test_run_queue_dispatches_job_on_submit(tmp_path) -> None:
    store = RunStore(tmp_path / "runs.sqlite")
    output = OutputConfig(
        github_org="example",
        modules_root=tmp_path / "modules",
    )
    dispatched: list[str] = []

    class FakeJobDispatcher:
        def dispatch(
            self,
            run_id: str,
            *,
            live_plan_secret_name: str | None = None,
        ) -> None:
            del live_plan_secret_name
            dispatched.append(run_id)

    queue = RunQueue(
        repo_root=tmp_path,
        output_config=output,
        store=store,
        config=RunQueueConfig(
            max_concurrent_runs=1,
            queue_max_depth=4,
            external_workers=True,
            enqueue_only=True,
        ),
        job_dispatcher=FakeJobDispatcher(),
    )
    record = queue.submit(
        blueprint_name="terraform-module-generic",
        inputs={"module_name": "demo"},
        dry_run=True,
        acting_user="tester",
    )
    assert dispatched == [record.run_id]
    queue.close()


def test_run_queue_dead_letters_after_infrastructure_retries(tmp_path) -> None:
    store = RunStore(tmp_path / "runs.sqlite")
    output = OutputConfig(
        github_org="example",
        modules_root=tmp_path / "modules",
    )
    queue = RunQueue(
        repo_root=tmp_path,
        output_config=output,
        store=store,
        config=RunQueueConfig(
            max_concurrent_runs=1,
            queue_max_depth=4,
            max_attempts=2,
            retry_base_seconds=1,
        ),
    )

    def boom(**kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("worker infra failure")

    with patch("repave_engine.run_queue.run_generate_api", side_effect=boom):
        record = queue.submit(
            blueprint_name="terraform-module-generic",
            inputs={"module_name": "demo"},
            dry_run=True,
            acting_user="tester",
        )
        run_id = record.run_id
        deadline = time.time() + 10.0
        while time.time() < deadline:
            terminal = store.get(run_id)
            if terminal is not None and terminal.status == RunStatus.DEAD_LETTER:
                assert "worker infra failure" in (terminal.error or "")
                break
            time.sleep(0.05)
        else:
            pytest.fail("run did not reach dead_letter")
    queue.close()


def test_run_queue_writes_audit_on_success(tmp_path) -> None:
    _enable_audit(tmp_path)
    store = RunStore(tmp_path / "runs.sqlite")
    output = OutputConfig(
        github_org="example",
        modules_root=tmp_path / "modules",
    )
    queue = RunQueue(
        repo_root=tmp_path,
        output_config=output,
        store=store,
        config=RunQueueConfig(max_concurrent_runs=1, queue_max_depth=4),
    )
    fake_result = {
        "blueprint": "terraform-module-generic",
        "blueprint_version": "0.12.0",
        "module_name": "tf-aws-eks",
        "repository_url": "https://github.com/opsdevcode/tf-aws-eks",
        "gates_outcome": "passed",
        "gates_passed": True,
        "gates": [],
        "pr_message": "GitHub publish failed.\nError (403): denied",
        "rendered_files": [],
        "output_dir": str(tmp_path / "out"),
    }
    with patch("repave_engine.run_queue.run_generate_api", return_value=fake_result):
        record = queue.submit(
            blueprint_name="terraform-module-generic",
            inputs={"module_name": "eks"},
            dry_run=False,
            acting_user="alice",
        )
        run_id = record.run_id
        deadline = time.time() + 15.0
        while time.time() < deadline:
            terminal = store.get(run_id)
            if terminal and terminal.status == RunStatus.SUCCEEDED:
                break
            time.sleep(0.05)
        terminal = store.get(run_id)
        assert terminal is not None and terminal.status == RunStatus.SUCCEEDED
    audit_path = tmp_path / "audit" / "generation.jsonl"
    entries = _wait_for_audit_entries(audit_path, repo_root=tmp_path)
    assert len(entries) == 1
    assert entries[0].module_name == "tf-aws-eks"
    assert entries[0].extra.get("run_id") == run_id
    assert entries[0].extra.get("publish_succeeded") is False
    assert entries[0].activity_outcome_label() == "Publish failed"
    queue.close()


def test_run_queue_marks_succeeded_before_artifact_persist_failure(tmp_path) -> None:
    store = RunStore(tmp_path / "runs.sqlite")
    output = OutputConfig(
        github_org="example",
        modules_root=tmp_path / "modules",
    )
    queue = RunQueue(
        repo_root=tmp_path,
        output_config=output,
        store=store,
        config=RunQueueConfig(max_concurrent_runs=1, queue_max_depth=4),
    )
    fake_result = {
        "blueprint": "terraform-module-generic",
        "gates_outcome": "passed",
        "gates_passed": True,
        "gates": [{"name": "docs-drift", "passed": True, "skipped": False, "message": "ok"}],
        "rendered_files": [{"path": "main.tf", "content": "# hi\n", "truncated": False}],
        "output_dir": str(tmp_path / "out"),
        "pr_message": "dry-run",
    }

    class BoomArtifacts:
        def local_staging_dir(self, repo_root: Path, run_id: str) -> Path:
            path = repo_root / "data" / "async-run-artifacts" / run_id
            path.mkdir(parents=True, exist_ok=True)
            return path

        def persist_run_artifacts(self, run_id: str, staging_dir: Path) -> dict[str, str]:
            raise RuntimeError("s3 unavailable")

        def materialize_run_artifacts(self, stored: dict[str, object]) -> Path | None:
            return None

    queue._artifact_store = BoomArtifacts()  # type: ignore[method-assign]
    with patch("repave_engine.run_queue.run_generate_api", return_value=fake_result):
        record = queue.submit(
            blueprint_name="terraform-module-generic",
            inputs={"module_name": "demo"},
            dry_run=True,
            acting_user="tester",
        )
        run_id = record.run_id
        deadline = time.time() + 5.0
        terminal = None
        while time.time() < deadline:
            terminal = store.get(run_id)
            if terminal and terminal.status == RunStatus.SUCCEEDED:
                break
            time.sleep(0.05)
        assert terminal is not None
        assert terminal.status == RunStatus.SUCCEEDED
        assert terminal.result is not None
        assert terminal.result.get("rendered_files")
    queue.close()


def test_run_queue_recovers_stalled_after_publish(tmp_path) -> None:
    from datetime import datetime, timedelta, timezone

    from repave_engine.run_events import build_run_event_store

    db = tmp_path / "runs.sqlite"
    store = RunStore(db)
    events = build_run_event_store(db)
    output = OutputConfig(github_org="example", modules_root=tmp_path / "modules")
    queue = RunQueue(
        repo_root=tmp_path,
        output_config=output,
        store=store,
        config=RunQueueConfig(max_concurrent_runs=1, queue_max_depth=4, enqueue_only=True),
        event_store=events,
    )
    record = store.create_run(
        blueprint_name="terraform-module-generic",
        dry_run=True,
        payload={"inputs": {"module_name": "demo", "cloud_provider": "aws"}},
        acting_user="tester",
    )
    store.update_status(record.run_id, RunStatus.RUNNING)
    stale = (datetime.now(timezone.utc) - timedelta(seconds=45)).isoformat()
    with store._lock, store._connect() as conn:
        conn.execute(
            "UPDATE runs SET updated_at = ? WHERE run_id = ?",
            (stale, record.run_id),
        )
        conn.commit()
    staging = queue._artifact_store.local_staging_dir(tmp_path, record.run_id)
    (staging / "main.tf").write_text("# recovered\n", encoding="utf-8")
    events.append(record.run_id, "stage_finished", {"stage": "gates"})
    events.append(
        record.run_id,
        "gate_finished",
        {"gate": "docs-drift", "passed": True, "skipped": False, "message": "ok"},
    )
    events.append(record.run_id, "stage_finished", {"stage": "publish"})
    events.append(
        record.run_id,
        "publish_finished",
        {"summary": "Plan preview — recovered", "succeeded": True},
    )

    recovered = queue.get(record.run_id)
    assert recovered is not None
    assert recovered.status == RunStatus.SUCCEEDED
    assert recovered.result is not None
    assert recovered.result.get("recovered_after_publish_stall") is True
    assert recovered.result["rendered_files"][0]["path"] == "main.tf"
    assert any(event.kind == "run_finished" for event in events.list_from(record.run_id))
    queue.close()


def test_run_queue_writes_audit_on_dead_letter(tmp_path) -> None:
    _enable_audit(tmp_path)
    store = RunStore(tmp_path / "runs.sqlite")
    output = OutputConfig(
        github_org="example",
        modules_root=tmp_path / "modules",
    )
    queue = RunQueue(
        repo_root=tmp_path,
        output_config=output,
        store=store,
        config=RunQueueConfig(
            max_concurrent_runs=1,
            queue_max_depth=4,
            max_attempts=1,
        ),
    )

    def boom(**kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("gate runner crashed")

    with patch("repave_engine.run_queue.run_generate_api", side_effect=boom):
        record = queue.submit(
            blueprint_name="terraform-module-generic",
            inputs={"module_name": "demo"},
            dry_run=True,
            acting_user="bob",
        )
        run_id = record.run_id
        deadline = time.time() + 15.0
        while time.time() < deadline:
            terminal = store.get(run_id)
            if terminal and terminal.status == RunStatus.DEAD_LETTER:
                break
            time.sleep(0.05)
        terminal = store.get(run_id)
        assert terminal is not None and terminal.status == RunStatus.DEAD_LETTER
    audit_path = tmp_path / "audit" / "generation.jsonl"
    entries = _wait_for_audit_entries(audit_path, repo_root=tmp_path)
    assert len(entries) == 1
    assert entries[0].gates_outcome == "failed"
    assert entries[0].extra.get("run_id") == run_id
    assert "gate runner crashed" in str(entries[0].extra.get("error"))
    queue.close()
