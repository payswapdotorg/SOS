-- PUB-01 migration 0003 (UP): evidence observed-result detail column.
-- Preserves the W4 TruthfulValue (state/value/detail) verbatim on the wire
-- so non-SUCCESS evidence carries its explanatory detail end-to-end (S18).

ALTER TABLE evidence ADD COLUMN result TEXT;
