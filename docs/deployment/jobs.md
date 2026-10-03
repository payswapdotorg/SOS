# The Job/Coordination Layer (PUB-06)

**Status:** ACTIVE — operational documentation for the Upstash job/coordination
layer (directive §8 async job architecture, §13 rate limiting, §3 Upstash
coordination plane; contract §D PUB-06).

This document is the binding disclosure of the retry policy, the lock/lease
semantics, the rate-limit buckets and the worker operation model. The
machine-checkable counterparts live in `tests/test_pub06_*.py`.

## 1. The job model (directive §8, exact)

Every job persists the directive §8 fields (durable truth in the `jobs`
table — SQLite LOCAL / Neon PostgreSQL PUBLIC, migration
`db/migrations/0002_overlay_entities.up.sql`):

```text
id  tenant_id  type  requested_by  authority_snapshot  input_hash
source_revision  provider  status  started_at  completed_at
receipt  artifact_refs  error_state        (+ idempotency_key, created_at)
```

- `input_hash` — SHA-256 (16 hex) of the canonical job input
  (`{type, workspaceId, experimentId | repositoryUrl, ref}`), computed at
  creation (stable across replays).
- `authority_snapshot` — the durable record of the authority the job runs
  under (`{principal, workspaceRole | provider}`); the worker re-derives its
  execution identity from it, never fabricating authority.
- `status` lifecycle: **`queued` → `running` → `succeeded` | `failed`**.

### Status lifecycle semantics

| Transition | Guard | Meaning |
|---|---|---|
| → `queued` | idempotent create (§2) | accepted, awaiting dispatch |
| `queued` → `running` | orchestration lock held (§3) + status re-check under the lock | claimed by exactly one executor |
| `running` → terminal | op result / retry budget (§4) | truthful outcome, receipt/error recorded |

Truthful non-SUCCESS provider outcomes (FAILED/UNKNOWN/UNAVAILABLE
receipts from the execution seam) are terminal **results**, not retryable
infrastructure failures — they are never retried into a fake success.

## 2. Idempotency keys

`POST /api/v1/jobs` accepts an explicit `idempotencyKey` (or derives one
from `type:workspaceId:experimentId|ref`). Duplicate POSTs with the same
key return the SAME job row and cause no duplicate side effects:

1. **Durable arbitration** — the `jobs.idempotency_key` UNIQUE index
   (partial, where not null) is the authoritative dedup; concurrent
   creators race on the insert and the loser re-fetches the winner's row.
2. **Coordination fast path** — Upstash `SET NX` (`sos:idem:job:…`, 7-day
   TTL) suppresses concurrent duplicates before they reach the DB.
3. **Deterministic side effects** — job ids (and the recovery evidence id)
   derive from the idempotency key, so a re-drive converges on the same
   rows (`job-recovery-<slug>`, `ev-job-recovery-<slug>`); the dispatcher
   treats duplicate-key inserts as already-recorded (converged), never as
   failures and never as duplicates.

Replays never consume the job-type/provider quotas (PUB-01 semantics).
A replay of a still-`queued` job re-registers it in the pending registry
(re-drive after a coordination-plane loss).

## 3. Orchestration locks (lease semantics)

Claiming a job acquires `sos:lock:job:{id}` via `SET NX EX` with
`SOS_JOB_LEASE_SECONDS` (default 600) as the lease TTL:

- **Concurrent dispatch → single execution**: the loser sees
  `acquired=False` and skips; the winner performs the status transition
  under the lock. The in-process LOCAL limiter provides the same
  mutual exclusion via thread locks.
- The lease must exceed the worst-case execution window
  (`timeout × attempts + backoff budget`); default 600s ≫ 60×3 + backoff.
- **Crash recovery**: a `running` job whose lease expired (executor died)
  is rescued by the worker sweep — requeued when attempts remain within
  the bounded budget, else terminal `failed` ("abandoned"). Attempt
  bookkeeping lives in the coordination plane (`sos:jobstate:{id}`,
  TTL-bounded).
- The lock is the *efficiency* guard; the durable status transition under
  the lock is the *correctness* guard. Losing the coordination plane never
  produces a status lie: jobs stay truthfully `queued`/`failed`.

## 4. Retry policy (bounded, jittered, disclosed)

| Setting | Default | Meaning |
|---|---|---|
| `SOS_JOB_MAX_ATTEMPTS` | 3 | hard attempt bound per job |
| `SOS_JOB_BACKOFF_BASE_SECONDS` | 1 | backoff = `min(max, base × 2^(attempt-1))` |
| `SOS_JOB_BACKOFF_MAX_SECONDS` | 30 | backoff cap; sleep is **full jitter** — `uniform(0, backoff)` |
| `SOS_JOB_TIMEOUT_SECONDS` | 60 | per-attempt time bound (the caller never waits longer) |
| `SOS_JOB_LEASE_SECONDS` | 600 | orchestration-lock lease (§3) |

