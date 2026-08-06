from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.github_client import GitHubError, StaticGitHubRestClient
from repave_engine.github_repo_provision import (
    apply_repository_ruleset,
    build_provision_spec,
    create_repository_from_selection,
    create_repository_from_template,
    ensure_org_team,
    ensure_team_repo_permission,
    list_org_teams,
    list_team_members,
    load_ruleset_profile,
    plan_provision,
    provision_github_repository,
    sync_and_grant_teams,
    sync_team_membership_additive,
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


def test_build_provision_spec_ruleset_and_membership(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    spec = build_provision_spec(
        repository=repository,
        values={
            "create_mode": "selection",
            "visibility": "private",
            "team_slugs": "dest-a",
            "membership_source_team": "source",
            "ruleset_profile": "default-pr",
        },
    )
    assert spec.ruleset_profile == "default-pr"
    assert spec.membership_source_team == "source"
    assert spec.sync_team_membership is True


def test_build_provision_spec_requires_source_when_sync_enabled(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    with pytest.raises(ValueError, match="membership_source_team is required"):
        build_provision_spec(
            repository=repository,
            values={
                "create_mode": "selection",
                "visibility": "private",
                "team_slugs": "dest-a",
                "sync_team_membership": "true",
            },
        )


def test_plan_provision_includes_ruleset_and_team_sync(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    spec = build_provision_spec(
        repository=repository,
        values={
            "create_mode": "selection",
            "visibility": "private",
            "team_slugs": "dest-a",
            "membership_source_team": "source",
            "ruleset_profile": "default-pr",
        },
    )
    plan = plan_provision(spec)
    assert plan.ruleset is not None
    assert plan.ruleset.status == "planned"
    assert "Would apply ruleset profile default-pr" in plan.ruleset.message
    assert len(plan.team_sync) == 1
    assert plan.team_sync[0].status == "planned"
    assert "source" in plan.team_sync[0].message


def test_load_ruleset_profile_default_pr() -> None:
    payload = load_ruleset_profile("default-pr")
    assert payload["name"] == "repave-default-pr"
    assert any(rule.get("type") == "pull_request" for rule in payload["rules"])
    assert any(rule.get("type") == "non_fast_forward" for rule in payload["rules"])


def test_apply_repository_ruleset_creates_and_updates() -> None:
    create_client = StaticGitHubRestClient(
        responses={
            ("GET", "/repos/example-org/demo/rulesets"): [],
            ("POST", "/repos/example-org/demo/rulesets"): {"id": 1},
        },
    )
    created = apply_repository_ruleset(
        owner="example-org",
        repo="demo",
        profile="default-pr",
        token="ghp_test",
        client=create_client,
    )
    assert created.status == "applied"
    assert any(call[0] == "POST" for call in create_client.calls)

    update_client = StaticGitHubRestClient(
        responses={
            ("GET", "/repos/example-org/demo/rulesets"): [
                {"id": 42, "name": "repave-default-pr"},
            ],
            ("PUT", "/repos/example-org/demo/rulesets/42"): {"id": 42},
        },
    )
    updated = apply_repository_ruleset(
        owner="example-org",
        repo="demo",
        profile="default-pr",
        token="ghp_test",
        client=update_client,
    )
    assert updated.status == "updated"

    skipped = apply_repository_ruleset(
        owner="example-org",
        repo="demo",
        profile="none",
        token="ghp_test",
        client=StaticGitHubRestClient(),
    )
    assert skipped.status == "skipped"


def test_ensure_org_team_creates_when_missing() -> None:
    client = StaticGitHubRestClient(
        errors={("GET", "/orgs/example-org/teams/new-team"): GitHubError(404, "missing")},
        responses={("POST", "/orgs/example-org/teams"): {"slug": "new-team"}},
    )
    result = ensure_org_team("example-org", "new-team", "ghp_test", client=client)
    assert result.status == "created"
    post = next(call for call in client.calls if call[0] == "POST")
    assert post[2] == {"name": "new-team", "privacy": "closed"}


def test_list_team_members_and_additive_sync() -> None:
    client = StaticGitHubRestClient(
        responses={
            ("GET", "/orgs/example-org/teams/source/members?per_page=100&page=1"): [
                {"login": "alice"},
                {"login": "bob"},
            ],
            ("GET", "/orgs/example-org/teams/dest"): {"slug": "dest"},
            ("GET", "/orgs/example-org/teams/dest/members?per_page=100&page=1"): [
                {"login": "alice"},
            ],
            ("PUT", "/orgs/example-org/teams/dest/memberships/bob"): {"state": "active"},
        },
    )
    members = list_team_members("example-org", "source", "ghp_test", client=client)
    assert members == ("alice", "bob")
    results = sync_team_membership_additive(
        org="example-org",
        source_slug="source",
        dest_slugs=("dest",),
        token="ghp_test",
        client=client,
    )
    assert len(results) == 1
    assert results[0].status == "synced"
    assert results[0].members_added == 1
    assert any(call[0] == "PUT" and call[1].endswith("/memberships/bob") for call in client.calls)


def test_list_team_members_missing_source_names_fix() -> None:
    client = StaticGitHubRestClient(
        errors={
            (
                "GET",
                "/orgs/example-org/teams/missing/members?per_page=100&page=1",
            ): GitHubError(404, "Not Found")
        },
    )
    with pytest.raises(GitHubError, match="membership_source_team"):
        list_team_members("example-org", "missing", "ghp_test", client=client)


def test_sync_and_grant_teams_orders_sync_before_grants(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    spec = build_provision_spec(
        repository=repository,
        values={
            "create_mode": "selection",
            "visibility": "private",
            "team_slugs": "dest",
            "membership_source_team": "source",
            "team_permission": "push",
        },
    )
    client = StaticGitHubRestClient(
        responses={
            ("GET", "/orgs/example-org/teams/source/members?per_page=100&page=1"): [
                {"login": "alice"},
            ],
            ("GET", "/orgs/example-org/teams/dest"): {"slug": "dest"},
            ("GET", "/orgs/example-org/teams/dest/members?per_page=100&page=1"): [],
            ("PUT", "/orgs/example-org/teams/dest/memberships/alice"): {},
            (
                "PUT",
                f"/orgs/example-org/teams/dest/repos/{spec.owner}/{spec.name}",
            ): None,
        },
    )
    team_sync, grants = sync_and_grant_teams(spec, "ghp_test", client=client)
    assert team_sync[0].members_added == 1
    assert grants[0].status == "granted"
    put_paths = [call[1] for call in client.calls if call[0] == "PUT"]
    assert put_paths.index("/orgs/example-org/teams/dest/memberships/alice") < put_paths.index(
        f"/orgs/example-org/teams/dest/repos/{spec.owner}/{spec.name}"
    )
