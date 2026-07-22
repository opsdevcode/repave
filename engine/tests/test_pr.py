from __future__ import annotations

from pathlib import Path

from repave_engine.pr import create_pull_request, plan_pull_request


def test_plan_pull_request_fields(tmp_path: Path) -> None:
    plan = plan_pull_request(
        module_name="networking-vnet",
        blueprint_name="terraform-module-generic",
        blueprint_version="0.1.0",
        standard_version="0.1.0",
        files_root=tmp_path / "output",
    )

    assert plan.branch == "repave/terraform-module-generic/networking-vnet"
    assert "networking-vnet" in plan.title
    assert "terraform-module-generic" in plan.body
    assert "0.1.0" in plan.body
    assert plan.files_root == tmp_path / "output"


def test_create_pull_request_dry_run(tmp_path: Path) -> None:
    plan = plan_pull_request(
        module_name="example",
        blueprint_name="terraform-module-generic",
        blueprint_version="0.1.0",
        standard_version="0.1.0",
        files_root=tmp_path,
    )

    message = create_pull_request(plan, github_token=None)

    assert "Dry-run" in message
    assert plan.branch in message
    assert plan.title in message


def test_create_pull_request_with_token_returns_stub(tmp_path: Path) -> None:
    plan = plan_pull_request(
        module_name="example",
        blueprint_name="terraform-module-generic",
        blueprint_version="0.1.0",
        standard_version="0.1.0",
        files_root=tmp_path,
    )

    message = create_pull_request(plan, github_token="ghp_test")

    assert "not yet wired" in message
    assert plan.branch in message
