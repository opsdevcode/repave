"""Governed assistant — intent to golden-path form. No LLM and no generate bypass."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from repave_engine.assistant_corpus import (
    CorpusDocument,
    corpus_allowed,
    excerpt_for,
    load_assistant_corpus,
    search_corpus,
    tokenize_intent,
)
from repave_engine.blueprint import Blueprint, artifact_family, list_catalog_blueprints
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
        tool_id="corpus.blueprints",
        kind="read",
        description="Blueprint README files in the catalog",
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

    def to_public_dict(self) -> dict[str, object]:
        return {
            "intent": self.intent,
            "matches": [item.to_public_dict() for item in self.matches],
            "tools": list(self.tools),
            "message": self.message,
            "citations": [item.to_public_dict() for item in self.citations],
        }


def is_assistant_enabled(repo_root: Path) -> bool:
    """True when v3.assistant.enabled is explicitly on."""
    return load_v3_foundation_config(repo_root).assistant_enabled


def resolve_catalog_intent(
    repo_root: Path,
    *,
    intent: str,
    role: str | None = None,
    auth_enabled: bool = False,
) -> AssistantResolution:
    """Match intent to catalog golden paths plus allowed corpus citations."""
    corpus: tuple[CorpusDocument, ...] = ()
    if corpus_allowed(role=role, auth_enabled=auth_enabled):
        corpus = load_assistant_corpus(repo_root)
    return resolve_intent(
        intent,
        blueprints=list_catalog_blueprints(repo_root),
        corpus=corpus,
    )


def resolve_intent(
    intent: str,
    *,
    blueprints: Sequence[Blueprint],
    corpus: Sequence[CorpusDocument] = (),
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
    corpus_hits = search_corpus(corpus, tokens=tokens)
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
        scored.append(
            AssistantMatch(
                blueprint=blueprint.name,
                description=blueprint.description,
                family=artifact_family(blueprint.artifact_type),
                score=score,
                form_href=f"/blueprints/{blueprint.name}",
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
                suggested_inputs=_suggested_inputs(cleaned, blueprint=blueprint),
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
