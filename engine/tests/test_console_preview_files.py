from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.portal_generate import console_preview_files_from_record
from repave_engine.run_store import RunRecord, RunStatus

_REPAVE_JS = Path(__file__).resolve().parents[1] / "src" / "repave_engine" / "static" / "repave.js"


def test_console_preview_files_from_record_dry_run_snapshot() -> None:
    record = RunRecord(
        run_id="run-1",
        status=RunStatus.SUCCEEDED,
        blueprint_name="terraform-module-generic",
        dry_run=True,
        client_request_id=None,
        acting_user="tester",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        payload={"inputs": {}},
        result={
            "rendered_files": [
                {"path": "main.tf", "content": "# hi\n", "truncated": False},
            ],
        },
    )
    files = console_preview_files_from_record(record)
    assert len(files) == 1
    assert files[0]["path"] == "main.tf"
    assert files[0]["content"] == "# hi\n"


def test_console_preview_files_skips_incomplete_runs() -> None:
    record = RunRecord(
        run_id="run-2",
        status=RunStatus.RUNNING,
        blueprint_name="terraform-module-generic",
        dry_run=True,
        client_request_id=None,
        acting_user="tester",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        payload={"inputs": {}},
        result={
            "rendered_files": [
                {"path": "main.tf", "content": "# hi\n", "truncated": False},
            ],
        },
    )
    assert console_preview_files_from_record(record) == ()


def test_run_console_ssr_preview_when_succeeded(
    repo_root: Path,
    output_config,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("REPAVE_ASYNC_GENERATION", "true")
    runs_db = tmp_path / "runs.sqlite"
    monkeypatch.setenv("REPAVE_RUNS_DB", str(runs_db))
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    queue = client.app.state.run_queue
    assert queue is not None
    record = queue._store.create_run(
        blueprint_name="terraform-module-generic",
        dry_run=True,
        payload={"inputs": {"module_name": "demo", "cloud_provider": "aws"}},
        acting_user="tester",
    )
    queue._store.update_status(
        record.run_id,
        RunStatus.SUCCEEDED,
        result={
            "gates_outcome": "passed",
            "gates": [{"name": "docs-drift", "passed": True, "skipped": False, "message": "ok"}],
            "rendered_files": [
                {"path": "README.md", "content": "# demo\n", "truncated": False},
                {
                    "path": "main.tf",
                    "content": 'resource "null_resource" "x" {}\n',
                    "truncated": False,
                },
            ],
        },
    )
    page = client.get(f"/runs/{record.run_id}")
    assert page.status_code == 200
    assert "data-run-file-preview-json" in page.text
    assert "README.md" in page.text
    assert "# demo" in page.text
    assert "Browse generated files" in page.text
    # Succeeded runs must not keep the CTA / preview shell hidden.
    assert "data-run-complete-actions hidden" not in page.text


def test_run_result_redirects_while_still_running(
    repo_root: Path,
    output_config,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Browse/result must not 400 with 'Run is not complete' during the succeed race."""
    monkeypatch.setenv("REPAVE_ASYNC_GENERATION", "true")
    monkeypatch.setenv("REPAVE_RUNS_DB", str(tmp_path / "runs.sqlite"))
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    queue = client.app.state.run_queue
    assert queue is not None
    record = queue._store.create_run(
        blueprint_name="terraform-module-generic",
        dry_run=True,
        payload={"inputs": {"module_name": "demo", "cloud_provider": "aws"}},
        acting_user="tester",
    )
    queue._store.update_status(record.run_id, RunStatus.RUNNING)
    page = client.get(f"/runs/{record.run_id}/result", follow_redirects=False)
    assert page.status_code == 303
    assert page.headers.get("location") == f"/runs/{record.run_id}"


def test_run_console_js_polls_dry_run_preview_after_run_complete() -> None:
    """run_finished sets runComplete before rendered_files exist — polling must continue."""
    js = _REPAVE_JS.read_text(encoding="utf-8")
    assert "function pollUntilTerminal" in js
    assert "previewSettled" in js
    assert "revealDryRunBrowseFallback" in js
    # Guard must be dry-run aware; a bare `if (runComplete) return` re-broke plan preview.
    assert "if (runComplete && !isDryRun)" in js
    assert "Plan complete — loading file preview…" in js
    assert "Plan preview ready — browse files below" in js
    assert "Could not load run status — refresh and sign in again" in js
    assert "Run not found — refresh or return to Runs" in js


def test_run_console_js_browse_waits_until_succeeded() -> None:
    """Browse must not navigate while RUNNING — /result 303s back to the console."""
    js = _REPAVE_JS.read_text(encoding="utf-8")
    assert "browsePending" in js
    assert "runStatusIsSucceeded" in js
    assert "Still saving preview — opening Browse when ready…" in js
    assert "Never unhide Browse while status is still running" in js
    assert "/result → console 303 loop" in js
    assert "resultCta.click()" in js
    assert "window.location.assign(resultUrl)" not in js
    assert "window.location.assign(dest)" not in js
