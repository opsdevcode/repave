from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from repave_engine.commercial_license import load_commercial_license


def _write(
    path: Path,
    *,
    product: str = "repave-control-plane",
    organization: str = "acme",
    sku: str = "pilot",
    expires: str = "2099-12-31",
) -> None:
    path.write_text(
        (
            f'{{"product":"{product}","organization":"{organization}",'
            f'"sku":"{sku}","expires":"{expires}"}}\n'
        ),
        encoding="utf-8",
    )


def test_load_skips_when_service_mode_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REPAVE_LICENSE_FILE", raising=False)
    assert load_commercial_license(service_enabled=False) is None


def test_load_requires_path_in_service_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REPAVE_LICENSE_FILE", raising=False)
    with pytest.raises(ValueError, match="REPAVE_LICENSE_FILE"):
        load_commercial_license(service_enabled=True)


def test_load_names_missing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    missing = tmp_path / "nope.json"
    monkeypatch.setenv("REPAVE_LICENSE_FILE", str(missing))
    with pytest.raises(ValueError, match="license file not found"):
        load_commercial_license(service_enabled=True)


def test_load_rejects_expired(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "license.json"
    _write(path, expires="2020-01-01")
    monkeypatch.setenv("REPAVE_LICENSE_FILE", str(path))
    with pytest.raises(ValueError, match="expired"):
        load_commercial_license(service_enabled=True)


def test_load_accepts_valid_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "license.json"
    tomorrow = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    _write(path, sku="annual", expires=tomorrow)
    monkeypatch.setenv("REPAVE_LICENSE_FILE", str(path))
    grant = load_commercial_license(service_enabled=True)
    assert grant is not None
    assert grant.organization == "acme"
    assert grant.sku == "annual"
