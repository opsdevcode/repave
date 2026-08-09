from __future__ import annotations

import time
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
        deadline = time.time() + 5.0
        while time.time() < deadline:
            terminal = store.get(run_id)
            if terminal and terminal.status == RunStatus.SUCCEEDED:
                break
            time.sleep(0.05)
    audit_path = tmp_path / "audit" / "generation.jsonl"
    entries = read_recent_audit_entries(audit_path, limit=5, repo_root=tmp_path)
    assert len(entries) == 1
    assert entries[0].module_name == "tf-aws-eks"
    assert entries[0].extra.get("run_id") == run_id
    assert entries[0].extra.get("publish_succeeded") is False
    assert entries[0].activity_outcome_label() == "Publish failed"
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
        deadline = time.time() + 5.0
        while time.time() < deadline:
            terminal = store.get(run_id)
            if terminal and terminal.status == RunStatus.DEAD_LETTER:
                break
            time.sleep(0.05)
    audit_path = tmp_path / "audit" / "generation.jsonl"
    entries = read_recent_audit_entries(audit_path, limit=5, repo_root=tmp_path)
    assert len(entries) == 1
    assert entries[0].gates_outcome == "failed"
    assert entries[0].extra.get("run_id") == run_id
    assert "gate runner crashed" in str(entries[0].extra.get("error"))
    queue.close()
