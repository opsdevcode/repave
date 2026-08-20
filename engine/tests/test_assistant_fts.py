from __future__ import annotations

from pathlib import Path

import pytest

from helpers import make_blueprint
from repave_engine.assistant import resolve_intent
from repave_engine.assistant_corpus import CorpusDocument, load_assistant_corpus
from repave_engine.assistant_fts import (
    RETRIEVAL_FTS,
    chunk_text,
    index_corpus_chunks,
    parse_assistant_retrieval,
    retrieve_corpus,
    search_corpus_fts,
    search_indexed_corpus,
)
from repave_engine.blueprint import InputField
from repave_engine.sql_store import DatabaseConfig, connect
from repave_engine.statestore.migrate import apply_migrations
from repave_engine.v3_foundation import load_v3_foundation_config


def test_parse_assistant_retrieval_rejects_unknown() -> None:
    with pytest.raises(ValueError, match=r"v3\.assistant\.retrieval"):
        parse_assistant_retrieval("hybrid")


def test_chunk_text_splits_long_markdown() -> None:
    body = "## One\n" + ("word " * 400) + "\n## Two\nshort"
    chunks = chunk_text(body)
    assert len(chunks) >= 2
    assert any("One" in chunk for chunk in chunks)


def test_search_corpus_fts_returns_extractive_chunk(tmp_path: Path) -> None:
    documents = (
        CorpusDocument(
            source="standards/terraform.md",
            title="Terraform layout",
            text="Terraform modules live under modules/ and use a standard layout.",
            kind="standards",
        ),
        CorpusDocument(
            source="policy/PACKS.md",
            title="Packs",
            text="Policy packs are unrelated to networking overlays.",
            kind="policy",
        ),
    )
    hits = search_corpus_fts(
        documents,
        tokens=frozenset({"terraform", "module", "layout"}),
    )
    assert hits
    assert hits[0].source == "standards/terraform.md"
    assert "layout" in hits[0].text.lower()


def test_retrieve_corpus_fts_matches_memory_sources(repo_root: Path) -> None:
    documents = load_assistant_corpus(repo_root)
    tokens = frozenset({"terraform", "module", "layout"})
    memory = retrieve_corpus(documents, tokens=tokens, mode="memory")
    fts = retrieve_corpus(documents, tokens=tokens, mode=RETRIEVAL_FTS)
    assert memory
    assert fts
    assert any(item.source.startswith("standards/") for item in fts)


def test_sqlite_store_fts_roundtrip(tmp_path: Path) -> None:
    documents = (
        CorpusDocument(
            source="standards/terraform.md",
            title="Terraform",
            text="Use a terraform module layout for vpc-core.",
            kind="standards",
        ),
    )
    with connect(DatabaseConfig(dialect="sqlite", sqlite_path=tmp_path / "state.db")) as conn:
        apply_migrations(conn)
        index_corpus_chunks(conn, documents)
        hits = search_indexed_corpus(
            conn,
            tokens=frozenset({"terraform", "vpc-core"}),
        )
    assert hits
    assert hits[0].source == "standards/terraform.md"


def test_resolve_intent_fts_still_ranks_catalog(tmp_path: Path) -> None:
    terraform = make_blueprint(
        tmp_path,
        name="terraform-module-generic",
        artifact_type="terraform-module",
        inputs=(
            InputField(name="module_name", type="string", required=True),
            InputField(
                name="cloud_provider",
                type="string",
                required=True,
                enum=("aws", "azure", "gcp"),
            ),
        ),
    )
    corpus = (
        CorpusDocument(
            source="standards/terraform.md",
            title="Terraform layout",
            text="Terraform module layout for aws vpc-core.",
            kind="standards",
        ),
    )
    result = resolve_intent(
        "generate a terraform module named vpc-core for aws",
        blueprints=(terraform,),
        corpus=corpus,
        retrieval=RETRIEVAL_FTS,
    )
    assert result.matches
    assert result.matches[0].blueprint == "terraform-module-generic"
    assert result.citations
    assert result.citations[0].source == "standards/terraform.md"


def test_assistant_retrieval_config(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\n"
        "output:\n  github_org: acme\n  modules_root: ../mods\n"
        "v3:\n  enabled: true\n  assistant:\n    enabled: true\n    retrieval: fts\n",
        encoding="utf-8",
    )
    config = load_v3_foundation_config(tmp_path)
    assert config.assistant_retrieval == "fts"
