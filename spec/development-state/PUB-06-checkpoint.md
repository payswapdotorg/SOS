# PUB-06 Checkpoint — Upstash job/coordination layer

**Status:** WAITING_FOR_ARCHITECT (review-ready at the exact head below)
**Worker:** Worker A (control plane + infrastructure lane)
**Branch:** `work/pub-06-upstash-jobs` (one bounded slice, one PR)

## Item + base + head

- **Work item:** PUB-06 — Upstash job/coordination layer
  (contract §D PUB-06; directive §8, §13, §16-A, §3-Upstash)
- **Exact base SHA:** `39e25ab03c93752d734a5fe09711709431aa2891`
  (verified: live merged `origin/main` at dispatch; PUB-01 MERGED as
  `c98972a` and PUB-05 MERGED as `65e29ad` per
  `spec/development-state/public-deployment-state.json` — dependencies
  satisfied from actual Git facts, not conversation)
- **Implementation head:** `458d27003b9437dd9dedc72b63dda9a422cbd7f7`
- **Final branch tip:** this checkpoint/state commit (adds ONLY this
  checkpoint + the PUB-06 status fields in
  `spec/development-state/public-deployment-state.json` — no code after
  the implementation head; the PUB-05 two-commit pattern).
- **PR:** `work/pub-06-upstash-jobs` → `main` (one PR per item).

## Files/artifacts changed vs the §D allowed surface

| Path | Kind | §D surface clause |
|---|---|---|
| `providers/upstash/seam.py` | modified | `providers/upstash/**` |
| `providers/upstash/local.py` | modified | `providers/upstash/**` |
| `providers/upstash/cloud.py` | modified (placeholder → real adapter) | `providers/upstash/**` |
| `services/api/jobs/__init__.py` | new | `services/api` job wiring |
| `services/api/jobs/service.py` | new | `services/api` job wiring |
| `services/api/jobs/dispatchers.py` | new | `services/api` job wiring |
| `services/api/jobs/worker.py` | new | `services/api` job wiring (worker entrypoint) |
| `services/api/jobs/callbacks.py` | new | `services/api` job wiring (callback validation primitive) |
| `services/api/routes/jobs.py` | modified (thin rewrite; OpenAPI byte-identical) | `services/api` job routes |
| `services/api/dependencies/rate_limit.py` | modified (workspace + provider buckets) | `services/api` dependencies wiring |
| `services/api/config.py` | modified (PUB-06 settings, appended, defaulted) | `services/api` job/dependencies wiring — disclosed below |
| `infra/environment.example` | modified (additive names only) | `infra/**` |
| `infra/render.yaml` | modified (new `sos-job-worker` service + new env names) | `infra/**` (worker config) |
| `docs/deployment/jobs.md` | new | docs |
| `docs/deployment/api-reference.md` | modified (jobs row semantics) | docs |
| `tests/test_pub06_coordination.py` | new | `tests/test_pub06*.py` (new files only) |
| `tests/test_pub06_jobs.py` | new | `tests/test_pub06*.py` (new files only) |
| `tests/test_pub06_rate_limits.py` | new | `tests/test_pub06*.py` (new files only) |
| `spec/development-state/PUB-06-checkpoint.md` | new (this file) | checkpoint |
| `spec/development-state/public-deployment-state.json` | modified (PUB-06 status fields only) | state |

**Nothing outside the §D surface was touched.** In particular:

- `src/sos/**` — zero changes (G02 holds; adapters import, never edit).
- Frozen documents — zero changes (byte-identical; G01 12/12 includes the
  frozen-digest checks).
- `tools/final_gate_check.py` + `tests/test_w15_final_gate_check.py` — zero
  changes (no gate logic beyond the PUB-01 reconciliation).
- `providers/neon/**`, `providers/github/**`, `providers/r2/**`,
  `execution/**`, `pyproject.toml`, `db/**`, `services/api/main.py`,
  `services/api/container.py`, `services/api/testing.py`,
  `services/api/schemas/**` — zero changes.
- No new migration is required: the directive §8 jobs table (migration
  0002, PUB-01) already carries the full field set incl. the
  `idempotency_key` unique partial index; PUB-06's retry/lease/input
  bookkeeping is coordination-plane state BY DESIGN (directive §3:
  "short-lived job state" — Redis is never the primary event store).
