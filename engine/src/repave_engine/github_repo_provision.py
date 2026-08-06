"""GitHub repository provisioning: create, rulesets, team sync, and grants."""

from __future__ import annotations

import contextlib
import json
import logging
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Literal, cast

from repave_engine.github_client import GitHubError, GitHubRestClient, UrllibGitHubRestClient
from repave_engine.github_rate_limit import record_github_response_headers
from repave_engine.target_repo import ModuleRepository

logger = logging.getLogger(__name__)

CreateMode = Literal["template", "selection"]
RepoVisibility = Literal["public", "private", "internal"]
TeamPermission = Literal["pull", "triage", "push", "maintain", "admin"]
RulesetProfile = Literal["none", "default-pr"]

_VALID_VISIBILITY = frozenset({"public", "private", "internal"})
_VALID_PERMISSIONS = frozenset({"pull", "triage", "push", "maintain", "admin"})
_VALID_CREATE_MODES = frozenset({"template", "selection"})
_VALID_RULESET_PROFILES = frozenset({"none", "default-pr"})
_RULESET_PACKAGE = "repave_engine.github_rulesets"

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
class TeamSyncResult:
    team_slug: str
    status: Literal["created", "exists", "synced", "planned", "failed", "skipped"]
    members_added: int
    message: str


@dataclass(frozen=True)
class RulesetApplyResult:
    profile: RulesetProfile
    status: Literal["applied", "updated", "planned", "skipped", "failed"]
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
    ruleset_profile: RulesetProfile = "none"
    membership_source_team: str = ""
    sync_team_membership: bool = False
    auto_init: bool = False


@dataclass(frozen=True)
class ProvisionApplyResult:
    create: RepoCreateResult
    teams: tuple[TeamGrantResult, ...]
    team_sync: tuple[TeamSyncResult, ...] = ()
    ruleset: RulesetApplyResult | None = None


@dataclass(frozen=True)
class GitHubRepoProvisionPlan:
    """Dry-run or apply outcome for github-repo publish."""

    create: RepoCreateResult
    teams: tuple[TeamGrantResult, ...]
    overlay_push: Literal["planned", "pushed", "skipped"]
    summary: str
    team_sync: tuple[TeamSyncResult, ...] = ()
    ruleset: RulesetApplyResult | None = None


