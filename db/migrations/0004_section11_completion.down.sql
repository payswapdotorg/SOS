-- PUB-05 migration 0004 (DOWN): reverse 0004 exactly (children first).

DROP INDEX IF EXISTS idx_provider_events_workspace;
DROP TABLE IF EXISTS provider_events;
DROP INDEX IF EXISTS idx_contexts_workspace;
DROP TABLE IF EXISTS contexts;
DROP INDEX IF EXISTS idx_value_model_revisions_model;
DROP TABLE IF EXISTS value_model_revisions;
DROP INDEX IF EXISTS idx_value_models_workspace;
DROP TABLE IF EXISTS value_models;