- `spec/development-state/W15-gate-report.json` — regenerated in the
  working tree by every `final_gate_check.py` run and left UNCOMMITTED
  (the W15/PUB precedent: it is the tool's output, not worker surface).

### Surface judgment calls (disclosed for review)

1. **`services/api/config.py`** — strictly the §D text lists "services/api
   job routes/dependencies wiring"; the retry policy, the §13
   workspace/provider buckets and the worker settings need config names
   (naming authority: `infra/environment.example`, which IS in the
   surface). All new `Settings` fields are appended WITH defaults
   (backward-compatible: every pre-PUB-06 construction site —
   `make_settings` included — works unchanged). No existing field or
   validation changed.
2. **`services/api/jobs/` subpackage** — the §D scope items (job model,
   idempotency, locks, retry, lifecycle, provider dispatcher, worker
   entrypoint) need a home; the package is the job wiring of
   `services/api`. The two runner functions moved here verbatim-in-spirit
   from `routes/jobs.py` (they were inline route logic in PUB-01 — the
   move makes the route a genuine thin controller per §C.4).
3. **`services/api/jobs/callbacks.py`** — directive §16-A PUB-06 lists
   "callback validation"; the repository contract §D places the signed
   callback ENDPOINT in PUB-08. PUB-06 ships only the validation
   PRIMITIVE (HMAC-SHA256 envelope, ±300s window, single-use nonce via
   the coordination plane, validated before any state mutation); PUB-08
   wires the endpoint to it.
4. **`routes/jobs.py` rewrite** — route signatures, response models,
   docstrings and parameter shapes are byte-identical: the OpenAPI
   snapshot hash is unchanged (asserted by the frozen
   `test_pub01_openapi_snapshot.py`, which passes unmodified).
5. **providers/upstash/local.py lock release fix** — the PUB-01
   `_InProcessLock.release()` set a flag but never released the
   underlying `threading.Lock` (latent: nothing called `acquire_lock`
   before PUB-06). Fixed in-surface; PUB-06's lock tests would be
   impossible without it.

## Requirement/directive traceability

- **Directive §8 (async job architecture):** job model with the exact §8
  fields (durable in the PUB-01 `jobs` table; `status` lifecycle
  `queued → running → succeeded | failed`); idempotency keys (duplicate
  POST /jobs → same job, no duplicate side effects — durable unique index
  + `SET NX` fast path + deterministic side-effect ids);
  Upstash enqueue/lock; provider dispatcher (local bounded operation +
  handoff to the execution seam).
- **Directive §13 (rate limiting/free-tier protection):** the bucket set
  is now complete — anonymous (demo reads only), authenticated, IP,
  workspace (NEW: per-targeted-workspace ceiling in the middleware),
  job type (per workspace per hour), provider (NEW: per-provider
  dispatch quota at job creation), plus the existing write/auth buckets.
  "Apify jobs: low concurrency" remains PUB-08's semaphore
  (`SOS_APIFY_MAX_CONCURRENT`); artifact size caps are PUB-07/S15.
- **Directive §3 (Upstash coordination plane):** locks, idempotency keys,
  short-lived job state, duplicate-job suppression, polling state — all
  TTL-bounded ephemeral coordination; Redis is NEVER the primary event
  store (jobs durable in SQLite/Neon; Redis loss → jobs stay truthfully
  queued and are re-driven on idempotent replay, or fail with an honest
  "input unavailable" error).
- **Directive §16-A (PUB-06 list):** job model ✓, idempotency ✓, retry
  policy ✓, provider dispatch ✓, callback validation ✓ (primitive; the
  endpoint is PUB-08 per the repository contract). Worker A never
  executes arbitrary user repository code (the dispatchers run the frozen
  W3/W11 pipelines only).
- **Contract §C.2/§C.3:** Job DTO unchanged (directive §8 fields exactly;
  the OpenAPI snapshot is untouched); every job mutation carries an audit
  event (`job.created`, `job.started`, `job.completed`, `job.failed`);
  truth states survive (truthful non-SUCCESS outcomes are terminal job
  RESULTS, never retried into fake success, never converted to transport
  errors).
- **Contract §C.4 (thin-layer rule):** `routes/jobs.py` is now
  authenticate → tenant-authorize → validate → JobService → DTO; the
  business logic lives in the job layer (the PUB-01 inline runners were
  moved OUT of the route file).

## Verification (§G matrix, run at the exact implementation head
`458d270` + re-run at the final checkpoint tip)

| Command | Result |
|---|---|
| `python3 -m pytest` | **691 passed, 38 skipped** (skips = the truthful PUB-05 Postgres-parity skips: asyncpg/Postgres absent in this env — identical skip set at the pristine base; zero failures) |
| `python3 -m compileall -q src tests services providers execution` | clean (exit 0) |
| `python3 tools/final_gate_check.py` | **OVERALL: PASS — 12/12 checks PASS (0 FAIL, 0 DEFERRED)**, exit 0 |
| `cd apps/web && bun install` | 362 packages, clean |
| `cd apps/web && bun run lint` | clean (eslint, exit 0) |
| `cd apps/web && bun run typecheck` | clean (tsc --noEmit, exit 0) |
| `cd apps/web && bun test` | **80 pass / 0 fail** (581 expect() calls) |

