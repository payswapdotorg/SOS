# PUB-05 Checkpoint — Neon persistence

**Work item:** PUB-05 (contract `spec/deployment/PUBLIC-DEPLOYMENT-CONTRACT.md` §D PUB-05; directive §11/§16-A; design §5)
**Worker:** Worker A (session `pub-05-neon-persistence`)
**Status:** WAITING_FOR_ARCHITECT (review-ready; this is NOT completion)
**Branch:** `work/pub-05-neon-persistence`
**PR:** #27 (https://github.com/payswapdotorg/SOS/pull/27)
**Base SHA:** `3eeefad72b502d678918e141d70b4f398b1ca9c0` (live `origin/main` HEAD at dispatch — verified reachable from origin/main before work started)
**Implementation head (all code + tests + docs; all verification below ran here):** `70a751c99ea3564fde12ff0c4c8a6035ce6656ac`
**Final branch head:** the checkpoint/state commit that follows the implementation head (adds only checkpoint + status documents — no code).

## Traceability

- Directive §11 (database model — the minimum relational model), §16-A
  (Worker A lane: control plane + infrastructure; never executes arbitrary
  user repository code), §4/§7 (the seam the adapter must serve); design
  §5 (persistence layer); contract §A (frozen-surface rules), §B
  (repository layout — `db/migrations/`, `providers/neon/`), §C.2/§C.3
  (wire-shaped rows: the seam returns DTO-shaped dicts; the DTOs own the
  wire names), §D PUB-05 (this work order), §G (gate matrix), §F
  (anti-fabrication).
- Dependencies: PUB-01 (MERGED as `c98972aadf79eae57e9438f6408e27f41165ebc0b`,
  PR #25 — verified by actual Git evidence BEFORE work started; PUB-02 and
  PUB-03 merges present on main but NOT dependencies of this item).
  **No unmerged sibling is a dependency.**

## Files changed (equals the §D allowed surface exactly)

- `providers/neon/**` — `cloud.py` (the Neon adapter: asyncpg, Neon
  serverless-compatible, dedicated event-loop bridge for the final SYNC
  seam, tenant-scoped queries, fail-closed DSN validation),
  `local.py` (shared registries + normalized-row projections; registries
  moved to the shared mapping module), `seam.py` (ConflictError moved to
  the seam module — shared by both implementations, re-exported from
  `local` so existing import sites are unchanged), `__init__.py` (doc).
- `db/**` — `mapping.py` (NEW: the single domain-object ↔ row mapping
  authority), `runner.py` (Postgres dialect translation + async migration
  functions + CLI `--url`), migrations `0004_section11_completion` …
  `0011_execution_records` (8 NEW numbered reversible pairs),
  `__init__.py` (doc).
- `services/api/main.py` — persistence wiring ONLY: migrations + demo seed
  for BOTH persistence modes (previously LOCAL-only) + the persistence
  adapter-selection comment. No route, schema, auth or orchestration change.
- `tests/test_pub05*.py` — 4 NEW files, 70 tests
  (`test_pub05_mapping.py`, `test_pub05_migrations.py`,
  `test_pub05_postgres_parity.py`, `test_pub05_neon_adapter.py`).
- `docs/deployment/database.md` — the PUB-05 finalization (dialect
  strategy, both implementations, parity instructions, deploy note).
- `spec/development-state/PUB-05-checkpoint.md` (this file) and
  `spec/development-state/public-deployment-state.json` (PUB-05 status
  fields only).

**Frozen surface untouched:** `src/sos/**` byte-identical (G02 PASS); all
frozen docs byte-identical (G01 PASS; the regenerated
`W15-gate-report.json` runtime artifact is restored, never committed —
PUB-01/02/03 precedent); `implementation-state.json` stays
ROADMAP_COMPLETE/currentFrontier []/currentTask null (G03 PASS); no
existing test file modified (the PUB-01 `test_pub01_config.py`
fail-closed expectation still passes: selecting
`SOS_PERSISTENCE=neon` without a valid DSN aborts boot with a
PUB-05-precise error); `tools/final_gate_check.py` untouched;
`.github/workflows/*` untouched; `pyproject.toml` untouched;
`infra/**` untouched.

## What was delivered

1. **Full relational schema (§11 minimum), numbered + reversible.**
   Migrations 0004–0011 add: `value_models`, `value_model_revisions`,
   `contexts`, `provider_events` (the §11 tables PUB-01 had not created —
   schema-forward per §11; their wire traffic is PUB-08/PUB-09 scope);
   `architecture_nodes`, `architecture_edges`,
   `architecture_boundary_contracts` (the `system_revisions.graph` wire
   document decomposed; `(system_revision_id, key)` unique because graph
   node ids repeat across revisions; `position` preserves document order);
   `evidence_artifacts` (artifact METADATA rows — bytes live in the
   artifact store per directive §12 / the PUB-05 forbidden "blobs in
   Postgres"; PUB-07 wires the store); `causal_hypotheses` (the W5 causal
   claim columnarized per hypothesis); `candidate_evaluations` (one row per
   objective + one per Pareto-front point, `record_kind` discriminates —
   the multi-objective evaluation is never a scalar);
   `assurance_results` (one row per executed gate, the frozen W7
   four-state vocabulary); `experiment_events` (the lifecycle event log);
   `execution_requests` + `execution_receipts` (the governed request
   identity and the columnar W11 receipt — outcome truth state VERBATIM,
   demo flag, provenance and side-effect references).
   Up/down round-trips cleanly on BOTH backends (parity tests run the full
   cycle twice on SQLite and once on a real PostgreSQL).
