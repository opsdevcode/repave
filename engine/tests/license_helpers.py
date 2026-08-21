from __future__ import annotations

from pathlib import Path

import pytest


def install_repave_license(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    sku: str = "annual",
    expires: str = "2099-01-01",
    organization: str = "example-org",
) -> Path:
    """Valid paid grant for create_app when REPAVE_SERVICE_MODE is on."""
    path = tmp_path / "repave-license.json"
    path.write_text(
        (
            '{"product":"repave-control-plane",'
            f'"organization":"{organization}","sku":"{sku}","expires":"{expires}"}}\n'
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("REPAVE_LICENSE_FILE", str(path))
    return path
