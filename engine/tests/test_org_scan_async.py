"""Async org scan via run queue."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

from repave_engine.org_import_scan import (
    ORG_SCAN_SENTINEL,
    ScannedRepository,
    scan_github_org,
)
from repave_engine.run_queue import RunQueue, RunQueueConfig
from repave_engine.run_store import RunStatus, RunStore
from repave_engine.run_submit import is_org_scan_run, submit_async_run
from repave_engine.settings import OutputConfig


def test_scan_github_org_emits_progress_events() -> None:
    events: list[tuple[str, dict[str, object]]] = []

    def on_event(kind: str, payload: dict[str, object]) -> None:
        events.append((kind, payload))

    listed = (
        ScannedRepository(
            url="https://github.com/acme/mod-a",
            owner="acme",
            name="mod-a",
            governed=False,
            classification_error=None,
            top_candidate=None,
        ),
        ScannedRepository(
            url="https://github.com/acme/mod-b",
            owner="acme",
            name="mod-b",
            governed=False,
            classification_error=None,
            top_candidate=None,
        ),
    )

    with (
        patch(
            "repave_engine.org_import_scan.discover_org_repositories",
            return_value=(
                [
                    type("OrgRepo", (), {"owner": "acme", "name": "mod-a"})(),
                    type("OrgRepo", (), {"owner": "acme", "name": "mod-b"})(),
                ],
                "list",
                None,
                False,
            ),
        ),
        patch(
            "repave_engine.org_import_scan.classify_remote_repository",
            side_effect=listed,
        ),
        patch(
            "repave_engine.org_import_scan._matches_scan_filters",
            return_value=True,
        ),
    ):
        result = scan_github_org(
            "acme",
            Path("/tmp"),
            "token",
            on_event=on_event,
        )

    assert result.listed == 2
    assert len(result.repos) == 2
    assert events[0][0] == "org_scan_started"
    assert events[0][1]["listed"] == 2
    progress_kinds = [kind for kind, _ in events if kind == "org_scan_progress"]
    assert len(progress_kinds) == 2
    assert events[-1][0] == "org_scan_finished"
    assert events[-1][1]["matched"] == 2


def test_submit_and_queue_org_scan(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    store = RunStore(tmp_path / "runs.sqlite")
    output = OutputConfig(github_org="acme", modules_root=tmp_path / "modules")
    queue = RunQueue(
        repo_root=tmp_path,
        output_config=output,
        store=store,
        config=RunQueueConfig(max_concurrent_runs=1, queue_max_depth=4),
    )
    fake_result = {
        "org": "acme",
        "listed": 3,
        "limit": 100,
        "truncated": False,
        "discovery_mode": "list",
        "search_query": None,
        "repos": [
            {
                "url": "https://github.com/acme/vpc",
                "owner": "acme",
                "name": "vpc",
                "governed": False,
                "classification_error": None,
                "top_candidate": None,
            }
        ],
    }
    with patch("repave_engine.run_queue.run_org_scan", return_value=fake_result):
        record = submit_async_run(
            queue,
            payload={
                "kind": "org_scan",
                "inputs": {
                    "org": "acme",
                    "families": ["terraform"],
                    "skip_governed": True,
                    "limit": 100,
                },
            },
            acting_user="tester",
            repo_root=tmp_path,
        )
        assert is_org_scan_run(record)
        assert record.blueprint_name == ORG_SCAN_SENTINEL
        assert record.payload["kind"] == "org_scan"
        assert record.payload["inputs"]["org"] == "acme"

        deadline = time.time() + 5.0
        terminal = None
        while time.time() < deadline:
            terminal = store.get(record.run_id)
            if terminal and terminal.status == RunStatus.SUCCEEDED:
                break
            time.sleep(0.05)
        assert terminal is not None
        assert terminal.result["org"] == fake_result["org"]
        assert terminal.result["listed"] == fake_result["listed"]
        assert terminal.result["repos"] == fake_result["repos"]
    queue.close()


def test_api_v2_github_org_scan_async(tmp_path, output_config, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from repave_engine.api import create_app

    (tmp_path / "repave.config.yaml").write_text(
        "durability:\n  async_generation: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))
    with patch(
        "repave_engine.run_queue.run_org_scan",
        return_value={
            "org": "acme",
            "listed": 1,
            "limit": 100,
            "truncated": False,
            "discovery_mode": "list",
            "search_query": None,
            "repos": [],
        },
    ):
        response = client.post(
            "/api/v2/github/org-scan",
            json={"org": "acme", "async": True},
        )
    assert response.status_code == 202
    body = response.json()
    assert body["kind"] == "org_scan"
    assert body["run_id"]
    assert body["status"] == "queued"


def test_org_scan_result_page(tmp_path, output_config, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from repave_engine.api import create_app
    from repave_engine.run_store import RunStatus
    from repave_engine.run_submit import submit_async_run

    (tmp_path / "repave.config.yaml").write_text(
        "durability:\n  async_generation: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))
    queue = client.app.state.run_queue
    assert queue is not None
    fake_result = {
        "org": "acme",
        "listed": 2,
        "limit": 100,
        "truncated": False,
        "discovery_mode": "search",
        "search_query": "org:acme language:HCL",
        "repos": [
            {
                "url": "https://github.com/acme/vpc",
                "owner": "acme",
                "name": "vpc",
                "governed": False,
                "classification_error": None,
                "top_candidate": {
                    "family": "terraform",
                    "artifact_type": "terraform-module",
                    "percent": 100,
                    "evidence": ["main.tf"],
                },
            }
        ],
    }
    try:
        with patch("repave_engine.run_queue.run_org_scan", return_value=fake_result):
            record = submit_async_run(
                queue,
                payload={
                    "kind": "org_scan",
                    "inputs": {"org": "acme", "families": ["terraform"]},
                },
                acting_user="tester",
                repo_root=tmp_path,
            )
            deadline = time.time() + 5.0
            while time.time() < deadline:
                terminal = queue.get(record.run_id)
                if terminal and terminal.status == RunStatus.SUCCEEDED:
                    break
                time.sleep(0.05)
            assert terminal is not None
            assert terminal.status == RunStatus.SUCCEEDED

            page = client.get(f"/runs/{record.run_id}/result")
            assert page.status_code == 200
            assert "Organization scan" in page.text
            assert "data-org-scan-add-to-batch" in page.text
            assert "https://github.com/acme/vpc" in page.text
    finally:
        queue.close()
