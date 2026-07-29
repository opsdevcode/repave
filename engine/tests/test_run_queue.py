from __future__ import annotations

import time
from unittest.mock import patch

from repave_engine.run_queue import RunQueue, RunQueueConfig
from repave_engine.run_store import RunStatus, RunStore
from repave_engine.settings import OutputConfig


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
