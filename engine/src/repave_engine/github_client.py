"""Injectable GitHub REST client for tests and alternate transports."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
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


class UrllibGitHubRestClient:
    def request_json(
        self,
        method: str,
        path: str,
        token: str,
        body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"https://api.github.com{path}"
        payload = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(  # nosec B310
            url,
            data=payload,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "repave-engine",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310
                raw = response.read().decode("utf-8")
                if not raw:
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise GitHubError(exc.code, detail) from exc


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
