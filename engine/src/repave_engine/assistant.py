"""Governed assistant — intent to golden-path form. No LLM and no generate bypass."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlencode

from repave_engine.assistant_corpus import (
    CorpusDocument,
    corpus_allowed,
    excerpt_for,
    load_assistant_corpus,
    tokenize_intent,
)
from repave_engine.assistant_fts import open_fts_store, retrieve_corpus
from repave_engine.assistant_reads import AssistantReadHit, collect_assistant_reads
from repave_engine.blueprint import Blueprint, artifact_family, list_catalog_blueprints
from repave_engine.sql_store import SqlConnection
from repave_engine.v3_foundation import load_v3_foundation_config

_MAX_INTENT_CHARS = 2000
_MAX_MATCHES = 5
_MIN_SCORE = 8.0
_FAMILY_HINTS: dict[str, frozenset[str]] = {
    "terraform": frozenset(
        {"terraform", "module", "tf", "aws", "azure", "gcp", "vpc", "s3", "iam"}
    ),
    "ansible": frozenset({"ansible", "role", "playbook", "collection"}),
    "policy": frozenset({"policy", "opa", "checkov", "conftest", "guardrail"}),
    "helm": frozenset({"helm", "chart", "kubernetes", "k8s"}),
    "gitops": frozenset({"gitops", "argo", "flux", "argocd"}),
    "app": frozenset({"app", "service", "dockerfile", "application"}),
    "observability": frozenset({"dashboard", "monitor", "observability", "slo", "grafana"}),
    "api": frozenset({"openapi", "asyncapi", "api", "contract", "spectral"}),
    "data": frozenset({"migration", "alembic", "flyway", "atlas", "schema"}),
    "platform": frozenset({"github", "repo", "repository", "team"}),
}
_CLOUD_ALIASES = {
    "aws": "aws",
    "amazon": "aws",
    "azure": "azure",
    "gcp": "gcp",
    "google": "gcp",
}
_NAMED_RE = re.compile(
    r"\b(?:named|called|name)\s+([a-z][a-z0-9_-]{1,62})\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AssistantTool:
    tool_id: str
    kind: str
    description: str

    def to_public_dict(self) -> dict[str, str]:
        return {
            "id": self.tool_id,
            "kind": self.kind,
            "description": self.description,
        }


ASSISTANT_SERVICE_REGISTRY: tuple[AssistantTool, ...] = (
    AssistantTool(
        tool_id="catalog.blueprints",
        kind="read",
        description="Golden-path catalog names, families, and input fields",
    ),
    AssistantTool(
        tool_id="corpus.standards",
        kind="read",
        description="In-repo standards markdown under standards/",
    ),
    AssistantTool(
        tool_id="corpus.policy",
        kind="read",
        description="Policy pack narrative and catalog pack sources",
    ),
    AssistantTool(
        tool_id="catalog.draft",
        kind="read",
        description="Optional model JSON of catalog inputs; never generate or score gates",
    ),
    AssistantTool(
        tool_id="corpus.synthesize",
        kind="read",
        description="Optional model paraphrase of citation excerpts; never generate",
    ),
    AssistantTool(
        tool_id="catalog.artifacts",
        kind="read",
        description="Optional candidate files gated by the matched blueprint; never publish",
    ),
    AssistantTool(
        tool_id="fleet.reads",
        kind="read",
        description="Registered fleet repos the portal already lists",
    ),
    AssistantTool(
        tool_id="fleet.drift",
        kind="read",
        description="Pin drift estimates vs catalog (same as /platform/standards)",
    ),
    AssistantTool(
        tool_id="audit.history",
        kind="read",
        description="Recent generation gate outcomes from the audit sink",
    ),
)


@dataclass(frozen=True)
class AssistantCitation:
    source: str
    title: str
    excerpt: str

    def to_public_dict(self) -> dict[str, str]:
        return {"source": self.source, "title": self.title, "excerpt": self.excerpt}


@dataclass(frozen=True)
class AssistantMatch:
    blueprint: str
    description: str
    family: str
    score: float
    form_href: str
    citations: tuple[AssistantCitation, ...]
    suggested_inputs: dict[str, str]

    def to_public_dict(self) -> dict[str, object]:
        return {
            "blueprint": self.blueprint,
            "description": self.description,
            "family": self.family,
            "score": round(self.score, 2),
            "form_href": self.form_href,
            "citations": [item.to_public_dict() for item in self.citations],
            "suggested_inputs": dict(self.suggested_inputs),
        }


@dataclass(frozen=True)
class AssistantResolution:
    intent: str
    matches: tuple[AssistantMatch, ...]
    tools: tuple[str, ...]
    message: str
    citations: tuple[AssistantCitation, ...] = ()
    draft_model: str = ""
    prompt_hash: str = ""
    draft_status: str = ""
    answer: str = ""
    synthesis_status: str = ""
    artifact_status: str = ""
    artifact_gates: tuple[dict[str, object], ...] = ()
    artifact_files: tuple[object, ...] = ()
    reads: tuple[AssistantReadHit, ...] = ()

    def to_public_dict(self) -> dict[str, object]:
        files = []
        for item in self.artifact_files:
            to_public = getattr(item, "to_public_dict", None)
            files.append(to_public() if callable(to_public) else item)
        return {
            "intent": self.intent,
            "matches": [item.to_public_dict() for item in self.matches],
            "tools": list(self.tools),
            "message": self.message,
            "citations": [item.to_public_dict() for item in self.citations],
            "draft_model": self.draft_model,
            "prompt_hash": self.prompt_hash,
            "draft_status": self.draft_status,
            "answer": self.answer,
            "synthesis_status": self.synthesis_status,
            "artifact_status": self.artifact_status,
            "artifact_gates": [dict(item) for item in self.artifact_gates],
            "artifact_files": files,
            "reads": [item.to_public_dict() for item in self.reads],
        }


def is_assistant_enabled(repo_root: Path) -> bool:
    """True when v3.assistant.enabled is explicitly on."""
    return load_v3_foundation_config(repo_root).assistant_enabled


def blueprint_form_href(name: str, *, inputs: Mapping[str, str] | None = None) -> str:
    """Link to the golden-path form with allowlisted suggested inputs as query params."""
    params = [
        (key, value)
        for key, value in (inputs or {}).items()
        if key.isidentifier() and value and len(value) <= 200
    ]
    if not params:
        return f"/blueprints/{name}"
    return f"/blueprints/{name}?{urlencode(params)}"


def match_confirmed_blueprint(
    resolution: AssistantResolution, *, blueprint: str
) -> AssistantMatch | None:
    """Return the match the caller confirmed, or None if it was not suggested."""
    name = blueprint.strip()
    if not name:
        return None
    for match in resolution.matches:
        if match.blueprint == name:
            return match
    return None


def resolve_catalog_intent(
    repo_root: Path,
    *,
    intent: str,
    role: str | None = None,
    auth_enabled: bool = False,
    draft_model: object | None = None,
) -> AssistantResolution:
    """Match intent to catalog golden paths plus allowed corpus citations."""
    corpus: tuple[CorpusDocument, ...] = ()
    if corpus_allowed(role=role, auth_enabled=auth_enabled):
        corpus = load_assistant_corpus(repo_root)
    blueprints = list_catalog_blueprints(repo_root)
    retrieval = load_v3_foundation_config(repo_root).assistant_retrieval
    with open_fts_store(repo_root, retrieval=retrieval) as store:
        resolution = resolve_intent(
            intent,
            blueprints=blueprints,
            corpus=corpus,
            retrieval=retrieval,
            store=store,
        )
    reads, read_tools = collect_assistant_reads(
        repo_root,
        intent=intent,
        blueprints=blueprints,
        role=role,
        auth_enabled=auth_enabled,
    )
    resolution = replace(
        resolution,
        reads=reads,
        tools=tuple(dict.fromkeys((*resolution.tools, *read_tools))),
    )
    return _maybe_apply_draft(
        repo_root,
        resolution,
        blueprints=blueprints,
        draft_model=draft_model,
        acting_role=role,
    )


def _maybe_apply_draft(
    repo_root: Path,
    resolution: AssistantResolution,
    *,
    blueprints: Sequence[Blueprint],
    draft_model: object | None,
    acting_role: str | None,
) -> AssistantResolution:
    config = load_v3_foundation_config(repo_root)
    if not config.assistant_draft_enabled:
        return resolution
    from repave_engine.assistant_artifacts import apply_artifact_draft
    from repave_engine.assistant_draft import (
        AssistantDraftModel,
        apply_model_draft,
        load_draft_model_from_env,
    )
    from repave_engine.assistant_synthesis import apply_cited_synthesis

    model: AssistantDraftModel | None
    if draft_model is not None:
        model = draft_model  # type: ignore[assignment]
    else:
        model = load_draft_model_from_env(model=config.assistant_draft_model)
    if model is None:
        return replace(
            resolution,
            draft_status="skipped-missing-REPAVE_ASSISTANT_API_KEY",
        )
    model_id = config.assistant_draft_model or "gpt-4o-mini"
    updated = apply_model_draft(
        resolution,
        blueprints=blueprints,
        model=model,
        model_id=model_id,
    )
    updated = apply_cited_synthesis(updated, model=model, model_id=model_id)
    if config.assistant_artifacts_enabled:
        updated = apply_artifact_draft(
            updated,
            blueprints=blueprints,
            model=model,
            model_id=model_id,
            repo_root=repo_root,
        )
    _record_draft_audit(repo_root, updated, acting_role=acting_role)
    return updated


def _record_draft_audit(
    repo_root: Path,
    resolution: AssistantResolution,
    *,
    acting_role: str | None,
) -> None:
    from repave_engine.audit import AuditRecord, append_audit_record
    from repave_engine.auth_context import current_acting_user
    from repave_engine.settings import load_audit_config

    try:
        audit_cfg = load_audit_config(repo_root)
    except ValueError:
        return
    if audit_cfg is None or not audit_cfg.enabled:
        return
    match = resolution.matches[0] if resolution.matches else None
    append_audit_record(
        audit_cfg.file,
        AuditRecord(
            event="assistant_draft",
            blueprint_name=match.blueprint if match is not None else "",
            blueprint_version="",
            module_name="",
            dry_run=True,
            gates_outcome=(
                "passed"
                if resolution.artifact_status == "gated"
                else "failed"
                if resolution.artifact_status == "blocked"
                else "not-run"
            ),
            repository_url=None,
            acting_user=current_acting_user(),
            extra={
                "prompt_hash": resolution.prompt_hash,
                "draft_model": resolution.draft_model,
                "draft_status": resolution.draft_status,
                "synthesis_status": resolution.synthesis_status,
                "artifact_status": resolution.artifact_status,
                "role": acting_role or "",
            },
        ),
        repo_root=repo_root,
    )


def resolve_intent(
    intent: str,
    *,
    blueprints: Sequence[Blueprint],
    corpus: Sequence[CorpusDocument] = (),
    retrieval: str = "memory",
    store: SqlConnection | None = None,
) -> AssistantResolution:
    """Score catalog blueprints and corpus docs against a short intent string."""
    tools = (
        "catalog.blueprints",
        "corpus.standards",
        "corpus.policy",
        "corpus.blueprints",
    )
    cleaned = intent.strip()
    if len(cleaned) > _MAX_INTENT_CHARS:
        return AssistantResolution(
            intent=cleaned[:_MAX_INTENT_CHARS],
            matches=(),
            tools=tools,
            message=(
                f"Intent is longer than {_MAX_INTENT_CHARS} characters. "
                "Shorten the description and try again."
            ),
        )
    if not cleaned:
        return AssistantResolution(
            intent="",
            matches=(),
            tools=tools,
            message="Enter a short description of the golden path you need.",
        )

    tokens = tokenize_intent(cleaned)
    corpus_hits = retrieve_corpus(
        corpus,
        tokens=tokens,
        mode=retrieval,
        store=store,
    )
    citations = tuple(
        AssistantCitation(
            source=document.source,
            title=document.title,
            excerpt=excerpt_for(document, tokens=tokens),
        )
        for document in corpus_hits
    )
    scored: list[AssistantMatch] = []
    for blueprint in blueprints:
        score = _score_blueprint(blueprint, tokens=tokens, intent=cleaned.lower())
        if score < _MIN_SCORE:
            continue
        excerpt = blueprint.description.strip() or blueprint.name
        suggested = _suggested_inputs(cleaned, blueprint=blueprint)
        scored.append(
            AssistantMatch(
                blueprint=blueprint.name,
                description=blueprint.description,
                family=artifact_family(blueprint.artifact_type),
                score=score,
                form_href=blueprint_form_href(blueprint.name, inputs=suggested),
                citations=(
                    AssistantCitation(
                        source=f"catalog:{blueprint.name}",
                        title=blueprint.name,
                        excerpt=excerpt[:240],
                    ),
                    *_match_corpus_citations(
                        blueprint,
                        citations=citations,
                    ),
                ),
                suggested_inputs=suggested,
            )
        )
    scored.sort(key=lambda item: (-item.score, item.blueprint))
    matches = tuple(scored[:_MAX_MATCHES])
    if not matches and not citations:
        return AssistantResolution(
            intent=cleaned,
            matches=(),
            tools=tools,
            citations=(),
            message="No golden path matched. Browse Golden paths or try a family name "
            "(Terraform, Ansible, policy).",
        )
    message = ""
    if not matches:
        message = (
            "No golden path matched. Related standards and policy are cited below; "
            "browse Golden paths to pick a form."
        )
    return AssistantResolution(
        intent=cleaned,
        matches=matches,
        tools=tools,
        citations=citations,
        message=message,
    )


def _match_corpus_citations(
    blueprint: Blueprint,
    *,
    citations: tuple[AssistantCitation, ...],
) -> tuple[AssistantCitation, ...]:
    family = artifact_family(blueprint.artifact_type)
    needle = (blueprint.standard_source or "").lower()
    related: list[AssistantCitation] = []
    for citation in citations:
        source = citation.source.lower()
        if needle and needle in source:
            related.append(citation)
            continue
        if family and family in source:
            related.append(citation)
    return tuple(related[:2])


def _score_blueprint(
    blueprint: Blueprint,
    *,
    tokens: frozenset[str],
    intent: str,
) -> float:
    name = blueprint.name.lower()
    score = 0.0
    if name and name in intent:
        score += 40.0
    name_parts = tokenize_intent(name.replace("-", " "))
    score += 10.0 * len(tokens & name_parts)
    desc_tokens = tokenize_intent(blueprint.description)
    score += 2.0 * len(tokens & desc_tokens)
    family = artifact_family(blueprint.artifact_type)
    hints = _FAMILY_HINTS.get(family, frozenset())
    score += 8.0 * len(tokens & hints)
    type_parts = frozenset(blueprint.artifact_type.lower().split("-"))
    score += 5.0 * len(tokens & type_parts)
    return score


def _suggested_inputs(intent: str, *, blueprint: Blueprint) -> dict[str, str]:
    tokens = tokenize_intent(intent)
    suggested: dict[str, str] = {}
    named = _NAMED_RE.search(intent)
    cloud = next((_CLOUD_ALIASES[token] for token in tokens if token in _CLOUD_ALIASES), None)
    for field in blueprint.inputs:
        if field.name in {"cloud_provider", "provider"} and cloud is not None:
            if field.enum and cloud not in field.enum:
                continue
            suggested[field.name] = cloud
        if field.name in {"module_name", "name", "role_name"} and named is not None:
            suggested[field.name] = named.group(1).lower()
    return suggested
