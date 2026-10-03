-- PUB-05 migration 0007 (DOWN): reverse 0007 exactly.

DROP INDEX IF EXISTS idx_causal_hypotheses_hypothesis;
DROP INDEX IF EXISTS idx_causal_hypotheses_workspace;
DROP TABLE IF EXISTS causal_hypotheses;
