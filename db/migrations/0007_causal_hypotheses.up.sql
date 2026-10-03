-- PUB-05 migration 0007 (UP): causal hypothesis normalization — the
-- causal_hypotheses table of the §11 minimum model. The W5 causal claim of
-- each hypothesis (hypotheses.causal document) is columnarized into one row
-- per hypothesis via db/mapping.py (causal_hypothesis_row): subjects,
-- relation, direction, status, uncertainty and the supporting-evidence
-- references (mapping only — the frozen sos.causal engine stays the
-- semantic authority).
-- SQLite-compatible DDL (Postgres dialect: JSON columns -> JSONB).

CREATE TABLE causal_hypotheses (
    id                  TEXT PRIMARY KEY,
    workspace_id        TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    hypothesis_id       TEXT NOT NULL REFERENCES hypotheses (id) ON DELETE CASCADE,
    cause_subject       TEXT,
    effect_subject      TEXT,
    relation_type       TEXT,
    direction           TEXT,
    rationale           TEXT,
    status              TEXT,
    uncertainty         TEXT,
    supporting_evidence TEXT,
    created_at          TEXT
);
CREATE INDEX idx_causal_hypotheses_workspace ON causal_hypotheses (workspace_id);
CREATE UNIQUE INDEX idx_causal_hypotheses_hypothesis ON causal_hypotheses (hypothesis_id);