2. **The Neon adapter** (`providers/neon/cloud.py`):
   `NeonPostgresPersistence` implements the final PUB-01 seam interface
   over PostgreSQL via the **asyncpg async driver**. Neon
   serverless-compatible: TLS from the DSN (`sslmode=require`),
   `statement_cache_size=0` (pooled/transaction-mode endpoints — Neon's
   PgBouncer pooler), `max_inactive_connection_lifetime=300` (compute
   suspend/wake). The seam interface is synchronous (final since PUB-01),
   so the adapter owns a dedicated event-loop thread and bridges every
   call (`_LoopRunner`); concurrent callers from FastAPI worker threads
   are served correctly (parity-tested). DSN forms accepted:
   `postgresql://`, `postgres://`, `postgresql+asyncpg://` (driver suffix
   stripped — the `infra/environment.example` documented form). Invalid or
   missing DSN aborts boot fail-closed (`NeonConfigError`, message names
   PUB-05 and SOS_DATABASE_URL — never a silent LOCAL fallback).
   asyncpg is a LAZY import: absent driver → precise ImportError, also
   fail-closed. Health is truthful (SUCCESS with detail, FAILED with the
   real error under fault injection — never a fake ok).
3. **Domain-object ↔ row mapping** (`db/mapping.py`): the SINGLE mapping
   authority shared by BOTH adapters — the JSON-column registry (which
   TEXT columns carry JSON documents → JSONB on Postgres; the migration
   dialect translation consumes the same registry), the tenant-table and
   parent-link registries (which column scopes each table),
   decomposition/reassembly functions with EXACT round-trip properties
   (graph incl. boundary contracts, evaluations, assurance gates,
   experiment events, execution request/receipt, causal claims, evidence
   artifacts), deterministic content-addressed row ids (idempotent
   re-projection), and `encode_row`/`decode_row` (byte-identical JSON on
   both backends). MAPPING ONLY — no semantic interpretation; truth states
   pass through verbatim; the frozen `src/sos` engines stay the only
   semantic authority.
4. **Normalized projections on BOTH backends:** every `insert_*` write on
   SQLite AND Neon projects the payload's decomposed content into the
   §11 tables in the same transaction (mapping tests + parity tests prove
   doc-column ↔ rows equivalence over the full demo dataset on both
   backends, and identical normalized-table row counts).
5. **Tenant-scoped queries ONLY, enforced at the adapter:** every scoped
   query on both implementations applies the `TenantScope` allowlist as a
   SQL filter; cross-tenant ids yield zero rows / None (parity-tested on
   both backends, including the workspace-scoped filter paths).
6. **Seed loader on both backends:** the deterministic demo dataset loads
   through the same seam on SQLite and PostgreSQL (identical content,
   idempotent re-run); `create_app` now migrates + seeds for BOTH
   persistence modes (a fresh Neon branch bootstraps exactly like a fresh
   LOCAL database; LOCAL behavior is unchanged).
7. **Postgres dialect in the runner** (`db/runner.py`):
   `translate_script_to_postgres` (registered JSON columns TEXT→JSONB,
   REAL→DOUBLE PRECISION; everything else passes verbatim), async
   migration functions for asyncpg, and CLI `--url DSN` support for
   operators. The same migration set serves both backends.
