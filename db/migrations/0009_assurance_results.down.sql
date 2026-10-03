-- PUB-05 migration 0009 (DOWN): reverse 0009 exactly.

DROP INDEX IF EXISTS idx_assurance_results_run;
DROP INDEX IF EXISTS idx_assurance_results_workspace;
DROP TABLE IF EXISTS assurance_results;
