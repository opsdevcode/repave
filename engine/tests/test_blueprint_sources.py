from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.blueprint import (
    blueprint_dir,
    blueprint_source_roots,
    list_catalog_blueprints,
    resolve_blueprint_path,
)


def _write_extra_blueprint(repo_root: Path, dest: Path, *, name: str) -> Path:
    dest.mkdir(parents=True)
    source = (repo_root / "blueprints" / "checkov-policy-generic" / "blueprint.yaml").read_text(
        encoding="utf-8"
    )
    (dest / "blueprint.yaml").write_text(
        source.replace("checkov-policy-generic", name),
        encoding="utf-8",
    )
    return dest


def test_list_catalog_includes_extra_root(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extra_root = tmp_path / "org-blueprints"
    _write_extra_blueprint(repo_root, extra_root / "my-org-vpc", name="my-org-vpc")
    monkeypatch.delenv("REPAVE_BLUEPRINTS_ROOT", raising=False)
    monkeypatch.setenv("REPAVE_BLUEPRINT_SOURCES", str(extra_root))

    names = [item.name for item in list_catalog_blueprints(repo_root)]

    assert "my-org-vpc" in names
    assert "terraform-module-generic" in names
    assert names.index("terraform-module-generic") < names.index("my-org-vpc")


def test_list_catalog_first_root_wins_on_name(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extra_root = tmp_path / "org-blueprints"
    _write_extra_blueprint(
        repo_root,
        extra_root / "terraform-module-generic",
        name="terraform-module-generic",
    )
    monkeypatch.delenv("REPAVE_BLUEPRINTS_ROOT", raising=False)
    monkeypatch.setenv("REPAVE_BLUEPRINT_SOURCES", str(extra_root))

    matches = [
        item
        for item in list_catalog_blueprints(repo_root)
        if item.name == "terraform-module-generic"
    ]

    assert len(matches) == 1
    assert matches[0].description.startswith("Generic Terraform module")


def test_blueprint_dir_resolves_name_and_path_specs(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extra_root = tmp_path / "org-blueprints"
    catalog = _write_extra_blueprint(repo_root, extra_root / "my-org-vpc", name="my-org-vpc")
    monkeypatch.delenv("REPAVE_BLUEPRINTS_ROOT", raising=False)
    monkeypatch.setenv("REPAVE_BLUEPRINT_SOURCES", str(extra_root))

    assert blueprint_dir(repo_root, "my-org-vpc") == catalog.resolve()
    assert (
        blueprint_dir(repo_root, "blueprints/terraform-module-generic").name
        == "terraform-module-generic"
    )
    assert blueprint_dir(repo_root, str(catalog)) == catalog.resolve()
    assert blueprint_dir(repo_root, f"file://{catalog}") == catalog.resolve()
    assert resolve_blueprint_path(repo_root, f"file://{catalog / 'blueprint.yaml'}") == (
        catalog.resolve()
    )


def test_blueprint_dir_rejects_path_outside_sources(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside" / "shadow-vpc"
    _write_extra_blueprint(repo_root, outside, name="shadow-vpc")
    monkeypatch.delenv("REPAVE_BLUEPRINTS_ROOT", raising=False)
    monkeypatch.delenv("REPAVE_BLUEPRINT_SOURCES", raising=False)

    with pytest.raises(ValueError, match="blueprint_sources"):
        blueprint_dir(repo_root, str(outside))
    assert resolve_blueprint_path(repo_root, str(outside)) is None


def test_list_catalog_includes_git_pack_root(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extra_root = tmp_path / "git-pack"
    _write_extra_blueprint(repo_root, extra_root / "my-git-vpc", name="my-git-vpc")
    monkeypatch.delenv("REPAVE_BLUEPRINTS_ROOT", raising=False)
    monkeypatch.delenv("REPAVE_BLUEPRINT_SOURCES", raising=False)
    monkeypatch.setattr(
        "repave_engine.blueprint_pack_fetch.materialize_blueprint_pack_roots",
        lambda _repo_root, **_kwargs: (extra_root.resolve(),),
    )

    names = [item.name for item in list_catalog_blueprints(repo_root)]
    roots = blueprint_source_roots(repo_root)

    assert "my-git-vpc" in names
    assert extra_root.resolve() in roots
    assert roots[0] == (repo_root / "blueprints").resolve()
    assert names.index("terraform-module-generic") < names.index("my-git-vpc")


def test_list_catalog_git_pack_loses_to_stock_name(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extra_root = tmp_path / "git-pack"
    _write_extra_blueprint(
        repo_root,
        extra_root / "terraform-module-generic",
        name="terraform-module-generic",
    )
    monkeypatch.delenv("REPAVE_BLUEPRINTS_ROOT", raising=False)
    monkeypatch.delenv("REPAVE_BLUEPRINT_SOURCES", raising=False)
    monkeypatch.setattr(
        "repave_engine.blueprint_pack_fetch.materialize_blueprint_pack_roots",
        lambda _repo_root, **_kwargs: (extra_root.resolve(),),
    )

    matches = [
        item
        for item in list_catalog_blueprints(repo_root)
        if item.name == "terraform-module-generic"
    ]

    assert len(matches) == 1
    assert matches[0].description.startswith("Generic Terraform module")