8. **Parity suite** (70 tests in 4 new files):
   - `test_pub05_mapping.py` (18): round-trips for every decomposed
     entity; registry ↔ migration-DDL consistency (the dialect
     translation's contract); §11 minimum tables present; doc↔rows
     equivalence over the full demo dataset (SQLite side).
   - `test_pub05_migrations.py` (8): SQLite up/down/up/down ×2 + partial
     revert/re-apply; dialect translation checks; a REAL-Postgres full
     up/down/up round-trip + JSONB/double-precision typing + JSONB value
     round-trip (gated: asyncpg + reachable Postgres).
   - `test_pub05_postgres_parity.py` (32): row-for-row parity of ALL 15
     entity collections, all single-resource getters, users/membership,
     activity, seed idempotence, tenant scoping (zero rows both
     backends), truth states (all six, verbatim), cursor pagination
     (identical opaque cursors, no dupes, several limits), filters,
     candidate/experiment/job filters, evidence+execution dedup,
     workspace-slug conflict, job patch updates, audit id
     disambiguation, normalized-table parity (counts + deep receipt
     equality), graph doc↔rows equivalence on Postgres, truthful health,
     and the FastAPI control plane booting on the Neon adapter
     (health/evidence/workspaces/systems/missions over PostgreSQL).
   - `test_pub05_neon_adapter.py` (12): DSN validation (all forms +
     fail-closed garbage), credential-free DSN labels, the frozen
     PUB-01-config fail-closed shape (still passes), adapter identity,
     concurrent sync-bridge threads, close() semantics, truthful timeout.
   - Postgres tests auto-discover `SOS_TEST_DATABASE_URL` or a LOCAL pg
     (probe ports 5432/54329) and SKIP cleanly with truthful reasons
     where absent (verified by blocking asyncpg in a subprocess run:
     14 ran / rest skipped, zero failures). Never a fabricated pass.

## Verification (§G gate matrix, run at the implementation head)

- `python3 -m pytest` → **676 passed** (606 baseline + 70 PUB-05), 0
  failures, 0 errors.
- `python3 -m compileall -q src tests services providers execution` →
  clean (exit 0).
- `python3 tools/final_gate_check.py` → **OVERALL PASS — 12/12** (exit 0;
  frozen surface clean, overlay-scoped G09 under the PUB-01
  reconciliation; the regenerated W15-gate-report.json is a runtime
  artifact and is NOT committed — restored after each run, per the
  PUB-01/02/03 precedent).
- `cd apps/web && bun install && bun run lint && bun run typecheck &&
  bun test` → lint clean, typecheck clean, **80/80** bun tests.
- Postgres parity ran against a REAL PostgreSQL 16.4 (LOCAL `pg`, asyncpg
  0.31.0) in this session: the full 32-test parity file + the 2
  Postgres migration tests + the 4 adapter driver tests all passed; the
  same suite is re-runnable by the TL via `SOS_TEST_DATABASE_URL` or a
  local pg (instructions in `docs/deployment/database.md`).
- Fresh-clone boot smoke (Neon path): `create_app` with
  `SOS_PERSISTENCE=neon` migrates (11 migrations), seeds the demo
  dataset, serves `/api/v1` with truthful health (`persistence.mode:
  neon, SUCCESS, postgres ok`) — covered by the boot integration test.

## Unresolved findings / known limitations (truthful)

1. **asyncpg is NOT in the frozen `[api]` dependency group.**
   `pyproject.toml` is outside PUB-05's allowed surface (PUB-01's surface
   included it explicitly; PUB-05's deliberately does not), and
   `infra/render.yaml` (PUB-03's surface) builds with
   `pip install -e '.[api]'` while running `SOS_PERSISTENCE=neon`. Before
   the PUBLIC deploy (PUB-11) the TL needs a one-line wiring decision:
   add `asyncpg` to the `api` group or to the Render build command.
   Booting neon mode without asyncpg fails closed with a precise error
   (by design — never a silent LOCAL fallback).
2. **CI parity coverage:** the pub workflow installs only `.[api]`
   (no asyncpg), so the Postgres-parity tests SKIP in CI with truthful
   reasons. Full Postgres parity is verified against a LOCAL real `pg`
   (this session) and is re-runnable identically by the TL/CI with one
   install line. The acceptance criterion ("a real Postgres in CI or
   LOCAL `pg`") is satisfied by the LOCAL `pg` runs recorded here.
3. **§11 name mappings (documented, no semantic change):** the directive
   §11 table `architecture_memory` is served by `memory_entries` (the
   §C.3 `MemoryEntry` wire DTO's table — PUB-01 reviewed naming; renaming
   a merged table would churn PUB-01's surface for zero semantic gain).
   The graph document's `boundaryContracts` (a first-class field of the
   frozen W2 `ArchitectureGraph` model) are normalized as
   `architecture_boundary_contracts` — one table beyond the §11 list,
   because the §11 list is a MINIMUM and an exact graph round-trip
   requires it. Disclosed here for the reviewer's judgment.
4. **Sequenced reads inside one seam method:** `list_mission_revisions`
   performs the parent lookup then the page query (two round-trips on
   Neon vs one on SQLite) — mirrored 1:1 from the PUB-01 SQLite adapter
   to keep semantics identical; harmless at demo scale.
5. No external credential was needed for this item (LOCAL `pg` +
   asyncpg only). Nothing was blocked: **no WAITING_FOR_CAPACITY state.**

## Explicit statements (dispatch law)

- No unmerged sibling branch is a dependency (PUB-01 verified MERGED by
  Git evidence before work started; PUB-02/PUB-03 are not dependencies).
- No frozen surface was touched (`src/sos/**`, frozen docs, frozen gate
  logic, existing tests, workflows, pyproject, infra).
- No merge was performed; no self-approval; no successor work item
  started; this checkpoint enters `WAITING_FOR_ARCHITECT` and stops.
- Anti-fabrication: every number above is re-runnable at the exact head
  `70a751c99ea3564fde12ff0c4c8a6035ce6656ac`; the branch head is pushed
  and fetchable (remote-ref truth gate).
