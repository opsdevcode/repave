from __future__ import annotations

from pathlib import Path

from repave_engine.gates import run_gates
from repave_engine.run_events import TERMINAL_EVENT_KINDS, RunEventStore


def test_run_event_store_append_and_list(tmp_path: Path) -> None:
    store = RunEventStore(tmp_path / "events.sqlite")
    first = store.append("run-1", "run_started", {"blueprint": "demo"})
    second = store.append("run-1", "gate_started", {"gate": "fmt"})
    assert first.seq == 1
    assert second.seq == 2
    replay = store.list_from("run-1", after_seq=0)
    assert len(replay) == 2
    assert replay[0].kind == "run_started"
    assert store.list_from("run-1", after_seq=1)[0].kind == "gate_started"


def test_run_event_store_wait_for_events(tmp_path: Path) -> None:
    store = RunEventStore(tmp_path / "events.sqlite")
    store.append("run-2", "run_started", {})
    waited = store.wait_for_events("run-2", after_seq=0, timeout_seconds=0.01)
    assert waited


def test_run_gates_on_event_callback(tmp_path: Path) -> None:
    output_dir = tmp_path / "module"
    output_dir.mkdir()
    (output_dir / "README.md").write_text("# demo", encoding="utf-8")
    events: list[tuple[str, dict]] = []

    def on_event(kind: str, payload: dict) -> None:
        events.append((kind, payload))

    results = run_gates(
        output_dir,
        ("docs-drift",),
        require_run=False,
        on_event=on_event,
    )
    assert results
    kinds = [kind for kind, _payload in events]
    assert "gate_started" in kinds
    assert "gate_finished" in kinds


def test_run_gates_without_on_event_unchanged(tmp_path: Path) -> None:
    output_dir = tmp_path / "module"
    output_dir.mkdir()
    (output_dir / "README.md").write_text("# demo", encoding="utf-8")
    baseline = run_gates(output_dir, ("docs-drift",), require_run=False)
    with_callback = run_gates(
        output_dir,
        ("docs-drift",),
        require_run=False,
        on_event=lambda _k, _p: None,
    )
    assert len(baseline) == len(with_callback)
    assert baseline[0].passed == with_callback[0].passed
    assert baseline[0].message == with_callback[0].message


def test_terminal_event_kinds_include_run_finished() -> None:
    assert "run_finished" in TERMINAL_EVENT_KINDS
    assert "run_failed" in TERMINAL_EVENT_KINDS
