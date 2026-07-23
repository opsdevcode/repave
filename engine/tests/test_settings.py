from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.settings import load_gate_overrides, load_output_config


def test_load_output_config_from_environment(tmp_path: Path, monkeypatch) -> None:
    modules_root = tmp_path / "modules"
    monkeypatch.setenv("REPAVE_GITHUB_ORG", "acme")
    monkeypatch.setenv("REPAVE_MODULES_ROOT", str(modules_root))

    config = load_output_config(tmp_path)

    assert config.github_org == "acme"
    assert config.modules_root == modules_root


def test_load_output_config_requires_github_org(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("REPAVE_GITHUB_ORG", raising=False)
    monkeypatch.delenv("REPAVE_MODULES_ROOT", raising=False)

    with pytest.raises(ValueError, match="GitHub organization is required"):
        load_output_config(tmp_path)


def test_load_output_config_from_file(tmp_path: Path) -> None:
    modules_root = tmp_path / "configured-modules"
    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "output:",
                "  github_org: from-file",
                f'  modules_root: "{modules_root}"',
            ]
        ),
        encoding="utf-8",
    )

    config = load_output_config(tmp_path)

    assert config.github_org == "from-file"
    assert config.modules_root == modules_root


def test_load_output_config_with_explicit_overrides(tmp_path: Path) -> None:
    modules_root = tmp_path / "override-modules"
    config = load_output_config(
        tmp_path,
        github_org="override-org",
        modules_root=modules_root,
    )

    assert config.github_org == "override-org"
    assert config.modules_root == modules_root


def test_load_gate_overrides_from_file(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "output:",
                "  github_org: acme",
                "  modules_root: ../modules",
                "gates:",
                "  checkov:",
                "    skip_checks:",
                "      - CKV_AWS_1",
            ]
        ),
        encoding="utf-8",
    )

    overrides = load_gate_overrides(tmp_path)

    assert overrides.checkov_skip_checks == ("CKV_AWS_1",)


def test_load_output_config_requires_modules_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REPAVE_GITHUB_ORG", "acme")
    monkeypatch.delenv("REPAVE_MODULES_ROOT", raising=False)

    with pytest.raises(ValueError, match="Module output root is required"):
        load_output_config(tmp_path)


def test_load_output_config_resolves_relative_modules_root(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "output:",
                "  github_org: acme",
                "  modules_root: ../configured-modules",
            ]
        ),
        encoding="utf-8",
    )

    config = load_output_config(tmp_path)

    assert config.modules_root == (tmp_path / "../configured-modules").resolve()


def test_load_gate_overrides_returns_empty_when_config_missing(tmp_path: Path) -> None:
    overrides = load_gate_overrides(tmp_path)

    assert overrides.checkov_skip_checks == ()


def test_load_gate_overrides_rejects_non_list_skip_checks(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "output:",
                "  github_org: acme",
                "  modules_root: ../modules",
                "gates:",
                "  checkov:",
                "    skip_checks: CKV_AWS_1",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be a list"):
        load_gate_overrides(tmp_path)
