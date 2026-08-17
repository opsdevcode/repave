from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.settings import (
    load_blueprint_pack_config,
    load_blueprint_sources,
    load_gate_overrides,
    load_notifications_config,
    load_output_config,
)


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
    assert overrides.infracost.required is False
    assert overrides.infracost.max_monthly_usd is None


def test_load_gate_overrides_infracost_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REPAVE_INFRACOST_REQUIRED", raising=False)
    monkeypatch.delenv("REPAVE_INFRACOST_MAX_MONTHLY_USD", raising=False)
    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "output:",
                "  github_org: acme",
                "  modules_root: ../modules",
                "gates:",
                "  infracost:",
                "    required: true",
                "    max_monthly_usd: 250",
            ]
        ),
        encoding="utf-8",
    )

    overrides = load_gate_overrides(tmp_path)

    assert overrides.infracost.required is True
    assert overrides.infracost.max_monthly_usd == 250.0


def test_load_gate_overrides_infracost_env_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REPAVE_INFRACOST_REQUIRED", "1")
    monkeypatch.setenv("REPAVE_INFRACOST_MAX_MONTHLY_USD", "100")
    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "output:",
                "  github_org: acme",
                "  modules_root: ../modules",
            ]
        ),
        encoding="utf-8",
    )

    overrides = load_gate_overrides(tmp_path)

    assert overrides.infracost.required is True
    assert overrides.infracost.max_monthly_usd == 100.0


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


def test_load_notifications_config_requires_webhook_when_enabled(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "notifications:\n  enabled: true\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no webhook URL"):
        load_notifications_config(tmp_path)


def test_load_blueprint_sources_defaults_to_repo_blueprints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REPAVE_BLUEPRINTS_ROOT", raising=False)
    monkeypatch.delenv("REPAVE_BLUEPRINT_SOURCES", raising=False)

    sources = load_blueprint_sources(tmp_path)

    assert sources.roots == ((tmp_path / "blueprints").resolve(),)


def test_load_blueprint_sources_from_file_and_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extra_root = tmp_path / "org-packs"
    extra_list = tmp_path / "vendor-packs"
    env_root = tmp_path / "env-root"
    env_a = tmp_path / "env-a"
    env_b = tmp_path / "env-b"
    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "apiVersion: repave.dev/v1",
                "blueprints_root: org-packs",
                "blueprint_sources:",
                "  - vendor-packs",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("REPAVE_BLUEPRINTS_ROOT", str(env_root))
    monkeypatch.setenv("REPAVE_BLUEPRINT_SOURCES", f"{env_a}, {env_b}")

    sources = load_blueprint_sources(tmp_path)

    assert sources.roots == (
        (tmp_path / "blueprints").resolve(),
        extra_root.resolve(),
        extra_list.resolve(),
        env_root.resolve(),
        env_a.resolve(),
        env_b.resolve(),
    )


def test_load_blueprint_sources_dedupes_and_rejects_bad_types(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REPAVE_BLUEPRINTS_ROOT", raising=False)
    monkeypatch.delenv("REPAVE_BLUEPRINT_SOURCES", raising=False)
    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "apiVersion: repave.dev/v1",
                "blueprints_root: blueprints",
                "blueprint_sources:",
                "  - ./blueprints",
            ]
        ),
        encoding="utf-8",
    )

    sources = load_blueprint_sources(tmp_path)
    assert sources.roots == ((tmp_path / "blueprints").resolve(),)

    (tmp_path / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\nblueprints_root: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="blueprints_root must be a local path"):
        load_blueprint_sources(tmp_path)

    (tmp_path / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\nblueprint_sources: extra-packs\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="blueprint_sources must be a list"):
        load_blueprint_sources(tmp_path)


def test_load_blueprint_pack_config_parses_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REPAVE_BLUEPRINT_PACK_CACHE", raising=False)
    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "apiVersion: repave.dev/v1",
                "blueprint_packs:",
                "  cache_dir: cache/packs",
                "  sources:",
                "    - url: https://github.com/acme/org-blueprints.git",
                "      ref: v1.2.0",
                "      subdir: blueprints",
                "      dest: acme-blueprints",
            ]
        ),
        encoding="utf-8",
    )

    config = load_blueprint_pack_config(tmp_path)

    assert config is not None
    assert config.cache_dir == (tmp_path / "cache" / "packs").resolve()
    assert len(config.sources) == 1
    assert config.sources[0].url == "https://github.com/acme/org-blueprints.git"
    assert config.sources[0].ref == "v1.2.0"
    assert config.sources[0].subdir == "blueprints"
    assert config.sources[0].dest == "acme-blueprints"


def test_load_blueprint_pack_config_parses_oci_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REPAVE_BLUEPRINT_PACK_CACHE", raising=False)
    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "apiVersion: repave.dev/v1",
                "blueprint_packs:",
                "  sources:",
                "    - url: oci://ghcr.io/acme/org-blueprints",
                "      ref: sha256:abcd",
                "      dest: acme-oci",
            ]
        ),
        encoding="utf-8",
    )

    config = load_blueprint_pack_config(tmp_path)

    assert config is not None
    assert config.sources[0].url == "oci://ghcr.io/acme/org-blueprints"
    assert config.sources[0].ref == "sha256:abcd"
    assert config.sources[0].dest == "acme-oci"


def test_load_blueprint_pack_config_env_cache_and_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REPAVE_BLUEPRINT_PACK_CACHE", "env-cache")
    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "apiVersion: repave.dev/v1",
                "blueprint_packs:",
                "  sources:",
                "    - url: file:///tmp/pack.git",
                "      ref: main",
            ]
        ),
        encoding="utf-8",
    )

    config = load_blueprint_pack_config(tmp_path)

    assert config is not None
    assert config.cache_dir == (tmp_path / "env-cache").resolve()
    assert config.sources[0].subdir == "."
    assert config.sources[0].dest is None
    assert load_blueprint_pack_config(tmp_path / "missing") is None


def test_load_blueprint_pack_config_rejects_bad_fields(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\nblueprint_packs: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="blueprint_packs must be a mapping"):
        load_blueprint_pack_config(tmp_path)

    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "apiVersion: repave.dev/v1",
                "blueprint_packs:",
                "  sources:",
                "    - url: https://github.com/acme/org-blueprints.git",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"sources\[\]\.ref is required"):
        load_blueprint_pack_config(tmp_path)

    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "apiVersion: repave.dev/v1",
                "blueprint_packs:",
                "  sources:",
                "    - url: git@github.com:acme/org-blueprints.git",
                "      ref: main",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"http\(s\) or file://"):
        load_blueprint_pack_config(tmp_path)

    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "apiVersion: repave.dev/v1",
                "blueprint_packs:",
                "  sources:",
                "    - url: https://github.com/acme/org-blueprints.git",
                "      ref: main",
                "      subdir: ../escape",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"without '\.\.'"):
        load_blueprint_pack_config(tmp_path)

    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "apiVersion: repave.dev/v1",
                "blueprint_packs:",
                "  cache_dir: []",
                "  sources: []",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="cache_dir must be a local path"):
        load_blueprint_pack_config(tmp_path)
