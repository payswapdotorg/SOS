-- PUB-01 migration 0003 (DOWN): reverse 0003 exactly.

ALTER TABLE evidence DROP COLUMN result;
