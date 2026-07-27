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
