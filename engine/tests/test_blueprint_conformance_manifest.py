from __future__ import annotations

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
