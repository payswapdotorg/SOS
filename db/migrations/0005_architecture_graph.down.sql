-- PUB-05 migration 0005 (DOWN): reverse 0005 exactly.

DROP INDEX IF EXISTS idx_architecture_boundary_contracts_key;
DROP INDEX IF EXISTS idx_architecture_boundary_contracts_revision;
DROP INDEX IF EXISTS idx_architecture_boundary_contracts_workspace;
DROP TABLE IF EXISTS architecture_boundary_contracts;

DROP INDEX IF EXISTS idx_architecture_edges_key;
DROP INDEX IF EXISTS idx_architecture_edges_revision;
DROP INDEX IF EXISTS idx_architecture_edges_system;
DROP INDEX IF EXISTS idx_architecture_edges_workspace;
DROP TABLE IF EXISTS architecture_edges;
DROP INDEX IF EXISTS idx_architecture_nodes_key;
DROP INDEX IF EXISTS idx_architecture_nodes_revision;
DROP INDEX IF EXISTS idx_architecture_nodes_system;
DROP INDEX IF EXISTS idx_architecture_nodes_workspace;
DROP TABLE IF EXISTS architecture_nodes;
