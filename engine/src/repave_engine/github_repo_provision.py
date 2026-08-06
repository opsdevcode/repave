"""GitHub repository provisioning: template/selection create and team grants."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any, Literal, cast

from repave_engine.github_client import GitHubError, GitHubRestClient, UrllibGitHubRestClient
from repave_engine.github_rate_limit import record_github_response_headers
from repave_engine.target_repo import ModuleRepository

CreateMode = Literal["template", "selection"]
RepoVisibility = Literal["public", "private", "internal"]
TeamPermission = Literal["pull", "triage", "push", "maintain", "admin"]

_VALID_VISIBILITY = frozenset({"public", "private", "internal"})
_VALID_PERMISSIONS = frozenset({"pull", "triage", "push", "maintain", "admin"})
_VALID_CREATE_MODES = frozenset({"template", "selection"})

_default_client: GitHubRestClient = UrllibGitHubRestClient(
    on_response=record_github_response_headers,
)


@dataclass(frozen=True)
class OrgTeam:
    slug: str
    name: str
    description: str = ""


@dataclass(frozen=True)
class RepoCreateResult:
    status: Literal["created", "exists", "planned"]
    owner: str
    name: str
    web_url: str
    create_mode: CreateMode
    visibility: RepoVisibility
    message: str


@dataclass(frozen=True)
class TeamGrantResult:
    team_slug: str
    permission: TeamPermission
    status: Literal["granted", "planned", "failed"]
    message: str


@dataclass(frozen=True)
class GitHubRepoProvisionSpec:
    create_mode: CreateMode
    owner: str
    name: str
    description: str
    visibility: RepoVisibility
    topics: tuple[str, ...]
    default_branch: str
    template_owner: str
    template_repo: str
    team_slugs: tuple[str, ...]
    team_permission: TeamPermission
    auto_init: bool = False


@dataclass(frozen=True)
class GitHubRepoProvisionPlan:
    """Dry-run or apply outcome for github-repo publish."""

    create: RepoCreateResult
    teams: tuple[TeamGrantResult, ...]
    overlay_push: Literal["planned", "pushed", "skipped"]
    summary: str


def parse_team_slugs(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    parts = [part.strip() for part in str(raw).split(",") if part.strip()]
    # Preserve order, drop duplicates
    seen: set[str] = set()
    ordered: list[str] = []
    for part in parts:
        if part in seen:
            continue
        seen.add(part)
        ordered.append(part)
    return tuple(ordered)


def parse_topics(raw: str | None) -> tuple[str, ...]:
    return parse_team_slugs(raw)


def build_provision_spec(
    *,
    repository: ModuleRepository,
    values: dict[str, Any],
) -> GitHubRepoProvisionSpec:
    mode = str(values.get("create_mode", "selection")).strip()
    if mode not in _VALID_CREATE_MODES:
        allowed = ", ".join(sorted(_VALID_CREATE_MODES))
        raise ValueError(f"Invalid create_mode: {mode!r}. Allowed values: {allowed}")

    visibility = str(values.get("visibility", "private")).strip()
    if visibility not in _VALID_VISIBILITY:
        allowed = ", ".join(sorted(_VALID_VISIBILITY))
        raise ValueError(f"Invalid visibility: {visibility!r}. Allowed values: {allowed}")

    permission = str(values.get("team_permission", "push")).strip()
    if permission not in _VALID_PERMISSIONS:
        allowed = ", ".join(sorted(_VALID_PERMISSIONS))
        raise ValueError(f"Invalid team_permission: {permission!r}. Allowed values: {allowed}")

    template_owner = str(values.get("template_owner", "")).strip()
    template_repo = str(values.get("template_repo", "")).strip()
    if mode == "template" and (not template_owner or not template_repo):
        raise ValueError(
            "template_owner and template_repo are required when create_mode is template"
        )

    default_branch = str(values.get("default_branch", "main")).strip() or "main"
    description = str(values.get("description", "")).strip()
    topics = parse_topics(str(values.get("topics", "")))
    team_slugs = parse_team_slugs(str(values.get("team_slugs", "")))

    return GitHubRepoProvisionSpec(
        create_mode=cast(CreateMode, mode),
        owner=repository.owner,
        name=repository.name,
        description=description,
        visibility=cast(RepoVisibility, visibility),
        topics=topics,
        default_branch=default_branch,
        template_owner=template_owner,
        template_repo=template_repo,
        team_slugs=team_slugs,
        team_permission=cast(TeamPermission, permission),
        auto_init=False,
    )


def plan_provision(spec: GitHubRepoProvisionSpec) -> GitHubRepoProvisionPlan:
    """Build a dry-run plan without calling GitHub."""
    web_url = f"https://github.com/{spec.owner}/{spec.name}"
    if spec.create_mode == "template":
        create_msg = (
            f"Would create {spec.owner}/{spec.name} from template "
            f"{spec.template_owner}/{spec.template_repo} "
            f"(visibility={spec.visibility})"
        )
    else:
        create_msg = (
            f"Would create {spec.owner}/{spec.name} via selection "
            f"(visibility={spec.visibility}, topics={len(spec.topics)})"
        )
    create = RepoCreateResult(
        status="planned",
        owner=spec.owner,
        name=spec.name,
        web_url=web_url,
        create_mode=spec.create_mode,
        visibility=spec.visibility,
        message=create_msg,
    )
    teams = tuple(
        TeamGrantResult(
            team_slug=slug,
            permission=spec.team_permission,
            status="planned",
            message=(
                f"Would grant team {slug!r} {spec.team_permission} on {spec.owner}/{spec.name}"
            ),
        )
        for slug in spec.team_slugs
    )
    summary = _format_plan_summary(create, teams, overlay="planned")
    return GitHubRepoProvisionPlan(
        create=create,
        teams=teams,
        overlay_push="planned",
        summary=summary,
    )


def list_org_teams(
    org: str,
    token: str,
    *,
    client: GitHubRestClient | None = None,
) -> tuple[OrgTeam, ...]:
    org_name = org.strip()
    if not org_name:
        raise ValueError("org is required to list GitHub teams; set REPAVE_GITHUB_ORG")
    rest = client if client is not None else _default_client
    teams: list[OrgTeam] = []
    page = 1
    while page <= 20:
        path = f"/orgs/{org_name}/teams?per_page=100&page={page}"
        payload = rest.request_json("GET", path, token)
        if not isinstance(payload, list) or not payload:
            break
        for item in payload:
            if not isinstance(item, dict):
                continue
            slug = str(item.get("slug", "")).strip()
            if not slug:
                continue
            teams.append(
                OrgTeam(
                    slug=slug,
                    name=str(item.get("name", slug)).strip() or slug,
                    description=str(item.get("description") or "").strip(),
                )
            )
        if len(payload) < 100:
            break
        page += 1
    return tuple(teams)


def ensure_team_repo_permission(
    *,
    org: str,
    team_slug: str,
    owner: str,
    repo: str,
    permission: TeamPermission,
    token: str,
    client: GitHubRestClient | None = None,
) -> TeamGrantResult:
    rest = client if client is not None else _default_client
    slug = team_slug.strip()
    if not slug:
        return TeamGrantResult(
            team_slug=team_slug,
            permission=permission,
            status="failed",
            message="team_slug is empty; pass a GitHub team slug",
        )
    path = f"/orgs/{org}/teams/{slug}/repos/{owner}/{repo}"
    try:
        rest.request_json("PUT", path, token, {"permission": permission})
    except GitHubError as exc:
        return TeamGrantResult(
            team_slug=slug,
            permission=permission,
            status="failed",
            message=(
                f"Failed to grant team {slug!r} {permission} on {owner}/{repo}: "
                f"HTTP {exc.status} — {exc.message}. "
                "Ensure the token can administer org team repository permissions."
            ),
        )
    return TeamGrantResult(
        team_slug=slug,
        permission=permission,
        status="granted",
        message=f"Granted team {slug!r} {permission} on {owner}/{repo}",
    )


def create_repository_from_template(
    spec: GitHubRepoProvisionSpec,
    token: str,
    *,
    client: GitHubRestClient | None = None,
) -> RepoCreateResult:
    rest = client if client is not None else _default_client
    web_url = f"https://github.com/{spec.owner}/{spec.name}"
    if _repository_exists(spec.owner, spec.name, token, client=rest):
        return RepoCreateResult(
            status="exists",
            owner=spec.owner,
            name=spec.name,
            web_url=web_url,
            create_mode="template",
            visibility=spec.visibility,
            message=f"Repository {spec.owner}/{spec.name} already exists",
        )
    private = spec.visibility != "public"
    path = f"/repos/{spec.template_owner}/{spec.template_repo}/generate"
    body: dict[str, Any] = {
        "owner": spec.owner,
        "name": spec.name,
        "description": spec.description,
        "include_all_branches": False,
        "private": private,
    }
    try:
        rest.request_json("POST", path, token, body)
    except GitHubError as exc:
        if exc.status == 422 and _name_already_exists(exc.message):
            return RepoCreateResult(
                status="exists",
                owner=spec.owner,
                name=spec.name,
                web_url=web_url,
                create_mode="template",
                visibility=spec.visibility,
                message=f"Repository {spec.owner}/{spec.name} already exists",
            )
        raise GitHubError(
            exc.status,
            (
                f"Failed to create {spec.owner}/{spec.name} from template "
                f"{spec.template_owner}/{spec.template_repo}: {exc.message}. "
                "Confirm the template repo exists and the token can create repositories."
            ),
        ) from exc
    _apply_visibility_and_topics(spec, token, client=rest)
    return RepoCreateResult(
        status="created",
        owner=spec.owner,
        name=spec.name,
        web_url=web_url,
        create_mode="template",
        visibility=spec.visibility,
        message=(
            f"Created {spec.owner}/{spec.name} from template "
            f"{spec.template_owner}/{spec.template_repo}"
        ),
    )


def create_repository_from_selection(
    spec: GitHubRepoProvisionSpec,
    token: str,
    *,
    client: GitHubRestClient | None = None,
) -> RepoCreateResult:
    rest = client if client is not None else _default_client
    web_url = f"https://github.com/{spec.owner}/{spec.name}"
    if _repository_exists(spec.owner, spec.name, token, client=rest):
        return RepoCreateResult(
            status="exists",
            owner=spec.owner,
            name=spec.name,
            web_url=web_url,
            create_mode="selection",
            visibility=spec.visibility,
            message=f"Repository {spec.owner}/{spec.name} already exists",
        )
    body: dict[str, Any] = {
        "name": spec.name,
        "description": spec.description or f"Repository provisioned by repave ({spec.name})",
        "auto_init": spec.auto_init,
        "private": spec.visibility != "public",
        "visibility": spec.visibility,
    }
    try:
        rest.request_json("POST", f"/orgs/{spec.owner}/repos", token, body)
    except GitHubError as exc:
        if exc.status == 404:
            user_body = {
                "name": spec.name,
                "description": body["description"],
                "auto_init": spec.auto_init,
                "private": spec.visibility != "public",
            }
            try:
                rest.request_json("POST", "/user/repos", token, user_body)
            except GitHubError as user_exc:
                if user_exc.status == 422 and _name_already_exists(user_exc.message):
                    return RepoCreateResult(
                        status="exists",
                        owner=spec.owner,
                        name=spec.name,
                        web_url=web_url,
                        create_mode="selection",
                        visibility=spec.visibility,
                        message=f"Repository {spec.owner}/{spec.name} already exists",
                    )
                raise GitHubError(
                    user_exc.status,
                    (
                        f"Failed to create user repository {spec.name}: {user_exc.message}. "
                        "Set REPAVE_GITHUB_ORG to an org the token can administer."
                    ),
                ) from user_exc
        elif exc.status == 422 and _name_already_exists(exc.message):
            return RepoCreateResult(
                status="exists",
                owner=spec.owner,
                name=spec.name,
                web_url=web_url,
                create_mode="selection",
                visibility=spec.visibility,
                message=f"Repository {spec.owner}/{spec.name} already exists",
            )
        else:
            raise GitHubError(
                exc.status,
                (
                    f"Failed to create org repository {spec.owner}/{spec.name}: {exc.message}. "
                    "Ensure the token can create repositories in the org."
                ),
            ) from exc
    _apply_visibility_and_topics(spec, token, client=rest)
    return RepoCreateResult(
        status="created",
        owner=spec.owner,
        name=spec.name,
        web_url=web_url,
        create_mode="selection",
        visibility=spec.visibility,
        message=f"Created {spec.owner}/{spec.name} (visibility={spec.visibility})",
    )


def provision_github_repository(
    spec: GitHubRepoProvisionSpec,
    token: str,
    *,
    client: GitHubRestClient | None = None,
) -> tuple[RepoCreateResult, tuple[TeamGrantResult, ...]]:
    """Create (or reuse) the repository and grant team permissions."""
    rest = client if client is not None else _default_client
    if spec.create_mode == "template":
        created = create_repository_from_template(spec, token, client=rest)
    else:
        created = create_repository_from_selection(spec, token, client=rest)
    grants = tuple(
        ensure_team_repo_permission(
            org=spec.owner,
            team_slug=slug,
            owner=spec.owner,
            repo=spec.name,
            permission=spec.team_permission,
            token=token,
            client=rest,
        )
        for slug in spec.team_slugs
    )
    return created, grants


def format_provision_message(
    create: RepoCreateResult,
    teams: tuple[TeamGrantResult, ...],
    *,
    overlay: Literal["planned", "pushed", "skipped"],
    local_path: str,
    branch: str,
) -> str:
    lines = [
        create.message + ".",
        f"Repository: {create.web_url}",
        f"Create mode: {create.create_mode}",
        f"Visibility: {create.visibility}",
        f"Branch: {branch}",
        f"Local repository: {local_path}",
        f"Overlay push: {overlay}",
    ]
    if teams:
        lines.append("Team grants:")
        for grant in teams:
            lines.append(f"- {grant.message}")
    else:
        lines.append("Team grants: none")
    failed = [g for g in teams if g.status == "failed"]
    if failed:
        lines.append(
            "One or more team grants failed; fix token/org admin permissions and re-run apply."
        )
    return "\n".join(lines)


def _apply_visibility_and_topics(
    spec: GitHubRepoProvisionSpec,
    token: str,
    *,
    client: GitHubRestClient,
) -> None:
    # Template generate only accepts private bool; set visibility for internal orgs.
    if spec.visibility == "internal":
        with contextlib.suppress(GitHubError):
            client.request_json(
                "PATCH",
                f"/repos/{spec.owner}/{spec.name}",
                token,
                {"visibility": "internal"},
            )
    if not spec.topics:
        return
    with contextlib.suppress(GitHubError):
        client.request_json(
            "PUT",
            f"/repos/{spec.owner}/{spec.name}/topics",
            token,
            {"names": list(spec.topics)},
        )


def _repository_exists(
    owner: str,
    name: str,
    token: str,
    *,
    client: GitHubRestClient,
) -> bool:
    try:
        client.request_json("GET", f"/repos/{owner}/{name}", token)
        return True
    except GitHubError as exc:
        if exc.status == 404:
            return False
        raise


def _name_already_exists(message: str) -> bool:
    lowered = message.lower()
    return "already exists" in lowered or "name already exists" in lowered


def _format_plan_summary(
    create: RepoCreateResult,
    teams: tuple[TeamGrantResult, ...],
    *,
    overlay: str,
) -> str:
    return format_provision_message(
        create,
        teams,
        overlay=overlay,  # type: ignore[arg-type]
        local_path="(staging)",
        branch="main",
    )
