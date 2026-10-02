# PUB-01 Checkpoint — FastAPI control-plane adapter

**Work item:** PUB-01 (contract `spec/deployment/PUBLIC-DEPLOYMENT-CONTRACT.md` §D PUB-01; directive §4/§7/§16-A)
**Worker:** Worker A (session `pub-01-fastapi-adapter`)
**Status:** WAITING_FOR_ARCHITECT (review-ready; this is NOT completion)
**Branch:** `work/pub-01-fastapi-adapter`
**PR:** #25 (https://github.com/payswapdotorg/SOS/pull/25)
**Base SHA:** `7b1adb4a6461565d54d689a05bda159474646966` (live `origin/main` HEAD at dispatch; PUB-00 merged as `ad3bf5c`, PR #23)
**Implementation head (all code + tests; all verification below ran here):** `79a76e047ce332d0abc4346c9756f0a8ac9faa3c`
**Final branch head:** the checkpoint/state commit that follows the implementation head (adds only checkpoint/state documents — no code).

## Traceability

- Directive §4 (repository structure), §7 (API design), §8 (job architecture),
  §10 (GitHub integration), §12 (R2 artifact layout), §13 (rate limiting);
  contract §B (layout), §C (wire contract), §D PUB-01 (this work order),
  §G (gate matrix), §A frozen-surface rules.
- Dependencies: PUB-00 (MERGED as `ad3bf5c` — verified by actual Git
  evidence before work started). **No unmerged sibling dependency.**

## Files changed (equals the allowed surface exactly)

- `tools/final_gate_check.py` + `tests/test_w15_final_gate_check.py` — ONLY
  the §D PUB-01.1 G09 overlay-prefix reconciliation (first standalone
  commit `ea84ed2`).
- `services/**` — the FastAPI adapter (main/config/errors/container,
  schemas, auth, dependencies, routes, orchestration, testing support).
- `providers/**` — neon (persistence seam + LOCAL SQLite + fail-closed
  cloud placeholder), upstash (coordination), r2 (artifacts, §12 layout),
  github (source seam + fixture mode + fixture repository tree).
- `execution/adapters/**` — DemoProvider (W11 port via imported
  `sos.execution` types) + registry.
- `db/**` — migrations 0001–0003 (numbered, forward-creatable, reversible),
  runner, deterministic demo seed.
- `infra/environment.example` — additive names only
  (`SOS_LOCAL_DB_PATH`, `SOS_LOCAL_ARTIFACTS_DIR`).
- `pyproject.toml` — `[project.optional-dependencies].api` group ONLY
  (default test collection behavior unchanged).
- `tests/test_pub01*.py` — 7 NEW files (53 tests).
- `docs/deployment/**` — api-reference.md, database.md.
- `spec/development-state/PUB-01-checkpoint.md` (this file) and
  `spec/development-state/public-deployment-state.json` (PUB-01 status
  fields only).

**Frozen surface untouched:** `src/sos/**` byte-identical (G02 PASS);
all frozen docs byte-identical (G01 PASS); `implementation-state.json`
stays ROADMAP_COMPLETE (G03 PASS); no existing test file other than the
G09-scoped `tests/test_w15_final_gate_check.py` changes; `.github/workflows/test.yml`
untouched.

## What was delivered

1. **G09 overlay-prefix reconciliation (standalone first commit):**
   `POST_ROADMAP_OVERLAY_PREFIXES = (apps/, services/, providers/,
   execution/, db/, infra/, docs/deployment/, spec/deployment/)` — a path
   is exempt from the G09 artifact-pattern scan ONLY under those prefixes;
   the entire frozen surface remains fully scanned; the existing
   .git/.github/__pycache__/.pytest_cache walk exclusions are unchanged; the
   G09 PASS message states BOTH facts (frozen surface clean + allowlisted
   overlay governed by the contract). Precedent class: disclosed post-merge
   reconciliations 69c822f (state-aware G10) / a956325 (CI full-history
   checkout). No other gate logic touched (G01–G08, G10–G12 unchanged).
2. **`services/api/`** — the full `/api/v1` surface (exactly directive §7):
   health (truthful per-adapter), auth/* (LOCAL deterministic stub; refused
   outside SOS_ENV=local), me, workspaces (+embedded activity trail),
   missions (+revisions), systems (+recovery), evidence, hypotheses,
   candidates, assurance, decisions, authorizations, experiments,
   executions, learning, memory, jobs, providers/* — plus
   `/api/v1/openapi.json`. Wire contract §C.2/§C.3 enforced: collection
   envelope, error envelope with the eight semantic codes, truth states and
   decision actions imported verbatim from `sos.model`.
3. **Thin-route discipline:** every route = authenticate → tenant-authorize
   → validate → domain orchestration (importing `sos.*`) → persist → typed
   DTO. The domain seam (`services/api/orchestration.py`) maps rows ↔
   domain objects and drives the frozen engines; no SOS decision logic in
   routes; no second authority.
4. **Provider seams + LOCAL implementations** (cloud placeholders fail
   closed with precise PUB-05/06/07/08 errors — never silent fallback).
5. **`db/`** — reversible migrations + runner; the deterministic demo seed
   constructed through the REAL engines: `sos.recovery.recover_repository`
   (brownfield system at a pinned fixture commit), W4 evidence of all 7
   wire kinds and all 6 truth states, W5 causal hypotheses
   (intervention-grade support with provenance-consistent metadata), W6
   candidates, `assure_candidate` (PASS + UNKNOWN), W8 experiment lifecycle
   + `evaluate_experiment` + `PromotionGate`, `evaluate_autonomy` (ACT via
   the full governed chain; ASK via blast-radius ceiling), `ExecutionSubstrate`
   dispatch (DemoProvider receipt, demo:true), learning/memory, jobs, audit.
6. **Governed execution dispatch:** POST /executions and POST /jobs build
   the W11 request from persisted rows and submit through the REAL
   substrate — all authority gates run BEFORE any provider call; receipts
   persist under the §12 artifact layout (content-addressed) and convert to
   W4 evidence via `receipt_to_w4_evidence`; simulated failure intents
   (`demo:fail`, `demo:unknown`) surface FAILED/UNKNOWN verbatim;
   idempotency keys and content-addressed ids prevent duplicate side
   effects.
7. **Rate limiting (§13):** per-IP, anonymous, user, write, job-type and
   recovery buckets behind the coordination seam; S16 body cap (413);
   health endpoint exempt (readiness); coordination-plane failure fails
   closed for protected traffic (503) while health reports the true state.
8. **53 deterministic tests** across 7 new files (hermetic; no network; no
   env; `importorskip` keeps the dependency-free frozen CI green).
9. **Docs:** `docs/deployment/api-reference.md`, `docs/deployment/database.md`.

## Verification commands + verbatim results

Run at the implementation head `79a76e047ce332d0abc4346c9756f0a8ac9faa3c`
(re-run after every subsequent doc-only commit — identical results; the
checkpoint and state updates add no code):

```text
$ python3 -m pytest
606 passed in 17.72s

$ python3 -m compileall -q src tests services providers execution
(clean; no output; exit 0)

$ python3 tools/final_gate_check.py
G09 ROLLBACK_SAFETY [rollback safety]: PASS
OVERALL: PASS — 12/12 checks PASS (0 FAIL, 0 DEFERRED) at 79a76e0…
(exit 0; followed by `git restore spec/development-state/W15-gate-report.json`
to keep the tree clean — the gate rewrites its own report file)

$ python3 -m uvicorn services.api.main:app --port 8099   # zero env vars
INFO: Uvicorn running on http://127.0.0.1:8099
$ curl http://127.0.0.1:8099/api/v1/health
{"status": "ok", "checks": {"persistence": {"status": "SUCCESS", "mode": "local",
"detail": "sqlite ok (3 workspaces) at local.sqlite3"}, "coordination": {"status":
"SUCCESS", "mode": "local", "detail": "in-process coordination ok"}, "artifacts":
{"status": "SUCCESS", "mode": "local", "detail": "local artifact store writable at
/tmp/sos-api/artifacts"}, "execution": {"status": "SUCCESS", "mode": "demo",
"detail": "DemoProvider registered (always available; simulation only, receipts
demo:true)"}}}    # then the server was stopped

$ curl http://127.0.0.1:8099/api/v1/workspaces
{"items": [{"id": "ws-demo", "name": "SOS Demo Workspace", "slug": "demo",
"createdAt": "2026-05-01T09:00:00Z", "isDemo": true}], "nextCursor": null}

$ curl -o /dev/null -w "%{http_code}" http://127.0.0.1:8099/api/v1/openapi.json
200
```

Baseline before work started (main `7b1adb4`): 551 passed / compileall
clean / final gate 12/12 PASS (recorded in the dispatch packet; re-verified
at bootstrap).

## Known limitations (disclosed)

- **Auth is the LOCAL deterministic stub** (clearly labeled
  `local-stub`/`stub: true`); real GitHub OAuth (state + PKCE, session
  cookies, CSRF) arrives with PUB-04 per the work order. Stub login is
  refused outside `SOS_ENV=local`.
- **Neon/Upstash/R2/Apify adapters are fail-closed placeholders** — the
  seams/interfaces are final for this slice; the cloud implementations
  arrive with PUB-05/06/07/08.
- **Jobs execute in-process in LOCAL mode** (bounded, synchronous); the
  separate worker process arrives with PUB-06.
- **Decision/authorization surfaces are read-only** in PUB-01 (the seed and
  the dispatch flow write them through the governed loop); journey-level
  authoring arrives with PUB-04+.
- **`INTERNAL` error code:** a reserved last-resort fault-barrier code for
  unexpected exceptions (the contract enumerates the eight semantic codes;
  INTERNAL never carries resource semantics). Disclosed for review.
- **Activity trail** surfaces embedded in `GET /workspaces/{id}`
  (`recentActivity`) rather than a separate endpoint, keeping the endpoint
  set exactly the directive §7 surface.
- **PUB-01 API tests require the `api` dependency group** (fastapi/uvicorn/
  pydantic/httpx); they skip cleanly when absent so the frozen
  dependency-free CI stays green. PUB-03 adds the `pub` workflow running
  the full matrix with the group installed.
- `services/api/testing.py` is test-support code inside the allowed
  `services/**` surface (no repo-root conftest was created — only
  `tests/test_pub01*.py` files are permitted in `tests/`).

## Explicit statements

- **No unmerged sibling dependency** (PUB-00 merged as `ad3bf5c`, verified
  in Git before work).
- **No frozen surface touched** (`src/sos` byte-identical; frozen docs
  byte-identical; gate logic changed ONLY per §D PUB-01.1).
- **No merge of PUB-01 into main performed**; no self-approval; no
  successor work item created. (One main→branch SYNC-merge of the TL's
  wave-1 dispatch record `73742ce` is recorded in branch history solely to
  resolve the textual overlap in the state JSON — it merges main INTO the
  branch, not this work into main; disclosed in its commit message.)
- Architecture Change Requests: **none** — no `src/sos` change was
  required.
- Stopping at **WAITING_FOR_ARCHITECT**.
