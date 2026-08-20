"""Extractive corpus retrieval — in-process FTS5, optional Postgres when durability is set.

Adapted from opsdevcode/relay rag_ingestion / portal_assistant (chunk + FTS, no LLM).
Relay is the working model, not a runtime dependency. Default retrieval stays memory
token scoring in assistant_corpus.search_corpus.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from repave_engine.assistant_corpus import (
    CorpusDocument,
    search_corpus,
)
from repave_engine.sql_store import SqlConnection

logger = logging.getLogger(__name__)

RETRIEVAL_MEMORY = "memory"
RETRIEVAL_FTS = "fts"
ASSISTANT_RETRIEVAL_MODES = frozenset({RETRIEVAL_MEMORY, RETRIEVAL_FTS})

_CHUNK_CHARS = 800
_CHUNK_OVERLAP = 80
_MAX_HITS = 5


def parse_assistant_retrieval(raw: object) -> str:
    """Normalize v3.assistant.retrieval. Default memory."""
    if raw is None:
        return RETRIEVAL_MEMORY
    if not isinstance(raw, str):
        raise ValueError("v3.assistant.retrieval must be 'memory' or 'fts'")
    value = raw.strip().lower()
    if value not in ASSISTANT_RETRIEVAL_MODES:
        raise ValueError(
            "v3.assistant.retrieval must be 'memory' or 'fts' "
            f"(got {raw!r}). Set memory for tests, or fts for extractive FTS."
        )
    return value


def chunk_text(text: str) -> tuple[str, ...]:
    """Split markdown into overlapping excerpts (Relay-style heading/size chunks)."""
    stripped = text.strip()
    if not stripped:
        return ()
    sections = _split_headings(stripped)
    chunks: list[str] = []
    for section in sections:
        chunks.extend(_pack_section(section))
    return tuple(item for item in chunks if item)


def retrieve_corpus(
    documents: Sequence[CorpusDocument],
    *,
    tokens: frozenset[str],
    mode: str = RETRIEVAL_MEMORY,
    store: SqlConnection | None = None,
) -> tuple[CorpusDocument, ...]:
    """Rank corpus hits. fts uses store when present, else in-process SQLite FTS5."""
    if not tokens:
        return ()
    retrieval = parse_assistant_retrieval(mode)
    if retrieval == RETRIEVAL_MEMORY:
        return search_corpus(documents, tokens=tokens)
    if store is not None:
        try:
            hits = search_store_corpus(store, documents=documents, tokens=tokens)
            if hits:
                return hits
        except Exception as exc:
            logger.warning(
                "assistant store FTS failed (%s); using in-process FTS",
                exc,
            )
    return search_corpus_fts(documents, tokens=tokens)


def search_corpus_fts(
    documents: Sequence[CorpusDocument],
    *,
    tokens: frozenset[str],
    limit: int = _MAX_HITS,
) -> tuple[CorpusDocument, ...]:
    """Build a throwaway FTS5 index and return extractive chunk documents."""
    if not tokens or not documents:
        return ()
    query = _fts_or_query(tokens)
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE corpus USING fts5("
            "source UNINDEXED, title, body, kind UNINDEXED, tokenize = 'porter')"
        )
        _insert_chunks(conn.execute, documents)
        try:
            rows = conn.execute(
                "SELECT source, title, body, kind FROM corpus "
                "WHERE corpus MATCH ? ORDER BY bm25(corpus) LIMIT ?",
                (query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return search_corpus(documents, tokens=tokens, limit=limit)
    finally:
        conn.close()
    return tuple(
        CorpusDocument(source=row[0], title=row[1], text=row[2], kind=row[3]) for row in rows
    )


def search_store_corpus(
    store: SqlConnection,
    *,
    documents: Sequence[CorpusDocument],
    tokens: frozenset[str],
    limit: int = _MAX_HITS,
) -> tuple[CorpusDocument, ...]:
    """Replace stored chunks then rank. Empty when the schema is missing."""
    if not tokens:
        return ()
    index_corpus_chunks(store, documents)
    return search_indexed_corpus(store, tokens=tokens, limit=limit)


def index_corpus_chunks(store: SqlConnection, documents: Sequence[CorpusDocument]) -> None:
    if store.dialect == "postgresql":
        store.execute("DELETE FROM assistant_corpus_chunks")
        for document in documents:
            for index, body in enumerate(chunk_text(document.text) or (document.text,)):
                store.execute(
                    "INSERT INTO assistant_corpus_chunks "
                    "(source, chunk_index, title, kind, body) VALUES (?, ?, ?, ?, ?)",
                    (document.source, index, document.title, document.kind, body),
                )
        store.commit()
        return
    store.execute("DELETE FROM assistant_corpus_fts")
    for document in documents:
        for body in chunk_text(document.text) or (document.text,):
            store.execute(
                "INSERT INTO assistant_corpus_fts (source, title, body, kind) VALUES (?, ?, ?, ?)",
                (document.source, document.title, body, document.kind),
            )
    store.commit()


def search_indexed_corpus(
    store: SqlConnection,
    *,
    tokens: frozenset[str],
    limit: int = _MAX_HITS,
) -> tuple[CorpusDocument, ...]:
    query = _fts_or_query(tokens)
    if store.dialect == "postgresql":
        phrase = " ".join(sorted(tokens))
        rows = store.execute(
            "SELECT source, title, body, kind FROM assistant_corpus_chunks, "
            "plainto_tsquery('simple', ?) AS query "
            "WHERE to_tsvector('simple', body) @@ query "
            "ORDER BY ts_rank(to_tsvector('simple', body), query) DESC LIMIT ?",
            (phrase, limit),
        ).fetchall()
        return tuple(_row_document(row) for row in rows)
    rows = store.execute(
        "SELECT source, title, body, kind FROM assistant_corpus_fts "
        "WHERE assistant_corpus_fts MATCH ? ORDER BY bm25(assistant_corpus_fts) LIMIT ?",
        (query, limit),
    ).fetchall()
    return tuple(_row_document(row) for row in rows)


@contextmanager
def open_fts_store(repo_root: Path, *, retrieval: str) -> Iterator[SqlConnection | None]:
    """Postgres durability connection when retrieval is fts; otherwise None."""
    if parse_assistant_retrieval(retrieval) != RETRIEVAL_FTS:
        yield None
        return
    from repave_engine.durability_store import load_durability_store_settings
    from repave_engine.sql_store import connect

    settings = load_durability_store_settings(repo_root)
    if settings is None or settings.database.dialect != "postgresql":
        yield None
        return
    try:
        conn = connect(settings.database)
    except Exception as exc:
        logger.warning("assistant FTS skipped postgres (%s)", exc)
        yield None
        return
    try:
        yield conn
    finally:
        conn.close()


def _row_document(row: object) -> CorpusDocument:
    mapping = row if isinstance(row, dict) else None
    if mapping is not None:
        return CorpusDocument(
            source=str(mapping["source"]),
            title=str(mapping["title"]),
            text=str(mapping["body"]),
            kind=str(mapping["kind"]),
        )
    sequence: tuple[object, ...] = tuple(row)  # type: ignore[arg-type]
    return CorpusDocument(
        source=str(sequence[0]),
        title=str(sequence[1]),
        text=str(sequence[2]),
        kind=str(sequence[3]),
    )


def _insert_chunks(
    execute: Callable[..., object],
    documents: Sequence[CorpusDocument],
) -> None:
    for document in documents:
        for body in chunk_text(document.text) or (document.text,):
            execute(
                "INSERT INTO corpus (source, title, body, kind) VALUES (?, ?, ?, ?)",
                (document.source, document.title, body, document.kind),
            )


def _fts_or_query(tokens: frozenset[str]) -> str:
    parts: list[str] = []
    for token in sorted(tokens):
        escaped = token.replace('"', '""')
        parts.append(f'"{escaped}"')
    return " OR ".join(parts)


def _split_headings(text: str) -> tuple[str, ...]:
    parts: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("## ") and current:
            parts.append("\n".join(current).strip())
            current = [line]
            continue
        current.append(line)
    if current:
        parts.append("\n".join(current).strip())
    return tuple(part for part in parts if part)


def _pack_section(section: str) -> list[str]:
    if len(section) <= _CHUNK_CHARS:
        return [section]
    packed: list[str] = []
    start = 0
    length = len(section)
    while start < length:
        end = min(start + _CHUNK_CHARS, length)
        if end < length:
            boundary = section.rfind("\n", start, end)
            if boundary > start + _CHUNK_CHARS // 2:
                end = boundary
        packed.append(section[start:end].strip())
        if end >= length:
            break
        start = max(end - _CHUNK_OVERLAP, start + 1)
    return [item for item in packed if item]
