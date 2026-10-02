# SOS Public Deployment Contract

**Status:** ACTIVE — BINDING WORK-ORDER CONTRACT for the Public Deployment Overlay
**Authority chain:** `spec/deployment/PUBLIC-DEPLOYMENT-DIRECTIVE.md` (operator
directive, verbatim) → this contract → `PUBLIC-DEPLOYMENT-WORKERS.md` (dispatch
model) → `PUBLIC-DEPLOYMENT-SECURITY.md` (security gate) →
`PUBLIC-DEPLOYMENT-CHECKLIST.md` (completion ledger) →
`spec/development-state/public-deployment-state.json` (machine state).
**Position:** post-roadmap productization overlay (PUB-00 … PUB-13). The frozen
W0–W15 artifacts remain authoritative for SOS semantics (directive §1). House
law (`AGENTS.md`, `ARCHITECT_START_HERE.md`,
`docs/implementation/SOS-IMPLEMENTATION-PROCESS.md`) applies in full to this
program unless this contract narrows it further.

## A. Frozen-surface rules (ALL workers, ALL items)

1. **`src/sos/` is immutable.** Zero file additions, modifications or deletions.
   G02 (exactly the 14 baseline modules + `__init__.py`) must hold at every
   merge. Adapters IMPORT `sos.*`; they never edit it. If a worker believes a
   `src/sos` change is required, it stops and raises an Architecture Change
   Request (process §12) in its checkpoint — never implements it.
2. **Frozen documents stay byte-identical:** `spec/architecture.md`,
   `spec/architecture-lock.md`, `spec/requirements.md`,
   `spec/implementation-roadmap.md`, `spec/constitution.md` (G01), plus all
   `spec/work-orders/W*.md`, `spec/development-state/W*-checkpoint.md`,
   `spec/development-state/W15-final-sign-off.md`,
   `spec/development-state/W15-gate-report.json`,
   `spec/development-state/implementation-state.json` (stays
   `ROADMAP_COMPLETE`, `currentFrontier: []`, `currentTask: null` — G03),
   `spec/development-state/current-state.md`, `AGENTS.md`,
   `ARCHITECT_START_HERE.md`, `tools/final_gate_check.py` §frozen-doc logic.
3. **`tools/final_gate_check.py` + `tests/test_w15_final_gate_check.py` change
   ONLY as specified in §D PUB-01 (the G09 overlay-prefix allowlist).** No other
   gate logic may change in any PUB item.
4. **Overlay roots** (the only places new code/artifacts may live):
   `apps/`, `services/`, `providers/`, `execution/`, `db/`, `infra/`,
   `docs/deployment/`, `spec/deployment/`, plus `spec/development-state/public-deployment-state.json`
   and per-item `spec/development-state/PUB-XX-checkpoint.md` files.
   `.github/workflows/` may gain PUB CI jobs without touching the existing
   `tests` workflow's full-history checkout semantics.
5. **Semantic authority stays in `src/sos`.** Route handlers, web components and
   providers contain no SOS decision logic, no autonomy-policy interpretation,
   no evidence-status invention, no promotion decisions. Transport/adapters map
   and delegate. LLM output remains proposal material (architecture-lock).
6. **Truth states are preserved end-to-end:** `SUCCESS`, `EMPTY`, `FAILED`,
   `UNKNOWN`, `UNSUPPORTED`, `UNAVAILABLE` survive every layer (DB → API → UI)
   with no silent conversion (architecture invariant 6; directive §5/§19).
7. **G09 pattern discipline for wave-1 siblings:** any path matching the G09
   deployment-artifact patterns (`dockerfile`, `docker-compose`, `terraform`,
   `.tf`, `.tfvars`, `helm/`, `k8s/`, `kubernetes/`, `migrations/`, `alembic`,
   `.sql`) may land only AFTER PUB-01's G09 overlay-prefix reconciliation is
   merged. PUB-02/PUB-03 branches must not introduce pattern-matching paths
   (PUB-03's Apify actor skeleton carries no Dockerfile; the actor's Dockerfile
   lands with PUB-08).

## B. Repository layout contract

Exactly the directive §4 tree. Additions inside overlay roots must follow:

