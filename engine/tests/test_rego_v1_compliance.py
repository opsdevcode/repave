"""Every shipped Rego file must load on OPA 1.x.

OPA 1.0 made `if` and `contains` mandatory, so classic `deny[msg] { ... }` rules fail to
load on any current toolchain — including conftest 0.68, which embeds OPA 1.15. Because
`import rego.v1` is accepted from OPA 0.59 onward, one syntax works on both the older pin
and OPA 1.x. This guards the policy corpus and the blueprint templates that generate it,
so a repo generated today is not broken on the user's toolchain.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Classic partial-set or function rules without the required v1 keywords.
_CLASSIC_RULE = re.compile(r"^\s*(?:\w+)\s*(?:\[[^\]]+\]|\([^)]*\))?\s*\{\s*$", re.MULTILINE)


def _shipped_rego_files(repo_root: Path) -> list[Path]:
    roots = (repo_root / "policy", repo_root / "blueprints", repo_root / "standards")
    files: list[Path] = []
    for root in roots:
        if root.is_dir():
            files.extend(sorted(root.rglob("*.rego")))
            files.extend(sorted(root.rglob("*.rego.jinja")))
    return files


def test_repo_ships_rego_files(repo_root: Path) -> None:
    assert _shipped_rego_files(repo_root), "expected to find Rego policies to check"


def test_every_rego_file_imports_rego_v1(repo_root: Path) -> None:
    missing = [
        str(path.relative_to(repo_root))
        for path in _shipped_rego_files(repo_root)
        if "import rego.v1" not in path.read_text(encoding="utf-8")
    ]

    assert not missing, "Rego files must declare `import rego.v1` to load on OPA 1.x: " + ", ".join(
        missing
    )


def test_no_classic_rule_bodies(repo_root: Path) -> None:
    offenders: list[str] = []
    for path in _shipped_rego_files(repo_root):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.endswith("{") or stripped.startswith("#"):
                continue
            if " if {" in line or " contains " in line or stripped.startswith("{"):
                continue
            if _CLASSIC_RULE.match(line):
                offenders.append(f"{path.relative_to(repo_root)}: {stripped}")

    assert not offenders, (
        "Rule bodies need the `if` keyword under OPA 1.x (use `deny contains msg if {`): "
        + "; ".join(offenders)
    )


@pytest.mark.parametrize(
    "snippet",
    [
        "deny[msg] {\n    input.x\n}\n",
        "helper(actions) {\n    actions[_] == 1\n}\n",
    ],
)
def test_guard_rejects_classic_syntax(tmp_path: Path, snippet: str, monkeypatch) -> None:
    """The guard must actually catch the syntax it is meant to prevent."""
    policy_dir = tmp_path / "policy"
    policy_dir.mkdir()
    (policy_dir / "sample.rego").write_text(f"package main\n\n{snippet}", encoding="utf-8")

    with pytest.raises(AssertionError):
        test_every_rego_file_imports_rego_v1(tmp_path)
    with pytest.raises(AssertionError):
        test_no_classic_rule_bodies(tmp_path)
