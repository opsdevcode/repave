"""SHA pins for GitHub Actions referenced by generated-repo CI.

A mutable tag like ``actions/checkout@v4`` lets the action owner change what runs in every
generated repository after the fact, so generated workflows reference an immutable commit SHA
and carry the tag as a trailing comment for readers.

Values load from ``.github/action-pins.json`` at the repo root — the same file
``scripts/check-action-pins.py`` enforces for this repository's own workflows — so a bump lands
in one place for both.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
PINS_FILE = _REPO_ROOT / ".github" / "action-pins.json"

# Actions referenced by templates/ci/repave-gates.yml.jinja.
REQUIRED_ACTIONS: tuple[str, ...] = (
    "actions/checkout",
    "actions/setup-python",
    "actions/setup-go",
    "actions/setup-node",
    "actions/setup-java",
    "actions/setup-dotnet",
    "hashicorp/setup-terraform",
    "terraform-linters/setup-tflint",
    "azure/setup-helm",
)


@dataclass(frozen=True)
class ActionPin:
    repository: str
    sha: str
    tag: str

    @property
    def ref(self) -> str:
        return f"{self.repository}@{self.sha}"


def load_action_pins(path: Path | None = None) -> dict[str, ActionPin]:
    """Load action pins keyed by repository (for example ``actions/checkout``)."""
    pins_path = path or PINS_FILE
    if not pins_path.is_file():
        raise FileNotFoundError(f"Missing action pins: {pins_path}")
    raw = json.loads(pins_path.read_text(encoding="utf-8"))
    pins: dict[str, ActionPin] = {}
    for spec, sha in raw.items():
        repository, _, tag = str(spec).partition("@")
        pins[repository] = ActionPin(repository=repository, sha=str(sha), tag=tag)
    missing = [name for name in REQUIRED_ACTIONS if name not in pins]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"{pins_path.name} missing required actions: {joined}")
    return pins


@lru_cache(maxsize=1)
def _pins() -> dict[str, ActionPin]:
    # Loaded on first use, not at import: `repave gates` and `repave doctor` never render a
    # workflow, and must keep working where .github/ is absent (published images, pip installs).
    return load_action_pins()


def action_pin(repository: str) -> ActionPin:
    try:
        return _pins()[repository]
    except KeyError:
        raise KeyError(
            f"unknown action pin {repository!r}; add it to .github/action-pins.json"
        ) from None


def action_pins() -> dict[str, ActionPin]:
    return dict(_pins())


__all__ = [
    "PINS_FILE",
    "REQUIRED_ACTIONS",
    "ActionPin",
    "action_pin",
    "action_pins",
    "load_action_pins",
]
