from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

from repave_engine.policy_standards_watch import (
    SourceSnapshot,
    WatchSource,
    check_standards_watch,
    snapshot_source,
)


def test_snapshot_source_hashes_body() -> None:
    source = WatchSource(
        id="demo",
        url="https://example.com",
        kind="text",
        notes="",
    )
    with patch(
        "repave_engine.policy_standards_watch._fetch",
        return_value=(200, b"hello", None),
    ):
        snap = snapshot_source(source)
    assert snap.sha256 == hashlib.sha256(b"hello").hexdigest()
    assert snap.http_status == 200


def test_check_standards_watch_detects_change(tmp_path: Path) -> None:
    policy_dir = tmp_path / "policy"
    policy_dir.mkdir()
    (policy_dir / "standards-watch.json").write_text(
        """
        {
          "version": "1.0.0",
          "sources": [
            {
              "id": "demo",
              "url": "https://example.com/x",
              "kind": "text",
              "notes": "test"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    def fake_a(_source: WatchSource) -> SourceSnapshot:
        return SourceSnapshot(sha256="aaa", extracted=None, http_status=200)

    with patch("repave_engine.policy_standards_watch.snapshot_source", side_effect=fake_a):
        changed, _ = check_standards_watch(tmp_path, update=True)
        assert changed is False

    def fake_b(_source: WatchSource) -> SourceSnapshot:
        return SourceSnapshot(sha256="bbb", extracted=None, http_status=200)

    with patch("repave_engine.policy_standards_watch.snapshot_source", side_effect=fake_b):
        changed2, report = check_standards_watch(tmp_path, update=False)
        assert changed2 is True
        assert "demo" in report
