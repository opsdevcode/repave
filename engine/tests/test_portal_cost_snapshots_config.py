from __future__ import annotations

from pathlib import Path

from repave_engine.settings import load_portal_config


def test_load_portal_config_cost_snapshots_without_reader(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        (
            "portal:\n"
            "  cost_snapshots:\n"
            "    enabled: true\n"
            "    file: data/fleet/cost-snapshots.jsonl\n"
        ),
        encoding="utf-8",
    )
    cfg = load_portal_config(tmp_path)
    assert cfg.cost_snapshots_enabled is True
    assert cfg.cost_snapshots_file == (tmp_path / "data/fleet/cost-snapshots.jsonl").resolve()
