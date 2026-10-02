-- PUB-01 migration 0002 (UP): system/graph/evidence/hypothesis/candidate/
-- assurance/decision/authorization/experiment/execution/learning/memory/
-- job/audit tables (the PUB-01 API-serving entity set; PUB-05 finalizes the
-- full relational mapping).
-- SQLite-compatible DDL (Postgres strategy: JSON columns -> JSONB).

CREATE TABLE systems (
    id                   TEXT PRIMARY KEY,
    workspace_id         TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    name                 TEXT NOT NULL,
    mode                 TEXT NOT NULL CHECK (mode IN ('greenfield', 'brownfield')),
    current_revision_id  TEXT,
    created_at           TEXT NOT NULL
);
CREATE INDEX idx_systems_workspace ON systems (workspace_id);

CREATE TABLE system_revisions (
    id             TEXT PRIMARY KEY,
    system_id      TEXT NOT NULL REFERENCES systems (id) ON DELETE CASCADE,
    revision       INTEGER NOT NULL,
    state_summary  TEXT NOT NULL,
    uncertainty    TEXT NOT NULL,
    source_ref     TEXT,
    recovery       TEXT,
    graph          TEXT NOT NULL,
    created_at     TEXT NOT NULL
);
CREATE INDEX idx_system_revisions_system ON system_revisions (system_id);

CREATE TABLE evidence (
    id                   TEXT PRIMARY KEY,
    workspace_id         TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    system_id            TEXT REFERENCES systems (id) ON DELETE SET NULL,
    kind                 TEXT NOT NULL,
    status               TEXT NOT NULL CHECK (status IN
        ('SUCCESS', 'EMPTY', 'FAILED', 'UNKNOWN', 'UNSUPPORTED', 'UNAVAILABLE')),
    provenance           TEXT NOT NULL,
    timestamp            TEXT,
    source_revision      TEXT,
    related_system_state TEXT,
    confidence           REAL,
    artifact_ref         TEXT,
    created_at           TEXT NOT NULL
);
CREATE INDEX idx_evidence_workspace ON evidence (workspace_id);
CREATE INDEX idx_evidence_system ON evidence (system_id);

CREATE TABLE hypotheses (
    id            TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    statement     TEXT NOT NULL,
    causal        TEXT NOT NULL,
    evidence_refs TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN
        ('SUCCESS', 'EMPTY', 'FAILED', 'UNKNOWN', 'UNSUPPORTED', 'UNAVAILABLE')),
    created_at    TEXT NOT NULL
);
CREATE INDEX idx_hypotheses_workspace ON hypotheses (workspace_id);

CREATE TABLE candidates (
    id                   TEXT PRIMARY KEY,
    workspace_id         TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    name                 TEXT NOT NULL,
    subgraph_replacement TEXT NOT NULL,
    effects              TEXT NOT NULL,
    costs                TEXT NOT NULL,
    risks                TEXT NOT NULL,
    constraints          TEXT NOT NULL,
    evidence_refs        TEXT NOT NULL,
    reversibility        TEXT NOT NULL,
    evaluation           TEXT NOT NULL,
    created_at           TEXT NOT NULL
);
CREATE INDEX idx_candidates_workspace ON candidates (workspace_id);

CREATE TABLE assurance_runs (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    candidate_id TEXT NOT NULL,
    checks       TEXT NOT NULL,
    verdict      TEXT NOT NULL CHECK (verdict IN ('PASS', 'FAIL', 'UNKNOWN', 'BLOCKED')),
    created_at   TEXT NOT NULL
);
CREATE INDEX idx_assurance_runs_workspace ON assurance_runs (workspace_id);
CREATE INDEX idx_assurance_runs_candidate ON assurance_runs (candidate_id);

