"""Drive the local IaC binary (ADR 004 Phase 3).

Every subprocess here runs on the caller's machine with the caller's cloud
credentials. The state store never sees them — it receives a plan summary, gate
results, and the resulting state document, and nothing else.
"""

from __future__ import annotations

import json
import subprocess  # nosec B404 - the IaC CLI is the whole point of this module
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repave_engine.iac_binary import iac_binary_name

DEFAULT_TIMEOUT = 3600


class RunnerError(RuntimeError):
    """A local command failed. The message includes the tool's own stderr."""


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass(frozen=True)
class IacRunner:
    """Runs `tofu` (or `terraform`) in one working directory."""

    workdir: Path
    binary: str = ""
    timeout: int = DEFAULT_TIMEOUT
    quiet: bool = False

    @property
    def name(self) -> str:
        return self.binary or iac_binary_name()

    def run(self, *args: str, check: bool = True) -> CommandResult:
        argv = (self.name, *args)
        try:
            completed = subprocess.run(  # nosec B603 - argv is a fixed list, never a shell string
                list(argv),
                cwd=str(self.workdir),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RunnerError(
                f"{self.name} is not on PATH; install OpenTofu or set REPAVE_IAC_BINARY"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RunnerError(
                f"{' '.join(argv)} exceeded {self.timeout}s; raise --timeout or split the change"
            ) from exc

        result = CommandResult(
            argv=argv,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        if check and not result.ok:
            raise RunnerError(
                f"{' '.join(argv)} failed with exit {result.returncode}:\n"
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        return result

    # -- the pieces of a plan/apply cycle -------------------------------------

    def init(self) -> CommandResult:
        return self.run("init", "-input=false")

    def plan(self, plan_file: Path, *, extra: tuple[str, ...] = ()) -> CommandResult:
        """Write a binary plan. Non-zero exit is a real failure; 2 is not used here.

        `-detailed-exitcode` is deliberately not passed: it makes "no changes" look
        like a failure to every caller that checks the exit code.
        """
        return self.run("plan", "-input=false", "-out", str(plan_file), *extra)

    def show_plan_json(self, plan_file: Path) -> dict[str, Any]:
        result = self.run("show", "-json", str(plan_file))
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RunnerError(f"{self.name} show -json did not return JSON: {exc}") from exc
        return payload if isinstance(payload, dict) else {}

    def apply(self, plan_file: Path) -> CommandResult:
        return self.run("apply", "-input=false", "-auto-approve", str(plan_file))

    def state_pull(self) -> bytes:
        """The post-apply state document, as bytes to hand to the store."""
        return self.run("state", "pull").stdout.encode("utf-8")

    def providers_schema(self) -> dict[str, Any]:
        result = self.run("providers", "schema", "-json")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RunnerError(f"{self.name} providers schema did not return JSON: {exc}") from exc
        return payload if isinstance(payload, dict) else {}


def plan_change_counts(payload: Any) -> tuple[int, int, int]:
    """(create, update, delete) from plan JSON, for the human-facing summary."""
    if not isinstance(payload, dict):
        return 0, 0, 0
    changes = payload.get("resource_changes")
    if not isinstance(changes, list):
        return 0, 0, 0

    create = update = delete = 0
    for item in changes:
        if not isinstance(item, dict):
            continue
        change = item.get("change")
        actions = change.get("actions") if isinstance(change, dict) else None
        if not isinstance(actions, list):
            continue
        if "create" in actions:
            create += 1
        if "update" in actions:
            update += 1
        if "delete" in actions:
            delete += 1
    return create, update, delete
