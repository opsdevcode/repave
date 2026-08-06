-- Config-derived edges from plan JSON `configuration` (ADR 004 decision 5 prep).
-- Recorded at preview; applied as replace_graph extra_edges on commit.

CREATE TABLE IF NOT EXISTS state_transaction_edges (
    tx_id         TEXT NOT NULL REFERENCES state_transactions(tx_id) ON DELETE CASCADE,
    from_address  TEXT NOT NULL,
    to_address    TEXT NOT NULL,
    kind          TEXT NOT NULL,
    PRIMARY KEY (tx_id, from_address, to_address, kind)
);

CREATE INDEX IF NOT EXISTS idx_state_transaction_edges_tx
    ON state_transaction_edges(tx_id);
