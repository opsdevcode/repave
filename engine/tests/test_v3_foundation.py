"""Tests for v3 foundation slice: deprecations, risk classes, waivers."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from repave_engine.api_deprecation import HTML_PORTAL_DEPRECATION_HEADERS, V1_DEPRECATION_HEADERS
from repave_engine.deprecations import V3_DEPRECATIONS, deprecation_by_id, sunset_http_date
from repave_engine.risk_class import RiskClass, classify_change
from repave_engine.v3_foundation import load_v3_foundation_config
from repave_engine.waivers import (
    FrozenClock,
    WaiverRecord,
    WaiverStatus,
    evaluate_waiver,
    load_waivers,
    waiver_blocks_gate,
)


def test_v3_deprecation_registry_lists_breaking_changes() -> None:
    ids = {entry.deprecation_id for entry in V3_DEPRECATIONS}
    assert ids == {
        "html_portal_removal",
        "api_v1_removal",
        "crd_v1alpha1_removal",
        "mandatory_policy_tier",
        "blueprint_schema_v2",
    }


def test_api_v1_headers_use_deprecation_registry() -> None:
    entry = deprecation_by_id("api_v1_removal")
    assert entry is not None
    assert V1_DEPRECATION_HEADERS["Sunset"] == sunset_http_date(entry)
    assert V1_DEPRECATION_HEADERS["Deprecation"] == "true"


def test_html_portal_headers_use_deprecation_registry() -> None:
    entry = deprecation_by_id("html_portal_removal")
    assert entry is not None
    assert entry.sunset == date(2027, 2, 14)
    assert HTML_PORTAL_DEPRECATION_HEADERS["Sunset"] == sunset_http_date(entry)
    assert HTML_PORTAL_DEPRECATION_HEADERS["Deprecation"] == "true"
    assert HTML_PORTAL_DEPRECATION_HEADERS["Link"] == '</docs/backstage>; rel="successor-version"'


def test_classify_change_defaults_to_standard() -> None:
    result = classify_change(change_type="custom", blueprint="terraform-module-generic")
    assert result.risk_class is RiskClass.STANDARD


def test_classify_change_mechanical_pin_bump() -> None:
    result = classify_change(change_type="pin_bump", blueprint="terraform-module-generic")
    assert result.risk_class is RiskClass.MECHANICAL


def test_classify_change_respects_declared_class() -> None:
    result = classify_change(
        change_type="pin_bump",
        blueprint="terraform-module-generic",
        declared_class="sensitive",
    )
    assert result.risk_class is RiskClass.SENSITIVE


def test_waiver_expired_fails_gate(tmp_path: Path) -> None:
    path = tmp_path / "waivers.jsonl"
    path.write_text(
        '{"waiver_id":"w1","gate_id":"opa","expires_at":"2026-01-01T00:00:00Z"}\n',
        encoding="utf-8",
    )
    records = load_waivers(path)
    clock = FrozenClock(datetime(2026, 6, 1, tzinfo=timezone.utc))
    evaluation = evaluate_waiver(gate_id="opa", waivers=records, clock=clock)
    assert evaluation.status is WaiverStatus.EXPIRED
    assert waiver_blocks_gate(evaluation)


def test_waiver_active_within_window(tmp_path: Path) -> None:
    path = tmp_path / "waivers.jsonl"
    path.write_text(
        '{"waiver_id":"w2","gate_id":"opa","expires_at":"2026-12-01T00:00:00Z"}\n',
        encoding="utf-8",
    )
    records = load_waivers(path)
    clock = FrozenClock(datetime(2026, 6, 1, tzinfo=timezone.utc))
    evaluation = evaluate_waiver(
        gate_id="opa",
        waivers=records,
        clock=clock,
        warn_days=7,
    )
    assert evaluation.status is WaiverStatus.ACTIVE
    assert not waiver_blocks_gate(evaluation)


def test_waiver_expiring_within_warn_window(tmp_path: Path) -> None:
    record = WaiverRecord(
        waiver_id="w3",
        gate_id="checkov",
        expires_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
    )
    clock = FrozenClock(datetime(2026, 6, 1, tzinfo=timezone.utc))
    evaluation = evaluate_waiver(
        gate_id="checkov",
        waivers=(record,),
        clock=clock,
        warn_days=7,
    )
    assert evaluation.status is WaiverStatus.EXPIRING
    assert not waiver_blocks_gate(evaluation)


def test_v3_foundation_disabled_by_default(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\noutput:\n  github_org: acme\n  modules_root: ../mods\n",
        encoding="utf-8",
    )
    config = load_v3_foundation_config(tmp_path)
    assert config.enabled is False
    assert config.developer_lab_enabled is False


def test_v3_foundation_loads_waivers_path(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\n"
        "v3:\n"
        "  enabled: true\n"
        "  waivers_file: data/custom-waivers.jsonl\n"
        "output:\n"
        "  github_org: acme\n"
        "  modules_root: ../mods\n",
        encoding="utf-8",
    )
    config = load_v3_foundation_config(tmp_path)
    assert config.enabled is True
    assert config.developer_lab_enabled is False
    assert config.auto_merge_enabled is False
    assert config.auto_merge_kill_switch is False
    assert config.mandatory_policy_enabled is False
    assert config.waivers_file == tmp_path / "data" / "custom-waivers.jsonl"


def test_v3_auto_merge_opt_in_and_kill_switch(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\n"
        "v3:\n"
        "  enabled: true\n"
        "  auto_merge:\n"
        "    enabled: true\n"
        "    kill_switch: true\n"
        "output:\n"
        "  github_org: acme\n"
        "  modules_root: ../mods\n",
        encoding="utf-8",
    )
    config = load_v3_foundation_config(tmp_path)
    assert config.auto_merge_enabled is True
    assert config.auto_merge_kill_switch is True


def test_v3_auto_merge_requires_v3_enabled(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\n"
        "v3:\n"
        "  enabled: false\n"
        "  auto_merge:\n"
        "    enabled: true\n"
        "output:\n"
        "  github_org: acme\n"
        "  modules_root: ../mods\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"v3\.auto_merge\.enabled"):
        load_v3_foundation_config(tmp_path)


@pytest.mark.v3
def test_v3_marker_reserved_for_post_flip_contracts() -> None:
    """Placeholder until breaking removals land; keeps make test-v3 wired."""
    assert date(2027, 8, 1) == deprecation_by_id("api_v1_removal").sunset  # type: ignore[union-attr]
