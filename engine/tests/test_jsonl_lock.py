from __future__ import annotations

import json
import multiprocessing
from pathlib import Path

from repave_engine.audit import AuditRecord, append_audit_record
from repave_engine.jsonl_lock import append_jsonl_line


def _append_worker(path: str, index: int) -> None:
    append_jsonl_line(Path(path), json.dumps({"index": index}))


def test_parallel_jsonl_appends_parse(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    processes = [
        multiprocessing.Process(target=_append_worker, args=(str(path), index))
        for index in range(20)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join()
        assert process.exitcode == 0

    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 20
    payloads = [json.loads(line) for line in lines]
    assert {item["index"] for item in payloads} == set(range(20))


def test_audit_uses_locked_append(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    append_audit_record(
        path,
        AuditRecord(
            event="generation",
            blueprint_name="demo",
            blueprint_version="1.0.0",
            module_name="mod",
            dry_run=True,
            gates_outcome="passed",
            repository_url=None,
            acting_user="tester",
        ),
    )
    assert json.loads(path.read_text(encoding="utf-8").strip())["acting_user"] == "tester"
