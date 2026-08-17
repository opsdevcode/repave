from __future__ import annotations

import logging
from pathlib import Path

import pytest

from repave_engine.blueprint_pack_fetch import (
    catalog_root_for_source,
    materialize_blueprint_pack_roots,
    pack_cache_name,
)
from repave_engine.git_clone import CloneError
from repave_engine.oci_pull import OciPullError
from repave_engine.settings import BlueprintPackConfig, BlueprintPackSource


def _source(
    *,
    url: str = "https://github.com/acme/org-blueprints.git",
    ref: str = "v1.2.0",
    subdir: str = ".",
    dest: str | None = None,
    token: str | None = None,
) -> BlueprintPackSource:
    return BlueprintPackSource(url=url, ref=ref, subdir=subdir, dest=dest, token=token)


def test_pack_cache_name_uses_dest_or_url_ref_hash() -> None:
    named = _source(dest="acme-blueprints")
    hashed = _source()
    other_ref = _source(ref="v9.0.0")

    assert pack_cache_name(named) == "acme-blueprints"
    assert pack_cache_name(hashed) != pack_cache_name(other_ref)
    assert len(pack_cache_name(hashed)) == 16


def test_catalog_root_for_source_joins_subdir(tmp_path: Path) -> None:
    source = _source(dest="acme", subdir="blueprints")
    catalog = catalog_root_for_source(source, tmp_path)
    assert catalog == (tmp_path / "acme" / "blueprints").resolve()


def test_materialize_clones_missing_cache_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, Path, str | None, str | None]] = []

    def fake_clone(
        url: str,
        dest_dir: Path,
        *,
        token: str | None = None,
        ref: str | None = None,
        **_kwargs: object,
    ) -> None:
        dest_dir.mkdir(parents=True)
        (dest_dir / "marker").write_text("ok", encoding="utf-8")
        calls.append((url, dest_dir, token, ref))

    monkeypatch.setattr("repave_engine.blueprint_pack_fetch.shallow_clone", fake_clone)
    monkeypatch.setattr("repave_engine.blueprint_pack_fetch.resolve_git_token", lambda: "env-token")

    source = _source(dest="acme-blueprints")
    config = BlueprintPackConfig(cache_dir=tmp_path / "cache", sources=(source,))

    first = materialize_blueprint_pack_roots(tmp_path, config=config)
    second = materialize_blueprint_pack_roots(tmp_path, config=config)

    assert first == ((tmp_path / "cache" / "acme-blueprints").resolve(),)
    assert second == first
    assert len(calls) == 1
    assert calls[0] == (
        source.url,
        (tmp_path / "cache" / "acme-blueprints").resolve(),
        "env-token",
        "v1.2.0",
    )


def test_materialize_uses_explicit_token_and_subdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_clone(
        url: str,
        dest_dir: Path,
        *,
        token: str | None = None,
        ref: str | None = None,
        **_kwargs: object,
    ) -> None:
        catalog = dest_dir / "packs"
        catalog.mkdir(parents=True)
        (catalog / "ok").write_text(token or "", encoding="utf-8")

    monkeypatch.setattr("repave_engine.blueprint_pack_fetch.shallow_clone", fake_clone)
    monkeypatch.setattr("repave_engine.blueprint_pack_fetch.resolve_git_token", lambda: "unused")

    source = _source(dest="acme", subdir="packs", token="explicit-token")
    config = BlueprintPackConfig(cache_dir=tmp_path / "cache", sources=(source,))

    roots = materialize_blueprint_pack_roots(tmp_path, config=config)

    assert roots == ((tmp_path / "cache" / "acme" / "packs").resolve(),)
    assert (tmp_path / "cache" / "acme" / "packs" / "ok").read_text(encoding="utf-8") == (
        "explicit-token"
    )


def test_materialize_skips_clone_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fake_clone(*_args: object, **_kwargs: object) -> None:
        raise CloneError("auth failed")

    monkeypatch.setattr("repave_engine.blueprint_pack_fetch.shallow_clone", fake_clone)
    monkeypatch.setattr("repave_engine.blueprint_pack_fetch.resolve_git_token", lambda: None)
    caplog.set_level(logging.WARNING)

    config = BlueprintPackConfig(cache_dir=tmp_path / "cache", sources=(_source(dest="missing"),))
    roots = materialize_blueprint_pack_roots(tmp_path, config=config)

    assert roots == ()
    assert "clone skipped" in caplog.text
    assert "auth failed" in caplog.text


def test_materialize_skips_missing_subdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fake_clone(
        url: str,
        dest_dir: Path,
        *,
        token: str | None = None,
        ref: str | None = None,
        **_kwargs: object,
    ) -> None:
        dest_dir.mkdir(parents=True)
        (dest_dir / "README.md").write_text("pack\n", encoding="utf-8")

    monkeypatch.setattr("repave_engine.blueprint_pack_fetch.shallow_clone", fake_clone)
    monkeypatch.setattr("repave_engine.blueprint_pack_fetch.resolve_git_token", lambda: None)
    caplog.set_level(logging.WARNING)

    source = _source(dest="acme", subdir="does-not-exist")
    config = BlueprintPackConfig(cache_dir=tmp_path / "cache", sources=(source,))
    roots = materialize_blueprint_pack_roots(tmp_path, config=config)

    assert roots == ()
    assert "catalog root" in caplog.text


def test_materialize_returns_empty_when_unconfigured(tmp_path: Path) -> None:
    assert materialize_blueprint_pack_roots(tmp_path) == ()


def test_materialize_pulls_oci_pack_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, Path, str, str | None]] = []

    def fake_pull(
        url: str,
        dest_dir: Path,
        *,
        ref: str,
        token: str | None = None,
    ) -> None:
        dest_dir.mkdir(parents=True)
        (dest_dir / "marker").write_text("oci", encoding="utf-8")
        calls.append((url, dest_dir, ref, token))

    monkeypatch.setattr("repave_engine.blueprint_pack_fetch.pull_oci_artifact", fake_pull)
    monkeypatch.setattr("repave_engine.blueprint_pack_fetch.resolve_git_token", lambda: "env-token")

    source = _source(url="oci://ghcr.io/acme/org-blueprints", dest="acme-oci")
    config = BlueprintPackConfig(cache_dir=tmp_path / "cache", sources=(source,))

    first = materialize_blueprint_pack_roots(tmp_path, config=config)
    second = materialize_blueprint_pack_roots(tmp_path, config=config)

    assert first == ((tmp_path / "cache" / "acme-oci").resolve(),)
    assert second == first
    assert len(calls) == 1
    assert calls[0] == (
        source.url,
        (tmp_path / "cache" / "acme-oci").resolve(),
        "v1.2.0",
        "env-token",
    )


def test_materialize_skips_oci_pull_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fake_pull(*_args: object, **_kwargs: object) -> None:
        raise OciPullError("oras pull failed")

    monkeypatch.setattr("repave_engine.blueprint_pack_fetch.pull_oci_artifact", fake_pull)
    monkeypatch.setattr("repave_engine.blueprint_pack_fetch.resolve_git_token", lambda: None)
    caplog.set_level(logging.WARNING)

    source = _source(url="oci://ghcr.io/acme/org-blueprints", dest="missing-oci")
    config = BlueprintPackConfig(cache_dir=tmp_path / "cache", sources=(source,))
    roots = materialize_blueprint_pack_roots(tmp_path, config=config)

    assert roots == ()
    assert "pull skipped" in caplog.text
    assert "oras pull failed" in caplog.text