```text
apps/web/          Next.js 16 App Router + TypeScript; package.json with
                   lint/typecheck/test scripts; typed API client in lib/; fixture
                   demo mode; no server-side SOS semantics.
services/api/      FastAPI; main.py app factory; routes/ (thin), auth/,
                   dependencies/ (session/tenant), schemas/ (pydantic wire DTOs).
providers/         one package per provider (neon/, upstash/, r2/, apify/,
                   github/) each exposing a LOCAL implementation and a cloud
                   implementation of one provider-neutral interface.
execution/adapters/ ExecutionSubstrate adapters: demo.py, apify.py, registry.
db/migrations/     forward-creatable, reversible schema migrations (SQL files +
                   runner); db/seeds/ deterministic demo seed data.
infra/             render.yaml, environment.example, apify/, deployment docs.
```

## C. API contract (binding wire rules)

### C.1 Surface

Exactly the directive §7 endpoint set under `/api/v1`, plus
`GET /api/v1/openapi.json` (FastAPI-generated) and
`GET /api/v1/health` → `{"status": "ok"|"degraded", "checks": {...}}` (readiness:
persistence, coordination, artifacts, execution — each reported truthfully; a
LOCAL-mode deployment reports the local adapters).

### C.2 Envelope

- Single-resource responses: the DTO object.
- Collections: `{"items": [...], "nextCursor": string|null}` (cursor pagination).
- Errors: `{"error": {"code": string, "message": string, "details": object|null}}`.
  Error codes: `UNAUTHENTICATED`, `FORBIDDEN`, `NOT_FOUND`, `VALIDATION`,
  `CONFLICT`, `RATE_LIMITED`, `PAYLOAD_TOO_LARGE`, `PROVIDER_UNAVAILABLE`.
  Transport errors (HTTP 4xx/5xx) never masquerade as resource truth states.
- Resource truth-state enums live ON the DTOs (`status` fields), values exactly:
  `SUCCESS | EMPTY | FAILED | UNKNOWN | UNSUPPORTED | UNAVAILABLE`.
- Every mutation carries an audit event (actor, action, target, timestamp, meta)
  persisted in `audit_events`.

### C.3 DTO minimums (field names binding; full types owned by `services/api/schemas`)

- `Workspace` {id, name, slug, createdAt}
- `User` {id, githubId, login, displayName, createdAt}
- `Mission` {id, workspaceId, title, status, currentRevisionId}
- `MissionRevision` {id, missionId, revision, goals, outcomes, stakeholders,
  measures, constraints, preferences, approval{state,requestedBy,decidedBy,decidedAt}}
- `System` {id, workspaceId, name, mode(greenfield|brownfield), currentRevisionId}
- `SystemRevision` {id, systemId, revision, stateSummary, uncertainty,
  sourceRef{kind,url,revision,immutable}, recovery{jobId,status}}
- `ArchitectureGraph` {nodes[], edges[]} (typed to W2 semantics via schema mapping)
- `Evidence` {id, workspaceId, systemId?, kind(source_revision|runtime_observation|
  test_result|telemetry|environment|experiment|business_outcome), status(6-state),
  provenance, timestamp, sourceRevision, relatedSystemState, confidence,
  artifactRef?}
- `Hypothesis` {id, statement, causal{…}, evidenceRefs, status}
- `Candidate` {id, name, subgraphReplacement, effects, costs, risks, constraints,
  evidenceRefs, reversibility, evaluation{objectives[], paretoFront}}
- `AssuranceRun`/`AssuranceResult` {id, candidateId, checks[], verdict}
- `Decision` {id, action(ACT|EXPERIMENT|GATHER_EVIDENCE|ASK|REJECT|ROLLBACK),
  rationale, evidenceRefs, authoritySnapshot, expectedImpact, risk, blastRadius,
  reversibility, requiredApprovals, askPayload?{decision,alternatives,
  evidenceQuality,uncertainty,tradeoffs}}
- `Authorization` {id, decisionId?, principal, scope, decision(granted|denied)}
- `Experiment` {id, candidateId, status(lifecycle), events[]}
- `Execution` {id, experimentId?, provider(demo|apify), requestHash, receipt?,
  artifactRefs, status}
- `LearningRecord` / `MemoryEntry` {id, context, candidate, predictedEffects,
  actualEffects, uncertainty, verdict, lessons}
- `Job` {id, tenantId, type, requestedBy, authoritySnapshot, inputHash,
  sourceRevision, provider, status, startedAt, completedAt, receipt,
  artifactRefs, errorState} — fields exactly per directive §8.
