from __future__ import annotations

import pytest

from repave_cli.config import (
    DEFAULT_TENANT,
    DEFAULT_TIMEOUT_SECONDS,
    STATE_TENANT_ENV,
    STATE_TIMEOUT_ENV,
    STATE_TOKEN_ENV,
    STATE_URL_ENV,
    ConfigError,
    load_client_config,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (STATE_URL_ENV, STATE_TOKEN_ENV, STATE_TENANT_ENV, STATE_TIMEOUT_ENV):
        monkeypatch.delenv(name, raising=False)


def test_missing_url_names_the_env_var() -> None:
    with pytest.raises(ConfigError, match=STATE_URL_ENV):
        load_client_config()


def test_url_must_have_a_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(STATE_URL_ENV, "repave.example.com")
    with pytest.raises(ConfigError, match="http://"):
        load_client_config()


def test_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(STATE_URL_ENV, "https://repave.example.com/")
    monkeypatch.setenv(STATE_TOKEN_ENV, "tok")
    monkeypatch.setenv(STATE_TENANT_ENV, "acme")
    config = load_client_config()
    assert config.base_url == "https://repave.example.com"
    assert config.token == "tok"
    assert config.tenant == "acme"
    assert config.timeout == DEFAULT_TIMEOUT_SECONDS


def test_explicit_arguments_win(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(STATE_URL_ENV, "https://env.example.com")
    monkeypatch.setenv(STATE_TENANT_ENV, "from-env")
    config = load_client_config(base_url="https://flag.example.com", tenant="from-flag")
    assert config.base_url == "https://flag.example.com"
    assert config.tenant == "from-flag"


def test_tenant_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(STATE_URL_ENV, "https://repave.example.com")
    assert load_client_config().tenant == DEFAULT_TENANT


def test_timeout_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(STATE_URL_ENV, "https://repave.example.com")
    monkeypatch.setenv(STATE_TIMEOUT_ENV, "12.5")
    assert load_client_config().timeout == 12.5


@pytest.mark.parametrize("value", ["abc", "0", "-3"])
def test_invalid_timeout_rejected(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(STATE_URL_ENV, "https://repave.example.com")
    monkeypatch.setenv(STATE_TIMEOUT_ENV, value)
    with pytest.raises(ConfigError, match=STATE_TIMEOUT_ENV):
        load_client_config()
