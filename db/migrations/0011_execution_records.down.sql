-- PUB-05 migration 0011 (DOWN): reverse 0011 exactly.

DROP INDEX IF EXISTS idx_execution_receipts_execution;
DROP INDEX IF EXISTS idx_execution_receipts_workspace;
DROP TABLE IF EXISTS execution_receipts;
DROP INDEX IF EXISTS idx_execution_requests_execution;
DROP INDEX IF EXISTS idx_execution_requests_workspace;
DROP TABLE IF EXISTS execution_requests;