**New PUB-06 tests (53):** `test_pub06_coordination.py` (21 — Upstash
REST command semantics over a scripted fake transport: SET-NX-EX locks,
release lease-reassignment guard, idempotency first-write-wins + 7-day
TTL, INCR+EXPIRE pipeline shape, job state NX/put, pending registry
RPUSH/LRANGE/LREM incl. duplicate semantics, truthful health
SUCCESS/UNAVAILABLE, transport error mapping, fail-closed URL validation
(rediss/https forms + PUB-06 message), construction performs no network
I/O; LOCAL adapter lock/idempotency/state/registry; and the
LOCAL↔Upstash PARITY suite: identical RateDecision sequences, epoch
window-boundary resets, lock + idempotency parity),
`test_pub06_jobs.py` (24 — route-level lifecycle + §8 wire fields +
audit trail; idempotent replays (3 POSTs → one job, one evidence row);
execution-job handoff with demo receipt; truthful failure = job state
(not an error envelope) with disclosed policy; pinned-input validation
(422); anonymous rejection (401); service-level: retry recovers within
the bound (op calls == 3, backoffs [1.0, 2.0]); retry bound stops at
max_attempts and discloses the policy; permanent errors don't retry;
timeouts bounded and retried then failed; the DEFAULT run_bounded
enforces its timeout; **concurrent dispatch executes exactly once**
(4 threads, one execution, truthful observation by the losers);
terminal re-execute is a no-op; stale-running rescue (requeue within the
budget, abandoned at the bound); lost job input fails truthfully;
lock-held claims are observation-only; the worker sweep (queued →
succeeded, registry drained; stale-running abandoned); **the PUBLIC
env enqueue-only split** (POST returns queued, worker completes);
callback validation (accept/replay-reject/tamper/expiry/unconfigured);
RATE_LIMITED-is-retryable vs other API errors permanent);
`test_pub06_rate_limits.py` (8 — workspace bucket on path targets and
query targets with the 429 envelope + exempt health probe;
per-workspace independence; provider bucket trips on the 3rd dispatch
with replay-exemption; per-provider-id split (local vs demo); job-type
quota per workspace; anonymous demo-reads-only).

Acceptance mapping (§D PUB-06): idempotency test ✓, lock test
(concurrent dispatch → single execution) ✓, rate-limit tests per bucket
✓, retry/timeout tests ✓, LOCAL/PUBLIC parity of limiter semantics ✓
(plus the execution-split parity test).

## Unresolved findings / known limitations (truthful)

1. **Upstash live-path I/O is not covered by default tests (by design).**
   The REST engine's real HTTP transport (`urllib.request`, 5s timeout) is
   thin I/O; the command semantics are covered against a scripted fake
   transport. No Upstash credentials exist in this environment
   (operator-held, PUB-11 input). The first real-instance verification
   happens at the PUBLIC deploy (PUB-11) via `infra/upstash/setup.py` +
   the truthful health probe.
2. **`pyproject.toml` is outside the surface** — deliberate: the Upstash
   adapter is stdlib-only (REST over HTTPS), so NO new dependency is
   needed (contrast with PUB-05's asyncpg limitation — PUB-06 has none).
3. **Timeout semantics:** the per-attempt time bound covers the WAITING
   side (daemon-thread execution; a stuck thread dies with the process).
   A timed-out operation's late side effect surfaces as a duplicate-key
   conflict on the next attempt → idempotent convergence, never a
   fabricated success. Disclosed in `docs/deployment/jobs.md` §4.
4. **Coordination-plane loss windows (inherent to the directive's
   Redis-is-not-the-event-store rule):** (a) queued-but-unpicked jobs lose
   their pending registration → stay truthfully `queued`, re-driven on
   idempotent replay (which re-registers); (b) a job whose ephemeral
   input state expired fails honestly with "re-submit" guidance. Both are
   disclosed; neither can produce a status lie.
5. **Lock release is compare-then-delete** (no Lua compare-and-delete over
   REST): a release racing a lease expiry+re-acquire can delete a
   re-acquired lock — an efficiency cost only (the durable status guard
   under the lock is the correctness authority). Disclosed in
   `providers/upstash/cloud.py`.
6. **Worker adapter selection mirrors `main._build_adapters`** (the worker
   cannot import `services.api.main` without booting the API app at
   import time). Kept aligned by comment + review; both fail closed
   identically on cloud modes.
7. **`services.api.jobs.worker` cross-process LOCAL operation:** with
   in-process coordination, pending registrations are per-process; the
   LOCAL worker sweep serves tests and same-process queues (documented).
   Cross-process LOCAL workers are not a supported topology (use
   `SOS_COORDINATION=upstash`).

## Explicit statements

- **No unmerged sibling is a dependency:** PUB-01 (merged `c98972a`) and
  PUB-05 (merged `65e29ad`) are the only dependencies — both verified
  from the live merged `origin/main` at base `39e25ab`. PUB-04 (Worker B,
  in flight) and PUB-07 (Worker C, in flight) are NOT dependencies and
  were not built against.
- **No frozen surface touched:** `src/sos/**` untouched; frozen docs
  byte-identical (gate G01 PASS at this head); gate/test tooling
  untouched; every existing test file unmodified (all 638 pre-PUB-06
  tests pass unmodified).
- **No merge performed; no self-approval; no successor work items
  created.** This branch stops at WAITING_FOR_ARCHITECT.
