-- PUB-01 migration 0001 (UP): core identity + mission tables.
-- SQLite-compatible DDL (Postgres strategy: TEXT->TEXT, INTEGER->BIGINT,
-- JSON columns -> JSONB, checks unchanged — see docs/deployment/database.md).

CREATE TABLE users (
    id          TEXT PRIMARY KEY,
    github_id   TEXT NOT NULL UNIQUE,
    login       TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE workspaces (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,
    is_demo     INTEGER NOT NULL DEFAULT 0 CHECK (is_demo IN (0, 1)),
    created_at  TEXT NOT NULL
);

CREATE TABLE workspace_members (
    workspace_id TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    user_id      TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role         TEXT NOT NULL CHECK (role IN ('owner', 'member')),
    created_at   TEXT NOT NULL,
    PRIMARY KEY (workspace_id, user_id)
);

CREATE TABLE missions (
    id                   TEXT PRIMARY KEY,
    workspace_id         TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    title                TEXT NOT NULL,
    status               TEXT NOT NULL,
    current_revision_id  TEXT,
    created_at           TEXT NOT NULL
);
CREATE INDEX idx_missions_workspace ON missions (workspace_id);

CREATE TABLE mission_revisions (
    id           TEXT PRIMARY KEY,
    mission_id   TEXT NOT NULL REFERENCES missions (id) ON DELETE CASCADE,
    revision     INTEGER NOT NULL,
    goals        TEXT NOT NULL,
    outcomes     TEXT NOT NULL,
    stakeholders TEXT NOT NULL,
    measures     TEXT NOT NULL,
    constraints  TEXT NOT NULL,
    preferences  TEXT NOT NULL,
    approval     TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX idx_mission_revisions_mission ON mission_revisions (mission_id);
