"""Cited corpus synthesis — model may paraphrase excerpts, never generate artifacts."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import replace

from repave_engine.assistant import AssistantCitation, AssistantResolution
from repave_engine.assistant_draft import AssistantDraftModel, prompt_hash

logger = logging.getLogger(__name__)

_MAX_ANSWER_CHARS = 1200
_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)
SYNTHESIS_SYSTEM = (
    'Reply with JSON only: {"answer":"<plain text>"}. '
    "Use only the provided excerpts. Name source paths in the answer. "
    "Never emit files, secrets, or gate results."
)


def build_synthesis_prompt(
    *,
    intent: str,
    citations: tuple[AssistantCitation, ...],
) -> str:
    """Intent plus citation excerpts only — not catalog schemas or pack source files."""
    lines = [
        "Answer the intent using only these excerpts.",
        f"Intent: {intent.strip()}",
        "Excerpts:",
    ]
    for citation in citations:
        excerpt = " ".join(citation.excerpt.split())
        lines.append(f"- {citation.source}: {excerpt}")
    return "\n".join(lines)


def parse_synthesis_payload(raw: str) -> str:
    text = raw.strip()
    fenced = _JSON_FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("assistant synthesis must be a JSON object") from exc
    if not isinstance(payload, dict):
        raise ValueError("assistant synthesis must be a JSON object")
    for blocked in ("files", "content", "generate", "dry_run"):
        if blocked in payload:
            raise ValueError(f"assistant synthesis must not include {blocked}")
    answer = str(payload.get("answer", "")).strip()
    if not answer:
        raise ValueError("assistant synthesis is missing answer")
    compact = " ".join(answer.split())
    if len(compact) > _MAX_ANSWER_CHARS:
        compact = compact[: _MAX_ANSWER_CHARS - 1].rstrip() + "…"
    return compact


def apply_cited_synthesis(
    resolution: AssistantResolution,
    *,
    model: AssistantDraftModel,
    model_id: str,
) -> AssistantResolution:
    """Fill answer from citation excerpts. No-op when there are no citations."""
    if not resolution.citations:
        return replace(resolution, synthesis_status="skipped-no-citations")
    prompt = build_synthesis_prompt(
        intent=resolution.intent,
        citations=resolution.citations,
    )
    digest = prompt_hash(prompt)
    try:
        raw = model.complete(prompt, system=SYNTHESIS_SYSTEM)
        answer = parse_synthesis_payload(raw)
    except ValueError as exc:
        logger.warning("assistant synthesis rejected: %s", exc)
        return replace(
            resolution,
            prompt_hash=resolution.prompt_hash or digest,
            synthesis_status="rejected",
        )
    tools = tuple(dict.fromkeys((*resolution.tools, "corpus.synthesize")))
    return replace(
        resolution,
        answer=answer,
        prompt_hash=resolution.prompt_hash or digest,
        synthesis_status="applied",
        tools=tools,
        draft_model=resolution.draft_model or model_id,
    )
