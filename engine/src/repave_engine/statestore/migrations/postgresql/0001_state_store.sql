-- ADR 004 Phase 1: authoritative state store.
-- The blob is the source of truth; everything derived from it is an index.

CREATE TABLE IF NOT EXISTS state_tenants (
    tenant_id    TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS states (
    state_id           TEXT PRIMARY KEY,
    tenant_id          TEXT NOT NULL REFERENCES state_tenants(tenant_id) ON DELETE CASCADE,
    name               TEXT NOT NULL,
    lineage            TEXT,
    serial             BIGINT NOT NULL DEFAULT 0,
    current_version_id TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    UNIQUE (tenant_id, name)
);

-- Immutable history. One row per accepted write; blob_sha256 is over the
-- PLAINTEXT bytes so byte-exact export can be verified after decryption.
CREATE TABLE IF NOT EXISTS state_versions (
    version_id        TEXT PRIMARY KEY,
    state_id          TEXT NOT NULL REFERENCES states(state_id) ON DELETE CASCADE,
    serial            BIGINT NOT NULL,
    lineage           TEXT NOT NULL,
    terraform_version TEXT NOT NULL,
    blob              BYTEA NOT NULL,
    blob_sha256       TEXT NOT NULL,
    blob_size         INTEGER NOT NULL,
    encryption        TEXT NOT NULL,
    key_id            TEXT,
    author            TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    UNIQUE (state_id, serial)
);

CREATE INDEX IF NOT EXISTS idx_state_versions_state_created
    ON state_versions(state_id, created_at DESC);

-- Whole-state lock, matching the Terraform http backend LOCK/UNLOCK protocol.
-- Resource-level concurrency is optimistic and lives in the transactions table.
CREATE TABLE IF NOT EXISTS state_locks (
    state_id   TEXT PRIMARY KEY REFERENCES states(state_id) ON DELETE CASCADE,
    lock_id    TEXT NOT NULL,
    who        TEXT NOT NULL,
    operation  TEXT NOT NULL,
    info       TEXT NOT NULL,
    version    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
