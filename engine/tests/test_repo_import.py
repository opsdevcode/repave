from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from repave_engine.blueprint import blueprints_dir, list_blueprints
from repave_engine.import_detect import detect_blueprint_candidates, inventory_relative_paths
from repave_engine.import_rules import (
    ImportRule,
    ImportRuleSet,
    classify_path,
    default_import_rules,
    matches_glob,
    parse_import_rules,
)
from repave_engine.repo_import import (
    BLAME_IGNORE_FILENAME,
    AlreadyGovernedError,
    RepoImportError,
    apply_import,
    artifact_name_from_repo,
    build_import_pull_request_body,
    infer_terraform_scope,
    layout_hash,
    plan_import,
    plan_import_batch,
    suggested_import_branch,
)


def _write(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _git_repo(root: Path, files: dict[str, str]) -> Path:
    if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
        pytest.skip("git not installed")
    root.mkdir(parents=True, exist_ok=True)
    _write(root, files)
    _git(root, "init", "--initial-branch", "main")
    _git(root, "config", "user.email", "test@repave.dev")
    _git(root, "config", "user.name", "repave test")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "initial")
    return root


_LEGACY_TF = {
    "terraform/main.tf": 'resource "aws_s3_bucket" "assets" {}\n',
    "terraform/variables.tf": 'variable "name" { type = string }\n',
    "terraform/outputs.tf": 'output "arn" { value = 1 }\n',
    "README.rst": "Legacy assets bucket\n",
    "LICENSE": "MIT\n",
    "scripts/deploy.sh": "echo deploy\n",
}


# --- glob and classification -------------------------------------------------


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        ("main.tf", "**/*.tf", True),
        ("terraform/main.tf", "**/*.tf", True),
        ("main.tf", "*.tf", True),
        ("terraform/main.tf", "*.tf", False),
        ("examples/simple/main.tf", "examples/**", True),
        ("examples", "examples/**", True),
        ("meta/main.yml", "**/meta/main.yml", True),
        ("roles/web/meta/main.yml", "**/meta/main.yml", True),
        ("README.md", "README.*", True),
        ("READMEs/x.md", "README.*", False),
    ],
)
def test_matches_glob(path: str, pattern: str, expected: bool) -> None:
    assert matches_glob(path, pattern) is expected


def test_classify_uses_first_matching_rule() -> None:
    rules = default_import_rules("terraform")

    assert classify_path("terraform/main.tf", rules).destination == "main.tf"
    assert classify_path("test/basic.tftest.hcl", rules).destination == "tests/basic.tftest.hcl"
    assert classify_path("README.rst", rules).destination == "README.md"


def test_classify_preserves_declared_subtrees() -> None:
    rules = default_import_rules("terraform")
    outcome = classify_path("examples/simple/main.tf", rules)

    assert outcome.destination == "examples/simple/main.tf"
    assert "subtree preserved" in outcome.reason


def test_classify_keeps_license_in_place() -> None:
    outcome = classify_path("LICENSE", default_import_rules("terraform"))

    assert outcome.kept is True
    assert outcome.destination == "LICENSE"


def test_classify_reports_unmapped_paths() -> None:
    outcome = classify_path("scripts/deploy.sh", default_import_rules("terraform"))

    assert outcome.destination is None
    assert outcome.reason == "no rule matched"


def test_exclude_opts_a_path_out_of_a_rule() -> None:
    rules = ImportRuleSet(
        rules=(ImportRule(match=("**/*.tf",), exclude=("vendor/**",), destination="."),)
    )

    assert classify_path("a/main.tf", rules).destination == "main.tf"
    assert classify_path("vendor/main.tf", rules).destination is None


def test_parse_import_rules_from_blueprint_spec() -> None:
    rules = parse_import_rules(
        {
            "rules": [
                {"match": ["src/**"], "preserveTree": True},
                {"match": ["*.md"], "destination": "docs/"},
            ],
            "keep": ["LICENSE"],
            "unmapped": "quarantine",
        },
        family="app",
    )

    assert rules.unmapped == "quarantine"
    assert classify_path("src/app.py", rules).destination == "src/app.py"
    assert classify_path("guide.md", rules).destination == "docs/guide.md"


def test_parse_import_rules_falls_back_to_family_defaults() -> None:
    assert parse_import_rules(None, family="helm") == default_import_rules("helm")


def test_every_shipped_blueprint_has_usable_import_rules(repo_root: Path) -> None:
    for blueprint in list_blueprints(blueprints_dir(repo_root)):
        assert blueprint.import_rules.rules, blueprint.name


