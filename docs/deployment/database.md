# SOS Public Deployment — Database Strategy (PUB-01)

## Layout

- `db/migrations/NNNN_name.up.sql` + `NNNN_name.down.sql` — numbered,
  forward-creatable, REVERSIBLE migrations (transactional application).
- `db/runner.py` — the migration runner + CLI:
  - `python3 -m db.runner up [--db PATH]` (forward; records in `_migrations`)
  - `python3 -m db.runner down [--db PATH] [--target N]` (reverse order)
  - `python3 -m db.runner status [--db PATH]`
- `db/seeds/demo_seed.py` — the deterministic demo dataset (driven through
  the REAL `src/sos` engines; idempotent).

## Current migrations

- `0001_core_identity_and_missions` — users, workspaces, workspace_members,
  missions, mission_revisions.
- `0002_overlay_entities` — systems, system_revisions, evidence,
  hypotheses, candidates, assurance_runs, decisions, authorizations,
  experiments, executions, learning_records, memory_entries, jobs,
  audit_events (CHECK constraints carry the frozen vocabularies: truth
  states, decision actions, job statuses, workspace modes, provider names).
- `0003_evidence_result` — the evidence observed-result detail column
  (W4 `TruthfulValue` state/value/detail preserved on the wire).

## SQLite (LOCAL, now) → Postgres (Neon, PUB-05) strategy

The DDL is written in a common subset that is SQLite-compatible today, with
this documented translation for PUB-05:

| SQLite (now) | PostgreSQL (PUB-05) |
|---|---|
| `TEXT` ids/keys | `TEXT` (UUID-shaped string ids unchanged) |
| `INTEGER` flags | `BOOLEAN` |
| `REAL` | `DOUBLE PRECISION` |
| JSON-in-`TEXT` columns (`goals`, `provenance`, `checks`, `events`, …) | `JSONB` |
| `INTEGER PRIMARY KEY` (audit sequence suffix) | `BIGSERIAL` equivalent via `TEXT` ids (unchanged) |
| partial `UNIQUE INDEX ... WHERE` | identical partial unique index syntax |
| `PRAGMA foreign_keys` | native `REFERENCES` enforcement |

PUB-05 delivers the full relational mapping (normalizing the JSON payload
columns into the §11 entity set) and the Neon adapter on the SAME seam
interface (`providers/neon/seam.py`); PUB-01's seam, migrations and parity
tests are structured so the same migration set runs on both backends
(migration files stay SQLite-valid; the Postgres variants land with PUB-05's
runner dialect support).

## Tenant scoping

Every tenant table carries `workspace_id` (or a parent link) and EVERY
query in the persistence adapter applies the `TenantScope` allowlist
(SECURITY S5 — enforced in the adapter, not per-route). Cross-tenant
requests yield zero rows.

## Runtime state locations

LOCAL SQLite/artifact state defaults to the platform temp directory
(`SOS_LOCAL_DB_PATH`, `SOS_LOCAL_ARTIFACTS_DIR` override) — runtime state
never lands in the governed repository tree.
