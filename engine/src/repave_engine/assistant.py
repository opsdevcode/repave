"""Governed assistant — intent to golden-path form. No LLM and no generate bypass."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from repave_engine.blueprint import Blueprint, artifact_family, list_catalog_blueprints
from repave_engine.v3_foundation import load_v3_foundation_config

_MAX_INTENT_CHARS = 2000
_MAX_MATCHES = 5
_MIN_SCORE = 8.0
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "for",
        "in",
        "of",
        "on",
        "the",
        "to",
        "with",
        "want",
        "need",
        "generate",
        "create",
        "make",
        "please",
        "me",
        "new",
    }
)
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
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]{1,}")
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

    def to_public_dict(self) -> dict[str, object]:
        return {
            "intent": self.intent,
            "matches": [item.to_public_dict() for item in self.matches],
            "tools": list(self.tools),
            "message": self.message,
        }


def is_assistant_enabled(repo_root: Path) -> bool:
    """True when v3.assistant.enabled is explicitly on."""
    return load_v3_foundation_config(repo_root).assistant_enabled


def resolve_catalog_intent(repo_root: Path, *, intent: str) -> AssistantResolution:
    """Match intent to catalog golden paths. Does not call generate or an LLM."""
    return resolve_intent(intent, blueprints=list_catalog_blueprints(repo_root))


def resolve_intent(intent: str, *, blueprints: Sequence[Blueprint]) -> AssistantResolution:
    """Score catalog blueprints against a short intent string."""
    cleaned = intent.strip()
    if len(cleaned) > _MAX_INTENT_CHARS:
        return AssistantResolution(
            intent=cleaned[:_MAX_INTENT_CHARS],
            matches=(),
            tools=("catalog.blueprints",),
            message=(
                f"Intent is longer than {_MAX_INTENT_CHARS} characters. "
                "Shorten the description and try again."
            ),
        )
    if not cleaned:
        return AssistantResolution(
            intent="",
            matches=(),
            tools=("catalog.blueprints",),
            message="Enter a short description of the golden path you need.",
        )

    tokens = _tokenize(cleaned)
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
                ),
                suggested_inputs=_suggested_inputs(cleaned, blueprint=blueprint),
            )
        )
    scored.sort(key=lambda item: (-item.score, item.blueprint))
    matches = tuple(scored[:_MAX_MATCHES])
    if not matches:
        return AssistantResolution(
            intent=cleaned,
            matches=(),
            tools=("catalog.blueprints",),
            message="No golden path matched. Browse Golden paths or try a family name "
            "(Terraform, Ansible, policy).",
        )
    return AssistantResolution(
        intent=cleaned,
        matches=matches,
        tools=("catalog.blueprints",),
        message="",
    )


def _tokenize(intent: str) -> frozenset[str]:
    found = {match.group(0) for match in _TOKEN_RE.finditer(intent.lower())}
    return frozenset(token for token in found if token not in _STOPWORDS)


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
    name_parts = frozenset(part for part in name.split("-") if part and part not in _STOPWORDS)
    score += 10.0 * len(tokens & name_parts)
    desc_tokens = _tokenize(blueprint.description)
    score += 2.0 * len(tokens & desc_tokens)
    family = artifact_family(blueprint.artifact_type)
    hints = _FAMILY_HINTS.get(family, frozenset())
    score += 8.0 * len(tokens & hints)
    type_parts = frozenset(blueprint.artifact_type.lower().split("-"))
    score += 5.0 * len(tokens & type_parts)
    return score


def _suggested_inputs(intent: str, *, blueprint: Blueprint) -> dict[str, str]:
    tokens = _tokenize(intent)
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
