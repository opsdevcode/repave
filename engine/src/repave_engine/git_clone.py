"""Shallow git clone for read-only remote verify (mirrors operator/internal/git/clone.go)."""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse

from repave_engine.github_auth import resolve_github_access_token
from repave_engine.subprocess_run import run_subprocess
from repave_engine.target_repo import _git_executable

_DEFAULT_DEPTH = 1
_REDACTED = "***"


class CloneError(RuntimeError):
    """Failed to clone a remote repository."""


def is_http_remote(repo_url: str) -> bool:
    lowered = repo_url.strip().lower()
    return lowered.startswith("https://") or lowered.startswith("http://")


def credential_remote(repo_url: str, token: str) -> str:
    """Inject an HTTPS token without changing the host (GHE-safe)."""
    parsed = urlparse(repo_url.strip())
    if not parsed.hostname:
        raise CloneError(f"repository URL {repo_url!r} has no host")
    userinfo = f"x-access-token:{quote(token, safe='')}"
    host = parsed.hostname
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=f"{userinfo}@{host}"))


def _redact_secrets(message: str, token: str | None) -> str:
    if not token:
        return message
    return message.replace(token, _REDACTED)


def shallow_clone(
    repo_url: str,
    dest_dir: Path,
    *,
    token: str | None = None,
    depth: int = _DEFAULT_DEPTH,
    ref: str | None = None,
) -> None:
    """Clone repo_url into dest_dir (created if needed). Raises CloneError on failure."""
    url = repo_url.strip()
    if not url:
        raise CloneError("repository URL is required")

    dest_dir = dest_dir.resolve()
    dest_dir.parent.mkdir(parents=True, exist_ok=True)

    remote = url
    secret = (token or "").strip() or None
    if secret and is_http_remote(url):
        try:
            remote = credential_remote(url, secret)
        except CloneError:
            raise
        except ValueError as exc:
            raise CloneError(f"parse repository URL: {exc}") from exc

    cmd = [
        _git_executable(),
        "clone",
        "--depth",
        str(max(depth, 1)),
        "--single-branch",
        "--no-tags",
    ]
    if ref and ref.strip():
        cmd.extend(["--branch", ref.strip()])
    cmd.extend([remote, str(dest_dir)])

    try:
        run_subprocess(cmd, git=True, check=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        detail = _redact_secrets(detail, secret)
        raise CloneError(detail or "git clone failed") from exc
    except FileNotFoundError as exc:
        raise CloneError("git executable not found") from exc


@contextmanager
def ephemeral_clone(
    repo_url: str,
    *,
    token: str | None = None,
    ref: str | None = None,
) -> Iterator[Path]:
    """Yield a shallow clone directory; removed when the context exits."""
    with tempfile.TemporaryDirectory(prefix="repave-verify-") as tmp:
        dest = Path(tmp) / "repo"
        shallow_clone(repo_url, dest, token=token, ref=ref)
        yield dest


def resolve_git_token(explicit: str | None = None) -> str | None:
    return resolve_github_access_token(explicit)
