"""Batch import per-family and per-target blueprint resolution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from repave_engine.import_detect import BlueprintCandidate
from repave_engine.repo_import import (
    FAMILY_BLUEPRINT_MAP_SENTINEL,
    build_default_family_blueprint_map,
    resolve_batch_import_blueprint_options,
    resolve_batch_target_blueprint,
    target_blueprints_from_org_scan,
)


def test_build_default_family_blueprint_map_includes_terraform(repo_root: Path) -> None:
    mapping = build_default_family_blueprint_map(repo_root)
    assert "terraform" in mapping
    assert mapping["terraform"] == "terraform-module-generic"


def test_resolve_batch_target_blueprint_prefers_target_override() -> None:
    candidates = (
        BlueprintCandidate(
            blueprint_name="ansible-role-generic",
            artifact_type="ansible-role",
            family="ansible",
            confidence=0.9,
            evidence=("tasks/main.yml",),
        ),
    )
    blueprint = resolve_batch_target_blueprint(
        "https://github.com/acme/vpc",
        candidates,
        blueprint_name=None,
        family_blueprints={"terraform": "terraform-module-generic"},
        target_blueprints={
            "https://github.com/acme/vpc": "terraform-environment-stack",
        },
    )
    assert blueprint == "terraform-environment-stack"


def test_resolve_batch_target_blueprint_uses_family_map() -> None:
    candidates = (
        BlueprintCandidate(
            blueprint_name="terraform-module-generic",
            artifact_type="terraform-module",
            family="terraform",
            confidence=0.9,
            evidence=("main.tf",),
        ),
    )
    blueprint = resolve_batch_target_blueprint(
        "https://github.com/acme/vpc",
        candidates,
        blueprint_name=None,
        family_blueprints={"terraform": "terraform-module-generic"},
        target_blueprints=None,
    )
    assert blueprint == "terraform-module-generic"


def test_resolve_batch_import_blueprint_options_family_sentinel(repo_root: Path) -> None:
    blueprint_name, family_blueprints = resolve_batch_import_blueprint_options(
        repo_root,
        blueprint=FAMILY_BLUEPRINT_MAP_SENTINEL,
        family_blueprints_raw={"ansible": "ansible-role-generic"},
    )
    assert blueprint_name == FAMILY_BLUEPRINT_MAP_SENTINEL
    assert family_blueprints is not None
    assert family_blueprints["terraform"] == "terraform-module-generic"
    assert family_blueprints["ansible"] == "ansible-role-generic"


def test_target_blueprints_from_org_scan() -> None:
    summary = {
        "repos": [
            {
                "url": "https://github.com/acme/vpc",
                "top_candidate": {
                    "blueprint_name": "terraform-module-generic",
                    "family": "terraform",
                },
            },
            {"url": "https://github.com/acme/other", "top_candidate": None},
        ],
    }
    mapping = target_blueprints_from_org_scan(summary)
    assert mapping == {"https://github.com/acme/vpc": "terraform-module-generic"}


def test_plan_import_batch_applies_family_map(repo_root: Path, tmp_path: Path) -> None:
    from repave_engine.repo_import import plan_import_batch

    good = tmp_path / "tf-a"
    good.mkdir()
    (good / "main.tf").write_text('resource "aws_vpc" "a" {}\n', encoding="utf-8")
    (good / "variables.tf").write_text("", encoding="utf-8")
    (good / "outputs.tf").write_text("", encoding="utf-8")

    family_map = build_default_family_blueprint_map(repo_root)
    with patch(
        "repave_engine.repo_import._detect_candidates_for_target",
        return_value=(
            BlueprintCandidate(
                blueprint_name="terraform-module-generic",
                artifact_type="terraform-module",
                family="terraform",
                confidence=0.9,
                evidence=("main.tf",),
            ),
        ),
    ):
        batch = plan_import_batch(
            [str(good)],
            repo_root,
            family_blueprints=family_map,
            with_gates=False,
        )
    assert len(batch.items) == 1
    assert batch.items[0].blueprint_name == "terraform-module-generic"


def test_build_parser_map_by_family() -> None:
    from repave_engine.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(
        ["import", "placeholder", "--batch-file", "repos.txt", "--map-by-family"]
    )
    assert args.map_by_family is True
