from __future__ import annotations

from pathlib import Path

from repave_engine.blueprint import list_blueprints
from repave_engine.governance import missing_governance_gates


def test_all_shipped_blueprints_meet_governance_baseline(repo_root: Path) -> None:
    blueprints = list_blueprints(repo_root / "blueprints")
    assert blueprints, "expected at least one blueprint"
    failures: list[str] = []
    for blueprint in blueprints:
        missing = missing_governance_gates(blueprint)
        if missing:
            failures.append(f"{blueprint.name}: missing gates {missing}")
    assert not failures, "\n".join(failures)
