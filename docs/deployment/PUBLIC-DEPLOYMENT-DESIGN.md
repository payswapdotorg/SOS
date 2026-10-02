# SOS Public Deployment Design

**Status:** ACTIVE — Public Deployment Overlay design authority (PUB-00)
**Directive record:** `spec/deployment/PUBLIC-DEPLOYMENT-DIRECTIVE.md` (operator, 2026-10-02, verbatim)
**Binding contract:** `spec/deployment/PUBLIC-DEPLOYMENT-CONTRACT.md`
**Position:** This design governs the POST-ROADMAP productization layer only. The
frozen W0–W15 artifacts (`spec/architecture.md`, `spec/architecture-lock.md`,
`spec/requirements.md`, `spec/implementation-roadmap.md`, `spec/constitution.md`,
all `spec/work-orders/W*.md`, all `spec/development-state/W*-checkpoint.md` and the
W15 sign-off) remain byte-frozen and authoritative for SOS semantics. Nothing in
this overlay reopens, reinterprets or amends them.

## 0. Verified baseline

This program starts from a personally re-verified terminal state (TL, 2026-10-02,
fresh full clone of `payswapdotorg/SOS` @ `ddc88a6`):

- `python3 -m pytest` → **551 passed** (0 failed)
- `python3 -m compileall -q src tests` → **CLEAN**
- `python3 tools/final_gate_check.py` → **OVERALL: PASS — 12/12** (exit 0)
- Machine state: `ROADMAP_COMPLETE`, `currentFrontier = []`, `currentTask = null`

Clone protocol note (binding for all workers and the TL): the W15 real-repo gate
resolves the W0–W15 lineage, including the W1/W2 squash-era PR heads that live only
on `refs/heads/work/w*` branches. A fresh clone MUST fetch all remote heads:

```bash
git clone https://github.com/payswapdotorg/SOS.git && cd SOS \
  && git fetch origin '+refs/heads/*:refs/remotes/origin/*'
```

A `--depth N` clone or a single-branch unshallow makes G04/G06/G11 fail spuriously
(the same class of failure CI had before `a956325`).

## 1. Architecture

The target architecture is the directive's §2 diagram, with one additional
architectural rule that makes the whole program testable and provider-neutral:

**The provider adapters are interfaces with two implementations each — a LOCAL
implementation (hermetic, deterministic, no network) and the cloud implementation
(Neon/Upstash/R2/Apify).** LOCAL mode is not a mock of the product; it is the same
adapter contract running on local substrates (embedded SQLite for persistence,
in-process coordination for Redis semantics, local filesystem for artifacts,
DemoProvider for execution). This yields:

```text
apps/web (Next.js client)
   │ typed API client + fixture/demo mode
   ▼
services/api (FastAPI transport adapter)
   │  authenticates, tenant-checks, validates, orchestrates
   │  NEVER decides SOS semantics (calls src/sos domain services)
   ▼
┌─────────────────────────────────────────────────────┐
│ provider seams (interfaces, provider-neutral)        │
├──────────────┬──────────────┬──────────┬─────────────┤
│ Persistence   │ Coordination │ Artifacts │ Execution   │
│ local SQLite │ in-process   │ local FS  │ DemoProvider│
│ Neon Postgres│ Upstash Redis│ Cloudflare│ Apify       │
└──────────────┴──────────────┴──────────┴─────────────┘
```

Authority boundary (directive §2, aligned with frozen architecture §12):

```text
src/sos          = semantic authority + policy + assurance + decision  (FROZEN)
services/api     = transport/orchestration adapter
providers/neon   = durable persistence adapter
providers/upstash= ephemeral coordination adapter
providers/r2     = durable artifact/evidence storage adapter
providers/apify  = execution/ingestion provider adapter
apps/web         = presentation/client surface (Vercel)
GitHub           = source integration + OAuth identity + CI

No provider is allowed to authorize an SOS action.
```

This is the frozen architecture's §12 trust-boundary rule applied to deployment:
execution-authority mechanisms (Render/Neon/Upstash/R2/Apify/Vercel) physically run
things; intent/knowledge/assurance authority stays in `src/sos` + the owner.
LLM output stays proposal material. The web application never implements its own
version of an SOS decision rule (directive §4).

## 2. Provider roles and free-tier budget

Per directive §3/§14: Vercel Hobby (web), Render Free (FastAPI, 0.1 CPU / 512 MB,
sleeps after 15 min idle), Neon Free (durable Postgres), Upstash Redis Free
(coordination; 500K commands/month — must not become the primary event store),
Cloudflare R2 (artifacts; private buckets + signed URLs), Apify Free (bounded
execution/ingestion; $5 usage, 5 concurrent runs).

Budget consequence (directive §14): interactive UI and normal API reads are cheap;
database state is cheap; large artifacts go to R2; background computation becomes
bounded jobs; expensive execution goes to Apify only when explicitly needed.

