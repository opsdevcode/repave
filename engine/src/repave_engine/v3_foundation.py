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
    developer_lab_enabled: bool
    waivers_file: Path | None
    waiver_warn_days: int
    auto_merge_enabled: bool = False
    auto_merge_kill_switch: bool = False
    mandatory_policy_enabled: bool = False
    regulated_families: frozenset[str] = frozenset()


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
    disabled = V3FoundationConfig(
        enabled=False,
        developer_lab_enabled=False,
        waivers_file=None,
        waiver_warn_days=7,
        auto_merge_enabled=False,
        auto_merge_kill_switch=False,
        mandatory_policy_enabled=False,
        regulated_families=frozenset(),
    )
    if path is None:
        return disabled

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return disabled

    block = data.get("v3")
    if not isinstance(block, dict):
        return disabled

    enabled_raw = block.get("enabled", False)
    if not isinstance(enabled_raw, bool):
        raise ValueError("v3.enabled must be a boolean")
    developer_lab_enabled = _parse_developer_lab_enabled(block)
    auto_merge_enabled, auto_merge_kill_switch = _parse_auto_merge(block)
    mandatory_policy_enabled, regulated_families = _parse_mandatory_policy(block)
    if not enabled_raw:
        if developer_lab_enabled:
            raise ValueError(
                "v3.developer_lab.enabled is true but v3.enabled is false. "
                "Set v3.enabled: true, or set v3.developer_lab.enabled: false."
            )
        if auto_merge_enabled:
            raise ValueError(
                "v3.auto_merge.enabled is true but v3.enabled is false. "
                "Set v3.enabled: true, or set v3.auto_merge.enabled: false."
            )
        if mandatory_policy_enabled:
            raise ValueError(
                "v3.mandatory_policy.enabled is true but v3.enabled is false. "
                "Set v3.enabled: true, or set v3.mandatory_policy.enabled: false."
            )
        return disabled

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
        developer_lab_enabled=developer_lab_enabled,
        waivers_file=waivers_file,
        waiver_warn_days=warn_raw,
        auto_merge_enabled=auto_merge_enabled,
        auto_merge_kill_switch=auto_merge_kill_switch,
        mandatory_policy_enabled=mandatory_policy_enabled,
        regulated_families=regulated_families,
    )


def _parse_auto_merge(block: dict[str, object]) -> tuple[bool, bool]:
    """Opt in with v3.auto_merge.enabled. Kill switch demotes the fleet (ADR 008)."""
    raw = block.get("auto_merge")
    if raw is None:
        return False, False
    if isinstance(raw, bool):
        return raw, False
    if not isinstance(raw, dict):
        raise ValueError("v3.auto_merge must be a boolean or mapping")
    enabled_raw = raw.get("enabled", False)
    if not isinstance(enabled_raw, bool):
        raise ValueError("v3.auto_merge.enabled must be a boolean")
    kill_raw = raw.get("kill_switch", False)
    if not isinstance(kill_raw, bool):
        raise ValueError("v3.auto_merge.kill_switch must be a boolean")
    return enabled_raw, kill_raw


def _parse_mandatory_policy(block: dict[str, object]) -> tuple[bool, frozenset[str]]:
    """Opt in with v3.mandatory_policy.enabled. Families default when the list is omitted."""
    from repave_engine.mandatory_policy import (
        DEFAULT_REGULATED_FAMILIES,
        KNOWN_ARTIFACT_FAMILIES,
    )

    raw = block.get("mandatory_policy")
    if raw is None:
        return False, DEFAULT_REGULATED_FAMILIES
    if isinstance(raw, bool):
        return raw, DEFAULT_REGULATED_FAMILIES
    if not isinstance(raw, dict):
        raise ValueError("v3.mandatory_policy must be a boolean or mapping")
    enabled_raw = raw.get("enabled", False)
    if not isinstance(enabled_raw, bool):
        raise ValueError("v3.mandatory_policy.enabled must be a boolean")
    families_raw = raw.get("regulated_families")
    if families_raw is None:
        return enabled_raw, DEFAULT_REGULATED_FAMILIES
    if not isinstance(families_raw, list) or not all(
        isinstance(item, str) for item in families_raw
    ):
        allowed = ", ".join(sorted(KNOWN_ARTIFACT_FAMILIES))
        raise ValueError(
            "v3.mandatory_policy.regulated_families must be a list of family names; "
            f"allowed: {allowed}"
        )
    families = frozenset(item.strip() for item in families_raw if item.strip())
    unknown = families - KNOWN_ARTIFACT_FAMILIES
    if unknown:
        allowed = ", ".join(sorted(KNOWN_ARTIFACT_FAMILIES))
        raise ValueError(f"unknown regulated family {sorted(unknown)[0]!r}; allowed: {allowed}")
    return enabled_raw, families


def _parse_developer_lab_enabled(block: dict[str, object]) -> bool:
    """Opt in with v3.developer_lab.enabled: true. Off when the key is absent (ADR 008)."""
    raw = block.get("developer_lab")
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    if not isinstance(raw, dict):
        raise ValueError("v3.developer_lab must be a boolean or mapping")
    enabled_raw = raw.get("enabled", False)
    if not isinstance(enabled_raw, bool):
        raise ValueError("v3.developer_lab.enabled must be a boolean")
    return enabled_raw


def _find_config(repo_root: Path) -> Path | None:
    for name in _CONFIG_NAMES:
        candidate = repo_root / name
        if candidate.is_file():
            return candidate
    return None
