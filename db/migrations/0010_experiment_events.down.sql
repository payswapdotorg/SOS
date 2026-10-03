-- PUB-05 migration 0010 (DOWN): reverse 0010 exactly.

DROP INDEX IF EXISTS idx_experiment_events_experiment;
DROP INDEX IF EXISTS idx_experiment_events_workspace;
DROP TABLE IF EXISTS experiment_events;
