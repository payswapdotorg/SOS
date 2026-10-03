-- PUB-05 migration 0010 (UP): experiment event normalization — the
-- experiment_events table of the §11 minimum model. The experiment
-- lifecycle event log (the "events" list of the events document) becomes
-- one row per event via db/mapping.py
-- (experiment_event_rows / rows_to_events); position preserves log order.
-- SQLite-compatible DDL.

CREATE TABLE experiment_events (
    id            TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    experiment_id TEXT NOT NULL REFERENCES experiments (id) ON DELETE CASCADE,
    position      INTEGER NOT NULL,
    occurred_at   TEXT,
    event_type    TEXT NOT NULL,
    detail        TEXT,
    created_at    TEXT
);
CREATE INDEX idx_experiment_events_workspace ON experiment_events (workspace_id);
CREATE INDEX idx_experiment_events_experiment ON experiment_events (experiment_id);
