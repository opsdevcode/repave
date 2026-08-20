-- Optional assistant FTS index (v3.assistant.retrieval: fts). Same allowlist as memory search.

CREATE TABLE IF NOT EXISTS assistant_corpus_chunks (
    source TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    kind TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (source, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_assistant_corpus_chunks_fts
    ON assistant_corpus_chunks
    USING GIN (to_tsvector('simple', body));
