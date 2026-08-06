"""Tests for platform feedback capture and rollup."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.feedback import (
    build_feedback_event,
    build_feedback_rollup,
    normalize_friction_tags,
    validate_csat,
)
from repave_engine.feedback_store import (
    append_feedback_event,
    read_feedback_events,
)
from repave_engine.settings import load_platform_metrics_config


def test_validate_csat_range() -> None:
    assert validate_csat(3) == 3
    try:
        validate_csat(0)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    try:
        validate_csat("bad")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_normalize_friction_tags_dedupes() -> None:
    tags = normalize_friction_tags(["slow", "slow", "other"])
    assert tags == ("slow", "other")


def test_build_feedback_rollup_aggregates() -> None:
    events = [
        build_feedback_event(
            submitted_at="2026-01-01T00:00:00Z",
            csat=5,
            friction_tags=("slow",),
            comment="",
            blueprint_name="helm-chart-generic",
            blueprint_version="1.0.0",
            dry_run=True,
            gates_outcome="passed",
            acting_user="alice",
            surface="result",
        ),
        build_feedback_event(
            submitted_at="2026-01-02T00:00:00Z",
            csat=3,
            friction_tags=("gates-heavy",),
            comment="too many gates",
            blueprint_name="helm-chart-generic",
            blueprint_version="1.0.0",
            dry_run=False,
            gates_outcome="failed",
            acting_user="bob",
            surface="run_console",
        ),
    ]
    rollup = build_feedback_rollup(events)
    assert rollup.event_count == 2
    assert rollup.csat_average == 4.0
    assert rollup.friction_tags[0].tag == "slow"
    assert rollup.by_blueprint[0].blueprint_name == "helm-chart-generic"
    assert rollup.by_surface == (("result", 1), ("run_console", 1))


def test_load_platform_metrics_config_feedback_file(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\n"
        "platform_metrics:\n"
        "  enabled: true\n"
        "  snapshot_file: data/metrics.jsonl\n"
        "  feedback_file: data/feedback.jsonl\n",
        encoding="utf-8",
    )
    config = load_platform_metrics_config(tmp_path)
    assert config is not None
    assert config.feedback_file == (tmp_path / "data" / "feedback.jsonl").resolve()

    monkeypatch.setenv("REPAVE_PLATFORM_FEEDBACK_FILE", str(tmp_path / "override.jsonl"))
    overridden = load_platform_metrics_config(tmp_path)
    assert overridden is not None
    assert overridden.feedback_file == tmp_path / "override.jsonl"


def test_feedback_roundtrip_jsonl(tmp_path: Path) -> None:
    feedback_path = tmp_path / "feedback.jsonl"
    event = build_feedback_event(
        submitted_at="2026-01-01T00:00:00Z",
        csat=4,
        friction_tags=("missing-docs",),
        comment="needs examples",
        blueprint_name="app-service-generic",
        blueprint_version="2.0.0",
        dry_run=False,
        gates_outcome="passed",
        acting_user="alice",
        run_id="run-1",
        surface="result",
    )
    append_feedback_event(feedback_path, event, repo_root=None)
    loaded = read_feedback_events(feedback_path, limit=5)
    assert len(loaded) == 1
    assert loaded[0].csat == 4
    assert loaded[0].friction_tags == ("missing-docs",)


def test_platform_feedback_page_and_api(
    repo_root: Path,
    output_config,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("REPAVE_PLATFORM_METRICS", "1")
    monkeypatch.setenv("REPAVE_PLATFORM_METRICS_FILE", str(tmp_path / "snaps.jsonl"))
    monkeypatch.setenv("REPAVE_PLATFORM_FEEDBACK_FILE", str(tmp_path / "feedback.jsonl"))
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    page = client.get("/platform/feedback")
    assert page.status_code == 200
    assert "Developer feedback" in page.text
    assert 'href="/platform/feedback"' in page.text

    post = client.post(
        "/api/v2/platform/feedback",
        json={
            "csat": 5,
            "friction_tags": ["slow"],
            "comment": "smooth",
            "blueprint_name": "helm-chart-generic",
            "blueprint_version": "1.0.0",
            "dry_run": True,
            "gates_outcome": "passed",
            "surface": "result",
            "run_id": "run-abc",
        },
    )
    assert post.status_code == 201
    body = post.json()
    assert body["csat"] == 5
    assert body["blueprint_name"] == "helm-chart-generic"

    api = client.get("/api/v2/platform/feedback")
    assert api.status_code == 200
    rollup = api.json()
    assert rollup["rollup"]["event_count"] == 1
    assert len(rollup["events"]) == 1


def test_platform_feedback_api_404_when_disabled(repo_root, output_config, monkeypatch) -> None:
    monkeypatch.delenv("REPAVE_PLATFORM_METRICS", raising=False)
    monkeypatch.delenv("REPAVE_PLATFORM_FEEDBACK_FILE", raising=False)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    assert client.get("/api/v2/platform/feedback").status_code == 404
    assert (
        client.post(
            "/api/v2/platform/feedback",
            json={"csat": 3, "blueprint_name": "x", "surface": "result"},
        ).status_code
        == 404
    )


def test_platform_feedback_post_validates_csat(
    repo_root: Path,
    output_config,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("REPAVE_PLATFORM_METRICS", "1")
    monkeypatch.setenv("REPAVE_PLATFORM_FEEDBACK_FILE", str(tmp_path / "feedback.jsonl"))
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/api/v2/platform/feedback",
        json={
            "csat": 9,
            "blueprint_name": "helm-chart-generic",
            "surface": "result",
        },
    )
    assert response.status_code == 400
