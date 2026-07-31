from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from repave_engine.blueprint import load_blueprint
from repave_engine.gates import GateResult
from repave_engine.notifications import (
    GenerationNotificationContext,
    notify_after_generation,
    publish_succeeded,
    summarize_gates,
)
from repave_engine.settings import NotificationsConfig, load_notifications_config


def test_publish_succeeded_rejects_dry_run_and_failures() -> None:
    assert publish_succeeded(pr_message="Pushed.", dry_run=True) is False
    assert publish_succeeded(pr_message="GitHub publish failed.", dry_run=False) is False
    assert publish_succeeded(pr_message="Dry-run: not pushed", dry_run=False) is False
    assert publish_succeeded(pr_message="Pushed initial commit.", dry_run=False) is True


def test_summarize_gates() -> None:
    gates = [
        GateResult("a", True, False, "ok"),
        GateResult("b", True, True, "skip"),
        GateResult("c", False, False, "fail"),
    ]
    assert summarize_gates(gates) == "1 passed, 1 failed, 1 skipped"


def test_load_notifications_config_from_file(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        """
notifications:
  enabled: true
  webhook_url: https://example.com/hook
  events:
    - publish_complete
""",
        encoding="utf-8",
    )
    config = load_notifications_config(tmp_path)
    assert config is not None
    assert config.enabled is True
    assert config.webhook_url == "https://example.com/hook"
    assert config.events == frozenset({"publish_complete"})


def test_notify_after_generation_posts_generic_webhook(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-module-generic",
        repo_root=repo_root,
    )
    config = NotificationsConfig(
        enabled=True,
        slack_webhook_url=None,
        teams_webhook_url=None,
        webhook_url="https://example.com/repave-events",
        events=frozenset({"publish_complete"}),
    )
    captured: list[dict] = []

    def fake_post(url: str, json: dict, timeout: float) -> MagicMock:
        captured.append({"url": url, "json": json})
        response = MagicMock()
        response.status_code = 204
        return response

    monkeypatch.setattr(httpx, "post", fake_post)

    notify_after_generation(
        repo_root,
        context=GenerationNotificationContext(
            blueprint=blueprint,
            gates=[GateResult("terraform-fmt", True, False, "ok")],
            dry_run=False,
            pr_message="Pushed initial commit.\nRepository: https://github.com/o/r",
            repository_web_url="https://github.com/o/r",
            module_name="demo",
        ),
        config=config,
    )

    assert len(captured) == 1
    assert captured[0]["json"]["event"] == "publish_complete"
    assert captured[0]["json"]["module_name"] == "demo"


def test_notify_after_generation_never_raises_on_http_error(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-module-generic",
        repo_root=repo_root,
    )

    def boom(*args: object, **kwargs: object) -> None:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", boom)
    config = NotificationsConfig(
        enabled=True,
        slack_webhook_url="https://hooks.slack.com/services/x",
        teams_webhook_url=None,
        webhook_url=None,
        events=frozenset({"publish_complete"}),
    )
    notify_after_generation(
        repo_root,
        context=GenerationNotificationContext(
            blueprint=blueprint,
            gates=[],
            dry_run=False,
            pr_message="Pushed.",
            repository_web_url="https://github.com/o/r",
            module_name="demo",
        ),
        config=config,
    )
