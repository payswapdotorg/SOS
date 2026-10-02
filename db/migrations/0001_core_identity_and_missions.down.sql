-- PUB-01 migration 0001 (DOWN): reverse 0001 exactly.

DROP INDEX IF EXISTS idx_mission_revisions_mission;
DROP TABLE IF EXISTS mission_revisions;
DROP INDEX IF EXISTS idx_missions_workspace;
DROP TABLE IF EXISTS missions;
DROP TABLE IF EXISTS workspace_members;
DROP TABLE IF EXISTS workspaces;
DROP TABLE IF EXISTS users;