# --- detection ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        (
            {"main.tf": "", "variables.tf": "", "outputs.tf": ""},
            "terraform-module-generic",
        ),
        (
            {"main.tf": "", "backend.tf": "", "envs/prod/terraform.tfvars": ""},
            "terraform-environment-stack",
        ),
        (
            {"meta/main.yml": "", "tasks/main.yml": "", "defaults/main.yml": ""},
            "ansible-role-generic",
        ),
        (
            {"galaxy.yml": "", "plugins/modules/x.py": "", "meta/runtime.yml": ""},
            "ansible-collection-generic",
        ),
        (
            {"Chart.yaml": "", "values.yaml": "", "templates/deploy.yaml": ""},
            "helm-chart-generic",
        ),
        ({"policy/deny.rego": "", "policy/deny_test.rego": ""}, "opa-policy-generic"),
        ({"Dockerfile": "", "pyproject.toml": "", "src/app.py": ""}, "app-service-generic"),
    ],
)
def test_detect_ranks_the_matching_family_first(
    repo_root: Path, tmp_path: Path, files: dict[str, str], expected: str
) -> None:
    repo = _write(tmp_path / "repo", files)
    candidates = detect_blueprint_candidates(repo, list_blueprints(blueprints_dir(repo_root)))

    assert candidates
    assert candidates[0].blueprint_name == expected
    assert candidates[0].evidence


def test_detect_tolerates_code_nested_one_level_down(repo_root: Path, tmp_path: Path) -> None:
    repo = _write(tmp_path / "repo", _LEGACY_TF)
    candidates = detect_blueprint_candidates(repo, list_blueprints(blueprints_dir(repo_root)))

    assert candidates[0].blueprint_name == "terraform-module-generic"


