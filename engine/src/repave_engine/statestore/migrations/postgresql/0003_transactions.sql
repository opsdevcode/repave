-- ADR 004 Phase 3: transactions with commit-time conflict detection.
--
-- Optimistic, not pessimistic. A transaction records the resources it touched and the
-- serial it read them at; conflicts are detected when it tries to commit. Holding locks
-- across a multi-minute plan would be worse than what Terraform does today.

CREATE TABLE IF NOT EXISTS state_transactions (
    tx_id                TEXT PRIMARY KEY,
    state_id             TEXT NOT NULL REFERENCES states(state_id) ON DELETE CASCADE,
    status               TEXT NOT NULL,
    author               TEXT NOT NULL DEFAULT '',
    operation            TEXT NOT NULL DEFAULT '',
    -- The version the client read before planning. NULL when the state was empty.
    base_version_id      TEXT,
    base_serial          INTEGER NOT NULL DEFAULT 0,
    -- Set on commit; lets a later transaction tell whether this one landed after it read.
    committed_serial     INTEGER,
    committed_version_id TEXT,
    detail               TEXT NOT NULL DEFAULT '',
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_state_transactions_state
    ON state_transactions(state_id, status);
CREATE INDEX IF NOT EXISTS idx_state_transactions_committed
    ON state_transactions(state_id, committed_serial);

-- The read and write set. `intent` separates them: only writes conflict with writes.
CREATE TABLE IF NOT EXISTS state_transaction_resources (
    tx_id   TEXT NOT NULL REFERENCES state_transactions(tx_id) ON DELETE CASCADE,
    address TEXT NOT NULL,
    intent  TEXT NOT NULL,
    action  TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (tx_id, address, intent)
);

CREATE INDEX IF NOT EXISTS idx_state_transaction_resources_address
    ON state_transaction_resources(address, intent);

-- Gate outcomes reported with a commit. A required gate that is missing or failing
-- blocks the commit, so policy and cost are enforcing rather than advisory.
CREATE TABLE IF NOT EXISTS state_transaction_gates (
    tx_id    TEXT NOT NULL REFERENCES state_transactions(tx_id) ON DELETE CASCADE,
    name     TEXT NOT NULL,
    passed   INTEGER NOT NULL,
    skipped  INTEGER NOT NULL DEFAULT 0,
    message  TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (tx_id, name)
);
