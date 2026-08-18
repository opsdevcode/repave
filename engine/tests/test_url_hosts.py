from __future__ import annotations

from repave_engine.url_hosts import (
    github_repo_name,
    hostname_is,
    is_github_url,
    parse_github_owner_repo,
    webhook_channel,
)


def test_webhook_channel_uses_hostname_not_substring() -> None:
    assert webhook_channel("https://hooks.slack.com/services/T/B/X") == "slack"
    assert webhook_channel("https://evil.example/hooks.slack.com") == "webhook"
    assert webhook_channel("https://company.webhook.office.com/webhookb2/x") == "teams"
    assert webhook_channel("https://office.com.evil.example/hook") == "webhook"


def test_is_github_url_rejects_embedded_host() -> None:
    assert is_github_url("https://github.com/acme/mod")
    assert is_github_url("git@github.com:acme/mod.git")
    assert not is_github_url("https://evil.example/github.com/acme/mod")


def test_parse_github_owner_repo_https_and_ssh() -> None:
    assert parse_github_owner_repo("https://github.com/acme/mod.git") == ("acme", "mod")
    assert parse_github_owner_repo("git@github.com:acme/mod") == ("acme", "mod")
    assert parse_github_owner_repo("https://gitlab.com/acme/mod") is None


def test_github_repo_name_uses_hostname() -> None:
    assert github_repo_name("https://github.com/opsdevcode/tf-aws-vpc-demo") == "tf-aws-vpc-demo"
    assert github_repo_name("https://evil.example/github.com/opsdevcode/stolen") == "stolen"


def test_hostname_is_exact() -> None:
    assert hostname_is("https://ghcr.io/acme/pack", "ghcr.io")
    assert not hostname_is("https://notghcr.io/acme/pack", "ghcr.io")
