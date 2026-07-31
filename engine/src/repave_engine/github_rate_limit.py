"""Per-installation GitHub REST rate-limit tracking and backoff.

Fleet-scale flows (batch import, upgrade campaigns) can exhaust the REST quota for a
single GitHub App installation. This module tracks ``X-RateLimit-*`` response headers
and sleeps before requests when remaining quota is low, or when GitHub returns 429.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

_DEFAULT_INSTALLATION = "default"
_LOW_REMAINING_THRESHOLD = 50
_MAX_BACKOFF_SECONDS = 300.0


@dataclass(frozen=True)
class RateLimitSnapshot:
    remaining: int
    limit: int
    reset_at: float

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0


class GitHubRateLimitTracker:
    """Thread-safe rate-limit state keyed by GitHub App installation id."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshots: dict[str, RateLimitSnapshot] = {}

    def clear(self) -> None:
        with self._lock:
            self._snapshots.clear()

    def update_from_headers(
        self,
        headers: dict[str, str],
        *,
        installation_id: str = _DEFAULT_INSTALLATION,
    ) -> None:
        remaining_raw = headers.get(
            "x-ratelimit-remaining", headers.get("X-RateLimit-Remaining", "")
        )
        limit_raw = headers.get("x-ratelimit-limit", headers.get("X-RateLimit-Limit", ""))
        reset_raw = headers.get("x-ratelimit-reset", headers.get("X-RateLimit-Reset", ""))
        if not remaining_raw or not reset_raw:
            return
        try:
            remaining = int(remaining_raw)
            limit = int(limit_raw) if limit_raw else 5000
            reset_at = float(reset_raw)
        except ValueError:
            return
        with self._lock:
            self._snapshots[installation_id] = RateLimitSnapshot(
                remaining=remaining,
                limit=limit,
                reset_at=reset_at,
            )

    def snapshot(self, installation_id: str = _DEFAULT_INSTALLATION) -> RateLimitSnapshot | None:
        with self._lock:
            return self._snapshots.get(installation_id)

    def wait_if_needed(
        self,
        *,
        installation_id: str = _DEFAULT_INSTALLATION,
        min_remaining: int = _LOW_REMAINING_THRESHOLD,
    ) -> None:
        """Sleep until quota recovers when remaining calls drop below the threshold."""
        with self._lock:
            state = self._snapshots.get(installation_id)
        if state is None or state.remaining >= min_remaining:
            return
        delay = max(0.0, state.reset_at - time.time()) + 1.0
        if delay > 0:
            time.sleep(min(delay, _MAX_BACKOFF_SECONDS))

    @staticmethod
    def backoff_seconds(retry_after: str | None, *, attempt: int = 0) -> float:
        if retry_after:
            try:
                return min(float(retry_after), _MAX_BACKOFF_SECONDS)
            except ValueError:
                pass
        return min(2.0**attempt, _MAX_BACKOFF_SECONDS)


_default_tracker = GitHubRateLimitTracker()


def default_rate_limit_tracker() -> GitHubRateLimitTracker:
    return _default_tracker


def current_installation_id() -> str:
    """Return the configured GitHub App installation id, or a stable default."""
    from repave_engine.github_auth import load_github_app_config

    config = load_github_app_config()
    if config is None:
        return _DEFAULT_INSTALLATION
    return config.installation_id


def wait_before_github_request(*, min_remaining: int = _LOW_REMAINING_THRESHOLD) -> None:
    _default_tracker.wait_if_needed(
        installation_id=current_installation_id(),
        min_remaining=min_remaining,
    )


def record_github_response_headers(headers: dict[str, str]) -> None:
    _default_tracker.update_from_headers(headers, installation_id=current_installation_id())


def clear_rate_limit_tracker() -> None:
    """Test helper."""
    _default_tracker.clear()
