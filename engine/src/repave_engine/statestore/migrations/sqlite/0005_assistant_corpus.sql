-- Optional assistant FTS index (v3.assistant.retrieval: fts). Same allowlist as memory search.

CREATE VIRTUAL TABLE IF NOT EXISTS assistant_corpus_fts USING fts5(
    source UNINDEXED,
    title,
    body,
    kind UNINDEXED,
    tokenize = 'porter'
);
