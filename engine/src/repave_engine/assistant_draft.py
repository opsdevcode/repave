"""Gated assistant draft — model may propose catalog inputs only, never artifacts."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Protocol

import httpx

from repave_engine.assistant import (
    AssistantCitation,
    AssistantMatch,
    AssistantResolution,
    blueprint_form_href,
)
from repave_engine.blueprint import Blueprint, artifact_family

logger = logging.getLogger(__name__)

_MAX_INPUT_CHARS = 200
_MAX_INPUT_KEYS = 24
_BLOCKED_FIELDS = frozenset(
    {
        "apply",
        "body",
        "content",
        "dry_run",
        "files",
        "generate",
        "password",
        "secret",
        "token",
    }
)
_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


_DRAFT_SYSTEM = (
    "Reply with JSON only: "
    '{"blueprint":"<catalog name>",'
    '"inputs":{"field":"value"}}. '
    "Use only listed field names. "
    "Never emit files, secrets, or gate results."
)


class AssistantDraftModel(Protocol):
    def complete(self, prompt: str, *, system: str = "") -> str:
        """Return model text. Callers must treat it as untrusted."""


@dataclass(frozen=True)
class StaticAssistantDraftModel:
    payload: str

    def complete(self, prompt: str, *, system: str = "") -> str:
        return self.payload


class RecordingAssistantDraftModel:
    """In-package fake that records prompts for tests."""

    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.prompts: list[str] = []
        self.systems: list[str] = []

    def complete(self, prompt: str, *, system: str = "") -> str:
        self.prompts.append(prompt)
        self.systems.append(system)
        return self.payload


class SequencedAssistantDraftModel:
    """In-package fake that returns successive payloads (draft then synthesis)."""

    def __init__(self, payloads: tuple[str, ...]) -> None:
        self._payloads = list(payloads)
        self.prompts: list[str] = []
        self.systems: list[str] = []

    def complete(self, prompt: str, *, system: str = "") -> str:
        self.prompts.append(prompt)
        self.systems.append(system)
        if not self._payloads:
            raise ValueError("assistant draft model has no remaining payloads")
        return self._payloads.pop(0)


@dataclass(frozen=True)
class HttpAssistantDraftModel:
    """OpenAI-compatible chat completions. URL and key come from operator env."""

    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: float = 20.0

    def complete(self, prompt: str, *, system: str = "") -> str:
        url = self.base_url.rstrip("/") + "/chat/completions"
        system_text = system.strip() or _DRAFT_SYSTEM
        try:
            response = httpx.post(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": system_text},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ValueError(
                "Assistant draft model request failed. Check REPAVE_ASSISTANT_BASE_URL "
                "and REPAVE_ASSISTANT_API_KEY."
            ) from exc
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Assistant draft model returned a non-object JSON body")
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("Assistant draft model returned no choices")
        message = choices[0]
        if not isinstance(message, dict):
            raise ValueError("Assistant draft model returned an invalid choice")
        inner = message.get("message")
        if not isinstance(inner, dict):
            raise ValueError("Assistant draft model returned an invalid message")
        content = inner.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Assistant draft model returned empty content")
        return content


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def load_draft_model_from_env(*, model: str) -> HttpAssistantDraftModel | None:
    """Build the HTTP model when a key is set. Returns None so callers skip draft."""
    name = model.strip()
    if not name:
        name = "gpt-4o-mini"
    key = os.environ.get("REPAVE_ASSISTANT_API_KEY", "").strip()
    if not key:
        return None
    base = os.environ.get("REPAVE_ASSISTANT_BASE_URL", "").strip() or "https://api.openai.com/v1"
    return HttpAssistantDraftModel(api_key=key, model=name, base_url=base)


def build_draft_prompt(
    *,
    intent: str,
    blueprints: Sequence[Blueprint],
    citation_sources: Sequence[str],
) -> str:
    """Catalog field schema plus citation paths. Does not include generate output."""
    lines = [
        "Map the intent to one catalog golden path and allowed input fields.",
        "Do not invent field names. Do not return files or source code.",
        f"Intent: {intent.strip()}",
        "Citations: " + ", ".join(citation_sources) if citation_sources else "Citations: none",
        "Catalog:",
    ]
    for blueprint in blueprints[:40]:
        fields = []
        for field in blueprint.inputs:
            if field.name in _BLOCKED_FIELDS:
                continue
            item = field.name
            if field.enum:
                item += f" enum={','.join(field.enum)}"
            fields.append(item)
        family = artifact_family(blueprint.artifact_type)
        lines.append(f"- {blueprint.name} family={family} fields={'; '.join(fields)}")
    return "\n".join(lines)


def apply_model_draft(
    resolution: AssistantResolution,
    *,
    blueprints: Sequence[Blueprint],
    model: AssistantDraftModel,
    model_id: str,
) -> AssistantResolution:
    """Merge a model JSON draft into catalog matches after field validation."""
    prompt = build_draft_prompt(
        intent=resolution.intent,
        blueprints=blueprints,
        citation_sources=tuple(item.source for item in resolution.citations),
    )
    digest = prompt_hash(prompt)
    try:
        raw = model.complete(prompt)
        parsed = parse_draft_payload(raw)
    except ValueError as exc:
        logger.warning("assistant draft rejected: %s", exc)
        return replace(
            resolution,
            draft_model=model_id,
            prompt_hash=digest,
            draft_status="rejected",
        )
    by_name = {item.name: item for item in blueprints}
    chosen = by_name.get(parsed.blueprint)
    if chosen is None:
        return replace(
            resolution,
            draft_model=model_id,
            prompt_hash=digest,
            draft_status="unknown-blueprint",
        )
    validated = validate_draft_inputs(chosen, parsed.inputs)
    matches = _merge_draft_match(resolution.matches, blueprint=chosen, inputs=validated)
    return replace(
        resolution,
        matches=matches,
        draft_model=model_id,
        prompt_hash=digest,
        draft_status="applied",
        tools=tuple(dict.fromkeys((*resolution.tools, "catalog.draft"))),
    )


@dataclass(frozen=True)
class ParsedDraft:
    blueprint: str
    inputs: dict[str, str]


def parse_draft_payload(raw: str) -> ParsedDraft:
    text = raw.strip()
    fenced = _JSON_FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("assistant draft must be a JSON object") from exc
    if not isinstance(payload, dict):
        raise ValueError("assistant draft must be a JSON object")
    for blocked in ("files", "content", "generate", "dry_run"):
        if blocked in payload:
            raise ValueError(f"assistant draft must not include {blocked}")
    blueprint = str(payload.get("blueprint", "")).strip()
    if not blueprint:
        raise ValueError("assistant draft is missing blueprint")
    inputs_raw = payload.get("inputs", {})
    if not isinstance(inputs_raw, dict):
        raise ValueError("assistant draft inputs must be an object")
    if len(inputs_raw) > _MAX_INPUT_KEYS:
        raise ValueError(f"assistant draft inputs exceed {_MAX_INPUT_KEYS} keys; remove extras")
    inputs: dict[str, str] = {}
    for key, value in inputs_raw.items():
        name = str(key).strip()
        if not name or name in _BLOCKED_FIELDS:
            continue
        if not isinstance(value, str | int | float | bool):
            continue
        text_value = str(value).strip()
        if not text_value or len(text_value) > _MAX_INPUT_CHARS:
            continue
        inputs[name] = text_value
    return ParsedDraft(blueprint=blueprint, inputs=inputs)


def validate_draft_inputs(blueprint: Blueprint, raw: Mapping[str, str]) -> dict[str, str]:
    allowed = {field.name: field for field in blueprint.inputs}
    validated: dict[str, str] = {}
    for name, value in raw.items():
        field = allowed.get(name)
        if field is None or name in _BLOCKED_FIELDS:
            continue
        if field.enum and value not in field.enum:
            continue
        validated[name] = value
    return validated


def _merge_draft_match(
    matches: tuple[AssistantMatch, ...],
    *,
    blueprint: Blueprint,
    inputs: dict[str, str],
) -> tuple[AssistantMatch, ...]:
    excerpt = blueprint.description.strip() or blueprint.name
    existing = next((item for item in matches if item.blueprint == blueprint.name), None)
    merged_inputs = dict(existing.suggested_inputs) if existing is not None else {}
    merged_inputs.update(inputs)
    updated = AssistantMatch(
        blueprint=blueprint.name,
        description=blueprint.description,
        family=artifact_family(blueprint.artifact_type),
        score=existing.score if existing is not None else 50.0,
        form_href=blueprint_form_href(blueprint.name, inputs=merged_inputs),
        citations=existing.citations
        if existing is not None
        else (
            AssistantCitation(
                source=f"catalog:{blueprint.name}",
                title=blueprint.name,
                excerpt=excerpt[:240],
            ),
        ),
        suggested_inputs=merged_inputs,
    )
    rest = tuple(item for item in matches if item.blueprint != blueprint.name)
    return (updated, *rest)
