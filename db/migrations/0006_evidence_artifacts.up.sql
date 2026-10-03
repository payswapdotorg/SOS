-- PUB-05 migration 0006 (UP): evidence artifact metadata — the
-- evidence_artifacts table of the §11 minimum model. Metadata lives here
-- (DB); BYTES live in the artifact store (LOCAL FS / R2 — PUB-07, §12
-- layout) — never in the database (directive §12 / PUB-05 forbidden
-- "blobs in Postgres"). Projected from evidence payload artifactRef via
-- db/mapping.py (evidence_artifact_row).
-- SQLite-compatible DDL.

CREATE TABLE evidence_artifacts (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    evidence_id  TEXT NOT NULL REFERENCES evidence (id) ON DELETE CASCADE,
    system_id    TEXT,
    artifact_ref TEXT NOT NULL,
    created_at   TEXT
);
CREATE INDEX idx_evidence_artifacts_workspace ON evidence_artifacts (workspace_id);
CREATE UNIQUE INDEX idx_evidence_artifacts_evidence ON evidence_artifacts (evidence_id);
