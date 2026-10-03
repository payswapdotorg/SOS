# SOS Public Deployment — Database Strategy (PUB-01 → PUB-05 final)

## Layout

- `db/migrations/NNNN_name.up.sql` + `NNNN_name.down.sql` — numbered,
  forward-creatable, REVERSIBLE migrations (transactional application).
- `db/runner.py` — the migration runner + CLI:
  - `python3 -m db.runner up [--db PATH | --url DSN]` (forward; records in `_migrations`)
  - `python3 -m db.runner down [--db PATH | --url DSN] [--target N]` (reverse order)
  - `python3 -m db.runner status [--db PATH | --url DSN]`
  - `--url` selects the PostgreSQL dialect (asyncpg driver, lazily imported).
- `db/mapping.py` — the SINGLE domain-object ↔ row mapping authority shared
  by BOTH persistence adapters (JSON-column registry, tenant-table registry,
  decomposition/reassembly of the normalized §11 entity rows, deterministic
  row ids, identical JSON serialization on both backends).
- `db/seeds/demo_seed.py` — the deterministic demo dataset (driven through
  the REAL `src/sos` engines; idempotent).

## Migrations (PUB-05 head)

- `0001_core_identity_and_missions` — users, workspaces, workspace_members,
  missions, mission_revisions.
- `0002_overlay_entities` — systems, system_revisions, evidence,
  hypotheses, candidates, assurance_runs, decisions, authorizations,
  experiments, executions, learning_records, memory_entries, jobs,
  audit_events (CHECK constraints carry the frozen vocabularies: truth
  states, decision actions, job statuses, workspace modes, provider names).
- `0003_evidence_result` — the evidence observed-result detail column
  (W4 `TruthfulValue` state/value/detail preserved on the wire).
- `0004_section11_completion` — value_models, value_model_revisions,
  contexts, provider_events (the directive §11 minimum tables not created
  by PUB-01; their wire traffic is wired by later items — PUB-08 provider
  callbacks, PUB-09 journey aggregates).
- `0005_architecture_graph` — architecture_nodes, architecture_edges,
  architecture_boundary_contracts (the system_revisions.graph document
  decomposed into rows; `(system_revision_id, node_key/edge_key/
  contract_key)` unique; position preserves document order).
- `0006_evidence_artifacts` — artifact METADATA rows (bytes live in the
  artifact store — LOCAL FS / R2 per §12 — never in the database).
- `0007_causal_hypotheses` — the W5 causal claim columnarized per
  hypothesis.
- `0008_candidate_evaluations` — one row per objective and per Pareto-front
  point (record_kind discriminates; the multi-objective evaluation is never
  a single scalar).
- `0009_assurance_results` — one row per executed assurance gate (the W7
  four-state vocabulary on gate_status).
- `0010_experiment_events` — the experiment lifecycle event log.
- `0011_execution_records` — execution_requests + execution_receipts (the
  governed request identity and the columnar W11 receipt: outcome truth
  state verbatim, demo flag, provenance and side-effect references).

## SQLite (LOCAL) ↔ PostgreSQL (Neon): one migration set, two dialects

The migration files are written in the common SQL subset (SQLite-valid).
PostgreSQL runs the SAME set through a deterministic dialect translation in
`db/runner.py` (`translate_script_to_postgres`):

| SQLite (verbatim) | PostgreSQL (translated) |
|---|---|
| JSON columns as `TEXT` (`goals`, `provenance`, `checks`, `events`, …) | `JSONB` — exactly the columns registered in `db/mapping.JSON_COLUMNS` |
| `REAL` | `DOUBLE PRECISION` (8-byte float on both) |
| `INTEGER` flags, `CHECK` constraints, partial unique indexes, `REFERENCES … ON DELETE CASCADE` | identical syntax, passes through verbatim |
| `_migrations.applied_at` default `datetime('now')` | `now()::text` (runner-internal, per dialect) |

The translation is exercised against a REAL Postgres by the PUB-05 parity
suite (`tests/test_pub05_migrations.py`: up/down round-trip on both
backends; JSONB/double-precision typing verified).

§11 name mapping (documented): the directive §11 table `architecture_memory`
is served by `memory_entries` — the §C.3 `MemoryEntry` wire DTO's table,
PUB-01 reviewed naming. `boundaryContracts` (the W2 frozen graph model's
boundary contracts) are normalized as `architecture_boundary_contracts`.

## The two persistence implementations (PUB-05)

- **LOCAL** — `providers/neon/local.LocalSqlitePersistence` (SQLite via the
  `db/`-managed schema): the PUB-01 reference implementation.
- **Neon** — `providers/neon/cloud.NeonPostgresPersistence` (PostgreSQL via
  the **asyncpg** async driver; Neon serverless-compatible: TLS via the DSN
  `sslmode`, `statement_cache_size=0` for pooled/transaction-mode endpoints,
  connection recycling for Neon suspend/compute-wake). The seam interface is
  synchronous (final since PUB-01), so the adapter drives asyncpg on a
  dedicated event-loop thread and bridges each seam call.

Both adapters:

- apply the SAME tenant scoping (`TenantScope` allowlist → SQL filter) in
  every scoped query — cross-tenant ids yield zero rows (SECURITY S5);
- use the SAME shared mapping module (`db/mapping.py`) — every `insert_*`
  write projects the payload's decomposed content into the normalized §11
  tables in the same transaction, and JSON columns serialize identically
  (`json.dumps(..., sort_keys=True)`; JSONB on PostgreSQL round-trips the
  decoded value);
- return wire-shaped row dicts whose content is IDENTICAL across backends —
  proven row-for-row by the parity suite
  (`tests/test_pub05_postgres_parity.py`: collections, getters, cursors,
  filters, dedup, conflicts, truth states, normalized-table counts, the
  FastAPI control plane booting on the Neon adapter).

## Running Postgres parity locally

```
python3 -m pip install asyncpg
python3 -m pytest tests/test_pub05_postgres_parity.py tests/test_pub05_migrations.py
```

The suite auto-discovers a real Postgres: `SOS_TEST_DATABASE_URL` (DSN) if
set, else a LOCAL `pg` on the probe ports (5432 default service / 54329
embedded). Without a reachable Postgres or without asyncpg the Postgres
tests SKIP with truthful reasons — never a fabricated pass.

## Tenant scoping

Every tenant table carries `workspace_id` (or a parent link) and EVERY
scoped query in the persistence adapter applies the `TenantScope`
allowlist (SECURITY S5 — enforced in the adapter, not per-route).
Cross-tenant requests yield zero rows.

## Runtime state locations

LOCAL SQLite/artifact state defaults to the platform temp directory
(`SOS_LOCAL_DB_PATH`, `SOS_LOCAL_ARTIFACTS_DIR` override) — runtime state
never lands in the governed repository tree. Neon state lives in the
operator's Neon project (`SOS_DATABASE_URL`, never committed).

## Deployment note (operator input — PUB-11)

`infra/render.yaml` (PUB-03) builds with `pip install -e '.[api]'` and runs
`SOS_PERSISTENCE=neon`. The `api` dependency group (PUB-01, frozen surface
for PUB-05) does not include `asyncpg`, and neither `pyproject.toml` nor
`infra/` is inside PUB-05's allowed surface — so the PUBLIC deploy needs a
one-line wiring decision before PUB-11 (add `asyncpg` to the `api` group or
to the Render build command). Booting `SOS_PERSISTENCE=neon` without
asyncpg installed fails closed with a precise error (by design; never a
silent LOCAL fallback).
