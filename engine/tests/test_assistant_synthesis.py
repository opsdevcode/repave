"""Tests for cited excerpt synthesis (no generate)."""

from __future__ import annotations

from pathlib import Path

import pytest

from helpers import make_blueprint
from repave_engine.assistant import AssistantCitation, AssistantResolution, resolve_intent
from repave_engine.assistant_corpus import CorpusDocument
from repave_engine.assistant_draft import RecordingAssistantDraftModel
from repave_engine.assistant_synthesis import (
    apply_cited_synthesis,
    parse_synthesis_payload,
)
from repave_engine.blueprint import InputField


def test_parse_synthesis_rejects_files() -> None:
    with pytest.raises(ValueError, match="must not include files"):
        parse_synthesis_payload('{"answer":"ok","files":{"a":"b"}}')


def test_parse_synthesis_accepts_fenced_json() -> None:
    parsed = parse_synthesis_payload('```json\n{"answer":"Use the terraform layout."}\n```')
    assert parsed == "Use the terraform layout."


def test_apply_cited_synthesis_prompt_is_excerpts_only(tmp_path: Path) -> None:
    blueprint = make_blueprint(
        tmp_path,
        name="terraform-module-generic",
        artifact_type="terraform-module",
        inputs=(InputField(name="module_name", type="string", required=True),),
    )
    secret_body = "INTERNAL_ONLY_PACK_SOURCE do-not-leak-this-token"
    corpus = (
        CorpusDocument(
            source="standards/terraform.md",
            title="Terraform layout",
            text=(
                "Terraform modules use a standard layout.\n\n"
                "INTERNAL_ONLY_PACK_SOURCE do-not-leak-this-token"
            ),
            kind="standards",
        ),
    )
    resolution = resolve_intent(
        "terraform module layout",
        blueprints=(blueprint,),
        corpus=corpus,
    )
    assert resolution.citations
    excerpt = resolution.citations[0].excerpt
    model = RecordingAssistantDraftModel('{"answer":"Follow the cited terraform module layout."}')
    updated = apply_cited_synthesis(resolution, model=model, model_id="static-test")
    assert updated.synthesis_status == "applied"
    assert updated.answer == "Follow the cited terraform module layout."
    assert "corpus.synthesize" in updated.tools
    prompt = model.prompts[0]
    assert excerpt in prompt
    assert "Catalog:" not in prompt
    assert "fields=" not in prompt
    assert secret_body not in prompt


def test_apply_cited_synthesis_skips_without_citations(tmp_path: Path) -> None:
    blueprint = make_blueprint(tmp_path, name="helm-chart-generic", artifact_type="helm-chart")
    resolution = resolve_intent("xyzzy-unrelated", blueprints=(blueprint,))
    model = RecordingAssistantDraftModel('{"answer":"should not run"}')
    updated = apply_cited_synthesis(resolution, model=model, model_id="static-test")
    assert updated.synthesis_status == "skipped-no-citations"
    assert updated.answer == ""
    assert model.prompts == []


def test_apply_cited_synthesis_rejects_invalid_json() -> None:
    resolution = AssistantResolution(
        intent="terraform layout",
        matches=(),
        tools=("corpus.standards",),
        message="",
        citations=(
            AssistantCitation(
                source="standards/terraform.md",
                title="Terraform",
                excerpt="Use a standard module layout.",
            ),
        ),
    )
    updated = apply_cited_synthesis(
        resolution,
        model=RecordingAssistantDraftModel("not-json"),
        model_id="static-test",
    )
    assert updated.synthesis_status == "rejected"
    assert updated.answer == ""
