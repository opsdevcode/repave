"""Hostname-based URL checks (avoid substring matches CodeQL flags)."""

from __future__ import annotations

from urllib.parse import urlparse

_SLACK_HOSTS = frozenset({"hooks.slack.com"})
_TEAMS_HOSTS = frozenset({"office.com", "office365.com", "webhook.office.com"})
_TEAMS_SUFFIXES = (".office.com", ".office365.com")


def url_hostname(url: str) -> str:
    """Return the lowercase hostname, including ``git@host:path`` remotes."""
    text = url.strip()
    if not text:
        return ""
    if text.startswith("git@"):
        host = text[4:].split(":", 1)[0]
        return host.lower()
    parsed = urlparse(text if "://" in text else f"https://{text}")
    return (parsed.hostname or "").lower()


def hostname_is(url: str, *hosts: str) -> bool:
    """True when the URL hostname equals one of ``hosts`` (no suffix match)."""
    host = url_hostname(url)
    return host in {item.lower() for item in hosts}


def hostname_matches(url: str, *hosts: str, suffixes: tuple[str, ...] = ()) -> bool:
    """True when the hostname equals ``hosts`` or ends with ``suffixes``."""
    host = url_hostname(url)
    if host in {item.lower() for item in hosts}:
        return True
    return any(host.endswith(suffix.lower()) for suffix in suffixes)


def is_github_url(url: str) -> bool:
    return hostname_matches(url, "github.com", suffixes=(".github.com",))


def webhook_channel(url: str) -> str:
    """Classify a notification URL as slack, teams, or generic webhook."""
    if hostname_is(url, *_SLACK_HOSTS):
        return "slack"
    if hostname_matches(url, *_TEAMS_HOSTS, suffixes=_TEAMS_SUFFIXES):
        return "teams"
    return "webhook"


def parse_github_owner_repo(raw: str) -> tuple[str, str] | None:
    """Return ``(owner, repo)`` for a GitHub HTTPS or SSH remote, else None."""
    text = raw.strip().rstrip("/")
    if not text:
        return None
    if text.endswith(".git"):
        text = text[: -len(".git")]
    if text.startswith("git@"):
        _, _, rest = text.partition("@")
        host, sep, path = rest.partition(":")
        if not sep or host.lower() != "github.com":
            return None
        parts = [part for part in path.split("/") if part]
    else:
        parsed = urlparse(text if "://" in text else f"https://{text}")
        host = (parsed.hostname or "").lower()
        if host != "github.com" and not host.endswith(".github.com"):
            return None
        parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    owner, name = parts[0], parts[1]
    if name.endswith(".git"):
        name = name[:-4]
    if not owner or not name:
        return None
    return owner, name


def github_repo_name(repository_url: str) -> str:
    """Repo name from a GitHub URL, or the last path segment as a fallback."""
    parsed = parse_github_owner_repo(repository_url)
    if parsed is not None:
        return parsed[1]
    normalized = repository_url.strip().rstrip("/")
    if not normalized:
        return ""
    return normalized.rsplit("/", 1)[-1]
