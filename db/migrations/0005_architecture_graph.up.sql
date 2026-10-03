-- PUB-05 migration 0005 (UP): architecture graph normalization — the
-- architecture_nodes/architecture_edges tables of the §11 minimum model.
-- system_revisions.graph (the wire document) decomposes into these rows via
-- db/mapping.py (graph_node_rows/graph_edge_rows); (system_revision_id,
-- node_key/edge_key) is unique per revision (graph node ids repeat across
-- revisions of the same system); position preserves document order; the
-- workspace_id column carries the tenant directly (adapter-level scoping).
-- SQLite-compatible DDL (Postgres dialect: JSON columns -> JSONB).

CREATE TABLE architecture_nodes (
    id                 TEXT PRIMARY KEY,
    workspace_id       TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    system_id          TEXT NOT NULL REFERENCES systems (id) ON DELETE CASCADE,
    system_revision_id TEXT NOT NULL REFERENCES system_revisions (id) ON DELETE CASCADE,
    graph_id           TEXT,
    graph_version      INTEGER,
    node_key           TEXT NOT NULL,
    node_type          TEXT NOT NULL,
    name               TEXT NOT NULL,
    position           INTEGER NOT NULL,
    attributes         TEXT NOT NULL,
    uncertainty        TEXT,
    created_at         TEXT NOT NULL
);
CREATE INDEX idx_architecture_nodes_workspace ON architecture_nodes (workspace_id);
CREATE INDEX idx_architecture_nodes_system ON architecture_nodes (system_id);
CREATE INDEX idx_architecture_nodes_revision ON architecture_nodes (system_revision_id);
CREATE UNIQUE INDEX idx_architecture_nodes_key
    ON architecture_nodes (system_revision_id, node_key);

CREATE TABLE architecture_edges (
    id                 TEXT PRIMARY KEY,
    workspace_id       TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    system_id          TEXT NOT NULL REFERENCES systems (id) ON DELETE CASCADE,
    system_revision_id TEXT NOT NULL REFERENCES system_revisions (id) ON DELETE CASCADE,
    graph_id           TEXT,
    graph_version      INTEGER,
    edge_key           TEXT NOT NULL,
    edge_type          TEXT NOT NULL,
    source_key         TEXT NOT NULL,
    target_key         TEXT NOT NULL,
    position           INTEGER NOT NULL,
    attributes         TEXT NOT NULL,
    uncertainty        TEXT,
    created_at         TEXT NOT NULL
);
CREATE INDEX idx_architecture_edges_workspace ON architecture_edges (workspace_id);
CREATE INDEX idx_architecture_edges_system ON architecture_edges (system_id);
CREATE INDEX idx_architecture_edges_revision ON architecture_edges (system_revision_id);
CREATE UNIQUE INDEX idx_architecture_edges_key
    ON architecture_edges (system_revision_id, edge_key);

CREATE TABLE architecture_boundary_contracts (
    id                 TEXT PRIMARY KEY,
    workspace_id       TEXT NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    system_id          TEXT NOT NULL REFERENCES systems (id) ON DELETE CASCADE,
    system_revision_id TEXT NOT NULL REFERENCES system_revisions (id) ON DELETE CASCADE,
    graph_id           TEXT,
    graph_version      INTEGER,
    contract_key       TEXT NOT NULL,
    interface_node_id  TEXT,
    contract           TEXT,
    invariants         TEXT,
    position           INTEGER NOT NULL,
    created_at         TEXT NOT NULL
);
CREATE INDEX idx_architecture_boundary_contracts_workspace ON architecture_boundary_contracts (workspace_id);
CREATE INDEX idx_architecture_boundary_contracts_revision ON architecture_boundary_contracts (system_revision_id);
CREATE UNIQUE INDEX idx_architecture_boundary_contracts_key
    ON architecture_boundary_contracts (system_revision_id, contract_key);
