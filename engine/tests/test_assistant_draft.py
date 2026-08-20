"""Tests for gated assistant draft (catalog inputs only)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from helpers import make_blueprint
from repave_engine.assistant import resolve_catalog_intent, resolve_intent
from repave_engine.assistant_draft import (
    SequencedAssistantDraftModel,
    StaticAssistantDraftModel,
    apply_model_draft,
    parse_draft_payload,
    validate_draft_inputs,
)
from repave_engine.blueprint import InputField
from repave_engine.v3_foundation import load_v3_foundation_config


def test_parse_draft_rejects_files_payload() -> None:
    with pytest.raises(ValueError, match="must not include files"):
        parse_draft_payload('{"blueprint":"terraform-module-generic","files":{"a":"b"}}')


def test_parse_draft_accepts_fenced_json() -> None:
    parsed = parse_draft_payload(
        '```json\n{"blueprint":"terraform-module-generic","inputs":{"cloud_provider":"aws"}}\n```'
    )
    assert parsed.blueprint == "terraform-module-generic"
    assert parsed.inputs["cloud_provider"] == "aws"


def test_validate_draft_inputs_drops_unknown_and_bad_enum(tmp_path: Path) -> None:
    blueprint = make_blueprint(
        tmp_path,
        name="terraform-module-generic",
        inputs=(
            InputField(
                name="cloud_provider",
                type="string",
                required=True,
                enum=("aws", "azure", "gcp"),
            ),
            InputField(name="module_name", type="string", required=True),
        ),
    )
    validated = validate_draft_inputs(
        blueprint,
        {"cloud_provider": "nope", "module_name": "vpc-core", "secret": "x", "unknown": "y"},
    )
    assert validated == {"module_name": "vpc-core"}


def test_apply_model_draft_merges_validated_inputs(tmp_path: Path) -> None:
    blueprint = make_blueprint(
        tmp_path,
        name="terraform-module-generic",
        artifact_type="terraform-module",
        inputs=(
            InputField(
                name="cloud_provider",
                type="string",
                required=True,
                enum=("aws", "azure", "gcp"),
            ),
        ),
    )
    resolution = resolve_intent(
        "terraform module for aws",
        blueprints=(blueprint,),
    )
    payload = json.dumps(
        {
            "blueprint": "terraform-module-generic",
            "inputs": {"cloud_provider": "gcp", "files": "nope"},
        }
    )
    updated = apply_model_draft(
        resolution,
        blueprints=(blueprint,),
        model=StaticAssistantDraftModel(payload),
        model_id="static-test",
    )
    assert updated.draft_status == "applied"
    assert len(updated.prompt_hash) == 64
    assert updated.matches[0].suggested_inputs["cloud_provider"] == "gcp"
    assert "files" not in updated.matches[0].suggested_inputs
    assert "catalog.draft" in updated.tools


def test_apply_model_draft_rejects_invalid_json(tmp_path: Path) -> None:
    blueprint = make_blueprint(tmp_path, name="terraform-module-generic")
    resolution = resolve_intent("terraform module", blueprints=(blueprint,))
    updated = apply_model_draft(
        resolution,
        blueprints=(blueprint,),
        model=StaticAssistantDraftModel("not-json"),
        model_id="static-test",
    )
    assert updated.draft_status == "rejected"
    assert updated.prompt_hash


def test_assistant_draft_requires_assistant_enabled(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\n"
        "output:\n  github_org: acme\n  modules_root: ../mods\n"
        "v3:\n  enabled: true\n  assistant:\n    enabled: false\n"
        "    draft:\n      enabled: true\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"v3\.assistant\.draft\.enabled"):
        load_v3_foundation_config(tmp_path)


def test_resolve_catalog_intent_applies_injected_draft(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = load_v3_foundation_config(repo_root)
    patched = replace(
        loaded,
        enabled=True,
        assistant_enabled=True,
        assistant_draft_enabled=True,
        assistant_draft_model="static-test",
    )
    monkeypatch.setattr(
        "repave_engine.assistant.load_v3_foundation_config",
        lambda _root: patched,
    )
    model = SequencedAssistantDraftModel(
        (
            '{"blueprint":"terraform-module-generic","inputs":{"cloud_provider":"gcp"}}',
            '{"answer":"Use the terraform module layout cited in standards."}',
        )
    )
    result = resolve_catalog_intent(
        repo_root,
        intent="terraform module named networking-vnet",
        draft_model=model,
    )
    assert result.draft_status == "applied"
    assert result.draft_model == "static-test"
    assert result.matches[0].blueprint == "terraform-module-generic"
    assert result.matches[0].suggested_inputs["cloud_provider"] == "gcp"
    assert len(result.prompt_hash) == 64
    assert result.synthesis_status in {"applied", "skipped-no-citations"}
    if result.citations:
        assert result.synthesis_status == "applied"
        assert "standards" in result.answer or "terraform" in result.answer.lower()
        assert "corpus.synthesize" in result.tools
        assert "Catalog:" not in model.prompts[1]
        assert any(":" in line for line in model.prompts[1].splitlines())
