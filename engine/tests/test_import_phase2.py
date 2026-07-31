"""Tests for import path overrides, trees-API preview, and GitHub rate-limit backoff."""

from __future__ import annotations

import time
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

from repave_engine.github_client import StaticGitHubRestClient, UrllibGitHubRestClient
from repave_engine.github_inventory import (
    inventory_github_paths,
    parse_github_repository,
    resolve_batch_targets,
)
from repave_engine.github_rate_limit import GitHubRateLimitTracker, clear_rate_limit_tracker
from repave_engine.import_rules import (
    OVERRIDE_KEEP,
    OVERRIDE_QUARANTINE,
    ImportRuleSet,
    classify_path,
    parse_path_overrides,
)
from repave_engine.repo_import import path_only_layout_hash, plan_import_remote


def test_parse_path_overrides_accepts_strings_and_objects() -> None:
    parsed = parse_path_overrides(
        {
            "legacy/main.tf": "main.tf",
            "junk.txt": OVERRIDE_QUARANTINE,
            "README.md": {"keep": True},
        }
    )
    assert parsed["legacy/main.tf"] == "main.tf"
    assert parsed["junk.txt"] == OVERRIDE_QUARANTINE
    assert parsed["README.md"] == OVERRIDE_KEEP


def test_classify_path_honours_destination_override() -> None:
    rules = ImportRuleSet()
    outcome = classify_path(
        "terraform/main.tf",
        rules,
        path_overrides={"terraform/main.tf": "network.tf"},
    )
    assert outcome.destination == "network.tf"
    assert "override" in outcome.reason


def test_classify_path_honours_keep_override() -> None:
    rules = ImportRuleSet()
    outcome = classify_path(
        "orphan.py",
        rules,
        path_overrides={"orphan.py": OVERRIDE_KEEP},
    )
    assert outcome.destination == "orphan.py"
    assert outcome.kept is True


def test_inventory_github_paths_filters_blobs() -> None:
    client = StaticGitHubRestClient(
        responses={
            ("GET", "/repos/acme/mod"): {"default_branch": "main"},
            ("GET", "/repos/acme/mod/git/ref/heads/main"): {"object": {"sha": "abc123"}},
            (
                "GET",
                "/repos/acme/mod/git/trees/abc123?recursive=1",
            ): {
                "truncated": False,
                "tree": [
                    {"path": "main.tf", "type": "blob"},
                    {"path": "README.md", "type": "blob"},
                    {"path": "modules", "type": "tree"},
                ],
            },
        }
    )
    with patch("repave_engine.github_inventory._github_json", side_effect=client.request_json):
        paths = inventory_github_paths("acme", "mod", "token")
    assert paths == ("README.md", "main.tf")


def test_parse_github_repository_normalizes_urls() -> None:
    assert parse_github_repository("https://github.com/acme/mod.git") == ("acme", "mod")
    assert parse_github_repository("git@github.com:acme/mod") == ("acme", "mod")


def test_resolve_batch_targets_deduplicates() -> None:
    targets = resolve_batch_targets(
        ["https://github.com/acme/a", "https://github.com/acme/a"],
        token=None,
    )
    assert targets == ["https://github.com/acme/a"]


def test_rate_limit_tracker_waits_when_remaining_is_low(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_rate_limit_tracker()
    tracker = GitHubRateLimitTracker()
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(time, "sleep", fake_sleep)
    tracker.update_from_headers(
        {
            "x-ratelimit-remaining": "1",
            "x-ratelimit-limit": "5000",
            "x-ratelimit-reset": str(int(time.time()) + 30),
        },
        installation_id="test",
    )
    tracker.wait_if_needed(installation_id="test", min_remaining=50)
    assert sleeps and sleeps[0] > 0


def test_urllib_client_retries_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def fake_urlopen(request, timeout=30):
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "rate limit",
                {"Retry-After": "0"},
                None,
            )
        payload = b'{"ok": true}'

        class Response:
            def __init__(self) -> None:
                self.headers = {
                    "x-ratelimit-remaining": "4999",
                    "x-ratelimit-reset": "9999999999",
                }

            def read(self) -> bytes:
                return payload

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    client = UrllibGitHubRestClient(max_retries=2)
    result = client.request_json("GET", "/rate_limit", "token")
    assert result == {"ok": True}
    assert calls["count"] == 2


def test_plan_import_remote_builds_limited_preview(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "repave_engine.repo_import.remote_has_provenance",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        "repave_engine.repo_import.inventory_github_paths",
        lambda *args, **kwargs: ("main.tf", "README.md"),
    )
    monkeypatch.setattr(
        "repave_engine.repo_import._fetch_terraform_texts",
        lambda *args, **kwargs: {"main.tf": 'resource "aws_vpc" "main" {}'},
    )

    plan = plan_import_remote(
        "https://github.com/acme/legacy-vpc",
        repo_root,
        git_token="token",
    )
    assert plan.preview_limited is True
    assert plan.remote is True
    assert plan.source_layout_hash == path_only_layout_hash(("README.md", "main.tf"))
    assert not plan.gates
