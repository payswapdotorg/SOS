-- PUB-05 migration 0011 (UP): execution record normalization — the
-- execution_requests + execution_receipts tables of the §11 minimum model.
-- The governed request identity (provider, request hash, experiment
-- binding) becomes an execution_requests row; the W11 receipt (outcome
-- truth state VERBATIM, demo flag, provenance, side-effect and rollback
-- references) becomes a columnar execution_receipts row via db/mapping.py
-- (execution_request_row / execution_receipt_row / rows_to_receipt).
-- Outcome states use the frozen six-state vocabulary; receipts from the
-- DemoProvider keep demo=1 (never claim a real deployment).
-- SQLite-compatible DDL (Postgres dialect: JSON columns -> JSONB).

CREATE TABLE execution_requests (
    id            TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    execution_id  TEXT NOT NULL REFERENCES executions (id) ON DELETE CASCADE,
    experiment_id TEXT,
    provider      TEXT NOT NULL CHECK (provider IN ('demo', 'apify')),
    request_hash  TEXT NOT NULL,
    created_at    TEXT
);
CREATE INDEX idx_execution_requests_workspace ON execution_requests (workspace_id);
CREATE UNIQUE INDEX idx_execution_requests_execution ON execution_requests (execution_id);

CREATE TABLE execution_receipts (
    id                  TEXT PRIMARY KEY,
    workspace_id        TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    execution_id        TEXT NOT NULL REFERENCES executions (id) ON DELETE CASCADE,
    receipt_id          TEXT,
    request_id          TEXT,
    provider_id         TEXT,
    action_scope        TEXT,
    lifecycle           TEXT,
    outcome_state       TEXT CHECK (outcome_state IN
        ('SUCCESS', 'EMPTY', 'FAILED', 'UNKNOWN', 'UNSUPPORTED', 'UNAVAILABLE')),
    outcome_value       TEXT,
    outcome_detail      TEXT,
    w9_decision_id      TEXT,
    w7_assurance_id     TEXT,
    source_revision     TEXT,
    provenance_revision TEXT,
    base_graph_id       TEXT,
    base_graph_revision TEXT,
    environment         TEXT,
    started_at          TEXT,
    finished_at         TEXT,
    side_effects        TEXT,
    stdout_ref          TEXT,
    stderr_ref          TEXT,
    log_ref             TEXT,
    changed_revisions   TEXT,
    rollback_reference  TEXT,
    demo                INTEGER CHECK (demo IN (0, 1)),
    created_at          TEXT
);
CREATE INDEX idx_execution_receipts_workspace ON execution_receipts (workspace_id);
CREATE UNIQUE INDEX idx_execution_receipts_execution ON execution_receipts (execution_id);
