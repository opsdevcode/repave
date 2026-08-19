"""Read-only assistant corpus — standards, policy narrative, and blueprint READMEs."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from repave_engine.auth import ROLE_ADMIN, ROLE_GENERATOR, ROLE_VIEWER
from repave_engine.safe_paths import confined_join, trusted_path

_MAX_FILE_BYTES = 256_000
_MAX_HITS = 5
_MIN_SCORE = 4.0
_EXCERPT_CHARS = 240
_CORPUS_VIEW_ROLES = frozenset({ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN})
_POLICY_MARKDOWN = ("PACKS.md", "README.md")
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
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]{1,}")


def tokenize_intent(text: str) -> frozenset[str]:
    found = {match.group(0) for match in _TOKEN_RE.finditer(text.lower())}
    return frozenset(token for token in found if token not in _STOPWORDS)


@dataclass(frozen=True)
class CorpusDocument:
    source: str
    title: str
    text: str
    kind: str


def corpus_allowed(*, role: str | None, auth_enabled: bool) -> bool:
    """True when the caller may read the same catalog/standards the portal already shows."""
    if not auth_enabled:
        return True
    return (role or "") in _CORPUS_VIEW_ROLES


def load_assistant_corpus(repo_root: Path) -> tuple[CorpusDocument, ...]:
    """Load allowed markdown and pack-source labels. Skips engine, ops docs, and pack code."""
    root = trusted_path(repo_root)
    documents: list[CorpusDocument] = []
    documents.extend(_load_markdown_tree(root, relative="standards", kind="standards"))
    documents.extend(_load_policy_markdown(root))
    documents.extend(_load_blueprint_readmes(root))
    documents.extend(_load_pack_source_docs(root))
    return tuple(documents)


def search_corpus(
    documents: Sequence[CorpusDocument],
    *,
    tokens: frozenset[str],
    limit: int = _MAX_HITS,
) -> tuple[CorpusDocument, ...]:
    """Rank corpus docs by token overlap. Empty tokens yield no hits."""
    if not tokens:
        return ()
    scored: list[tuple[float, CorpusDocument]] = []
    for document in documents:
        score = _score_document(document, tokens=tokens)
        if score >= _MIN_SCORE:
            scored.append((score, document))
    scored.sort(key=lambda item: (-item[0], item[1].source))
    return tuple(document for _score, document in scored[:limit])


def excerpt_for(document: CorpusDocument, *, tokens: frozenset[str]) -> str:
    """Return a short excerpt preferring a line that contains an intent token."""
    text = document.text.strip()
    if not text:
        return document.title[:_EXCERPT_CHARS]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        lowered = line.lower()
        if any(token in lowered for token in tokens):
            return _clip(line)
    return _clip(lines[0] if lines else document.title)


def _score_document(document: CorpusDocument, *, tokens: frozenset[str]) -> float:
    title_tokens = tokenize_intent(document.title)
    body_tokens = tokenize_intent(document.text[:4000])
    path_tokens = tokenize_intent(document.source.replace("/", " ").replace(".", " "))
    score = 12.0 * len(tokens & title_tokens)
    score += 6.0 * len(tokens & path_tokens)
    score += 2.0 * len(tokens & body_tokens)
    return score


def _load_markdown_tree(root: Path, *, relative: str, kind: str) -> list[CorpusDocument]:
    base = root / relative
    if not base.is_dir():
        return []
    documents: list[CorpusDocument] = []
    for path in sorted(base.rglob("*.md")):
        loaded = _read_markdown(root, path, kind=kind)
        if loaded is not None:
            documents.append(loaded)
    return documents


def _load_policy_markdown(root: Path) -> list[CorpusDocument]:
    documents: list[CorpusDocument] = []
    policy_dir = root / "policy"
    if not policy_dir.is_dir():
        return documents
    for name in _POLICY_MARKDOWN:
        path = policy_dir / name
        loaded = _read_markdown(root, path, kind="policy")
        if loaded is not None:
            documents.append(loaded)
    return documents


def _load_blueprint_readmes(root: Path) -> list[CorpusDocument]:
    documents: list[CorpusDocument] = []
    blueprints = root / "blueprints"
    if not blueprints.is_dir():
        return documents
    for path in sorted(blueprints.glob("*/README.md")):
        loaded = _read_markdown(root, path, kind="blueprint")
        if loaded is not None:
            documents.append(loaded)
    return documents


def _load_pack_source_docs(root: Path) -> list[CorpusDocument]:
    catalog_path = root / "policy" / "catalog.json"
    if not catalog_path.is_file():
        return []
    from repave_engine.policy_catalog import load_policy_catalog

    try:
        catalog = load_policy_catalog(root)
    except (OSError, ValueError, FileNotFoundError):
        return []
    documents: list[CorpusDocument] = []
    for source in catalog.pack_sources:
        pack_id = source.get("id", "")
        if not pack_id:
            continue
        label = source.get("label", pack_id)
        description = source.get("description", "")
        documents.append(
            CorpusDocument(
                source=f"policy/catalog.json#{pack_id}",
                title=label,
                text=f"{label} {pack_id} {description} {source.get('default_profile', '')}",
                kind="policy",
            )
        )
    return documents


def _read_markdown(root: Path, path: Path, *, kind: str) -> CorpusDocument | None:
    if not path.is_file():
        return None
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        return None
    try:
        confined_join(root, *Path(relative).parts)
    except ValueError:
        return None
    size = path.stat().st_size
    if size > _MAX_FILE_BYTES:
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    title = _title_from_markdown(text) or path.stem.replace("-", " ")
    return CorpusDocument(source=relative, title=title, text=text, kind=kind)


def _title_from_markdown(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _clip(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) <= _EXCERPT_CHARS:
        return compact
    return compact[: _EXCERPT_CHARS - 1].rstrip() + "…"
