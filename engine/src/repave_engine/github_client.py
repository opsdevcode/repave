"""Injectable GitHub REST client for tests and alternate transports."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


class GitHubError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class GitHubRestClient(Protocol):
    def request_json(
        self,
        method: str,
        path: str,
        token: str,
        body: dict[str, Any] | None = None,
    ) -> Any: ...


def _header_dict(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    return {str(key).lower(): str(value) for key, value in raw.items()}


@dataclass
class UrllibGitHubRestClient:
    max_retries: int = 3
    on_response: Callable[[dict[str, str]], None] | None = None

    def request_json(
        self,
        method: str,
        path: str,
        token: str,
        body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"https://api.github.com{path}"
        payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "repave-engine",
        }
        last_error: GitHubError | None = None
        for attempt in range(self.max_retries + 1):
            request = urllib.request.Request(  # nosec B310
                url,
                data=payload,
                method=method,
                headers=headers,
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310
                    response_headers = _header_dict(response.headers)
                    if self.on_response is not None:
                        self.on_response(response_headers)
                    raw = response.read().decode("utf-8")
                    if not raw:
                        return None
                    return json.loads(raw)
            except urllib.error.HTTPError as exc:
                response_headers = _header_dict(exc.headers)
                if self.on_response is not None:
                    self.on_response(response_headers)
                detail = exc.read().decode("utf-8", errors="replace")
                last_error = GitHubError(exc.code, detail)
                if exc.code == 429 and attempt < self.max_retries:
                    retry_after = response_headers.get("retry-after")
                    delay = 1.0
                    if retry_after:
                        try:
                            delay = min(float(retry_after), 300.0)
                        except ValueError:
                            delay = min(2.0**attempt, 300.0)
                    else:
                        delay = min(2.0**attempt, 300.0)
                    time.sleep(delay)
                    continue
                raise last_error from exc
        if last_error is not None:
            raise last_error
        raise GitHubError(0, "GitHub request failed")


@dataclass
class StaticGitHubRestClient:
    """In-package fake returning canned responses keyed by (method, path)."""

    responses: dict[tuple[str, str], Any] = field(default_factory=dict)
    errors: dict[tuple[str, str], GitHubError] = field(default_factory=dict)
    calls: list[tuple[str, str, dict[str, Any] | None]] = field(default_factory=list)

    def request_json(
        self,
        method: str,
        path: str,
        token: str,
        body: dict[str, Any] | None = None,
    ) -> Any:
        self.calls.append((method, path, body))
        key = (method.upper(), path)
        if key in self.errors:
            raise self.errors[key]
        if key in self.responses:
            return self.responses[key]
        return {}
