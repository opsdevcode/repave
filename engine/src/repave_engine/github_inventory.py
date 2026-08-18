"""List remote repository files via the GitHub REST API without a git clone."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from repave_engine.github import GitHubError, _github_json
from repave_engine.github_rate_limit import wait_before_github_request
from repave_engine.import_detect import _SKIP_DIRS, MAX_SCANNED_FILES
from repave_engine.url_hosts import parse_github_owner_repo

_PUSHED_SINCE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class GitHubInventoryError(RuntimeError):
    """Failed to inventory a remote repository via the GitHub API."""


def parse_github_repository(raw: str) -> tuple[str, str]:
    """Return ``(owner, repo)`` for a GitHub HTTPS or SSH remote URL."""
    parsed = parse_github_owner_repo(raw)
    if parsed is None:
        raise GitHubInventoryError(f"not a GitHub repository URL: {raw!r}")
    return parsed


def _github_get(path: str, token: str) -> Any:
    wait_before_github_request()
    return _github_json("GET", path, token)


def remote_has_provenance(
    owner: str,
    repo: str,
    token: str,
    *,
    ref: str | None = None,
) -> bool:
    """True when ``repave.yaml`` exists at the repository root on GitHub."""
    query = f"?ref={ref}" if ref else ""
    try:
        _github_get(f"/repos/{owner}/{repo}/contents/repave.yaml{query}", token)
        return True
    except GitHubError as exc:
        if exc.status == 404:
            return False
        raise GitHubInventoryError(f"GitHub returned {exc.status}: {exc.message}") from exc


def resolve_ref_sha(owner: str, repo: str, token: str, ref: str | None) -> str:
    if ref:
        try:
            payload = _github_get(f"/repos/{owner}/{repo}/git/ref/heads/{ref}", token)
            if isinstance(payload, dict):
                object_payload = payload.get("object")
                if isinstance(object_payload, dict):
                    sha = str(object_payload.get("sha", "")).strip()
                    if sha:
                        return sha
        except GitHubError:
            payload = _github_get(f"/repos/{owner}/{repo}/git/ref/tags/{ref}", token)
            if isinstance(payload, dict):
                object_payload = payload.get("object")
                if isinstance(object_payload, dict):
                    sha = str(object_payload.get("sha", "")).strip()
                    if sha:
                        return sha
            raise
    payload = _github_get(f"/repos/{owner}/{repo}", token)
    if not isinstance(payload, dict):
        raise GitHubInventoryError(f"unexpected repository payload for {owner}/{repo}")
    default_branch = str(payload.get("default_branch") or "main")
    branch = _github_get(f"/repos/{owner}/{repo}/git/ref/heads/{default_branch}", token)
    if not isinstance(branch, dict):
        raise GitHubInventoryError(f"could not resolve default branch for {owner}/{repo}")
    object_payload = branch.get("object")
    if not isinstance(object_payload, dict):
        raise GitHubInventoryError(f"could not resolve commit for {owner}/{repo}")
    sha = str(object_payload.get("sha", "")).strip()
    if not sha:
        raise GitHubInventoryError(f"empty commit sha for {owner}/{repo}")
    return sha


def inventory_github_paths(
    owner: str,
    repo: str,
    token: str,
    *,
    ref: str | None = None,
    limit: int = MAX_SCANNED_FILES,
) -> tuple[str, ...]:
    """Return repo-relative blob paths from the Git trees API (no clone)."""
    sha = resolve_ref_sha(owner, repo, token, ref)
    payload = _github_get(f"/repos/{owner}/{repo}/git/trees/{sha}?recursive=1", token)
    if not isinstance(payload, dict):
        raise GitHubInventoryError(f"unexpected tree payload for {owner}/{repo}")
    if payload.get("truncated"):
        raise GitHubInventoryError(
            f"{owner}/{repo} tree is too large for a trees-API preview — clone locally or "
            "narrow the repository"
        )
    tree = payload.get("tree")
    if not isinstance(tree, list):
        return ()
    paths: list[str] = []
    for item in tree:
        if not isinstance(item, dict):
            continue
        if str(item.get("type", "")) != "blob":
            continue
        path = str(item.get("path", "")).strip()
        if not path:
            continue
        if any(part in _SKIP_DIRS for part in path.split("/")):
            continue
        paths.append(path)
        if len(paths) >= limit:
            break
    return tuple(sorted(paths))


@dataclass(frozen=True)
class OrgRepository:
    owner: str
    name: str
    clone_url: str
    html_url: str
    archived: bool
    fork: bool
    default_branch: str


@dataclass(frozen=True)
class GitHubRepoSearchFilters:
    """GitHub repository search qualifiers for org discovery and batch targets."""

    org: str = ""
    topic: str = ""
    language: str = ""
    pushed_since: str = ""
    exclude_archived: bool = True
    exclude_forks: bool = True


def build_github_search_query(filters: GitHubRepoSearchFilters) -> str:
    """Compose a GitHub ``search/repositories`` query from structured filters."""
    parts: list[str] = []
    org = filters.org.strip()
    if org:
        parts.append(f"org:{org}")
    topic = filters.topic.strip()
    if topic:
        parts.append(f"topic:{topic}")
    language = filters.language.strip()
    if language:
        parts.append(f"language:{language}")
    if filters.exclude_archived:
        parts.append("archived:false")
    if filters.exclude_forks:
        parts.append("fork:false")
    pushed_since = filters.pushed_since.strip()
    if pushed_since:
        parts.append(f"pushed:>{pushed_since}")
    return " ".join(parts)


def validate_pushed_since(value: str) -> str:
    """Return a normalized ``YYYY-MM-DD`` pushed-since date or raise ValueError."""
    text = value.strip()
    if not text:
        return ""
    if not _PUSHED_SINCE_RE.match(text):
        raise ValueError("pushed_since must be YYYY-MM-DD (for example 2026-01-01)")
    return text


def _org_repo_from_payload(item: dict[str, Any], fallback_org: str) -> OrgRepository | None:
    owner_payload = item.get("owner")
    owner = (
        str(owner_payload.get("login", "")).strip()
        if isinstance(owner_payload, dict)
        else fallback_org
    )
    name = str(item.get("name", "")).strip()
    clone_url = str(item.get("clone_url", "")).strip()
    if not owner or not name or not clone_url:
        return None
    return OrgRepository(
        owner=owner,
        name=name,
        clone_url=clone_url,
        html_url=str(item.get("html_url", clone_url)).strip() or clone_url,
        archived=bool(item.get("archived")),
        fork=bool(item.get("fork")),
        default_branch=str(item.get("default_branch") or "main").strip() or "main",
    )


def list_org_repositories(
    org: str,
    token: str,
    *,
    limit: int = 100,
) -> tuple[OrgRepository, ...]:
    """Return repositories for a GitHub organization or user account (paginated)."""
    org_name = org.strip()
    if not org_name:
        raise GitHubInventoryError("org is required to list repositories")
    if limit <= 0:
        return ()
    cap = min(limit, 1000)
    repos: list[OrgRepository] = []
    page = 1
    list_paths = (
        f"/orgs/{org_name}/repos",
        f"/users/{org_name}/repos",
    )
    active_path = list_paths[0]
    while page <= 10 and len(repos) < cap:
        per_page = min(100, cap - len(repos))
        path = f"{active_path}?per_page={per_page}&page={page}&type=all"
        try:
            payload = _github_get(path, token)
        except GitHubError as exc:
            if exc.status == 404 and active_path == list_paths[0] and page == 1:
                active_path = list_paths[1]
                path = f"{active_path}?per_page={per_page}&page={page}&type=all"
                try:
                    payload = _github_get(path, token)
                except GitHubError as retry_exc:
                    raise GitHubInventoryError(
                        f"could not list repositories for {org_name}: HTTP {retry_exc.status}"
                    ) from retry_exc
            else:
                raise GitHubInventoryError(
                    f"could not list repositories for {org_name}: HTTP {exc.status}"
                ) from exc
        if not isinstance(payload, list) or not payload:
            break
        for item in payload:
            if not isinstance(item, dict):
                continue
            owner_payload = item.get("owner")
            owner = (
                str(owner_payload.get("login", "")).strip()
                if isinstance(owner_payload, dict)
                else org_name
            )
            name = str(item.get("name", "")).strip()
            clone_url = str(item.get("clone_url", "")).strip()
            if not owner or not name or not clone_url:
                continue
            repos.append(
                OrgRepository(
                    owner=owner,
                    name=name,
                    clone_url=clone_url,
                    html_url=str(item.get("html_url", clone_url)).strip() or clone_url,
                    archived=bool(item.get("archived")),
                    fork=bool(item.get("fork")),
                    default_branch=str(item.get("default_branch") or "main").strip() or "main",
                )
            )
            if len(repos) >= cap:
                break
        if len(payload) < per_page or len(repos) >= cap:
            break
        page += 1
    return tuple(repos)


def fetch_github_file_text(
    owner: str,
    repo: str,
    rel_path: str,
    token: str,
    *,
    ref: str | None = None,
) -> str:
    """Fetch a single file's decoded text from the contents API."""
    import base64

    query = f"?ref={ref}" if ref else ""
    payload = _github_get(f"/repos/{owner}/{repo}/contents/{rel_path}{query}", token)
    if not isinstance(payload, dict):
        return ""
    encoding = str(payload.get("encoding", ""))
    content = payload.get("content")
    if encoding != "base64" or not isinstance(content, str):
        return ""
    try:
        return base64.b64decode(content).decode("utf-8", errors="replace")
    except (ValueError, OSError):
        return ""


