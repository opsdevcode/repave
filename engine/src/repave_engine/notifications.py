"""Best-effort outbound notifications for generation and publish events."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from repave_engine.blueprint import Blueprint
from repave_engine.gates import GateResult, gate_summary
from repave_engine.settings import NotificationsConfig, load_notifications_config

logger = logging.getLogger(__name__)

_EVENT_PUBLISH_COMPLETE = "publish_complete"
_EVENT_GENERATION_FAILED = "generation_failed"
_EVENT_GENERATION_SUCCEEDED = "generation_succeeded"


def publish_succeeded(*, pr_message: str, dry_run: bool) -> bool:
    if dry_run:
        return False
    lowered = pr_message.lower()
    if "github publish failed" in lowered:
        return False
    return "dry-run:" not in lowered


def summarize_gates(gates: list[GateResult]) -> str:
    summary = gate_summary(gates)
    parts = [f"{summary['passed']} passed"]
    if summary["failed"]:
        parts.append(f"{summary['failed']} failed")
    if summary["skipped"]:
        parts.append(f"{summary['skipped']} skipped")
    return ", ".join(parts)


def _redact_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme:
        return "<webhook>"
    host = parsed.netloc or parsed.path.split("/")[0]
    return f"{parsed.scheme}://{host}/…"


def _post_webhook(url: str, payload: dict[str, Any], *, label: str) -> None:
    last_error: str | None = None
    for attempt in range(3):
        try:
            response = httpx.post(url, json=payload, timeout=10.0)
            if response.status_code < 400:
                logger.info("Notification delivered (%s → %s)", label, _redact_url(url))
                return
            last_error = f"HTTP {response.status_code}"
        except httpx.HTTPError as exc:
            last_error = str(exc)
        if attempt < 2:
            time.sleep(0.5 * (attempt + 1))
    logger.warning(
        "Notification failed after retries (%s → %s): %s",
        label,
        _redact_url(url),
        last_error or "unknown error",
    )


def _slack_payload(text: str) -> dict[str, Any]:
    return {"text": text}


def _teams_payload(text: str) -> dict[str, Any]:
    return {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": "repave",
        "text": text,
    }


@dataclass(frozen=True)
class GenerationNotificationContext:
    blueprint: Blueprint
    gates: list[GateResult]
    dry_run: bool
    pr_message: str
    repository_web_url: str | None
    module_name: str


def notify_after_generation(
    repo_root: Path,
    *,
    context: GenerationNotificationContext,
    config: NotificationsConfig | None = None,
) -> None:
    """Send configured webhooks; never raises."""
    try:
        resolved = config if config is not None else load_notifications_config(repo_root)
    except ValueError as exc:
        logger.warning("Skipping notifications: %s", exc)
        return
    if resolved is None or not resolved.enabled:
        return

    gates_ok = all(gate.passed or gate.skipped for gate in context.gates)
    published = publish_succeeded(pr_message=context.pr_message, dry_run=context.dry_run)

    events: list[str] = []
    if published and _EVENT_PUBLISH_COMPLETE in resolved.events:
        events.append(_EVENT_PUBLISH_COMPLETE)
    if not gates_ok and _EVENT_GENERATION_FAILED in resolved.events:
        events.append(_EVENT_GENERATION_FAILED)
    if context.dry_run and gates_ok and _EVENT_GENERATION_SUCCEEDED in resolved.events:
        events.append(_EVENT_GENERATION_SUCCEEDED)

    if not events:
        return

    repo_line = context.repository_web_url or "(local dry-run)"
    gate_line = summarize_gates(context.gates)
    title = ", ".join(events)
    text = (
        f"*{title}*\n"
        f"Blueprint: `{context.blueprint.name}` v{context.blueprint.version}\n"
        f"Module: `{context.module_name}`\n"
        f"Repository: {repo_line}\n"
        f"Gates: {gate_line}\n"
        f"\n{context.pr_message.strip()}"
    )
    generic_payload = {
        "event": events[0] if len(events) == 1 else events,
        "blueprint": context.blueprint.name,
        "blueprint_version": context.blueprint.version,
        "module_name": context.module_name,
        "repository_url": context.repository_web_url,
        "dry_run": context.dry_run,
        "gates": gate_line,
        "message": context.pr_message.strip(),
    }

    for url in resolved.webhook_urls():
        if "office.com" in url or "office365.com" in url or "webhook.office.com" in url:
            _post_webhook(url, _teams_payload(text), label="teams")
        elif "hooks.slack.com" in url:
            _post_webhook(url, _slack_payload(text), label="slack")
        else:
            _post_webhook(url, generic_payload, label="webhook")
