-- PUB-05 migration 0008 (DOWN): reverse 0008 exactly.

DROP INDEX IF EXISTS idx_candidate_evaluations_candidate;
DROP INDEX IF EXISTS idx_candidate_evaluations_workspace;
DROP TABLE IF EXISTS candidate_evaluations;
