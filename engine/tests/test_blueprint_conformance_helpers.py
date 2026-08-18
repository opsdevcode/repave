from __future__ import annotations

from pathlib import Path

from repave_engine.blueprint_conformance import (
    _CONFORMANCE_GITHUB_ORG,
    _snapshot_output_config,
    _text_has_unresolved_template,
    build_file_manifest,
    find_unresolved_placeholders,
    load_conformance_specs,
)
from repave_engine.settings import OutputConfig


def test_helm_template_syntax_allowed(tmp_path) -> None:
    chart = tmp_path / "templates" / "deploy.yaml"
    chart.parent.mkdir(parents=True)
    chart.write_text('image: "{{ .Values.image.repository }}"\n', encoding="utf-8")
    assert find_unresolved_placeholders(tmp_path) == []


def test_copier_leftover_detected(tmp_path) -> None:
    bad = tmp_path / "README.md"
    bad.write_text("Hello {{ unresolved_var }}\n", encoding="utf-8")
    assert len(find_unresolved_placeholders(tmp_path)) == 1


def test_jinja_block_detected() -> None:
    assert _text_has_unresolved_template("{% if x %}")


def test_manifest_skips_zero_byte_copier_stubs(tmp_path) -> None:
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    (tmp_path / "empty.go").write_bytes(b"")
    manifest = build_file_manifest(tmp_path, artifact_type="app-service")
    assert "README.md" in manifest
    assert "empty.go" not in manifest


def test_placeholder_scan_skips_node_modules(tmp_path) -> None:
    deps = tmp_path / "node_modules" / "pkg"
    deps.mkdir(parents=True)
    (deps / "broken.json").write_text('{"msg": "{{ not a copier var }}"}\n', encoding="utf-8")
    (tmp_path / "README.md").write_text("ok\n", encoding="utf-8")
    assert find_unresolved_placeholders(tmp_path) == []


def test_load_app_service_variant_specs(repo_root: Path) -> None:
    specs = load_conformance_specs(repo_root / "blueprints" / "app-service-generic")
    assert len(specs) == 20
    python_api = next(spec for spec in specs if spec.variant_id == "python-http-api")
    assert python_api.inputs["runtime"] == "python"
    assert python_api.inputs["layout"] == "http-api"
    assert "tests/test_health.py" in python_api.required_files
    assert python_api.snapshot is True
    assert python_api.run_gates is True
    python_worker = next(spec for spec in specs if spec.variant_id == "python-worker")
    assert python_worker.run_gates is False
    assert python_worker.slow_harness is False


def test_load_legacy_single_spec_conformance(repo_root: Path) -> None:
    specs = load_conformance_specs(repo_root / "blueprints" / "terraform-module-generic")
    assert len(specs) == 1
    assert specs[0].variant_id == ""
    assert specs[0].inputs["module_name"] == "conformance-example"


def test_snapshot_output_config_pins_conformance_org(tmp_path: Path) -> None:
    modules_root = tmp_path / "modules"
    modules_root.mkdir()
    output_config = OutputConfig(github_org="example-org", modules_root=modules_root)
    pinned = _snapshot_output_config(output_config)
    assert pinned.github_org == _CONFORMANCE_GITHUB_ORG
    assert pinned.modules_root == modules_root
