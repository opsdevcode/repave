from __future__ import annotations

import pytest

from repave_engine.auth_context import current_acting_user, reset_acting_user, set_acting_user


def test_current_acting_user_from_context() -> None:
    token = set_acting_user("alice@example.com")
    try:
        assert current_acting_user() == "alice@example.com"
    finally:
        reset_acting_user(token)


def test_current_acting_user_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPAVE_ACTING_USER", "env-user")
    assert current_acting_user() == "env-user"
