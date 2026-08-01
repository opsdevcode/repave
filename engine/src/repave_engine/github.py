from __future__ import annotations

from pathlib import Path
from typing import Any

from repave_engine.github_client import GitHubError, GitHubRestClient, UrllibGitHubRestClient
from repave_engine.github_rate_limit import record_github_response_headers
from repave_engine.subprocess_run import run_subprocess
from repave_engine.target_repo import ModuleRepository, _git_executable, _run_git

_default_github_client: GitHubRestClient = UrllibGitHubRestClient(
    on_response=record_github_response_headers,
)


def ensure_github_repository(
    repository: ModuleRepository,
    token: str,
    *,
    description: str = "",
) -> str:
    if _repository_exists(repository, token):
        return "exists"

    try:
        _create_org_repository(repository, token, description=description)
        return "created"
    except GitHubError as exc:
        if exc.status == 404:
            _create_user_repository(repository, token, description=description)
            return "created"
        if exc.status == 422 and _name_already_exists(exc.message):
            return "exists"
        raise


def push_module_repository(
    repository: ModuleRepository,
    token: str,
    *,
    branch: str = "main",
) -> None:
    _configure_git_origin(repository.local_path, repository.owner, repository.name, token)
    _run_git(["branch", "-M", branch], cwd=repository.local_path)
    _run_git(["push", "-u", "origin", branch], cwd=repository.local_path)


def push_git_branch(
    repo_dir: Path,
    *,
    owner: str,
    name: str,
    token: str,
    branch: str,
) -> None:
    _configure_git_origin(repo_dir, owner, name, token)
    _run_git(["push", "-u", "origin", branch], cwd=repo_dir)


def create_github_pull_request(
    owner: str,
    repo: str,
    *,
    title: str,
    body: str,
    head: str,
    base: str,
    token: str,
    draft: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": title,
        "body": body,
        "head": head,
        "base": base,
    }
    if draft:
        payload["draft"] = True
    return _github_request("POST", f"/repos/{owner}/{repo}/pulls", token, payload)


def add_pull_request_labels(
    owner: str,
    repo: str,
    pull_number: int,
    labels: tuple[str, ...] | list[str],
    token: str,
) -> None:
    if not labels or pull_number <= 0:
        return
    _github_request(
        "POST",
        f"/repos/{owner}/{repo}/issues/{pull_number}/labels",
        token,
        {"labels": list(labels)},
    )


def get_pull_request(
    owner: str,
    repo: str,
    pull_number: int,
    token: str,
) -> dict[str, Any]:
    if pull_number <= 0:
        raise ValueError(f"invalid pull request number: {pull_number}")
    return _github_request(
        "GET",
        f"/repos/{owner}/{repo}/pulls/{pull_number}",
        token,
    )


def update_pull_request_body(
    owner: str,
    repo: str,
    pull_number: int,
    body: str,
    token: str,
) -> dict[str, Any]:
    if pull_number <= 0:
        raise ValueError(f"invalid pull request number: {pull_number}")
    return _github_request(
        "PATCH",
        f"/repos/{owner}/{repo}/pulls/{pull_number}",
        token,
        {"body": body},
    )


def default_branch(owner: str, repo: str, token: str) -> str:
    """Return the repository's default branch, falling back to main."""
    payload = _github_request("GET", f"/repos/{owner}/{repo}", token)
    return str(payload.get("default_branch") or "main")


def can_push_to_repository(owner: str, repo: str, token: str) -> tuple[bool, str]:
    """Pre-flight the token's push access so import fails fast instead of after cloning."""
    try:
        payload = _github_request("GET", f"/repos/{owner}/{repo}", token)
    except GitHubError as exc:
        if exc.status == 404:
            return False, f"{owner}/{repo} not found, or the token cannot see it"
        return False, f"GitHub returned {exc.status}: {exc.message}"
    permissions = payload.get("permissions")
    if not isinstance(permissions, dict):
        # Fine-grained tokens may omit permissions; let the push itself be the check.
        return True, ""
    if permissions.get("push") or permissions.get("admin") or permissions.get("maintain"):
        return True, ""
    return False, f"token lacks push access to {owner}/{repo}"


def find_open_pull_request(
    owner: str,
    repo: str,
    token: str,
    *,
    head_branch: str,
) -> dict[str, Any] | None:
    """Return an existing open PR for head_branch so import does not duplicate it."""
    payload = _github_json(
        "GET",
        f"/repos/{owner}/{repo}/pulls?state=open&head={owner}:{head_branch}",
        token,
    )
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                return item
    return None


def _configure_git_origin(repo_dir: Path, owner: str, name: str, token: str) -> None:
    auth_url = f"https://x-access-token:{token}@github.com/{owner}/{name}.git"
    remotes = run_subprocess(
        [_git_executable(), "remote"],
        cwd=repo_dir,
        check=True,
        git=True,
    )
    if "origin" in remotes.stdout.split():
        _run_git(["remote", "set-url", "origin", auth_url], cwd=repo_dir)
    else:
        _run_git(["remote", "add", "origin", auth_url], cwd=repo_dir)


def _repository_exists(repository: ModuleRepository, token: str) -> bool:
    try:
        _github_request(
            "GET",
            f"/repos/{repository.owner}/{repository.name}",
            token,
        )
        return True
    except GitHubError as exc:
        if exc.status == 404:
            return False
        raise


def _create_org_repository(
    repository: ModuleRepository,
    token: str,
    *,
    description: str,
) -> None:
    _github_request(
        "POST",
        f"/orgs/{repository.owner}/repos",
        token,
        {
            "name": repository.name,
            "description": description
            or f"Terraform module generated by repave ({repository.name})",
            "private": False,
            "auto_init": False,
        },
    )


def _create_user_repository(
    repository: ModuleRepository,
    token: str,
    *,
    description: str,
) -> None:
    _github_request(
        "POST",
        "/user/repos",
        token,
        {
            "name": repository.name,
            "description": description
            or f"Terraform module generated by repave ({repository.name})",
            "private": False,
            "auto_init": False,
        },
    )


def list_repository_tags(
    owner: str,
    repo: str,
    token: str,
    *,
    client: GitHubRestClient | None = None,
) -> list[str]:
    """Return tag names for a GitHub repository (API order, up to 500 tags)."""
    tags: list[str] = []
    page = 1
    while page <= 5:
        payload = _github_json(
            "GET",
            f"/repos/{owner}/{repo}/tags?per_page=100&page={page}",
            token,
            client=client,
        )
        if not isinstance(payload, list) or not payload:
            break
        for item in payload:
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                if name:
                    tags.append(name)
        if len(payload) < 100:
            break
        page += 1
    return tags


def _github_json(
    method: str,
    path: str,
    token: str,
    body: dict[str, Any] | None = None,
    *,
    client: GitHubRestClient | None = None,
) -> Any:
    rest = client if client is not None else _default_github_client
    return rest.request_json(method, path, token, body)


def _github_request(
    method: str,
    path: str,
    token: str,
    body: dict[str, Any] | None = None,
    *,
    client: GitHubRestClient | None = None,
) -> dict[str, Any]:
    parsed = _github_json(method, path, token, body, client=client)
    return parsed if isinstance(parsed, dict) else {}


def _name_already_exists(message: str) -> bool:
    lowered = message.lower()
    return "already exists" in lowered or "name already exists" in lowered
