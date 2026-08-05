"""Resolve the IaC CLI: OpenTofu preferred, Terraform fallback (ADR 004 decision 2).

Terraform 1.6+ ships under BUSL 1.1, whose Additional Use Grant restricts offering the
Licensed Work on a hosted or embedded basis in a competing paid product. OpenTofu is
MPL-2.0 and carries no such restriction, so `tofu` is preferred everywhere and
`terraform` stays supported for internal use. Set ``REPAVE_IAC_BINARY`` to pin one.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from repave_engine.gate_toolchain import resolve_tool, subprocess_cwd
from repave_engine.subprocess_run import run_subprocess

IAC_BINARY_ENV: Final = "REPAVE_IAC_BINARY"

#: Preference order. OpenTofu first — see module docstring.
IAC_BINARIES: Final[tuple[str, ...]] = ("tofu", "terraform")

_VERSION_TIMEOUT_SECONDS: Final = 15


@dataclass(frozen=True)
class IacBinary:
    """A resolved IaC CLI."""

    name: str
    """``tofu`` or ``terraform``."""

    path: str
    """Absolute path to the executable."""

    @property
    def is_opentofu(self) -> bool:
        return self.name == "tofu"


def iac_binary_preference() -> tuple[str, ...]:
    """Binary names to try, honoring the ``REPAVE_IAC_BINARY`` pin."""
    pinned = os.environ.get(IAC_BINARY_ENV, "").strip()
    if not pinned:
        return IAC_BINARIES
    if pinned not in IAC_BINARIES:
        raise ValueError(
            f"{IAC_BINARY_ENV} must be one of {', '.join(IAC_BINARIES)} (got {pinned!r})"
        )
    return (pinned,)


def resolve_iac_binary() -> IacBinary | None:
    """First IaC CLI found on PATH, or None when neither is installed."""
    for name in iac_binary_preference():
        found = resolve_tool(name)
        if found:
            return IacBinary(name=name, path=found)
    return None


def iac_binary_name() -> str:
    """Name to place at argv[0]; falls back to the preferred name when unresolved.

    Returning a name rather than a path keeps argv readable in logs and lets
    ``gate_runners.run_command`` do the final PATH resolution.
    """
    binary = resolve_iac_binary()
    if binary is not None:
        return binary.name
    return iac_binary_preference()[0]


def iac_argv(*args: str) -> list[str]:
    """Build an argv list led by the resolved IaC binary."""
    return [iac_binary_name(), *args]


def iac_cli_ready(cwd: Path | None = None) -> bool:
    """True when an IaC CLI is on PATH and ``<binary> version`` succeeds."""
    binary = resolve_iac_binary()
    if binary is None:
        return False
    run_cwd = subprocess_cwd(cwd if cwd is not None else Path(tempfile.gettempdir()))
    result = run_subprocess(
        [binary.path, "version"],
        cwd=run_cwd,
        check=False,
        env=os.environ.copy(),
        timeout=_VERSION_TIMEOUT_SECONDS,
    )
    return result.returncode == 0
