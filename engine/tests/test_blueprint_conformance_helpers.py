from __future__ import annotations

from repave_engine.blueprint_conformance import (
    _text_has_unresolved_template,
    find_unresolved_placeholders,
)


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
