from __future__ import annotations

import json
import multiprocessing
from pathlib import Path
from unittest.mock import patch

from repave_engine.audit import AuditRecord, append_audit_record
from repave_engine.fleet import FleetEntry, read_fleet, register_repo
from repave_engine.jsonl_lock import append_jsonl_line, append_jsonl_line_best_effort
from repave_engine.metrics import JSONL_APPEND_FAILURES


def _append_worker(path: str, index: int) -> None:
    append_jsonl_line(Path(path), json.dumps({"index": index}))


def _audit_worker(path: str, index: int) -> None:
    append_audit_record(
        Path(path),
        AuditRecord(
            event="generation",
            blueprint_name="demo",
            blueprint_version="1.0.0",
            module_name=f"mod-{index}",
            dry_run=True,
            gates_outcome="passed",
            repository_url=None,
            acting_user=f"user-{index}",
        ),
    )


def _fleet_worker(path: str, index: int) -> None:
    register_repo(
        Path(path),
        FleetEntry(
            repo_url=f"https://github.com/acme/repo-{index}.git",
            blueprint_name="terraform-module-generic",
            blueprint_version="1.0.0",
            registered_by=f"user-{index}",
        ),
    )


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


def test_parallel_audit_appends_parse(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    processes = [
        multiprocessing.Process(target=_audit_worker, args=(str(path), index))
        for index in range(12)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join()
        assert process.exitcode == 0

    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 12
    payloads = [json.loads(line) for line in lines]
    assert {item["module_name"] for item in payloads} == {f"mod-{index}" for index in range(12)}


def test_parallel_fleet_registers_parse(tmp_path: Path) -> None:
    path = tmp_path / "fleet.jsonl"
    processes = [
        multiprocessing.Process(target=_fleet_worker, args=(str(path), index))
        for index in range(12)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join()
        assert process.exitcode == 0

    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 12
    payloads = [json.loads(line) for line in lines]
    assert {item["repo_url"] for item in payloads} == {
        f"https://github.com/acme/repo-{index}" for index in range(12)
    }
    assert len(read_fleet(path)) == 12


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


def test_jsonl_append_failure_increments_metric(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    before = JSONL_APPEND_FAILURES.labels(store="audit")._value.get()

    with patch.object(Path, "open", side_effect=OSError("disk full")):
        assert append_jsonl_line_best_effort(path, "{}", store="audit") is False

    after = JSONL_APPEND_FAILURES.labels(store="audit")._value.get()
    assert after == before + 1


def test_jsonl_append_failure_metric_on_raise(tmp_path: Path) -> None:
    path = tmp_path / "fleet.jsonl"
    before = JSONL_APPEND_FAILURES.labels(store="fleet")._value.get()

    with patch.object(Path, "open", side_effect=OSError("disk full")):
        try:
            append_jsonl_line(path, "{}", store="fleet")
        except OSError:
            pass
        else:
            raise AssertionError("expected OSError")

    after = JSONL_APPEND_FAILURES.labels(store="fleet")._value.get()
    assert after == before + 1