## 3. Repository layout

Exactly the directive §4 layout (apps/web, services/api, providers/*,
execution/adapters, db/migrations, db/seeds, infra/, docs/deployment/,
spec/deployment/), with `src/sos` and `tests/` (the frozen deterministic suite)
untouched. The key rule:

```text
apps/web       → client
services/api   → transport
providers/*    → adapters
src/sos        → authority (FROZEN — zero modifications)
```

## 4. HTTP API surface

Versioned `/api/v1` exactly as directive §7 lists. The HTTP layer is thin:
authenticate → tenant authorize → validate → call SOS domain service → persist →
typed response. No architecture logic in route handlers. Typed schemas live in
`services/api/schemas/` (pydantic) and are exposed via FastAPI's OpenAPI document;
`apps/web` derives/mirrors TypeScript types from that contract (fixture mode first).
Schemas are the single source of truth for wire shapes (see CONTRACT §C).

## 5. Data model and artifact layout

Relational model: the directive §11 minimum (`users`, `workspaces`,
`workspace_members`, `missions`, `mission_revisions`, `value_models`,
`value_model_revisions`, `contexts`, `systems`, `system_revisions`,
`architecture_nodes`, `architecture_edges`, `evidence`, `evidence_artifacts`,
`hypotheses`, `causal_hypotheses`, `candidates`, `candidate_evaluations`,
`assurance_runs`, `assurance_results`, `decisions`, `authorizations`,
`experiments`, `experiment_events`, `execution_requests`, `execution_receipts`,
`learning_records`, `architecture_memory`, `jobs`, `audit_events`,
`provider_events`). Every row: immutable id (UUIDv7-style, sortable), tenant
ownership, created/updated provenance. Large blobs NEVER in Postgres —
`evidence_artifacts` rows point at R2 objects.

R2 layout: the directive §12 deterministic keys
(`tenants/{tenantId}/systems/{systemId}/{revisions|recovery|evidence|experiments|executions}/…`,
content-hash object names, signed upload/download URLs, private buckets, secrets
never in the browser).

## 6. Async job architecture

Directive §8: `POST /jobs` → create Job (Neon) → enqueue/lock (Upstash) → provider
dispatcher → local bounded operation or Apify execution → R2 artifacts → signed
callback → Render API → Neon/Redis. Job record fields exactly as directive §8
(job_id, tenant_id, type, requested_by, authority_snapshot, input_hash,
source_revision, provider, status, started_at, completed_at, receipt,
artifact_refs, error_state). Idempotency keys prevent duplicate side effects.
Jobs are the ONLY path for long-running work; the API process never runs
unbounded work (Render Free constraints; directive §8/§9).

## 7. Execution-provider strategy

Directive §9 on the W11 substrate seam (`src/sos/execution.py` — imported, never
modified): `execution/adapters/` maps the substrate contract to providers.

- **DemoProvider** — always available; deterministic; used for public demo,
  integration tests, architecture walkthrough; MUST never claim a real external
  deployment (receipts are explicitly marked demo).
- **ApifyProvider** — bounded isolated jobs; request carries the authorized
  action, exact source revision, allowed operation, resource/time limits,
  artifact policy, callback target, request hash; returns an ExecutionReceipt
  that becomes Evidence and promotion/rollback state. The provider never decides
  authorization.
- **FutureProvider(s)** — the seam stays provider-neutral so replacements need no
  semantic change.

## 8. Authentication, tenancy, GitHub integration

GitHub OAuth (directive §6): GitHub identity → SOS User → Workspace →
Missions/Systems/Evidence. Every durable row carries tenant ownership; the
browser never supplies the tenant identifier (server-side session identity only).
Brownfield onboarding (directive §10): paste repo URL → resolve → select exact ref
→ record immutable source reference → architecture recovery. "latest main" is
never an immutable evidence reference.

## 9. Rate limiting and free-tier protection

Directive §13: Upstash-enforced separate buckets for anonymous visitor
(demo reads only), authenticated user, workspace, job type, provider, IP;
explicit quotas for expensive operations; low Apify concurrency; size-limited
artifact uploads; rate-limited repository recovery. LOCAL mode implements the
same limiter interface in-process so the policy is testable hermetically.

## 10. Environments

Directive §20, plus the adapter-swap rule:

```text
LOCAL   — services/api + apps/web run on one machine with LOCAL adapters
          (SQLite, in-process coordination, local FS artifacts, DemoProvider);
          zero credentials; deterministic; this is what CI and the review gate run.
PREVIEW — Vercel preview + Neon branch + isolated test data.
PUBLIC  — Vercel production + Render public API + Neon production branch +
          Upstash production + R2 production bucket + Apify production actor.
```

Mode selection is environment-driven (`SOS_PERSISTENCE=local|neon`,
`SOS_COORDINATION=local|upstash`, `SOS_ARTIFACTS=local|r2`, `SOS_EXECUTION=demo|apify`,
`SOS_ENV=local|preview|public`) — see `infra/environment.example`. No code path
branches on provider identity beyond the adapter interface.

## 11. Coexistence with the frozen W15 gate (CRITICAL)

The W15 gate's G09 check ("no deployment/migration/network artifact exists
anywhere in the repository tree") encodes the frozen program's rollback-safety
invariant: the W0–W15 semantic surface has no unrevertable external state. The
Public Deployment Overlay adds deployment/migration artifacts BY DESIGN — so the
overlay's rollback safety must be governed separately, and G09 must keep proving
the frozen program's invariant without false-failing on governed overlay paths.

Design (binding, delivered in PUB-01):

1. `tools/final_gate_check.py` gains an explicit, enumerated
   `POST_ROADMAP_OVERLAY_PREFIXES` allowlist (exactly: `apps/`, `services/`,
   `providers/`, `execution/`, `db/`, `infra/`, `docs/deployment/`,
   `spec/deployment/`) excluded from the G09 deployment-artifact pattern scan.
   Everything else — the entire frozen surface — remains fully scanned.
2. The G09 PASS message must state both facts: frozen-surface clean AND overlay
   allowlisted under `spec/deployment/PUBLIC-DEPLOYMENT-CONTRACT.md`.
3. This adaptation is a disclosed post-merge reconciliation in the exact
   precedent class of `69c822f` (state-aware G10 expectation) and `a956325`
   (CI full-history checkout): gate/test machinery adapted, frozen docs
   byte-identical (G01), semantic surface untouched (G02), disclosed in the
   PUB-01 checkpoint and `public-deployment-state.json` notes.
4. The overlay's own rollback discipline: every overlay merge must leave
   `python3 -m pytest` green and `tools/final_gate_check.py` exit 0 (G06/G09
   discipline), and the overlay is revertable by ordinary Git (LOCAL mode needs
   no external state; cloud state is forward-creatable from migrations).

Gate matrix (binding for every PUB merge — see CONTRACT §G):

```text
python3 -m pytest                      # hermetic; includes services/api tests
python3 -m compileall -q src tests services providers execution
python3 tools/final_gate_check.py      # 12/12 PASS, exit 0 (with overlay-scoped G09)
cd apps/web && bun install && bun run lint && bun run typecheck && bun test
```

The deterministic suite stays hermetic (WORKER-DISPATCH discipline: no
network/provider dependency in default tests). Provider integration tests live
under an explicit marker/directory that self-skips without credentials.

## 12. Launch stages

Directive §21: Stage A private (operator-only; verify web→API→DB, web→API→Redis,
web→API→R2, API→Apify, Apify→API) → Stage B public read/demo (everyone explores
the demo; writes stay authenticated) → Stage C authenticated beta (mission
creation, repo onboarding, bounded recovery, candidates, experiments, execution
jobs; deliberately low expensive-execution quotas) → Stage D commercial
hardening (plan upgrades; no semantic rewrite). PUB-11/PUB-12 correspond to
Stages B/C. Actual public deployment requires operator-held provider accounts
and credentials; those are recorded as external inputs, never secrets in Git.

## 13. Product boundary

Directive §22: the public v1 delivers the coherent owner journey —
MISSION → SYSTEM STATE → EVIDENCE → CANDIDATES → ASSURANCE → DECISION/ASK →
EXPERIMENT → EXECUTION RECEIPT → LEARNING — visible, usable and demonstrable as
a real public product, control plane intact. It is NOT an unlimited autonomous
software engineer. ASK is a first-class UI state. Candidate comparison shows
multi-objective trade-offs (no fake single "AI score"). Truth states
(SUCCESS/EMPTY/FAILED/UNKNOWN/UNSUPPORTED/UNAVAILABLE) are preserved end-to-end.

## 14. Design decisions register

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | LOCAL adapter implementations with identical interfaces | hermetic tests (house law), sandbox verification, provider neutrality (directive §1) |
| D2 | G09 overlay-prefix allowlist (disclosed reconciliation) | keeps the frozen gate green without weakening the frozen-surface scan; precedent 69c822f/a956325 |
| D3 | Separate `public-deployment-state.json` (never mutating `implementation-state.json`) | frozen machine state stays ROADMAP_COMPLETE; G03 stays green |
| D4 | OpenAPI-derived TypeScript types | single wire-contract truth for A and B (directive §16: B builds against typed contracts + fixtures first) |
| D5 | Jobs as the only long-running path | Render Free constraints; directive §8 |
| D6 | SQLite in LOCAL persistence | deterministic, zero-credential local runs; same adapter interface as Neon |
| D7 | DemoProvider receipts explicitly marked demo | directive §9 truthfulness rule |
| D8 | All web↔API calls relative URLs with configurable base | deployment portability + preview-panel routing constraints |