- Provider callback bodies: signed envelopes (HMAC), replay-protected (nonce +
  timestamp window), validated before any state mutation (§SECURITY).

### C.4 Thin-layer rule

Every route: authenticate → tenant authorize → validate (pydantic) → call a
domain orchestration function → persist → return DTO. Any file under
`services/api/routes/` exceeding thin-controller responsibility (business/
semantic logic) is a contract violation (review finding class `PUB-F-LOGIC`).

## D. Per-item work orders

Each item follows the house Work Order template (roadmap §"Work Order execution
template"). One bounded slice per branch/PR. Workers stop at
`WAITING_FOR_ARCHITECT` (review-ready), never merge their own work.

---

### PUB-00 — Deployment contract + repository layout (TL)

- **Traceability:** directive §1, §4, §17, §23; AGENTS.md repository-only rule.
- **Dependencies:** none (baseline = verified terminal main).
- **Owner:** TL (this delivery; documents + infra skeletons only, no application code).
- **Scope:** persist the directive verbatim; this contract; WORKERS; SECURITY;
  CHECKLIST; `public-deployment-state.json`; `infra/render.yaml` skeleton;
  `infra/environment.example`.
- **Acceptance:** all §17 artifacts exist on `main`; state JSON parses; frozen
  docs untouched; `pytest` 551 passed; `final_gate_check.py` 12/12.
- **Verification:** §G gate matrix (python parts).

---

### PUB-01 — FastAPI control-plane adapter (Worker A)

- **Traceability:** directive §4, §7, §16-A; design §1, §4, §C.
- **Dependencies:** PUB-00.
- **Scope:**
  1. **G09 overlay-prefix reconciliation (FIRST commit of the branch, standalone):**
     add `POST_ROADMAP_OVERLAY_PREFIXES` (exactly `apps/`, `services/`,
     `providers/`, `execution/`, `db/`, `infra/`, `docs/deployment/`,
     `spec/deployment/`) to `tools/final_gate_check.py`; exclude exactly those
     prefixes from the G09 artifact-pattern scan; G09 PASS message states
     frozen-surface clean + overlay allowlisted under this contract; update the
     corresponding test expectations in `tests/test_w15_final_gate_check.py`
     coherently; no other gate logic touched. Disclose in the checkpoint.
  2. `services/api/` FastAPI app factory, `/api/v1` router, health/readiness
     (truthful per-adapter checks), request logging to `audit_events`.
  3. Provider-neutral seams + LOCAL implementations: persistence (SQLite),
     coordination (in-process), artifacts (local FS), execution (DemoProvider),
     GitHub source adapter (local fixture mode: canned repo metadata).
  4. `services/api/schemas/`: pydantic DTOs for the FULL §C surface; OpenAPI
     export verified in tests.
  5. Environment/config module consuming `infra/environment.example` names;
     fail-closed on missing required config (no silent defaults for secrets).
  6. Migration runner scaffolding (`db/migrations/` conventions: numbered,
     forward-creatable, reversible; SQLite + Postgres compatible DDL strategy).
  7. Deterministic tests: route-level API tests (LOCAL adapters), auth/tenant
     boundary tests (401/403/404 isolation), truth-state preservation tests,
     schema/OpenAPI snapshot test.
- **Allowed surface:** `services/**`, `providers/**`, `execution/adapters/**`,
  `db/**`, `infra/environment.example` (name additions only, backward-compatible),
  `tools/final_gate_check.py` + `tests/test_w15_final_gate_check.py` (G09
  reconciliation ONLY), `tests/test_pub01*.py` (NEW files only — every existing
  test file is frozen surface), `spec/development-state/PUB-01-checkpoint.md`,
  `spec/development-state/public-deployment-state.json` (status fields only, via
  checkpoint discipline), `docs/deployment/**` (API reference doc),
  `pyproject.toml` (dependency group for the API, without changing default
  test collection behavior).
- **Forbidden:** `src/sos/**`; frozen docs; any gate logic beyond §D.1;
  cloud credentials in Git; network calls in default tests.
- **Acceptance:** gate matrix green (incl. 12/12 gate with overlay-scoped G09);
  `uvicorn` boots LOCAL mode with zero env vars; health reports local adapters;
  OpenAPI served; demo seed loads; 401/403/404 isolation tests pass.

---

### PUB-02 — Next.js public cockpit (Worker B)

- **Traceability:** directive §5, §16-B; design §1, §13.
- **Dependencies:** PUB-00 (builds against the CONTRACT schemas + fixtures, not
  against PUB-01 code — no unmerged sibling dependency).
- **Scope:** `apps/web/` Next.js 16 App Router + TypeScript: landing (Explore
  Demo / Sign in with GitHub), workspace shell (Mission/Systems/Evidence/
  Candidates/Experiments/Decisions/Memory/Activity), mission journey editor
  (goals→outcomes→stakeholders→measures→constraints→preferences→approve
  revision), greenfield/brownfield onboarding UI (mode distinction explicit),
  evidence explorer (7 kinds, 6 truth states, artifact links), candidate
  comparison (multi-objective rows; NO single AI score), assurance view,
  decision panel (visible rationale/authority/evidence/risk/blast-radius/
  reversibility/required-approvals; ASK as a real UI state with approve/reject/
  provide-evidence actions), experiment lifecycle, execution receipts, learning/
  memory, activity/audit trail. Typed API client generated from (or validated
  against) the contract schemas; **fixture/demo mode** serves Journey-1 content
  client-side when no API is configured; all API calls relative URLs with
  configurable base; honest loading/error/empty states everywhere.
- **Allowed surface:** `apps/web/**`, `spec/development-state/PUB-02-checkpoint.md`,
  state JSON status fields, `docs/deployment/**` (UI guide).
- **Forbidden:** everything outside `apps/web` (except checkpoint/state/docs);
  any SOS decision logic in the client; secrets; absolute API URLs.
- **Acceptance:** `bun run lint`, `bun run typecheck`, `bun test` green;
  fixture-mode demo renders all §5 surfaces; responsive; accessibility basics
  (semantic HTML, keyboard navigation, labels); no console errors.

---

### PUB-03 — Free-tier infrastructure (Worker C)

- **Traceability:** directive §3, §16-C, §20, §21.
- **Dependencies:** PUB-00.
- **Scope:** final `infra/render.yaml` (free service, Python runtime, rootDir
  `services/api`, health check `/api/v1/health`, env wiring per
  `environment.example`, spin-down notes); Vercel project config for `apps/web`
  (framework preset, API base env, no long-running work); Neon/Upstash/R2 setup
  runbooks + scripts (`infra/` — idempotent, documented, operator-executed);
  environment templates complete; CI additions: a `pub` workflow running the
  §G gate matrix (python parts + apps/web checks) on PRs touching overlay roots,
  without modifying the existing `tests` workflow semantics; preview-environment
  guidance (Vercel preview + Neon branch); deployment runbook (Stage A private →
  B public read → C beta, with the credential inputs listed as operator-held);
  Apify actor project skeleton under `infra/apify/` (package metadata + input
  schema + stub entry; NO Dockerfile in this item — the actor's Dockerfile lands
  with PUB-08, after PUB-01's G09 reconciliation is merged).
- **Allowed surface:** `infra/**`, `.github/workflows/pub*.yml` (new files only),
  `docs/deployment/**`, checkpoint/state.
- **Forbidden:** actual cloud credentials anywhere; touching the existing
  `tests` workflow; app code.
- **Acceptance:** render.yaml passes `render blueprint validate`-equivalent
  structural checks (or documented manual validation); CI workflow syntax-valid
  and runs the matrix; runbooks complete and honest about operator inputs.

---

### PUB-04 — GitHub authentication + tenancy (Worker B)

- **Traceability:** directive §6, §16-B.
- **Dependencies:** PUB-01, PUB-02 (both merged).
- **Scope:** GitHub OAuth device/web flow against `services/api` (state + PKCE,
  session cookies httpOnly/secure/sameSite, CSRF protection on mutations);
  `User`→`Workspace`→membership model (PUB-05 tables via migrations); session
  validation dependency; tenant-aware navigation and protected actions in
  `apps/web` (sign-in callback, workspace creation, member roles owner/member);
  LOCAL mode: a documented deterministic fake-GitHub provider (fixtures, clearly
  labeled) so the full flow is testable without secrets; logout; rate-limited
  auth endpoints.
- **Allowed surface:** `apps/web/**`, `services/api/auth/**`,
  `services/api/routes/auth*`, `providers/github/**`, `db/migrations/**`,
  `tests/test_pub04*.py` (new files only), checkpoint/state, docs.
- **Forbidden:** browser-supplied tenant identifiers; storing OAuth tokens in
  the browser; weakening the §SECURITY auth rules.
- **Acceptance:** gate matrix green; auth+tenancy integration test in LOCAL
  mode (login → workspace create → tenant isolation 403/404 → logout);
  Journey-2 (with fake-GitHub) passes locally end-to-end.

---

### PUB-05 — Neon persistence (Worker A)

- **Traceability:** directive §11, §16-A; design §5.
- **Dependencies:** PUB-01.
- **Scope:** full relational schema (§11 minimum) as numbered reversible
  migrations; the Neon adapter implementation of the persistence seam
  (PostgreSQL via async driver; Neon serverless-compatible); domain-object ↔
  row mapping for the persisted entity set (missions/revisions, systems/
  revisions, architecture nodes/edges, evidence + artifacts, hypotheses,
  candidates + evaluations, assurance runs/results, decisions,
  authorizations, experiments + events, execution requests/receipts,
  learning records, architecture memory, jobs, audit events); tenant-scoped
  queries ONLY (enforced at the adapter, not per-route); seed loader for the
  deterministic demo dataset; LOCAL (SQLite) and Neon parity tests (same
  migration set, same mapping tests, run against both backends).
- **Allowed surface:** `providers/neon/**`, `db/**`, `services/api` persistence
  wiring, `tests/test_pub05*.py` (new files only), checkpoint/state, docs.
- **Forbidden:** blobs in Postgres; denormalized semantic re-interpretation
  (mapping only — semantics stay in `src/sos`); touching frozen state.
- **Acceptance:** gate matrix green; parity suite passes on SQLite AND Postgres
  (a real Postgres in CI or LOCAL `pg`); demo seed loads in both; migrations
  up/down round-trip cleanly.

---

### PUB-06 — Upstash job/coordination layer (Worker A)

- **Traceability:** directive §8, §13, §16-A.
- **Dependencies:** PUB-01, PUB-05.
- **Scope:** job model (exact directive §8 fields); idempotency keys
  (duplicate POST /jobs → same job, no duplicate side effects); orchestration
  locks; retry policy (bounded, jittered, disclosed backoff); job status
  lifecycle; provider dispatcher (local bounded operations + handoff to the
  execution seam); rate limiting middleware with the directive §13 buckets
  (anonymous demo-reads-only, authenticated, workspace, job type, provider, IP);
  Upstash adapter + in-process LOCAL implementation with identical semantics;
  job worker entrypoint (separate process from the API in PUBLIC mode; in
  LOCAL mode, an in-process bounded executor for tests).
- **Allowed surface:** `providers/upstash/**`, `services/api` job routes/
  dependencies wiring, `db/migrations` (job tables if PUB-05 didn't cover),
  `infra/**` (worker config), `tests/test_pub06*.py` (new files only),
  checkpoint/state, docs.
- **Forbidden:** Redis as the primary event store (jobs are durable in Neon/
  SQLite; Redis holds only ephemeral coordination); unbounded work in the API
  process.
- **Acceptance:** gate matrix green; idempotency test (same key → one job);
  lock test (concurrent dispatch → single execution); rate-limit tests per
  bucket; retry/timeout tests; LOCAL/PUBLIC parity of limiter semantics.

---

### PUB-07 — R2 evidence/artifact layer (Worker C)

- **Traceability:** directive §12, §16-C(provider lane); design §5.
- **Dependencies:** PUB-01.
- **Scope:** artifact-store seam implementation: LOCAL (content-addressed local
  FS store with the same key layout) and R2 (S3-compatible API); deterministic
  key layout per directive §12; signed upload/download URLs (time-bounded,
  scoped to the exact object key); private-bucket defaults; artifact size
  limits; `evidence_artifacts` wiring (metadata in DB, bytes in the store);
  upload/download endpoints (authenticated, tenant-scoped, rate-limited);
  audit events for artifact operations.
- **Allowed surface:** `providers/r2/**`, `services/api` artifact routes,
  `tests/test_pub07*.py` (new files only), checkpoint/state, docs.
- **Forbidden:** R2 secrets to the browser; public buckets; unbounded uploads;
  storing artifact bytes in Postgres.
- **Acceptance:** gate matrix green; LOCAL artifact store round-trip tests;
  key-layout determinism tests; signed-URL expiry/scope tests; size-limit
  rejection tests.

---

### PUB-08 — Apify bounded execution provider (Worker C)

- **Traceability:** directive §9, §16-C; design §7.
- **Dependencies:** PUB-06, PUB-07.
- **Scope:** `execution/adapters/apify.py` (maps the W11 substrate contract —
  imported, unmodified — to Apify runs); the Apify actor under `infra/apify/`
  (bounded job input: authorized action, exact source revision, allowed
  operation, resource limits, time limit, artifact policy, callback target,
  request hash); signed callback endpoint on the API (HMAC envelope, nonce
  replay protection, timestamp window, validated BEFORE any state mutation);
  execution receipt conversion → evidence records → promotion/rollback state
  (through `src/sos` domain services, never in the adapter); failure/timeout
  handling (FAILED evidence, no false SUCCESS, bounded retries, learning
  records); DemoProvider parity (same receipt/evidence semantics, explicitly
  marked demo); low-concurrency semaphore for Apify dispatch.
- **Allowed surface:** `execution/adapters/**`, `providers/apify/**`,
  `infra/apify/**`, `services/api` callback route, `tests/test_pub08*.py`
  (new files only), checkpoint/state, docs.
- **Forbidden:** the provider deciding authorization; executing arbitrary user
  repository code in the Render API process; unsigned callback acceptance.
- **Acceptance:** gate matrix green; callback signature/replay tests
  (tampered, replayed, expired → rejected, no state change); receipt→evidence
  conversion tests; failure-path tests (FAILED evidence recorded, rollback
  path present, learning record written); DemoProvider truthfulness tests.

---

### PUB-09 — Integrated user journeys (TL-coordinated; A+B+C contributions)

- **Traceability:** directive §18 Journeys 1–7; design §13.
- **Dependencies:** PUB-04, PUB-05, PUB-06, PUB-07, PUB-08.
- **Allowed surface:** `tests/test_pub09*.py` (new files only), journey scripts
  under `docs/deployment/`, integration wiring inside the existing overlay
  roots, checkpoint/state.
- **Scope:** end-to-end journey wiring in LOCAL mode: Journey 1 anonymous demo;
  Journey 2 new user (fake-GitHub LOCAL); Journey 3 brownfield recovery
  (fixture repo metadata → recovery job → uncertainty + evidence + candidates);
  Journey 4 governed optimization (candidate → assurance → experiment →
  authorization → DemoProvider execution → receipt → evidence → promotion
  decision surfaced); Journey 5 ASK (insufficient authority → ASK state → user
  approves/rejects → lifecycle continues); Journey 6 failure (provider failure
  → FAILED evidence, no false SUCCESS, rollback path, learning record);
  Journey 7 provider isolation (adversarial probes, see SECURITY). Browser-
  level verification of the UI paths; API-level assertions for each step;
  documented journey scripts under `docs/deployment/`.
- **Acceptance:** all seven journeys pass in LOCAL mode with machine-checkable
  evidence (test suite + scripted browser run); the §G matrix green.

---

### PUB-10 — Security/adversarial verification (Worker C + independent review)

- **Traceability:** directive §19 (all 21 checks); `PUBLIC-DEPLOYMENT-SECURITY.md`.
- **Dependencies:** PUB-09.
- **Allowed surface:** `tests/test_pub10*.py` (new files only), fixes inside the
  overlay roots for findings, checkpoint/state, evidence records under
  `docs/deployment/`.
- **Scope:** adversarial test battery implementing every §19 check as an
  executable test or documented verification with evidence: secret scanning
  (repo + browser bundle), tenant isolation (cross-tenant probes 403/404),
  CSRF, auth-required mutations, rate limits, job idempotency, callback replay
  protection, exact source revision recording, provider-cannot-self-authorize
  probes, no-arbitrary-code-in-API proof (static + runtime probes), Apify
  resource bounds, artifact/request size limits, audit trail completeness,
  truth-state preservation, ASK-cannot-become-ACT, ACT-cannot-bypass-assurance,
  demo-cannot-mutate-other-tenants. Plus an adversarial review pass of the whole
  overlay diff (fresh reviewer session recommended).
- **Acceptance:** every §19 line has an executable check that PASSES (or a
  documented operator-input blocker honestly recorded); adversarial probes
  red-team the seams; findings fixed or filed.

---

### PUB-11 — Public demo deployment (Stage B)

- **Traceability:** directive §21 Stage B; §20 PUBLIC environment.
- **Dependencies:** PUB-10; operator-held provider accounts/credentials.
- **Scope:** deploy PUBLIC stack (Vercel production web, Render public API,
  Neon production branch, Upstash production DB, R2 production bucket,
  DemoProvider execution); public read/demo mode enabled (anonymous demo reads
  only; all writes authenticated); production smoke verification of Journey 1
  from the public URL; deployment record with URLs, revisions and evidence.
- **Acceptance:** public URL serves the demo; Journey 1 verified from the
  public internet; writes require auth; deployment record persisted.

---

### PUB-12 — Authenticated beta deployment (Stage C)

- **Traceability:** directive §21 Stage C.
- **Dependencies:** PUB-11.
- **Scope:** enable authenticated flows in PUBLIC (GitHub OAuth live, workspace
  creation, mission/repo onboarding, bounded recovery, candidates,
  experiments, DemoProvider execution jobs; Apify quota-gated); deliberately
  low expensive-execution quotas; monitoring/health checks; operator runbook
  for quota incidents.
- **Acceptance:** Journeys 2–5 verified live (or honestly recorded as blocked
  on external inputs); quotas enforced; health endpoints truthful.

---

### PUB-13 — Final deployment Architect gate

- **Traceability:** directive §23 (final state); §16 TL/Architect final launch gate.
- **Dependencies:** PUB-12.
- **Scope:** the final review gate: re-run the full §G matrix at the final
  head; re-verify all seven journeys; re-verify the §19 security battery;
  verify provider-isolation invariants; verify the frozen W0–W15 gate still
  passes (12/12, overlay-scoped G09); verify frozen docs byte-identical; verify
  the state JSON ledger is complete and consistent; independent-context review
  (fresh reviewer session, zero implementation exposure — the W13–W15
  discipline) with the verdict recorded; TL sign-off record authored
  (`spec/development-state/PUB-13-final-sign-off.md`); terminal reconciliation
  of `public-deployment-state.json` → `DEPLOYMENT_COMPLETE`.
- **Acceptance:** sign-off record APPROVED; every §23 line ⬜→✅ with evidence;
  no fabrication (all evidence re-runnable from the repo).

## E. Worker discipline

Per `PUBLIC-DEPLOYMENT-WORKERS.md` (dispatch model, lifecycle, rotation,
reporting) and house law: one bounded slice per branch/PR; workers never merge,
never self-approve, never create successor work; corrections stay on the same
PR; `WAITING_FOR_ARCHITECT` is the review-ready stop state; a truthful blocked
report is always acceptable.

## F. Anti-fabrication truth rules (binding)

1. A completion claim is valid ONLY with the exact branch head pushed to the
   remote AND the TL able to fetch that exact ref (remote-ref truth gate —
   the W14 fabrication incident is standing precedent).
2. Reported verification numbers are never trusted: the TL re-runs every gate
   fresh at the exact reviewed head.
3. Blocked-by-capacity or blocked-by-credentials reports are legitimate
   checkpoint states (`WAITING_FOR_CAPACITY`), not failures.
4. Any fabricated evidence voids the session and its work (dispatch law).

## G. Gate matrix (every PUB merge, exact head)

```text
python3 -m pytest                                   # hermetic, green, no network
python3 -m compileall -q src tests services providers execution
python3 tools/final_gate_check.py                   # 12/12 PASS, exit 0
cd apps/web && bun install && bun run lint && bun run typecheck && bun test
```

(from PUB-02 onward; earlier items run the python parts + any web parts they
introduce). CI runs the same matrix via the `pub` workflow (PUB-03). The
existing `tests` workflow must remain green on every head (full-history
checkout semantics untouched).

## H. Completion boundary

A PUB item is complete ONLY through: implementation → exact-head verification
(TL re-run) → checkpoint → review (Architect/TL per the WORKERS rotation;
independent-context review for PUB-13) → actual Git merge → canonical
reconciliation of `public-deployment-state.json` (merge SHA + frontier
recompute). Code existing, tests passing, a PR being open, or an agent saying
"done" never establishes completion (house completion rule). The overlay
program is complete when PUB-13's sign-off is APPROVED and every §23 line
carries verified evidence — or carries an honestly recorded external-input
blocker (operator-held credentials) with everything else verified.
