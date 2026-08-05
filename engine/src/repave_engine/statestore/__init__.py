"""Authoritative Terraform state store and resource graph (ADR 004).

The store owns state bytes and a normalized graph derived from them. Execution
lives in the `repave-cli` client, which never touches this package.
"""

from repave_engine.statestore.migrate import (
    Migration,
    apply_migrations,
    current_schema_version,
    load_migrations,
)

__all__ = [
    "Migration",
    "apply_migrations",
    "current_schema_version",
    "load_migrations",
]
