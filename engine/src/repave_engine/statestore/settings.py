"""Configuration for the state store.

Off by default: with no `state_store` block and no `REPAVE_STATE_STORE_URL`, repave
behaves exactly as it did before ADR 004 and mounts no state routes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from repave_engine.sql_store import DatabaseConfig, parse_database_url
from repave_engine.statestore.store import DEFAULT_TENANT

STATE_STORE_URL_ENV: Final = "REPAVE_STATE_STORE_URL"
STATE_STORE_TENANT_ENV: Final = "REPAVE_STATE_STORE_TENANT"
STATE_REQUIRED_GATES_ENV: Final = "REPAVE_STATE_REQUIRED_GATES"


@dataclass(frozen=True)
class StateStoreConfig:
    database: DatabaseConfig
    default_tenant: str = DEFAULT_TENANT
    required_gates: frozenset[str] = frozenset()
    """Gates that must be reported passing before a transaction may commit.

    Empty means gates are advisory. Naming one here makes it enforcing: a commit
    missing that gate is refused, so "forgot to run it" cannot read as "it passed".
    """

    @property
    def requires_postgres_warning(self) -> bool:
        """SQLite is accepted for local development only (ADR 004 Phase 0)."""
        return self.database.dialect != "postgresql"


def load_state_store_config(repo_root: Path) -> StateStoreConfig | None:
    """Read the `state_store` block, env first. None means the feature is disabled."""
    tenant = os.environ.get(STATE_STORE_TENANT_ENV, "").strip() or DEFAULT_TENANT

    env_gates = _gate_names(os.environ.get(STATE_REQUIRED_GATES_ENV, ""))

    env_url = os.environ.get(STATE_STORE_URL_ENV, "").strip()
    if env_url:
        return StateStoreConfig(
            database=parse_database_url(env_url, repo_root=repo_root),
            default_tenant=tenant,
            required_gates=env_gates,
        )

    from repave_engine.settings import _load_config_file

    file_data = _load_config_file(repo_root / "repave.config.yaml")
    block = file_data.get("state_store")
    if not isinstance(block, dict):
        return None
    if not _truthy(block.get("enabled", True)):
        return None
    url_raw = block.get("database_url")
    if not url_raw:
        return None
    return StateStoreConfig(
        database=parse_database_url(str(url_raw).strip(), repo_root=repo_root),
        default_tenant=str(block.get("default_tenant", tenant)).strip() or tenant,
        required_gates=env_gates or _gate_names(block.get("required_gates")),
    )


def _gate_names(raw: object) -> frozenset[str]:
    """Accept a comma-separated string (env) or a YAML list (config file)."""
    if isinstance(raw, str):
        items: list[str] = raw.split(",")
    elif isinstance(raw, list | tuple):
        items = [str(item) for item in raw]
    else:
        return frozenset()
    return frozenset(name.strip() for name in items if str(name).strip())


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")