Classification: `JobPermanentError` (validation, governed rejections,
conflicts) terminates immediately; infrastructure failures and timeouts are
retried within the bound; `RATE_LIMITED` dispatch trips retry after the
backoff. Every failed job's `errorState` carries the attempt count and the
disclosed policy JSON (`maxAttempts`, backoff formula, timeout, lease) —
the policy is visible on the wire, not just in docs.

Timeout disclosure: the time bound covers the *waiting* side (a daemon
thread runs the operation; the bound never blocks the API/worker caller).
A timed-out operation's thread dies with the process; a late side effect
surfaces as a duplicate-key conflict on the next attempt (converged, §2) —
never a fabricated success.

## 5. Rate limiting (directive §13 buckets — complete set)

All buckets are fixed-window counters, **epoch-aligned**
(`floor(now / window)`) with IDENTICAL semantics on the LOCAL in-process
limiter and the Upstash Redis limiter (`INCR` + `EXPIRE` on a
window-scoped key) — asserted by the PUB-06 parity suite.

| Bucket | Scope | Window | Default | Enforced |
|---|---|---|---|---|
| `ip` | per client IP, all traffic | 60s | anon+user sum | middleware |
| `anonymous` | per IP, unauthenticated (demo reads only) | 60s | 60 | middleware |
| `user` | per authenticated user | 60s | 240 | middleware |
| `auth` | login/logout session exchange | 60s | =anon | middleware |
| `workspace` | per targeted workspace (query `workspaceId` or `/workspaces/{id}` path) | 60s | 600 | middleware (PUB-06) |
| `write` | per user, mutations | 60s | 30 | mutation routes |
| `job-type` | per workspace per job type | 3600s | 10 | job creation |
| `recovery` | per workspace, `system_recovery` | 3600s | 2 | job creation |
| `provider` | per execution provider (dispatches) | 60s | 30 | job creation (PUB-06) |

The Apify **low-concurrency semaphore** (`SOS_APIFY_MAX_CONCURRENT`) is
PUB-08's complement to the provider bucket. Requests that identify no
workspace target are covered by the ip/identity buckets only (disclosed).
429 responses carry the contract error envelope + `Retry-After`.

## 6. LOCAL ↔ PUBLIC parity

| Concern | LOCAL (`SOS_COORDINATION=local`) | PUBLIC (`upstash`) |
|---|---|---|
| Execution trigger | inline bounded executor after POST /jobs (env=local) | worker process only; API enqueues |
| Job discovery | in-process pending registry | Upstash `sos:pending` list (RPUSH/LRANGE/LREM) |
| Locks / leases | thread locks (process lifetime) | `SET NX EX` TTL leases |
| Rate windows | epoch-aligned in-process counters | epoch-aligned Redis counters |
| Idempotency | in-process first-write map + DB unique index | Upstash `SET NX` (7d TTL) + DB unique index |

The worker code path (`services/api/jobs/worker.py:run_worker_once`) is
mode-independent: the same sweep executes jobs in both modes; only the
trigger differs. The pending registry and job input are EPHEMERAL
coordination state (TTL = max(4×lease, 1h)): a Redis loss leaves jobs
truthfully `queued` (re-driven on idempotent replay) or fails them with an
honest "input unavailable — re-submit" error. Redis is never the event
store (directive §3).

## 7. Operating the worker (PUBLIC)

`infra/render.yaml` defines the `sos-job-worker` Render background worker
(free tier) — same provider wiring as the API, start command:

```text
PYTHONPATH=../.. python3 -m services.api.jobs.worker --poll 5 --limit 10
```

- One sweep claims up to `--limit` queued jobs; `--once` runs a single
  sweep (operator diagnostics / tests).
- A failing sweep never kills the worker (jobs stay durably queued; the
  error is printed, not swallowed as success).
- Worker-side execution runs under the job's recorded authority
  (`requested_by` + `authority_snapshot`) — never a fabricated identity;
  the tenant scope is exactly the job's workspace.

## 8. Coordination-plane failure behavior (fail-closed)

- `/api/v1/health` stays exempt and reports the coordination seam's TRUE
  state (`UNAVAILABLE` + detail when Redis is unreachable).
- Protected traffic fails CLOSED: 503 `PROVIDER_UNAVAILABLE` from the
  middleware — never a fake pass-through.
- `SOS_COORDINATION=upstash` without a valid `SOS_REDIS_URL` aborts boot
  with a precise PUB-06 error (no silent LOCAL fallback).

## 9. Scope boundaries (for reviewers)

- The provider **callback endpoint** (signed envelopes from Apify) is
  PUB-08's surface; PUB-06 ships the validation primitive
  (`services/api/jobs/callbacks.py`: HMAC-SHA256 over `timestamp.nonce.body`,
  ±300s window, single-use nonces via the coordination plane, validated
  BEFORE any state mutation).
- The durable `jobs` table (migration 0002) and the persistence adapter
  (`providers/neon/**`) are PUB-01/PUB-05 surface — untouched by PUB-06;
  no new migration is required (retry bookkeeping is coordination-plane
  state by design).