def parse_team_slugs(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    parts = [part.strip() for part in str(raw).split(",") if part.strip()]
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


def _parse_bool(raw: Any, *, default: bool = False) -> bool:
    if raw is None or raw == "":
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


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

    ruleset_profile = str(values.get("ruleset_profile", "none")).strip() or "none"
    if ruleset_profile not in _VALID_RULESET_PROFILES:
        allowed = ", ".join(sorted(_VALID_RULESET_PROFILES))
        raise ValueError(f"Invalid ruleset_profile: {ruleset_profile!r}. Allowed values: {allowed}")

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
    membership_source = str(values.get("membership_source_team", "")).strip()
    sync_membership = _parse_bool(values.get("sync_team_membership"), default=False)
    if membership_source and values.get("sync_team_membership") in (None, ""):
        sync_membership = True
    if sync_membership and team_slugs and not membership_source:
        raise ValueError(
            "membership_source_team is required when sync_team_membership is true "
            "and team_slugs is set"
        )

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
        ruleset_profile=cast(RulesetProfile, ruleset_profile),
        membership_source_team=membership_source,
        sync_team_membership=sync_membership,
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
    team_sync = _plan_team_sync(spec)
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
    ruleset = _plan_ruleset(spec)
    summary = format_provision_message(
        create,
        teams,
        overlay="planned",
        local_path="(staging)",
        branch=spec.default_branch,
        team_sync=team_sync,
        ruleset=ruleset,
    )
    return GitHubRepoProvisionPlan(
        create=create,
        teams=teams,
        overlay_push="planned",
        summary=summary,
        team_sync=team_sync,
        ruleset=ruleset,
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


def list_team_members(
    org: str,
    team_slug: str,
    token: str,
    *,
    client: GitHubRestClient | None = None,
) -> tuple[str, ...]:
    rest = client if client is not None else _default_client
    slug = team_slug.strip()
    if not slug:
        raise ValueError("team_slug is required to list team members")
    members: list[str] = []
    page = 1
    while page <= 20:
        path = f"/orgs/{org}/teams/{slug}/members?per_page=100&page={page}"
        try:
            payload = rest.request_json("GET", path, token)
        except GitHubError as exc:
            raise GitHubError(
                exc.status,
                (
                    f"Failed to list members of team {slug!r} in org {org}: "
                    f"HTTP {exc.status} — {exc.message}. "
                    "Set membership_source_team to an existing org team the token can read."
                ),
            ) from exc
        if not isinstance(payload, list) or not payload:
            break
        for item in payload:
            if isinstance(item, dict):
                login = str(item.get("login", "")).strip()
                if login:
                    members.append(login)
        if len(payload) < 100:
            break
        page += 1
    return tuple(members)


def ensure_org_team(
    org: str,
    team_slug: str,
    token: str,
    *,
    client: GitHubRestClient | None = None,
) -> TeamSyncResult:
    rest = client if client is not None else _default_client
    slug = team_slug.strip()
    if not slug:
        return TeamSyncResult(
            team_slug=team_slug,
            status="failed",
            members_added=0,
            message="team_slug is empty; pass a GitHub team slug",
        )
    try:
        rest.request_json("GET", f"/orgs/{org}/teams/{slug}", token)
        return TeamSyncResult(
            team_slug=slug,
            status="exists",
            members_added=0,
            message=f"Team {slug!r} already exists in {org}",
        )
    except GitHubError as exc:
        if exc.status != 404:
            return TeamSyncResult(
                team_slug=slug,
                status="failed",
                members_added=0,
                message=(
                    f"Failed to look up team {slug!r}: HTTP {exc.status} — {exc.message}. "
                    "Ensure the token can read organization teams."
                ),
            )
    try:
        rest.request_json(
            "POST",
            f"/orgs/{org}/teams",
            token,
            {
                # Use the slug as the display name so GitHub derives a matching slug.
                "name": slug,
                "privacy": "closed",
            },
        )
    except GitHubError as exc:
        return TeamSyncResult(
            team_slug=slug,
            status="failed",
            members_added=0,
            message=(
                f"Failed to create team {slug!r} in {org}: HTTP {exc.status} — {exc.message}. "
                "Ensure the token can administer organization teams."
            ),
        )
    return TeamSyncResult(
        team_slug=slug,
        status="created",
        members_added=0,
        message=f"Created team {slug!r} in {org}",
    )


def sync_team_membership_additive(
    *,
    org: str,
    source_slug: str,
    dest_slugs: tuple[str, ...],
    token: str,
    client: GitHubRestClient | None = None,
) -> tuple[TeamSyncResult, ...]:
    rest = client if client is not None else _default_client
    source_members = list_team_members(org, source_slug, token, client=rest)
    results: list[TeamSyncResult] = []
    for dest in dest_slugs:
        ensured = ensure_org_team(org, dest, token, client=rest)
        if ensured.status == "failed":
            results.append(ensured)
            continue
        existing = set(list_team_members(org, dest, token, client=rest))
        added = 0
        failures: list[str] = []
        for login in source_members:
            if login in existing:
                continue
            try:
                rest.request_json(
                    "PUT",
                    f"/orgs/{org}/teams/{dest}/memberships/{login}",
                    token,
                    {"role": "member"},
                )
                added += 1
            except GitHubError as exc:
                failures.append(f"{login} (HTTP {exc.status})")
        if failures:
            results.append(
                TeamSyncResult(
                    team_slug=dest,
                    status="failed",
                    members_added=added,
                    message=(
                        f"Partial sync to {dest!r} from {source_slug!r}: added {added}, "
                        f"failed for {', '.join(failures)}. "
                        "Ensure the token can manage team memberships."
                    ),
                )
            )
            continue
        status: Literal["created", "exists", "synced"] = (
            "created" if ensured.status == "created" else "synced"
        )
        results.append(
            TeamSyncResult(
                team_slug=dest,
                status=status,
                members_added=added,
                message=(
                    f"Synced {added} member(s) from {source_slug!r} into {dest!r} "
                    f"(team {ensured.status})"
                ),
            )
        )
    return tuple(results)


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


def load_ruleset_profile(profile: RulesetProfile) -> dict[str, Any]:
    if profile == "none":
        raise ValueError("ruleset profile 'none' has no payload")
    filename = f"{profile}.json"
    try:
        package = resources.files(_RULESET_PACKAGE)
        data = package.joinpath(filename).read_text(encoding="utf-8")
    except (FileNotFoundError, TypeError, AttributeError):
        path = Path(__file__).resolve().parent / "github_rulesets" / filename
        if not path.is_file():
            raise ValueError(
                f"Unknown ruleset profile {profile!r}; expected file {filename}"
            ) from None
        data = path.read_text(encoding="utf-8")
    payload = json.loads(data)
    if not isinstance(payload, dict):
        raise ValueError(f"ruleset profile {profile!r} must be a JSON object")
    return payload


def apply_repository_ruleset(
    *,
    owner: str,
    repo: str,
    profile: RulesetProfile,
    token: str,
    client: GitHubRestClient | None = None,
) -> RulesetApplyResult:
    if profile == "none":
        return RulesetApplyResult(
            profile=profile,
            status="skipped",
            message="Ruleset profile none; skipped",
        )
    rest = client if client is not None else _default_client
    try:
        body = load_ruleset_profile(profile)
    except ValueError as exc:
        return RulesetApplyResult(profile=profile, status="failed", message=str(exc))
    ruleset_name = str(body.get("name", profile)).strip() or profile
    existing_id = _find_ruleset_id(owner, repo, ruleset_name, token, client=rest)
    try:
        if existing_id is not None:
            rest.request_json(
                "PUT",
                f"/repos/{owner}/{repo}/rulesets/{existing_id}",
                token,
                body,
            )
            return RulesetApplyResult(
                profile=profile,
                status="updated",
                message=f"Updated ruleset {ruleset_name!r} ({profile}) on {owner}/{repo}",
            )
        rest.request_json("POST", f"/repos/{owner}/{repo}/rulesets", token, body)
    except GitHubError as exc:
        return RulesetApplyResult(
            profile=profile,
            status="failed",
            message=(
                f"Failed to apply ruleset profile {profile!r} on {owner}/{repo}: "
                f"HTTP {exc.status} — {exc.message}. "
                "Ensure the token can administer repository rulesets."
            ),
        )
    return RulesetApplyResult(
        profile=profile,
        status="applied",
        message=f"Applied ruleset {ruleset_name!r} ({profile}) on {owner}/{repo}",
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


def create_github_repository(
    spec: GitHubRepoProvisionSpec,
    token: str,
    *,
    client: GitHubRestClient | None = None,
) -> RepoCreateResult:
    rest = client if client is not None else _default_client
    if spec.create_mode == "template":
        return create_repository_from_template(spec, token, client=rest)
    return create_repository_from_selection(spec, token, client=rest)


def sync_and_grant_teams(
    spec: GitHubRepoProvisionSpec,
    token: str,
    *,
    client: GitHubRestClient | None = None,
) -> tuple[tuple[TeamSyncResult, ...], tuple[TeamGrantResult, ...]]:
    rest = client if client is not None else _default_client
    team_sync: tuple[TeamSyncResult, ...] = ()
    if spec.sync_team_membership and spec.team_slugs and spec.membership_source_team:
        try:
            team_sync = sync_team_membership_additive(
                org=spec.owner,
                source_slug=spec.membership_source_team,
                dest_slugs=spec.team_slugs,
                token=token,
                client=rest,
            )
        except GitHubError as exc:
            team_sync = (
                TeamSyncResult(
                    team_slug=spec.membership_source_team,
                    status="failed",
                    members_added=0,
                    message=str(exc.message),
                ),
            )
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
    return team_sync, grants


def provision_github_repository(
    spec: GitHubRepoProvisionSpec,
    token: str,
    *,
    client: GitHubRestClient | None = None,
) -> tuple[RepoCreateResult, tuple[TeamGrantResult, ...]]:
    """Create (or reuse) the repository and grant team permissions (legacy tuple API)."""
    rest = client if client is not None else _default_client
    created = create_github_repository(spec, token, client=rest)
    _, grants = sync_and_grant_teams(spec, token, client=rest)
    return created, grants


def format_provision_message(
    create: RepoCreateResult,
    teams: tuple[TeamGrantResult, ...],
    *,
    overlay: Literal["planned", "pushed", "skipped"],
    local_path: str,
    branch: str,
    team_sync: tuple[TeamSyncResult, ...] = (),
    ruleset: RulesetApplyResult | None = None,
    fleet_message: str | None = None,
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
    if ruleset is not None:
        lines.append(f"Ruleset: {ruleset.message}")
    if team_sync:
        lines.append("Team membership sync:")
        for item in team_sync:
            lines.append(f"- {item.message}")
    if teams:
        lines.append("Team grants:")
        for grant in teams:
            lines.append(f"- {grant.message}")
    else:
        lines.append("Team grants: none")
    failed_grants = [g for g in teams if g.status == "failed"]
    if failed_grants:
        lines.append(
            "One or more team grants failed; fix token/org admin permissions and re-run apply."
        )
    failed_sync = [s for s in team_sync if s.status == "failed"]
    if failed_sync:
        lines.append(
            "One or more team membership sync steps failed; fix org admin permissions and re-run."
        )
    if ruleset is not None and ruleset.status == "failed":
        lines.append("Ruleset apply failed; fix administration permissions and re-run apply.")
    if fleet_message:
        lines.append(fleet_message)
    return "\n".join(lines)


def _plan_team_sync(spec: GitHubRepoProvisionSpec) -> tuple[TeamSyncResult, ...]:
    if not spec.sync_team_membership or not spec.team_slugs:
        return ()
    source = spec.membership_source_team or "(unset)"
    return tuple(
        TeamSyncResult(
            team_slug=slug,
            status="planned",
            members_added=0,
            message=(f"Would ensure team {slug!r} and sync members additively from {source!r}"),
        )
        for slug in spec.team_slugs
    )


def _plan_ruleset(spec: GitHubRepoProvisionSpec) -> RulesetApplyResult:
    if spec.ruleset_profile == "none":
        return RulesetApplyResult(
            profile="none",
            status="skipped",
            message="Ruleset profile none; skipped",
        )
    return RulesetApplyResult(
        profile=spec.ruleset_profile,
        status="planned",
        message=f"Would apply ruleset profile {spec.ruleset_profile}",
    )


def _find_ruleset_id(
    owner: str,
    repo: str,
    name: str,
    token: str,
    *,
    client: GitHubRestClient,
) -> int | None:
    try:
        payload = client.request_json("GET", f"/repos/{owner}/{repo}/rulesets", token)
    except GitHubError:
        return None
    if not isinstance(payload, list):
        return None
    for item in payload:
        if isinstance(item, dict) and str(item.get("name", "")).strip() == name:
            raw_id = item.get("id")
            if isinstance(raw_id, int):
                return raw_id
            if isinstance(raw_id, str) and raw_id.isdigit():
                return int(raw_id)
    return None


def _apply_visibility_and_topics(
    spec: GitHubRepoProvisionSpec,
    token: str,
    *,
    client: GitHubRestClient,
) -> None:
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
