"""Tests for GitHub org scan and remote repository classification."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from repave_engine.github_client import GitHubError, StaticGitHubRestClient
from repave_engine.github_inventory import OrgRepository, list_org_repositories
from repave_engine.org_import_scan import classify_remote_repository, scan_github_org


def _terraform_tree_responses(
    owner: str, repo: str
) -> tuple[dict[tuple[str, str], object], dict[tuple[str, str], GitHubError]]:
    responses: dict[tuple[str, str], object] = {
        ("GET", f"/repos/{owner}/{repo}"): {"default_branch": "main"},
        ("GET", f"/repos/{owner}/{repo}/git/ref/heads/main"): {"object": {"sha": "abc123"}},
        (
            "GET",
            f"/repos/{owner}/{repo}/git/trees/abc123?recursive=1",
        ): {
            "truncated": False,
            "tree": [
                {"path": "main.tf", "type": "blob"},
                {"path": "variables.tf", "type": "blob"},
                {"path": "outputs.tf", "type": "blob"},
            ],
        },
    }
    errors = {
        ("GET", f"/repos/{owner}/{repo}/contents/repave.yaml"): GitHubError(404, "not found"),
    }
    return responses, errors


def test_list_org_repositories_returns_repos() -> None:
    client = StaticGitHubRestClient(
        responses={
            (
                "GET",
                "/orgs/acme/repos?per_page=3&page=1&type=all",
            ): [
                {
                    "name": "mod-a",
                    "clone_url": "https://github.com/acme/mod-a.git",
                    "html_url": "https://github.com/acme/mod-a",
                    "owner": {"login": "acme"},
                    "archived": False,
                    "fork": False,
                    "default_branch": "main",
                },
                {
                    "name": "mod-b",
                    "clone_url": "https://github.com/acme/mod-b.git",
                    "html_url": "https://github.com/acme/mod-b",
                    "owner": {"login": "acme"},
                    "archived": False,
                    "fork": False,
                    "default_branch": "main",
                },
            ],
        }
    )
    with patch("repave_engine.github_inventory._github_json", side_effect=client.request_json):
        repos = list_org_repositories("acme", "token", limit=3)
    assert len(repos) == 2
    assert repos[0].name == "mod-a"


def test_list_org_repositories_fetches_next_page_when_first_is_full() -> None:
    first_page = [
        {
            "name": f"mod-{index}",
            "clone_url": f"https://github.com/acme/mod-{index}.git",
            "html_url": f"https://github.com/acme/mod-{index}",
            "owner": {"login": "acme"},
            "archived": False,
            "fork": False,
            "default_branch": "main",
        }
        for index in range(100)
    ]
    client = StaticGitHubRestClient(
        responses={
            ("GET", "/orgs/acme/repos?per_page=100&page=1&type=all"): first_page,
            ("GET", "/orgs/acme/repos?per_page=5&page=2&type=all"): [
                {
                    "name": "mod-last",
                    "clone_url": "https://github.com/acme/mod-last.git",
                    "html_url": "https://github.com/acme/mod-last",
                    "owner": {"login": "acme"},
                    "archived": False,
                    "fork": False,
                    "default_branch": "main",
                },
            ],
        }
    )
    with patch("repave_engine.github_inventory._github_json", side_effect=client.request_json):
        repos = list_org_repositories("acme", "token", limit=105)
    assert len(repos) == 101
    assert repos[-1].name == "mod-last"


def test_classify_remote_repository_detects_terraform(repo_root: Path) -> None:
    responses, errors = _terraform_tree_responses("acme", "vpc")
    client = StaticGitHubRestClient(responses=responses, errors=errors)
    with patch("repave_engine.github_inventory._github_json", side_effect=client.request_json):
        row = classify_remote_repository("acme", "vpc", "token", repo_root)
    assert row.governed is False
    assert row.top_candidate is not None
    assert row.top_candidate.family == "terraform"
    assert row.top_candidate.artifact_type == "terraform-module"


def test_classify_remote_repository_marks_governed_repos(repo_root: Path) -> None:
    client = StaticGitHubRestClient(
        responses={
            ("GET", "/repos/acme/governed/contents/repave.yaml"): {
                "encoding": "base64",
                "content": "eHk=\n",
            },
        }
    )
    with patch("repave_engine.github_inventory._github_json", side_effect=client.request_json):
        row = classify_remote_repository("acme", "governed", "token", repo_root)
    assert row.governed is True
    assert row.top_candidate is None


def test_scan_github_org_filters_by_family(repo_root: Path) -> None:
    org_repos = (
        OrgRepository(
            owner="acme",
            name="vpc",
            clone_url="https://github.com/acme/vpc.git",
            html_url="https://github.com/acme/vpc",
            archived=False,
            fork=False,
            default_branch="main",
        ),
        OrgRepository(
            owner="acme",
            name="role",
            clone_url="https://github.com/acme/role.git",
            html_url="https://github.com/acme/role",
            archived=False,
            fork=False,
            default_branch="main",
        ),
    )
    ansible_responses = {
        ("GET", "/repos/acme/role"): {"default_branch": "main"},
        ("GET", "/repos/acme/role/git/ref/heads/main"): {"object": {"sha": "role-sha"}},
        (
            "GET",
            "/repos/acme/role/git/trees/role-sha?recursive=1",
        ): {
            "truncated": False,
            "tree": [
                {"path": "meta/main.yml", "type": "blob"},
                {"path": "tasks/main.yml", "type": "blob"},
            ],
        },
    }
    ansible_errors = {
        ("GET", "/repos/acme/role/contents/repave.yaml"): GitHubError(404, "not found"),
    }
    tf_responses, tf_errors = _terraform_tree_responses("acme", "vpc")
    responses = {**tf_responses, **ansible_responses}
    errors = {**tf_errors, **ansible_errors}
    client = StaticGitHubRestClient(responses=responses, errors=errors)

    with (
        patch(
            "repave_engine.org_import_scan.list_org_repositories",
            return_value=org_repos,
        ),
        patch("repave_engine.github_inventory._github_json", side_effect=client.request_json),
    ):
        result = scan_github_org(
            "acme",
            repo_root,
            "token",
            families=frozenset({"terraform"}),
            skip_governed=True,
            limit=10,
        )
    assert result.listed == 2
    assert len(result.repos) == 1
    assert result.repos[0].name == "vpc"
    assert result.repos[0].top_candidate is not None
    assert result.repos[0].top_candidate.family == "terraform"


def test_scan_github_org_rejects_unknown_families(repo_root: Path) -> None:
    with pytest.raises(ValueError, match="unknown artifact families"):
        scan_github_org(
            "acme",
            repo_root,
            "token",
            families=frozenset({"not-a-family"}),
        )