def search_org_repositories(
    query: str,
    token: str,
    *,
    limit: int = 100,
    fallback_org: str = "",
) -> tuple[OrgRepository, ...]:
    """Return repositories from a GitHub search query (paginated, up to 1000)."""
    if not query.strip():
        return ()
    if limit <= 0:
        return ()
    cap = min(limit, 1000)
    repos: list[OrgRepository] = []
    page = 1
    while page <= 10 and len(repos) < cap:
        per_page = min(100, cap - len(repos))
        wait_before_github_request()
        payload = _github_json(
            "GET",
            f"/search/repositories?q={quote(query)}&per_page={per_page}&page={page}",
            token,
        )
        if not isinstance(payload, dict):
            break
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            break
        for item in items:
            if not isinstance(item, dict):
                continue
            entry = _org_repo_from_payload(item, fallback_org)
            if entry is None:
                continue
            repos.append(entry)
            if len(repos) >= cap:
                break
        if len(items) < per_page or len(repos) >= cap:
            break
        page += 1
    return tuple(repos)


def search_github_repositories(
    query: str,
    token: str,
    *,
    limit: int = 30,
) -> tuple[str, ...]:
    """Return clone URLs from a GitHub repository search query."""
    if not query.strip():
        return ()
    repos = search_org_repositories(query, token, limit=limit)
    return tuple(repo.clone_url for repo in repos)


def resolve_batch_targets(
    raw_targets: list[str],
    *,
    org: str = "",
    topic: str = "",
    language: str = "",
    pushed_since: str = "",
    exclude_archived: bool = True,
    exclude_forks: bool = True,
    token: str | None = None,
    limit: int = 30,
) -> list[str]:
    """Expand pasted targets plus optional org/search query into a deduplicated repo list."""
    seen: set[str] = set()
    resolved: list[str] = []
    for line in raw_targets:
        for part in line.replace(",", "\n").splitlines():
            target = part.strip()
            if not target or target in seen:
                continue
            seen.add(target)
            resolved.append(target)

    filters = GitHubRepoSearchFilters(
        org=org,
        topic=topic,
        language=language,
        pushed_since=pushed_since,
        exclude_archived=exclude_archived,
        exclude_forks=exclude_forks,
    )
    query = build_github_search_query(filters)
    if query and token:
        for url in search_github_repositories(query, token, limit=limit):
            if url not in seen:
                seen.add(url)
                resolved.append(url)
    return resolved
