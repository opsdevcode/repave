-- ADR 004 Phase 2: normalized resource graph (SQLite mirror for local development).
-- JSON columns are TEXT here; PostgreSQL uses JSONB.

CREATE TABLE IF NOT EXISTS state_resources (
    resource_id    TEXT PRIMARY KEY,
    state_id       TEXT NOT NULL REFERENCES states(state_id) ON DELETE CASCADE,
    version_id     TEXT NOT NULL,
    address        TEXT NOT NULL,
    module         TEXT NOT NULL DEFAULT '',
    mode           TEXT NOT NULL,
    type           TEXT NOT NULL,
    name           TEXT NOT NULL,
    provider       TEXT NOT NULL DEFAULT '',
    instance_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE (state_id, address)
);

CREATE INDEX IF NOT EXISTS idx_state_resources_type ON state_resources(state_id, type);
CREATE INDEX IF NOT EXISTS idx_state_resources_mode ON state_resources(state_id, mode);

CREATE TABLE IF NOT EXISTS state_resource_instances (
    instance_id      TEXT PRIMARY KEY,
    resource_id      TEXT NOT NULL REFERENCES state_resources(resource_id) ON DELETE CASCADE,
    state_id         TEXT NOT NULL,
    address          TEXT NOT NULL,
    index_key        TEXT,
    schema_version   INTEGER NOT NULL DEFAULT 0,
    attributes       TEXT NOT NULL,
    redacted_keys    TEXT NOT NULL,
    UNIQUE (state_id, address)
);

CREATE INDEX IF NOT EXISTS idx_state_instances_resource
    ON state_resource_instances(resource_id);

CREATE TABLE IF NOT EXISTS state_edges (
    edge_id      TEXT PRIMARY KEY,
    state_id     TEXT NOT NULL REFERENCES states(state_id) ON DELETE CASCADE,
    from_address TEXT NOT NULL,
    to_address   TEXT NOT NULL,
    kind         TEXT NOT NULL,
    UNIQUE (state_id, from_address, to_address, kind)
);

CREATE INDEX IF NOT EXISTS idx_state_edges_from ON state_edges(state_id, from_address);
CREATE INDEX IF NOT EXISTS idx_state_edges_to ON state_edges(state_id, to_address);

CREATE TABLE IF NOT EXISTS state_provider_schemas (
    schema_key      TEXT PRIMARY KEY,
    provider        TEXT NOT NULL,
    version         TEXT NOT NULL DEFAULT '',
    sensitive_paths TEXT NOT NULL,
    fetched_at      TEXT NOT NULL
);
