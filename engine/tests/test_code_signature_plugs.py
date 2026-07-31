from __future__ import annotations

import sqlite3

import pytest

from repave_engine.github import GitHubError, _github_json
from repave_engine.github_client import StaticGitHubRestClient
from repave_engine.sql_store import is_unique_constraint_error
from repave_engine.upgrade_api import UpgradeTargetError, resolve_upgrade_target_outcome


def test_is_unique_constraint_error_sqlite() -> None:
    assert is_unique_constraint_error(sqlite3.IntegrityError("unique"))


def test_is_unique_constraint_error_other() -> None:
    assert not is_unique_constraint_error(ValueError("unique"))


def test_static_github_rest_client_returns_canned_response() -> None:
    client = StaticGitHubRestClient(
        responses={("GET", "/repos/acme/mod"): {"full_name": "acme/mod"}},
    )
    payload = _github_json("GET", "/repos/acme/mod", "token", client=client)
    assert payload == {"full_name": "acme/mod"}
    assert client.calls == [("GET", "/repos/acme/mod", None)]


def test_static_github_rest_client_raises_configured_error() -> None:
    client = StaticGitHubRestClient(
        errors={("GET", "/repos/acme/missing"): GitHubError(404, "not found")},
    )
    with pytest.raises(GitHubError) as exc:
        _github_json("GET", "/repos/acme/missing", "token", client=client)
    assert exc.value.status == 404


def test_resolve_upgrade_target_outcome_missing_input() -> None:
    outcome = resolve_upgrade_target_outcome(target_repo="", repo_url=None)
    assert not outcome.ok
    assert outcome.target is None
    assert isinstance(outcome.error, UpgradeTargetError)
