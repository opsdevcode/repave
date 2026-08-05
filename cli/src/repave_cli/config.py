"""Client configuration, loaded from the environment.

Deliberately narrow: a server URL, a bearer token, and a default tenant. There is no
database setting because the client has no database access by design (ADR 004).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

STATE_URL_ENV: Final = "REPAVE_STATE_URL"
STATE_TOKEN_ENV: Final = "REPAVE_STATE_TOKEN"
STATE_TENANT_ENV: Final = "REPAVE_STATE_TENANT"
STATE_TIMEOUT_ENV: Final = "REPAVE_STATE_TIMEOUT"

DEFAULT_TENANT: Final = "default"
DEFAULT_TIMEOUT_SECONDS: Final = 60.0


class ConfigError(ValueError):
    """Configuration is missing or unusable."""


@dataclass(frozen=True)
class ClientConfig:
    base_url: str
    token: str = ""
    tenant: str = DEFAULT_TENANT
    timeout: float = DEFAULT_TIMEOUT_SECONDS


def load_client_config(
    *,
    base_url: str | None = None,
    tenant: str | None = None,
) -> ClientConfig:
    """Resolve client configuration; explicit arguments win over the environment."""
    url = (base_url or os.environ.get(STATE_URL_ENV, "")).strip().rstrip("/")
    if not url:
        raise ConfigError(
            f"no repave state server configured: set {STATE_URL_ENV} "
            "(for example https://repave.example.com) or pass --server"
        )
    if not url.startswith(("http://", "https://")):
        raise ConfigError(f"{STATE_URL_ENV} must start with http:// or https:// (got {url!r})")

    return ClientConfig(
        base_url=url,
        token=os.environ.get(STATE_TOKEN_ENV, "").strip(),
        tenant=(tenant or os.environ.get(STATE_TENANT_ENV, "")).strip() or DEFAULT_TENANT,
        timeout=_timeout_seconds(),
    )


def _timeout_seconds() -> float:
    raw = os.environ.get(STATE_TIMEOUT_ENV, "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{STATE_TIMEOUT_ENV} must be a number of seconds (got {raw!r})") from exc
    if value <= 0:
        raise ConfigError(f"{STATE_TIMEOUT_ENV} must be greater than zero (got {raw!r})")
    return value
