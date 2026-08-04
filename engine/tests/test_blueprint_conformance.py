from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.blueprint_conformance import (
    conformance_cases,
    load_conformance_specs,
    run_blueprint_conformance,
)


@pytest.fixture
def conformance_staging(tmp_path: Path) -> Path:
    path = tmp_path / "conformance-staging"
    path.mkdir()
    return path


def _conformance_case_ids(repo_root: Path) -> list[str]:
    return [
        f"{blueprint_name}/{variant_id}" if variant_id else blueprint_name
        for blueprint_name, variant_id in conformance_cases(repo_root)
    ]


@pytest.mark.slow
@pytest.mark.parametrize(
    ("blueprint_name", "variant_id"),
    conformance_cases(Path(__file__).resolve().parents[2]),
    ids=_conformance_case_ids(Path(__file__).resolve().parents[2]),
)
def test_blueprint_conformance_harness(
    repo_root: Path,
    output_config,
    conformance_staging: Path,
    blueprint_name: str,
    variant_id: str,
) -> None:
    blueprint_dir = repo_root / "blueprints" / blueprint_name
    spec_path = blueprint_dir / "conformance.yaml"
    assert spec_path.is_file(), (
        f"Add {spec_path.relative_to(repo_root)} with fixture inputs "
        "(see blueprints/terraform-module-generic/conformance.yaml)."
    )
    load_conformance_specs(blueprint_dir)

    label = blueprint_name if not variant_id else f"{blueprint_name}/{variant_id}"
    outcome = run_blueprint_conformance(
        blueprint_dir,
        repo_root=repo_root,
        output_config=output_config,
        staging_root=conformance_staging,
        variant_id=variant_id or None,
    )
    assert not outcome.gate_failures, f"{label} gate failures:\n" + "\n".join(outcome.gate_failures)
    assert not outcome.missing_files, (
        f"{label} missing required files: {', '.join(outcome.missing_files)}"
    )
    assert not outcome.placeholder_hits, f"{label} unresolved template markers:\n" + "\n".join(
        outcome.placeholder_hits[:20]
    )
    if outcome.manifest_diff:
        pytest.fail(
            f"{label} conformance manifest drift: {outcome.manifest_diff}. "
            "Run: make blueprint-conformance-update"
        )


def test_app_service_conformance_has_twenty_variants(repo_root: Path) -> None:
    specs = load_conformance_specs(repo_root / "blueprints" / "app-service-generic")
    assert len(specs) == 20
    ids = {spec.variant_id for spec in specs}
    assert "python-http-api" in ids
    assert "dotnet-grpc" in ids
    snapshotted = [spec.variant_id for spec in specs if spec.snapshot]
    assert snapshotted == ["python-http-api", "go-grpc", "nodejs-scheduled-job"]
