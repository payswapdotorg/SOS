-- PUB-05 migration 0006 (DOWN): reverse 0006 exactly.

DROP INDEX IF EXISTS idx_evidence_artifacts_evidence;
DROP INDEX IF EXISTS idx_evidence_artifacts_workspace;
DROP TABLE IF EXISTS evidence_artifacts;
