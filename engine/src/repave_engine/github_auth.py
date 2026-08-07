"""GitHub App installation tokens with PAT fallback for publish and git remotes."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import jwt

_TOKEN_REFRESH_BUFFER_SECONDS = 300
_APP_JWT_LIFETIME = timedelta(minutes=9)
_APP_JWT_CLOCK_SKEW = timedelta(seconds=60)


@dataclass(frozen=True)
class GitHubAppConfig:
    app_id: str
    installation_id: str
    private_key_pem: str


def _normalize_pem(raw: str) -> str:
    return raw.replace("\\n", "\n").strip()


def load_github_app_config() -> GitHubAppConfig | None:
    app_id = os.environ.get("GITHUB_APP_ID", "").strip()
    installation_id = os.environ.get("GITHUB_APP_INSTALLATION_ID", "").strip()
    private_key = os.environ.get("GITHUB_APP_PRIVATE_KEY", "").strip()
    key_file = os.environ.get("GITHUB_APP_PRIVATE_KEY_FILE", "").strip()
    if key_file and not private_key:
        private_key = Path(key_file).read_text(encoding="utf-8").strip()
    private_key = _normalize_pem(private_key)
    if not app_id or not installation_id or not private_key:
        return None
    return GitHubAppConfig(
        app_id=app_id,
        installation_id=installation_id,
        private_key_pem=private_key,
    )


def github_credentials_configured() -> bool:
    if os.environ.get("GITHUB_TOKEN", "").strip():
        return True
    return load_github_app_config() is not None


def mint_app_jwt(config: GitHubAppConfig) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "iat": int((now - _APP_JWT_CLOCK_SKEW).timestamp()),
        "exp": int((now + _APP_JWT_LIFETIME).timestamp()),
        "iss": config.app_id,
    }
    token = jwt.encode(payload, config.private_key_pem, algorithm="RS256")
    return token if isinstance(token, str) else token.decode("utf-8")


def _parse_github_expires(raw: str) -> float:
    if not raw:
        return time.time() + 3600
    normalized = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return time.time() + 3600


def fetch_installation_token(config: GitHubAppConfig) -> tuple[str, float]:
    app_jwt = mint_app_jwt(config)
    url = f"https://api.github.com/app/installations/{config.installation_id}/access_tokens"
    response = httpx.post(
        url,
        headers={
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "repave-engine",
        },
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("GitHub installation token response must be a JSON object")
    token = str(data.get("token", "")).strip()
    if not token:
        raise ValueError("GitHub installation token response missing token")
    _validate_installation_token_permissions(data)
    expires_at = _parse_github_expires(str(data.get("expires_at", "")).strip())
    return token, expires_at


class _InstallationTokenCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._token: str | None = None
        self._expires_at: float = 0.0

    def get(self, mint: Callable[[], tuple[str, float]]) -> str:
        with self._lock:
            now = time.time()
            if self._token and now < self._expires_at - _TOKEN_REFRESH_BUFFER_SECONDS:
                return self._token
            token, expires_at = mint()
            self._token = token
            self._expires_at = expires_at
            return token

    def clear(self) -> None:
        with self._lock:
            self._token = None
            self._expires_at = 0.0


_installation_token_cache = _InstallationTokenCache()


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


def _prefer_github_app_over_pat() -> bool:
    return _env_truthy("REPAVE_PREFER_GITHUB_APP") or _env_truthy("REPAVE_FORCE_GITHUB_APP")


def _pat_is_oauth_user_token(token: str) -> bool:
    # OAuth user-to-server tokens (gho_) cannot push to org repos via git in hosted mode.
    return token.startswith("gho_")


def _validate_installation_token_permissions(data: dict[str, object]) -> None:
    if _env_truthy("REPAVE_SKIP_GITHUB_APP_PERMISSION_CHECK"):
        return
    perms = data.get("permissions")
    if not isinstance(perms, dict):
        return
    contents = str(perms.get("contents", "")).lower()
    if contents in {"write", "admin"}:
        return
    raise ValueError(
        "GitHub App installation token lacks contents: write — set Repository permissions "
        "→ Contents to Read and write on the app, save, and accept the org installation update"
    )


def resolve_github_access_token(explicit: str | None = None) -> str | None:
    """Return PAT, explicit token, or a cached GitHub App installation token."""
    raw = (explicit or "").strip()
    if raw:
        return raw
    config = load_github_app_config()
    pat = os.environ.get("GITHUB_TOKEN", "").strip()
    if pat and config is not None:
        if _prefer_github_app_over_pat() or _pat_is_oauth_user_token(pat):
            pat = ""
    if pat:
        return pat
    if config is None:
        return None
    return _installation_token_cache.get(lambda: fetch_installation_token(config))


def clear_installation_token_cache() -> None:
    """Test helper: drop cached installation token."""
    _installation_token_cache.clear()