def test_detect_returns_nothing_for_an_empty_repo(repo_root: Path, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    assert detect_blueprint_candidates(empty, list_blueprints(blueprints_dir(repo_root))) == ()


def test_inventory_skips_vcs_and_vendor_directories(tmp_path: Path) -> None:
    repo = _write(
        tmp_path / "repo",
        {"main.tf": "", ".git/config": "", "node_modules/x/index.js": "", ".terraform/lock": ""},
    )

    assert inventory_relative_paths(repo) == ("main.tf",)


# --- value inference ---------------------------------------------------------


@pytest.mark.parametrize(
    ("repo_name", "expected"),
    [
        ("tf-aws-vpc", "aws_vpc"),
        ("terraform-s3", "s3"),
        ("ansible-role-nginx", "nginx"),
        ("plain.name", "plain_name"),
    ],
)
def test_artifact_name_from_repo(repo_name: str, expected: str) -> None:
    assert artifact_name_from_repo(repo_name) == expected


def test_infer_terraform_scope_reads_the_repos_own_resources(
    repo_root: Path, tmp_path: Path, terraform_blueprint: object
) -> None:
    repo = _write(
        tmp_path / "repo",
        {"main.tf": 'resource "aws_s3_bucket" "a" {}\nresource "aws_vpc" "v" {}\n'},
    )
    provider, services = infer_terraform_scope(
        terraform_blueprint,  # type: ignore[arg-type]
        repo,
        inventory_relative_paths(repo),
    )

    assert provider == "aws"
    assert "s3" in services


# --- planning ----------------------------------------------------------------


def test_plan_import_detects_moves_and_scaffold(repo_root: Path, tmp_path: Path) -> None:
    repo = _write(tmp_path / "tf-legacy-assets", _LEGACY_TF)
    plan = plan_import(str(repo), repo_root, with_gates=False)

    assert plan.blueprint_name == "terraform-module-generic"
    assert plan.detected is True
    assert plan.ok is True
    assert plan.is_noop is False

    destinations = {move.source: move.destination for move in plan.renames}
    assert destinations["terraform/main.tf"] == "main.tf"
    assert destinations["README.rst"] == "README.md"
    assert "repave.yaml" in plan.scaffold_added
    assert plan.unmapped == ("scripts/deploy.sh",)
    assert plan.source_layout_hash


def test_plan_import_never_grafts_generated_resource_code(repo_root: Path, tmp_path: Path) -> None:
    repo = _write(tmp_path / "tf-legacy", _LEGACY_TF)
    plan = plan_import(str(repo), repo_root, with_gates=False)

    assert not [rel for rel in plan.scaffold_added if rel.endswith(".tf")]


def test_plan_import_adds_scaffold_for_a_repo_with_no_terraform_of_its_own(
    repo_root: Path, tmp_path: Path
) -> None:
    repo = _write(tmp_path / "tf-docs-only", {"README.md": "docs\n"})
    plan = plan_import(
        str(repo), repo_root, blueprint_name="terraform-module-generic", with_gates=False
    )

    assert [rel for rel in plan.scaffold_added if rel.endswith(".tf")]


def test_plan_import_flags_two_files_competing_for_one_destination(
    repo_root: Path, tmp_path: Path
) -> None:
    repo = _write(
        tmp_path / "tf-legacy",
        {
            "a/main.tf": 'resource "aws_s3_bucket" "a" {}\n',
            "b/main.tf": 'resource "aws_vpc" "v" {}\n',
        },
    )
    plan = plan_import(
        str(repo), repo_root, blueprint_name="terraform-module-generic", with_gates=False
    )

    assert plan.ok is False
    assert any("both map to `main.tf`" in line for line in plan.conflicts)


def test_plan_import_reports_a_conforming_repo_as_a_noop(repo_root: Path, tmp_path: Path) -> None:
    repo = _write(tmp_path / "tf-legacy", _LEGACY_TF)
    plan = plan_import(str(repo), repo_root, with_gates=False)
    # repave.yaml is deliberately excluded: a repo that already has it is governed, and the
    # governed guard would route it to upgrade before the no-op check ran.
    conforming = _write(
        tmp_path / "tf-conforming",
        {
            **{move.destination: "" for move in plan.moves},
            **{rel: "" for rel in plan.scaffold_added if rel != "repave.yaml"},
        },
    )

    second = plan_import(
        str(conforming), repo_root, blueprint_name=plan.blueprint_name, with_gates=False
    )

    assert second.renames == ()
    assert second.scaffold_added == ("repave.yaml",)


def test_plan_import_reports_a_fully_conforming_repo_as_a_noop(
    repo_root: Path, tmp_path: Path
) -> None:
    repo = _write(tmp_path / "tf-legacy", _LEGACY_TF)
    plan = plan_import(str(repo), repo_root, with_gates=False)
    conforming = _write(
        tmp_path / "tf-conforming",
        {
            **{move.destination: "" for move in plan.moves},
            **{rel: "" for rel in plan.scaffold_added if rel != "repave.yaml"},
        },
    )
    second = plan_import(
        str(conforming), repo_root, blueprint_name=plan.blueprint_name, with_gates=False
    )
    (conforming / "repave.yaml").write_text("", encoding="utf-8")

    # Bypass the governed guard to exercise the no-op summary directly.
    noop = replace(second, scaffold_added=())

    assert noop.is_noop is True
    assert "Already conforms" in noop.summary


def test_plan_import_rejects_a_governed_repo(repo_root: Path, tmp_path: Path) -> None:
    repo = _write(
        tmp_path / "governed",
        {"main.tf": "", "repave.yaml": "apiVersion: repave.dev/v1beta1\n"},
    )

    with pytest.raises(AlreadyGovernedError, match="/update"):
        plan_import(str(repo), repo_root, with_gates=False)


def test_plan_import_rejects_an_empty_repo(repo_root: Path, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    with pytest.raises(RepoImportError, match="no files to import"):
        plan_import(str(empty), repo_root, with_gates=False)


def test_plan_import_rejects_an_unknown_blueprint(repo_root: Path, tmp_path: Path) -> None:
    repo = _write(tmp_path / "repo", {"main.tf": ""})

    with pytest.raises(RepoImportError, match="unknown blueprint"):
        plan_import(str(repo), repo_root, blueprint_name="nope", with_gates=False)


def test_plan_import_scores_before_and_after(repo_root: Path, tmp_path: Path) -> None:
    repo = _write(tmp_path / "tf-legacy", _LEGACY_TF)
    plan = plan_import(str(repo), repo_root, with_gates=False)

    assert plan.scorecard.total >= 4
    assert plan.scorecard.passing_after > plan.scorecard.passing_before
    assert plan.scorecard.improved is True


def test_plan_import_batch_collects_failures_without_aborting(
    repo_root: Path, tmp_path: Path
) -> None:
    good = _write(tmp_path / "tf-legacy", _LEGACY_TF)
    batch = plan_import_batch([str(good), str(tmp_path / "missing")], repo_root, with_gates=False)

    assert len(batch.items) == 1
    assert len(batch.failures) == 1
    assert batch.ok is False


def test_layout_hash_changes_with_content(tmp_path: Path) -> None:
    repo = _write(tmp_path / "repo", {"a.tf": "one\n"})
    first = layout_hash(repo, ("a.tf",))
    (repo / "a.tf").write_text("two\n", encoding="utf-8")

    assert layout_hash(repo, ("a.tf",)) != first


# --- apply -------------------------------------------------------------------


def test_apply_import_moves_files_without_changing_content(repo_root: Path, tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "tf-legacy", _LEGACY_TF)
    plan = plan_import(str(repo), repo_root, with_gates=False)

    result = apply_import(repo, plan, repo_root, git_branch=suggested_import_branch(plan))

    assert result.verified_moves == len(plan.renames)
    assert (repo / "main.tf").read_text() == _LEGACY_TF["terraform/main.tf"]
    assert not (repo / "terraform").exists()


def test_apply_import_splits_moves_and_scaffold_into_two_commits(
    repo_root: Path, tmp_path: Path
) -> None:
    repo = _git_repo(tmp_path / "tf-legacy", _LEGACY_TF)
    plan = plan_import(str(repo), repo_root, with_gates=False)

    result = apply_import(repo, plan, repo_root, git_branch="repave/import/test")

    assert result.move_commit_sha
    assert result.scaffold_commit_sha
    assert result.move_commit_sha != result.scaffold_commit_sha
    numstat = _git(repo, "show", "--numstat", "--format=", result.move_commit_sha)
    for line in numstat.splitlines():
        added, removed, _path = line.split("\t", 2)
        assert (added, removed) == ("0", "0"), line


def test_apply_import_preserves_history_through_git_mv(repo_root: Path, tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "tf-legacy", _LEGACY_TF)
    plan = plan_import(str(repo), repo_root, with_gates=False)
    apply_import(repo, plan, repo_root, git_branch="repave/import/test")

    log = _git(repo, "log", "--follow", "--format=%s", "--", "main.tf")

    assert "initial" in log


def test_apply_import_records_the_move_commit_for_git_blame(
    repo_root: Path, tmp_path: Path
) -> None:
    repo = _git_repo(tmp_path / "tf-legacy", _LEGACY_TF)
    plan = plan_import(str(repo), repo_root, with_gates=False)

    result = apply_import(repo, plan, repo_root, git_branch="repave/import/test")

    assert result.move_commit_sha in (repo / BLAME_IGNORE_FILENAME).read_text()


def test_apply_import_records_import_provenance(repo_root: Path, tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "tf-legacy", _LEGACY_TF)
    plan = plan_import(str(repo), repo_root, with_gates=False)
    apply_import(repo, plan, repo_root, git_branch="repave/import/test")

    stanza = yaml.safe_load((repo / "repave.yaml").read_text())["spec"]["import"]

    assert stanza["pre_import_layout_hash"] == plan.source_layout_hash
    assert stanza["moved_files"] == len(plan.renames)
    assert stanza["unmapped_files"] == ["scripts/deploy.sh"]


def test_apply_import_refuses_a_plan_with_conflicts(repo_root: Path, tmp_path: Path) -> None:
    repo = _git_repo(
        tmp_path / "tf-legacy",
        {"a/main.tf": 'resource "aws_vpc" "a" {}\n', "b/main.tf": 'resource "aws_vpc" "b" {}\n'},
    )
    plan = plan_import(
        str(repo), repo_root, blueprint_name="terraform-module-generic", with_gates=False
    )

    with pytest.raises(RepoImportError, match="conflicts"):
        apply_import(repo, plan, repo_root, git_branch="repave/import/test")


def test_pull_request_body_states_the_hash_assertion(repo_root: Path, tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "tf-legacy", _LEGACY_TF)
    plan = plan_import(str(repo), repo_root, with_gates=False)
    result = apply_import(repo, plan, repo_root, git_branch="repave/import/test")

    body = build_import_pull_request_body(result)

    assert "byte-identical; SHA-256 verified" in body
    assert "terraform/main.tf" in body
    assert BLAME_IGNORE_FILENAME in body


def test_suggested_import_branch_names_the_blueprint(repo_root: Path, tmp_path: Path) -> None:
    repo = _write(tmp_path / "tf-legacy", _LEGACY_TF)
    plan = plan_import(str(repo), repo_root, with_gates=False)

    assert suggested_import_branch(plan) == (
        f"repave/import/{plan.blueprint_name}-{plan.blueprint_version}"
    )
