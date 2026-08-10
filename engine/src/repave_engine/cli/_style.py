"""Subtle terminal styling for CLI output.

Respects ``NO_COLOR``, ``FORCE_COLOR``, and non-TTY stdout. Color never carries
meaning alone — status labels (``PASS`` / ``FAIL``) remain in the plain text.
"""

from __future__ import annotations

import os
import sys
from typing import TextIO

_RESET = "\033[0m"
_BOLD = "\033[1m"
# Brand amber (golden path) — 256-color approx of #F59E0B
_BRAND = "\033[38;5;214m"
_SUCCESS = "\033[32m"
_ERROR = "\033[31m"
_MUTED = "\033[90m"


def color_enabled(*, stream: TextIO | None = None) -> bool:
    """Return True when ANSI colors may be emitted on ``stream`` (default stdout)."""
    out = stream if stream is not None else sys.stdout
    force = os.environ.get("FORCE_COLOR", "").strip()
    if force and force != "0":
        return True
    if os.environ.get("NO_COLOR", "").strip() != "":
        return False
    if os.environ.get("TERM", "") == "dumb":
        return False
    return bool(getattr(out, "isatty", lambda: False)())


def _wrap(code: str, text: str, *, stream: TextIO | None = None) -> str:
    if not text or not color_enabled(stream=stream):
        return text
    return f"{code}{text}{_RESET}"


def brand(text: str, *, stream: TextIO | None = None) -> str:
    """Highlight Repave / golden-path emphasis (amber when color is on)."""
    return _wrap(_BRAND, text, stream=stream)


def heading(text: str, *, stream: TextIO | None = None) -> str:
    """Bold + brand for section headings."""
    if not color_enabled(stream=stream):
        return text
    return f"{_BOLD}{_BRAND}{text}{_RESET}"


def success(text: str, *, stream: TextIO | None = None) -> str:
    return _wrap(_SUCCESS, text, stream=stream)


def error(text: str, *, stream: TextIO | None = None) -> str:
    return _wrap(_ERROR, text, stream=stream)


def muted(text: str, *, stream: TextIO | None = None) -> str:
    return _wrap(_MUTED, text, stream=stream)


def gate_status(status: str, *, stream: TextIO | None = None) -> str:
    """Color a gate status token without removing the plain label."""
    key = status.strip().upper()
    if key == "PASS":
        return success(status, stream=stream)
    if key == "FAIL":
        return error(status, stream=stream)
    return muted(status, stream=stream)
