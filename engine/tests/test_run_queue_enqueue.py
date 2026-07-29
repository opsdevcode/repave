from __future__ import annotations

import time
from unittest.mock import patch

from repave_engine.run_queue import RunQueue, RunQueueConfig
from repave_engine.run_store import RunStatus, RunStore
from repave_engine.settings import OutputConfig


def test_enqueue_only_does_not_execute(tmp_path) -> None:
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
            enqueue_only=True,
        ),
    )
    with patch("repave_engine.run_queue.run_generate_api") as mock_gen:
        record = queue.submit(
            blueprint_name="terraform-module-generic",
            inputs={"module_name": "demo"},
            dry_run=True,
            acting_user="tester",
        )
        time.sleep(0.2)
        terminal = store.get(record.run_id)
        assert terminal is not None
        assert terminal.status == RunStatus.QUEUED
        mock_gen.assert_not_called()
    queue.close()
