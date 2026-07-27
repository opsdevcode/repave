from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.blueprint_conformance import (
    blueprint_dirs,
    load_conformance_spec,
    run_blueprint_conformance,
)


@pytest.fixture
def conformance_staging(tmp_path: Path) -> Path:
    path = tmp_path / "conformance-staging"
    path.mkdir()
    return path


def _blueprint_ids(repo_root: Path) -> list[str]:
    return [path.name for path in blueprint_dirs(repo_root)]


@pytest.mark.slow
@pytest.mark.parametrize("blueprint_name", _blueprint_ids(Path(__file__).resolve().parents[2]))
def test_blueprint_conformance_harness(
    repo_root: Path,
    output_config,
    conformance_staging: Path,
    blueprint_name: str,
) -> None:
    blueprint_dir = repo_root / "blueprints" / blueprint_name
    spec_path = blueprint_dir / "conformance.yaml"
    assert spec_path.is_file(), (
        f"Add {spec_path.relative_to(repo_root)} with fixture inputs "
        "(see blueprints/terraform-module-generic/conformance.yaml)."
    )
    load_conformance_spec(blueprint_dir)

    outcome = run_blueprint_conformance(
        blueprint_dir,
        repo_root=repo_root,
        output_config=output_config,
        staging_root=conformance_staging,
    )
    assert not outcome.gate_failures, f"{blueprint_name} gate failures:\n" + "\n".join(
        outcome.gate_failures
    )
    assert not outcome.missing_files, (
        f"{blueprint_name} missing required files: {', '.join(outcome.missing_files)}"
    )
    assert not outcome.placeholder_hits, (
        f"{blueprint_name} unresolved template markers:\n"
        + "\n".join(outcome.placeholder_hits[:20])
    )
    if outcome.manifest_diff:
        pytest.fail(
            f"{blueprint_name} conformance manifest drift: {outcome.manifest_diff}. "
            "Run: make blueprint-conformance-update"
        )
