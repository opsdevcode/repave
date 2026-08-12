"""v3 foundation config — default-off until the v3 line ships."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from repave_engine.waivers import Clock, WaiverRecord, load_waivers

_CONFIG_NAMES = ("repave.config.yaml", "repave.config.yml")


@dataclass(frozen=True)
class V3FoundationConfig:
    enabled: bool
    waivers_file: Path | None
    waiver_warn_days: int


@dataclass(frozen=True)
class WaiverPolicy:
    """Resolved waiver enforcement for a gate run."""

    enabled: bool
    waivers: tuple[WaiverRecord, ...] = ()
    warn_days: int = 7
    entity_id: str | None = None
    clock: Clock | None = None

    @classmethod
    def disabled(cls) -> WaiverPolicy:
        return cls(enabled=False)


def load_waiver_policy(
    repo_root: Path | None,
    *,
    entity_id: str | None = None,
    clock: Clock | None = None,
) -> WaiverPolicy:
    """Load waiver records when v3 foundation is enabled; otherwise disabled."""
    if repo_root is None:
        return WaiverPolicy.disabled()
    config = load_v3_foundation_config(repo_root)
    if not config.enabled or config.waivers_file is None:
        return WaiverPolicy.disabled()
    return WaiverPolicy(
        enabled=True,
        waivers=load_waivers(config.waivers_file),
        warn_days=config.waiver_warn_days,
        entity_id=entity_id,
        clock=clock,
    )


def load_v3_foundation_config(repo_root: Path) -> V3FoundationConfig:
    """Load v3 foundation knobs. Disabled when the block is absent or enabled: false."""
    path = _find_config(repo_root)
    if path is None:
        return V3FoundationConfig(enabled=False, waivers_file=None, waiver_warn_days=7)

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return V3FoundationConfig(enabled=False, waivers_file=None, waiver_warn_days=7)

    block = data.get("v3")
    if not isinstance(block, dict):
        return V3FoundationConfig(enabled=False, waivers_file=None, waiver_warn_days=7)

    enabled_raw = block.get("enabled", False)
    if not isinstance(enabled_raw, bool):
        raise ValueError("v3.enabled must be a boolean")
    if not enabled_raw:
        return V3FoundationConfig(enabled=False, waivers_file=None, waiver_warn_days=7)

    waivers_raw = block.get("waivers_file")
    waivers_file: Path | None
    if waivers_raw is None:
        waivers_file = repo_root / "data" / "waivers.jsonl"
    else:
        waivers_file = Path(str(waivers_raw))
        if not waivers_file.is_absolute():
            waivers_file = repo_root / waivers_file

    warn_raw = block.get("waiver_warn_days", 7)
    if not isinstance(warn_raw, int) or warn_raw < 0:
        raise ValueError("v3.waiver_warn_days must be a non-negative integer")

    return V3FoundationConfig(
        enabled=True,
        waivers_file=waivers_file,
        waiver_warn_days=warn_raw,
    )


def _find_config(repo_root: Path) -> Path | None:
    for name in _CONFIG_NAMES:
        candidate = repo_root / name
        if candidate.is_file():
            return candidate
    return None
