-- PUB-05 migration 0009 (UP): assurance result normalization — the
-- assurance_results table of the §11 minimum model. Each executed
-- assurance gate of an assurance run (the "gates" list of the checks
-- document) becomes one row via db/mapping.py
-- (assurance_result_rows / rows_to_gates); gate status uses the frozen W7
-- four-state vocabulary (PASS is never the default).
-- SQLite-compatible DDL (Postgres dialect: JSON columns -> JSONB).

CREATE TABLE assurance_results (
    id               TEXT PRIMARY KEY,
    workspace_id     TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    assurance_run_id TEXT NOT NULL REFERENCES assurance_runs (id) ON DELETE CASCADE,
    candidate_id     TEXT,
    position         INTEGER NOT NULL,
    gate_name        TEXT NOT NULL,
    gate_status      TEXT NOT NULL CHECK (gate_status IN ('PASS', 'FAIL', 'UNKNOWN', 'BLOCKED')),
    evidence_ids     TEXT,
    detail           TEXT,
    created_at       TEXT
);
CREATE INDEX idx_assurance_results_workspace ON assurance_results (workspace_id);
CREATE INDEX idx_assurance_results_run ON assurance_results (assurance_run_id);
