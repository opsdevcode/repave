"""Request-scoped acting user for audit and provenance."""

from __future__ import annotations

import contextvars

from repave_engine.audit import acting_user_from_env

_acting_user: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "repave_acting_user",
    default=None,
)


def set_acting_user(subject: str | None) -> contextvars.Token[str | None]:
    return _acting_user.set(subject)


def reset_acting_user(token: contextvars.Token[str | None]) -> None:
    _acting_user.reset(token)


def current_acting_user() -> str:
    value = _acting_user.get()
    if value and value.strip():
        return value.strip()
    return acting_user_from_env()
