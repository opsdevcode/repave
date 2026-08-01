"""List remote repository files via the GitHub REST API without a git clone."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from repave_engine.github import GitHubError, _github_json
from repave_engine.github_rate_limit import wait_before_github_request
from repave_engine.import_detect import _SKIP_DIRS, MAX_SCANNED_FILES

_GITHUB_REMOTE = re.compile(r"github\.com[/:](?P<owner>[^/]+)/(?P<name>[^/.]+(?:\.git)?)")


class GitHubInventoryError(RuntimeError):
    """Failed to inventory a remote repository via the GitHub API."""


def parse_github_repository(raw: str) -> tuple[str, str]:
    """Return ``(owner, repo)`` for a GitHub HTTPS or SSH remote URL."""
    text = raw.strip().rstrip("/")
    if text.endswith(".git"):
        text = text[: -len(".git")]
    match = _GITHUB_REMOTE.search(text)
    if not match:
        raise GitHubInventoryError(f"not a GitHub repository URL: {raw!r}")
    owner = match.group("owner")
    name = match.group("name")
    if name.endswith(".git"):
        name = name[:-4]
    return owner, name


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


def search_github_repositories(
    query: str,
    token: str,
    *,
    limit: int = 30,
) -> tuple[str, ...]:
    """Return clone URLs from a GitHub repository search query."""
    if not query.strip():
        return ()
    wait_before_github_request()
    payload = _github_json(
        "GET",
        f"/search/repositories?q={quote(query)}&per_page={min(limit, 100)}",
        token,
    )
    if not isinstance(payload, dict):
        return ()
    items = payload.get("items")
    if not isinstance(items, list):
        return ()
    urls: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        clone_url = str(item.get("clone_url", "")).strip()
        if clone_url:
            urls.append(clone_url)
        if len(urls) >= limit:
            break
    return tuple(urls)


def resolve_batch_targets(
    raw_targets: list[str],
    *,
    org: str = "",
    topic: str = "",
    token: str | None = None,
    limit: int = 30,
) -> list[str]:
    """Expand pasted targets plus optional org/topic query into a deduplicated repo list."""
    seen: set[str] = set()
    resolved: list[str] = []
    for line in raw_targets:
        for part in line.replace(",", "\n").splitlines():
            target = part.strip()
            if not target or target in seen:
                continue
            seen.add(target)
            resolved.append(target)

    org_query = org.strip()
    topic_query = topic.strip()
    if (org_query or topic_query) and token:
        parts: list[str] = []
        if org_query:
            parts.append(f"org:{org_query}")
        if topic_query:
            parts.append(f"topic:{topic_query}")
        for url in search_github_repositories(" ".join(parts), token, limit=limit):
            if url not in seen:
                seen.add(url)
                resolved.append(url)
    return resolved
