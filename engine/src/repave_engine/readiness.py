"""Kubernetes readiness checks for /readyz."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from repave_engine.gate_toolchain import gate_tool_status, portal_runtime_info


@dataclass
class ReadinessReport:
    ready: bool
    checks: dict[str, bool] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": "ready" if self.ready else "not_ready",
            "checks": self.checks,
        }
        payload.update(self.details)
        return payload


def path_writable(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".repave-write-check"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def github_api_reachable(token: str, *, timeout: float = 5.0) -> tuple[bool, str | None]:
    """Lightweight GET /rate_limit; returns (ok, error_detail)."""
    request = urllib.request.Request(  # nosec B310
        "https://api.github.com/rate_limit",
        method="GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "repave-engine",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
            raw = response.read().decode("utf-8")
            if raw:
                json.loads(raw)
            return True, None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        return False, f"HTTP {exc.code}: {detail}"
    except OSError as exc:
        return False, str(exc)


def gate_toolchain_required() -> bool:
    if os.environ.get("REPAVE_EXTERNAL_WORKERS", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return False
    if os.environ.get("REPAVE_EXECUTION_MODE", "").strip().lower() == "worker":
        return False
    gate_env = os.environ.get("REPAVE_IMAGE_GATE_TOOLCHAIN", "").strip().lower()
    if gate_env in ("1", "true", "yes"):
        return True
    if gate_env in ("0", "false", "no"):
        return False
    repave_env = os.environ.get("REPAVE_ENV", "").strip().lower()
    return repave_env not in ("local", "dev", "development", "")


def evaluate_readiness(
    *,
    modules_root: Path,
    runs_db: Path | None,
    shutting_down: bool,
    auth_service_enabled: bool,
    require_session_secret: bool,
    github_token_configured: bool,
    run_queue_depth: int | None = None,
    sql_session_store_ok: bool | None = None,
) -> ReadinessReport:
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {
        "config_loaded": True,
        "github_token_configured": github_token_configured,
    }

    checks["not_shutting_down"] = not shutting_down
    if shutting_down:
        details["shutting_down"] = True

    checks["modules_root_writable"] = path_writable(modules_root)
    details["modules_root"] = str(modules_root)

    if runs_db is not None:
        checks["runs_db_writable"] = path_writable(runs_db.parent)
        details["runs_db"] = str(runs_db)

    session_ok = True
    if auth_service_enabled or require_session_secret:
        session_ok = bool(os.environ.get("REPAVE_SESSION_SECRET", "").strip())
    checks["session_secret"] = session_ok

    if sql_session_store_ok is not None:
        checks["session_store"] = sql_session_store_ok

    if gate_toolchain_required():
        tools = gate_tool_status()
        details["gate_tools"] = tools
        checks["gate_tools"] = all(tools.values())
    else:
        details["runtime"] = portal_runtime_info()

    if github_token_configured:
        require_github = os.environ.get("REPAVE_READY_REQUIRE_GITHUB", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        reachable, err = github_api_reachable(os.environ["GITHUB_TOKEN"].strip())
        details["github_api_reachable"] = reachable
        if err:
            details["github_api_error"] = err
        if require_github:
            checks["github_api"] = reachable

    if run_queue_depth is not None:
        details["async_generation"] = True
        details["run_queue_inflight"] = run_queue_depth

    ready = all(checks.values())
    return ReadinessReport(ready=ready, checks=checks, details=details)
