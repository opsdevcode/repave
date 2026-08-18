from __future__ import annotations

from pathlib import Path

from repave_engine.blueprint_conformance import _file_manifest_digest


def test_manifest_digest_neutralizes_engine_version_in_workflow() -> None:
    before = b'pip install "repave-engine==1.66.0"\n'
    after = b'pip install "repave-engine==1.67.0"\n'
    assert _file_manifest_digest(
        ".github/workflows/repave-gates.yml",
        before,
    ) == _file_manifest_digest(".github/workflows/repave-gates.yml", after)


def test_manifest_digest_neutralizes_engine_version_in_repave_yaml() -> None:
    before = b"generation:\n  engine_version: 1.66.0\n"
    after = b"generation:\n  engine_version: 1.67.0\n"
    assert _file_manifest_digest("repave.yaml", before) == _file_manifest_digest(
        "repave.yaml", after
    )


def test_manifest_digest_neutralizes_engine_line_in_readme() -> None:
    before = b"- **Engine:** `1.66.0` (pinned)\n"
    after = b"- **Engine:** `1.67.0` (pinned)\n"
    assert _file_manifest_digest("README.md", before) == _file_manifest_digest("README.md", after)


def test_manifest_digest_neutralizes_engine_version_in_catalog_info() -> None:
    """Release bumps rewrite repave.dev/engine-version; hashes must not chase them."""
    before = (
        b"metadata:\n"
        b"  annotations:\n"
        b"    repave.dev/blueprint: app-service-generic\n"
        b"    repave.dev/engine-version: 2.25.1\n"
    )
    after = (
        b"metadata:\n"
        b"  annotations:\n"
        b"    repave.dev/blueprint: app-service-generic\n"
        b"    repave.dev/engine-version: 2.26.0\n"
    )
    assert _file_manifest_digest("catalog-info.yaml", before) == _file_manifest_digest(
        "catalog-info.yaml", after
    )


def test_manifest_digest_neutralizes_blueprint_and_standard_version_in_catalog_info() -> None:
    before = (
        b"metadata:\n"
        b"  annotations:\n"
        b"    repave.dev/blueprint-version: 0.12.0\n"
        b"    repave.dev/standard-version: 1.4.0\n"
    )
    after = (
        b"metadata:\n"
        b"  annotations:\n"
        b"    repave.dev/blueprint-version: 0.13.0\n"
        b"    repave.dev/standard-version: 1.5.0\n"
    )
    assert _file_manifest_digest("catalog-info.yaml", before) == _file_manifest_digest(
        "catalog-info.yaml", after
    )


def test_manifest_digest_neutralizes_prerelease_engine_version() -> None:
    """Hyphen prereleases (PSR rc tags) must hash the same as the matching GA pin."""
    cases: tuple[tuple[str, bytes, bytes], ...] = (
        (
            ".github/workflows/repave-gates.yml",
            b'pip install "repave-engine==2.61.0-rc.1"\n',
            b'pip install "repave-engine==2.61.0"\n',
        ),
        (
            "repave.yaml",
            b"generation:\n  engine_version: 2.61.0-rc.1\n",
            b"generation:\n  engine_version: 2.61.0\n",
        ),
        (
            "README.md",
            b"- **Engine:** `2.61.0-rc.1` (generated `1970-01-01T00:00:00+00:00`)\n",
            b"- **Engine:** `2.61.0` (generated `1970-01-01T00:00:00+00:00`)\n",
        ),
        (
            "catalog-info.yaml",
            b"    repave.dev/engine-version: 2.61.0-rc.1\n",
            b"    repave.dev/engine-version: 2.61.0\n",
        ),
    )
    for rel, before, after in cases:
        assert _file_manifest_digest(rel, before) == _file_manifest_digest(rel, after), rel


def test_manifest_digest_still_sees_non_version_catalog_changes() -> None:
    before = (
        b"metadata:\n"
        b"  annotations:\n"
        b"    repave.dev/engine-version: 2.26.0\n"
        b"    repave.dev/blueprint: a\n"
    )
    after = (
        b"metadata:\n"
        b"  annotations:\n"
        b"    repave.dev/engine-version: 2.26.0\n"
        b"    repave.dev/blueprint: b\n"
    )
    assert _file_manifest_digest("catalog-info.yaml", before) != _file_manifest_digest(
        "catalog-info.yaml", after
    )


_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_snapshot_conformance_manifests_match_repo_blueprints(tmp_path: Path) -> None:
    """CI corpus-manifest-check uses the same render-only path as this guard."""
    from repave_engine.blueprint_conformance import find_snapshot_manifest_drifts

    drifts = find_snapshot_manifest_drifts(
        _REPO_ROOT,
        modules_root=tmp_path / "mods",
        staging_root=tmp_path / "staging",
        render_only=True,
    )
    assert drifts == ()
