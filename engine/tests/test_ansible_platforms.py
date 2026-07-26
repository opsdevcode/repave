from __future__ import annotations

import pytest

from repave_engine.ansible_platforms import (
    LINUX_DEFAULT_PLATFORMS,
    infer_platform_form_values,
    resolve_target_platforms,
)


def test_resolve_linux_defaults_only() -> None:
    resolved = resolve_target_platforms(
        support_linux=True,
        support_windows=False,
        windows_server_generation="2022",
        target_platforms_advanced="",
    )
    assert resolved == "Debian:bookworm,EL:9,Ubuntu:jammy"


def test_resolve_linux_and_windows_2022() -> None:
    resolved = resolve_target_platforms(
        support_linux=True,
        support_windows=True,
        windows_server_generation="2022",
        target_platforms_advanced="",
    )
    parts = set(resolved.split(","))
    assert parts == set(LINUX_DEFAULT_PLATFORMS) | {"Windows:2022"}


def test_advanced_overrides_presets() -> None:
    resolved = resolve_target_platforms(
        support_linux=False,
        support_windows=False,
        windows_server_generation="2022",
        target_platforms_advanced="EL:8,Ubuntu:focal",
    )
    assert resolved == "EL:8,Ubuntu:focal"


def test_resolve_requires_some_platform() -> None:
    with pytest.raises(ValueError, match="Linux and/or Windows"):
        resolve_target_platforms(
            support_linux=False,
            support_windows=False,
            windows_server_generation="2022",
            target_platforms_advanced="",
        )


def test_infer_platform_form_values_round_trip_linux() -> None:
    values = infer_platform_form_values(list(LINUX_DEFAULT_PLATFORMS))
    assert values["support_linux"] == "true"
    assert values["support_windows"] == "false"
    assert values["target_platforms_advanced"] == ""


def test_infer_platform_form_values_custom_goes_advanced() -> None:
    values = infer_platform_form_values(["EL:8", "Ubuntu:focal"])
    assert values["target_platforms_advanced"] == "EL:8,Ubuntu:focal"
