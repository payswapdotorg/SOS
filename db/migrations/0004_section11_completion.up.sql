-- PUB-05 migration 0004 (UP): §11 minimum-model completion — the tables of
-- the directive §11 relational model not yet created by PUB-01 (value model,
-- context, provider events). Schema-forward per §11 ("every entity needs
-- immutable IDs and appropriate revision/provenance fields"); the wire
-- traffic for these entities is wired by later items (value-model journey
-- editing and provider-event callbacks are PUB-08/PUB-09 scope) — the
-- tables land now so the §11 minimum is complete and the same migration
-- set runs on SQLite AND PostgreSQL.
-- SQLite-compatible DDL (Postgres dialect: JSON columns -> JSONB, per
-- db/runner.py translate + db/mapping.py JSON_COLUMNS).

CREATE TABLE value_models (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX idx_value_models_workspace ON value_models (workspace_id);

CREATE TABLE value_model_revisions (
    id             TEXT PRIMARY KEY,
    value_model_id TEXT NOT NULL REFERENCES value_models (id) ON DELETE CASCADE,
    revision       INTEGER NOT NULL,
    objectives     TEXT NOT NULL,
    constraints    TEXT NOT NULL,
    tradeoffs      TEXT NOT NULL,
    signals        TEXT NOT NULL,
    created_at     TEXT NOT NULL
);
CREATE INDEX idx_value_model_revisions_model ON value_model_revisions (value_model_id);

CREATE TABLE contexts (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    conditions   TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX idx_contexts_workspace ON contexts (workspace_id);

CREATE TABLE provider_events (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    provider     TEXT NOT NULL,
    event_kind   TEXT NOT NULL,
    payload      TEXT NOT NULL,
    occurred_at  TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX idx_provider_events_workspace ON provider_events (workspace_id);
