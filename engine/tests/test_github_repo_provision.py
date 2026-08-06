from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.github_client import GitHubError, StaticGitHubRestClient
from repave_engine.github_repo_provision import (
    build_provision_spec,
    create_repository_from_selection,
    create_repository_from_template,
    ensure_team_repo_permission,
    list_org_teams,
    plan_provision,
    provision_github_repository,
)
from repave_engine.settings import OutputConfig
from repave_engine.target_repo import resolve_module_repository


def _repository(tmp_path: Path, name: str = "platform-demo"):
    config = OutputConfig(github_org="example-org", modules_root=tmp_path / "modules")
    return resolve_module_repository(
        module_name=name,
        config=config,
        name_template="{repo_name}",
        template_values={"repo_name": name},
    )


def test_build_provision_spec_requires_template_fields(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    with pytest.raises(ValueError, match="template_owner and template_repo"):
        build_provision_spec(
            repository=repository,
            values={"create_mode": "template", "visibility": "private"},
        )


def test_build_provision_spec_parses_teams_and_topics(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    spec = build_provision_spec(
        repository=repository,
        values={
            "create_mode": "selection",
            "visibility": "internal",
            "description": "demo",
            "topics": "platform, github, platform",
            "team_slugs": "platform-admins, developers",
            "team_permission": "maintain",
            "default_branch": "main",
        },
    )
    assert spec.create_mode == "selection"
    assert spec.visibility == "internal"
    assert spec.topics == ("platform", "github")
    assert spec.team_slugs == ("platform-admins", "developers")
    assert spec.team_permission == "maintain"


def test_plan_provision_is_dry_run(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    spec = build_provision_spec(
        repository=repository,
        values={
            "create_mode": "template",
            "template_owner": "example-org",
            "template_repo": "template-service",
            "visibility": "private",
            "team_slugs": "platform",
            "team_permission": "push",
        },
    )
    plan = plan_provision(spec)
    assert plan.create.status == "planned"
    assert plan.overlay_push == "planned"
    assert len(plan.teams) == 1
    assert plan.teams[0].status == "planned"
    assert "template-service" in plan.create.message


def test_create_repository_from_template(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    spec = build_provision_spec(
        repository=repository,
        values={
            "create_mode": "template",
            "template_owner": "example-org",
            "template_repo": "template-service",
            "visibility": "private",
            "topics": "gov",
        },
    )
    client = StaticGitHubRestClient(
        errors={("GET", f"/repos/{spec.owner}/{spec.name}"): GitHubError(404, "missing")},
        responses={
            (
                "POST",
                f"/repos/{spec.template_owner}/{spec.template_repo}/generate",
            ): {"html_url": f"https://github.com/{spec.owner}/{spec.name}"},
            ("PUT", f"/repos/{spec.owner}/{spec.name}/topics"): {},
        },
    )
    result = create_repository_from_template(spec, "ghp_test", client=client)
    assert result.status == "created"
    assert any(call[0] == "POST" and "/generate" in call[1] for call in client.calls)
    assert any(call[0] == "PUT" and call[1].endswith("/topics") for call in client.calls)


def test_create_repository_from_selection_sets_visibility(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    spec = build_provision_spec(
        repository=repository,
        values={
            "create_mode": "selection",
            "visibility": "private",
            "description": "selected repo",
            "topics": "a,b",
        },
    )
    client = StaticGitHubRestClient(
        errors={("GET", f"/repos/{spec.owner}/{spec.name}"): GitHubError(404, "missing")},
        responses={
            ("POST", f"/orgs/{spec.owner}/repos"): {"name": spec.name},
            ("PUT", f"/repos/{spec.owner}/{spec.name}/topics"): {},
        },
    )
    result = create_repository_from_selection(spec, "ghp_test", client=client)
    assert result.status == "created"
    create_call = next(call for call in client.calls if call[0] == "POST")
    assert create_call[2] is not None
    assert create_call[2]["visibility"] == "private"
    assert create_call[2]["private"] is True


def test_create_repository_from_selection_exists(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    spec = build_provision_spec(
        repository=repository,
        values={"create_mode": "selection", "visibility": "public"},
    )
    client = StaticGitHubRestClient(
        responses={("GET", f"/repos/{spec.owner}/{spec.name}"): {"name": spec.name}},
    )
    result = create_repository_from_selection(spec, "ghp_test", client=client)
    assert result.status == "exists"


def test_list_org_teams_paginates() -> None:
    client = StaticGitHubRestClient(
        responses={
            ("GET", "/orgs/example-org/teams?per_page=100&page=1"): [
                {"slug": "platform", "name": "Platform", "description": "ops"},
                {"slug": "developers", "name": "Developers"},
            ],
        },
    )
    teams = list_org_teams("example-org", "ghp_test", client=client)
    assert [team.slug for team in teams] == ["platform", "developers"]
    assert teams[0].description == "ops"


def test_ensure_team_repo_permission_success_and_failure() -> None:
    ok_client = StaticGitHubRestClient(
        responses={("PUT", "/orgs/example-org/teams/platform/repos/example-org/demo"): None},
    )
    granted = ensure_team_repo_permission(
        org="example-org",
        team_slug="platform",
        owner="example-org",
        repo="demo",
        permission="push",
        token="ghp_test",
        client=ok_client,
    )
    assert granted.status == "granted"

    fail_client = StaticGitHubRestClient(
        errors={
            ("PUT", "/orgs/example-org/teams/missing/repos/example-org/demo"): GitHubError(
                404, "Not Found"
            )
        },
    )
    failed = ensure_team_repo_permission(
        org="example-org",
        team_slug="missing",
        owner="example-org",
        repo="demo",
        permission="admin",
        token="ghp_test",
        client=fail_client,
    )
    assert failed.status == "failed"
    assert "404" in failed.message


def test_provision_github_repository_grants_teams(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    spec = build_provision_spec(
        repository=repository,
        values={
            "create_mode": "selection",
            "visibility": "private",
            "team_slugs": "platform",
            "team_permission": "push",
        },
    )
    client = StaticGitHubRestClient(
        errors={("GET", f"/repos/{spec.owner}/{spec.name}"): GitHubError(404, "missing")},
        responses={
            ("POST", f"/orgs/{spec.owner}/repos"): {"name": spec.name},
            (
                "PUT",
                f"/orgs/{spec.owner}/teams/platform/repos/{spec.owner}/{spec.name}",
            ): None,
        },
    )
    created, grants = provision_github_repository(spec, "ghp_test", client=client)
    assert created.status == "created"
    assert len(grants) == 1
    assert grants[0].status == "granted"
