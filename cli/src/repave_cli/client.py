"""HTTP client for `/api/state/v1`.

The only way this package reaches the state store. It must never import
`repave_engine.sql_store`, `psycopg`, or any database driver — see ADR 004, "the
credential boundary is the architecture".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from repave_engine.state_contract import (
    CLIENT_HEADER,
    HTTP_UPGRADE_REQUIRED,
    STATE_API_PREFIX,
)

from repave_cli import __version__
from repave_cli.config import ClientConfig


class StateClientError(RuntimeError):
    """A request failed. The message names the fix where one exists."""


@dataclass(frozen=True)
class StateSummary:
    tenant: str
    state: str
    serial: int
    version_count: int
    updated_at: str
    locked: bool

    @staticmethod
    def from_payload(payload: dict[str, Any]) -> StateSummary:
        return StateSummary(
            tenant=str(payload.get("tenant", "")),
            state=str(payload.get("state", "")),
            serial=int(payload.get("serial", 0)),
            version_count=int(payload.get("version_count", 0)),
            updated_at=str(payload.get("updated_at", "")),
            locked=bool(payload.get("locked", False)),
        )


@dataclass(frozen=True)
class StateVersion:
    version_id: str
    serial: int
    terraform_version: str
    size: int
    author: str
    created_at: str

    @staticmethod
    def from_payload(payload: dict[str, Any]) -> StateVersion:
        return StateVersion(
            version_id=str(payload.get("version_id", "")),
            serial=int(payload.get("serial", 0)),
            terraform_version=str(payload.get("terraform_version", "")),
            size=int(payload.get("size", 0)),
            author=str(payload.get("author", "")),
            created_at=str(payload.get("created_at", "")),
        )


class StateClient:
    """Thin, synchronous client. One instance per command invocation."""

    def __init__(self, config: ClientConfig, *, transport: httpx.BaseTransport | None = None):
        self._config = config
        headers = {CLIENT_HEADER: __version__, "Accept": "application/json"}
        if config.token:
            headers["Authorization"] = f"Bearer {config.token}"
        self._http = httpx.Client(
            base_url=f"{config.base_url}{STATE_API_PREFIX}",
            headers=headers,
            timeout=config.timeout,
            transport=transport,
            # Starlette redirects between `/path` and `/path/`; without this the
            # client sees an empty 307 body instead of the payload.
            follow_redirects=True,
        )

    def __enter__(self) -> StateClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    @property
    def tenant(self) -> str:
        return self._config.tenant

    # -- requests -----------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise StateClientError(
                f"cannot reach the repave state server at {self._config.base_url}: {exc}"
            ) from exc
        _raise_for_status(response)
        return response

    def describe(self) -> dict[str, Any]:
        payload = self._request("GET", "").json()
        return payload if isinstance(payload, dict) else {}

    def list_states(self, tenant: str | None = None) -> list[StateSummary]:
        params = {"tenant": tenant or self.tenant}
        payload = self._request("GET", "/states", params=params).json()
        items = payload.get("states", []) if isinstance(payload, dict) else []
        return [StateSummary.from_payload(item) for item in items if isinstance(item, dict)]

    def describe_state(self, state: str, *, tenant: str | None = None) -> dict[str, Any]:
        path = f"/states/{tenant or self.tenant}/{state}"
        payload = self._request("GET", path).json()
        return payload if isinstance(payload, dict) else {}

    def export_state(self, state: str, *, tenant: str | None = None) -> bytes:
        path = f"/states/{tenant or self.tenant}/{state}/export"
        return self._request("GET", path).content

    def import_state(self, state: str, raw: bytes, *, tenant: str | None = None) -> dict[str, Any]:
        path = f"/states/{tenant or self.tenant}/{state}/import"
        payload = self._request(
            "POST", path, content=raw, headers={"Content-Type": "application/json"}
        ).json()
        return payload if isinstance(payload, dict) else {}

    def list_versions(
        self, state: str, *, tenant: str | None = None, limit: int = 100
    ) -> list[StateVersion]:
        path = f"/states/{tenant or self.tenant}/{state}/versions"
        payload = self._request("GET", path, params={"limit": limit}).json()
        items = payload.get("versions", []) if isinstance(payload, dict) else []
        return [StateVersion.from_payload(item) for item in items if isinstance(item, dict)]


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    detail = _detail(response)
    if response.status_code == HTTP_UPGRADE_REQUIRED:
        raise StateClientError(f"repave-tf is too old for this server: {detail}")
    if response.status_code == 401:
        raise StateClientError(
            "not authorized: set REPAVE_STATE_TOKEN to a token with access to this state"
        )
    if response.status_code == 403:
        raise StateClientError(f"forbidden: {detail}")
    if response.status_code == 404:
        raise StateClientError(f"not found: {detail}")
    if response.status_code in (409, 423):
        raise StateClientError(detail)
    raise StateClientError(f"state server returned {response.status_code}: {detail}")


def _detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip() or response.reason_phrase
    if isinstance(payload, dict):
        for key in ("detail", "message", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return str(payload)
