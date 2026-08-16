from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from repave_engine.blueprint import artifact_family, load_blueprint
from repave_engine.gates import run_gates
from repave_engine.provenance import build_provenance_document


def _openapi_repo(root: Path) -> None:
    spec = "\n".join(
        [
            "openapi: 3.1.0",
            "info:",
            "  title: Demo",
            "  version: 0.1.0",
            "paths:",
            "  /health:",
            "    get:",
            "      responses:",
            '        "200":',
            "          description: OK",
        ]
    )
    (root / "openapi.yaml").write_text(spec + "\n", encoding="utf-8")
    (root / "baseline").mkdir()
    (root / "baseline" / "openapi.yaml").write_text(spec + "\n", encoding="utf-8")
    (root / ".spectral.yaml").write_text("extends:\n  - spectral:oas\n", encoding="utf-8")


def test_artifact_family_api_contract() -> None:
    assert artifact_family("api-contract") == "api"


def test_spectral_skips_when_tool_missing(tmp_path: Path, monkeypatch) -> None:
    _openapi_repo(tmp_path)
    monkeypatch.setattr("repave_engine.gate_runners.tool_available", lambda name: False)

    results = run_gates(tmp_path, ("spectral",))

    assert results[0].passed is True
    assert results[0].skipped is True
    assert "not installed" in results[0].message


def test_spectral_fails_on_lint_error(tmp_path: Path, monkeypatch) -> None:
    _openapi_repo(tmp_path)
    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda name: name == "spectral",
    )
    monkeypatch.setattr(
        "repave_engine.gate_runners.run_command",
        lambda cmd, cwd, **kwargs: MagicMock(returncode=1, stdout="", stderr="oas3-schema error"),
    )

    results = run_gates(tmp_path, ("spectral",))

    assert results[0].passed is False
    assert results[0].skipped is False
    assert "oas3-schema" in results[0].message


def test_spectral_fails_when_spec_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda name: name == "spectral",
    )

    results = run_gates(tmp_path, ("spectral",))

    assert results[0].passed is False
    assert "spec_file" in results[0].message


def test_oasdiff_fails_on_breaking_change(tmp_path: Path, monkeypatch) -> None:
    _openapi_repo(tmp_path)
    captured: list[list[str]] = []

    def _run(cmd: list[str], cwd: Path, **kwargs: object) -> MagicMock:
        captured.append(cmd)
        return MagicMock(returncode=1, stdout="", stderr="deleted path /health")

    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda name: name == "oasdiff",
    )
    monkeypatch.setattr("repave_engine.gate_runners.run_command", _run)

    results = run_gates(tmp_path, ("oasdiff",))

    assert results[0].passed is False
    assert results[0].skipped is False
    assert captured[0][:2] == ["oasdiff", "breaking"]
    assert "baseline/openapi.yaml" in captured[0]
    assert "deleted path" in results[0].message


def test_oasdiff_skips_asyncapi(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "asyncapi.yaml").write_text(
        "asyncapi: 3.0.0\ninfo:\n  title: Demo\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda name: name == "oasdiff",
    )

    results = run_gates(tmp_path, ("oasdiff",))

    assert results[0].passed is True
    assert results[0].skipped is True
    assert "OpenAPI" in results[0].message


def test_api_contract_blueprint_and_provenance(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "api-contract-generic",
        repo_root=repo_root,
    )
    assert blueprint.artifact_type == "api-contract"
    assert "spectral" in blueprint.gates
    assert "oasdiff" in blueprint.gates
    document = build_provenance_document(
        blueprint,
        {
            "spec_name": "checkout",
            "organization": "platform",
            "spec_kind": "openapi",
            "api_title": "Checkout API",
            "api_version": "0.1.0",
        },
    )
    assert document["spec"]["artifactType"] == "api-contract"
    assert document["spec"]["apiContract"]["spec_name"] == "checkout"
