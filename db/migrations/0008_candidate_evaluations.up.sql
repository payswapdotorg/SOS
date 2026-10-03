-- PUB-05 migration 0008 (UP): candidate evaluation normalization — the
-- candidate_evaluations table of the §11 minimum model. The candidate
-- evaluation document (objectives + Pareto front; multi-objective, never a
-- single scalar — architecture invariant) decomposes into one row per
-- objective (record_kind='objective') and one row per Pareto-front point
-- (record_kind='pareto_point') via db/mapping.py
-- (candidate_evaluation_rows / rows_to_evaluation).
-- SQLite-compatible DDL (Postgres dialect: JSON columns -> JSONB).

CREATE TABLE candidate_evaluations (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    candidate_id    TEXT NOT NULL REFERENCES candidates (id) ON DELETE CASCADE,
    record_kind     TEXT NOT NULL CHECK (record_kind IN ('objective', 'pareto_point')),
    position        INTEGER NOT NULL,
    objective_name  TEXT,
    direction       TEXT,
    predicted_value REAL,
    uncertainty     TEXT,
    candidate_ref   TEXT,
    point_values    TEXT,
    created_at      TEXT
);
CREATE INDEX idx_candidate_evaluations_workspace ON candidate_evaluations (workspace_id);
CREATE INDEX idx_candidate_evaluations_candidate ON candidate_evaluations (candidate_id);