CREATE TABLE decisions (
    id                 TEXT PRIMARY KEY,
    workspace_id       TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    action             TEXT NOT NULL CHECK (action IN
        ('ACT', 'EXPERIMENT', 'GATHER_EVIDENCE', 'ASK', 'REJECT', 'ROLLBACK')),
    rationale          TEXT NOT NULL,
    evidence_refs      TEXT NOT NULL,
    authority_snapshot TEXT NOT NULL,
    expected_impact    TEXT NOT NULL,
    risk               REAL NOT NULL CHECK (risk >= 0 AND risk <= 1),
    blast_radius       TEXT NOT NULL,
    reversibility      TEXT NOT NULL,
    required_approvals TEXT NOT NULL,
    ask_payload        TEXT,
    created_at         TEXT NOT NULL
);
CREATE INDEX idx_decisions_workspace ON decisions (workspace_id);

CREATE TABLE authorizations (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    decision_id  TEXT REFERENCES decisions (id) ON DELETE SET NULL,
    principal    TEXT NOT NULL,
    scope        TEXT NOT NULL,
    decision     TEXT NOT NULL CHECK (decision IN ('granted', 'denied')),
    created_at   TEXT NOT NULL
);
CREATE INDEX idx_authorizations_workspace ON authorizations (workspace_id);

CREATE TABLE experiments (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    candidate_id TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN
        ('planned', 'ready', 'running', 'stopped', 'completed', 'failed',
         'rolled_back')),
    events       TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX idx_experiments_workspace ON experiments (workspace_id);
CREATE INDEX idx_experiments_candidate ON experiments (candidate_id);

CREATE TABLE executions (
    id            TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    experiment_id TEXT REFERENCES experiments (id) ON DELETE SET NULL,
    provider      TEXT NOT NULL CHECK (provider IN ('demo', 'apify')),
    request_hash  TEXT NOT NULL,
    receipt       TEXT,
    artifact_refs TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN
        ('SUCCESS', 'EMPTY', 'FAILED', 'UNKNOWN', 'UNSUPPORTED', 'UNAVAILABLE')),
    created_at    TEXT NOT NULL
);
CREATE INDEX idx_executions_workspace ON executions (workspace_id);
CREATE INDEX idx_executions_experiment ON executions (experiment_id);

CREATE TABLE learning_records (
    id                TEXT PRIMARY KEY,
    workspace_id      TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    context           TEXT NOT NULL,
    candidate         TEXT NOT NULL,
    predicted_effects TEXT NOT NULL,
    actual_effects    TEXT NOT NULL,
    uncertainty       TEXT NOT NULL,
    verdict           TEXT NOT NULL,
    lessons           TEXT NOT NULL,
    created_at        TEXT NOT NULL
);
CREATE INDEX idx_learning_records_workspace ON learning_records (workspace_id);

CREATE TABLE memory_entries (
    id                TEXT PRIMARY KEY,
    workspace_id      TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    context           TEXT NOT NULL,
    candidate         TEXT NOT NULL,
    predicted_effects TEXT NOT NULL,
    actual_effects    TEXT NOT NULL,
    uncertainty       TEXT NOT NULL,
    verdict           TEXT NOT NULL,
    lessons           TEXT NOT NULL,
    created_at        TEXT NOT NULL
);
CREATE INDEX idx_memory_entries_workspace ON memory_entries (workspace_id);

CREATE TABLE jobs (
    id                 TEXT PRIMARY KEY,
    tenant_id          TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    type               TEXT NOT NULL,
    requested_by       TEXT NOT NULL,
    authority_snapshot TEXT NOT NULL,
    input_hash         TEXT NOT NULL,
    source_revision    TEXT NOT NULL,
    provider           TEXT NOT NULL,
    status             TEXT NOT NULL CHECK (status IN
        ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    started_at         TEXT,
    completed_at       TEXT,
    receipt            TEXT,
    artifact_refs      TEXT NOT NULL,
    error_state        TEXT,
    idempotency_key    TEXT,
    created_at         TEXT NOT NULL
);
CREATE INDEX idx_jobs_tenant ON jobs (tenant_id);
CREATE UNIQUE INDEX idx_jobs_idempotency ON jobs (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE TABLE audit_events (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT REFERENCES workspaces (id) ON DELETE CASCADE,
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    target      TEXT NOT NULL,
    meta        TEXT NOT NULL,
    ts          TEXT NOT NULL
);
CREATE INDEX idx_audit_events_tenant ON audit_events (tenant_id);
