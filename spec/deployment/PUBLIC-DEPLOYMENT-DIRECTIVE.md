# PUBLIC-DEPLOYMENT-DIRECTIVE — Operator Directive Record (verbatim)

**Status:** FROZEN OPERATOR DIRECTIVE RECORD
**Received:** 2026-10-02 (~02:05 UTC), operator's authenticated session channel (the
same channel that issued the standing resident-watch delegation
"monitor → harvest → review → approve/require-changes → dispatch next, until the
roadmap is complete", re-issued 2026-10-01).
**Recorded by:** the campaign Tech Lead, under `AGENTS.md` §Repository-only rule
("If an important fact exists only in conversation, persist it in the appropriate
repository artifact before relying on it") and
`docs/implementation/SOS-IMPLEMENTATION-PROCESS.md` §4 (durable dispatch).
**Purpose:** This file preserves the operator's public-deployment directive VERBATIM.
It is the authorizing record for the Public Deployment Overlay (PUB-00 … PUB-13).
Derived normative artifacts: `spec/deployment/PUBLIC-DEPLOYMENT-CONTRACT.md` (binding
per-item work orders), `PUBLIC-DEPLOYMENT-WORKERS.md`, `PUBLIC-DEPLOYMENT-SECURITY.md`,
`PUBLIC-DEPLOYMENT-CHECKLIST.md`, `spec/development-state/public-deployment-state.json`.
The frozen W0–W15 artifacts remain authoritative for SOS semantics; this program is a
post-roadmap productization layer, not a reopening of W0–W15.
**Transcription note:** prose, lists, tables and requirements are exact; the ASCII
box-drawing diagrams are transcribed to best effort (the directive's rendering of a
few connector glyphs was ambiguous; every node, label and edge relation is preserved).
Numbering quirks in the directive are preserved as received (§18 contains two
"Journey 6" headings; the normative checklist renumbers them as Journeys 6 and 7).

---

# SOS Public Deployment Implementation Plan

## 1. Deployment objective

Turn the completed `payswapdotorg/SOS` repository into a publicly accessible SOS application that a new user can open in a browser and use to:

`Sign in → define mission → onboard system → recover state → inspect evidence → generate candidates → review assurance → make ACT / EXPERIMENT / GATHER_EVIDENCE / ASK decisions → run bounded experiments → inspect receipts → learn`

The deployment must:

* preserve the frozen SOS architecture and authority model;
* keep `src/sos` as the semantic/control-plane core;
* add a user-facing web application and HTTP adapter rather than replacing the core;
* use free tiers wherever practical;
* keep durable state outside ephemeral compute;
* offload expensive/unsafe work from the public API;
* make the application genuinely usable, not merely expose an API;
* remain provider-neutral so providers can later be swapped.

The existing repository is already at `ROADMAP_COMPLETE` through W15, with the terminal gate passing. The deployment program is therefore a **post-roadmap productization layer**, not a reopening of W0-W15.

---

## 2. Target public architecture

```text
                               PUBLIC INTERNET
                                      │
                                      ▼
                         ┌────────────────────────┐
                         │      VERCEL HOBBY      │
                         │     Next.js Web App     │
                         │                        │
                         │ landing / auth / UI    │
                         │ missions / state       │
                         │ evidence / candidates  │
                         │ approvals / activity   │
                         └───────────┬────────────┘
                                     │ HTTPS
                                     ▼
                         ┌────────────────────────┐
                         │     RENDER FREE        │
                         │      FastAPI API        │
                         │                        │
                         │ HTTP adapter           │
                         │ auth/session boundary  │
                         │ tenant isolation       │
                         │ orchestration          │
                         └──────┬─────┬─────┬─────┘
                                │     │     │
                ┌───────────────┘     │     └────────────────┐
                ▼                     ▼                      ▼
       ┌────────────────┐    ┌────────────────┐    ┌────────────────┐
       │      NEON      │    │ UPSTASH REDIS  │    │ CLOUDFLARE R2  │
       │   PostgreSQL   │    │ cache / queue  │    │ evidence/blob  │
       │                │    │ locks / limits │    │ artifacts/logs │
       │ durable state  │    │ job status     │    │ source bundles │
       └────────────────┘    └────────────────┘    └────────────────┘
                                │
                                │ async bounded jobs
                                ▼
                         ┌────────────────────────┐
                         │        APIFY           │
                         │ ingestion / sandbox    │
                         │ repository analysis    │
                         │ external evidence      │
                         │ isolated execution     │
                         └───────────┬────────────┘
                                     │
                              signed callback
                                     │
                                     ▼
                              Render API
                                     │
                         ┌───────────┴────────────┐
                         │                        │
                         ▼                        ▼
                       Neon                     R2
```

### Authority boundary

```text
SOS Core
  = semantic authority + policy + assurance + decision

Render API
  = transport/orchestration adapter

Neon
  = durable persistence

Upstash
  = ephemeral coordination/cache/rate limits

R2
  = durable artifact/evidence storage

Apify
  = execution / ingestion provider

Vercel
  = presentation/client surface

GitHub
  = source-control integration + OAuth/identity + CI

No provider is allowed to authorize an SOS action.
```

That follows the existing architecture's rule that providers execute authorized bounded requests while SOS remains the authority.

---

# 3. Provider selection

## Vercel — public web application

Use **Vercel Hobby** for the initial public, non-commercial deployment. Vercel currently lists Hobby at $0 and includes automatic CI/CD, CDN delivery, HTTPS, DDoS mitigation and other web-platform capabilities. Its current Hobby limits include 1M function invocations/month, 100 GB/month fast data transfer and 4 hours/month of Fluid active CPU. Vercel explicitly describes Hobby as intended for personal/non-commercial use, so a commercial deployment must move to an appropriate paid plan.

Use Vercel for:

* Next.js application
* static/interactive UI
* authentication callbacks
* lightweight API proxying where useful
* public documentation
* health/status pages

Do **not** put long-running SOS work here.

---

## Render — Python/FastAPI runtime

Render is the simplest free-tier home for the existing Python SOS implementation. Render supports FastAPI directly and offers free web services with 0.1 CPU / 512 MB RAM. Free web services spin down after 15 minutes without traffic and take roughly a minute to wake. Render explicitly positions free instances for testing, hobby work and previews rather than production-grade workloads.

Use Render for:

* `FastAPI` HTTP adapter
* SOS orchestration
* authentication/session validation
* durable-state reads/writes
* provider dispatch
* webhook/callback processing
* health endpoints

Do not depend on its local filesystem or process memory for state.

---

## Neon — durable relational state

Use Neon PostgreSQL as the durable system-of-record database.

Current Neon material describes a Free plan with up to 100 projects, 100 CU-hours per project, 0.5 GB database storage per project and 10 branches, with scale-to-zero behavior.

Neon should hold:

* users
* organizations/tenants
* missions
* mission revisions
* value models
* contexts
* system-state metadata
* architecture graphs/indexes
* evidence metadata
* hypotheses
* candidate metadata
* assurance results
* decisions
* authorization records
* experiment lifecycle
* execution receipts
* learning records
* architecture-memory indexes
* audit trail
* jobs/status metadata

Large evidence blobs must **not** be stored in Postgres.

---

## Upstash Redis — coordination plane

Use Upstash Redis for:

* request rate limiting
* idempotency keys
* short-lived job state
* orchestration locks
* API/session cache
* polling state
* duplicate-job suppression
* lightweight pub/sub where useful

The current free tier is 256 MB, 500K commands/month and 10 GB/month bandwidth.

Because 500K commands/month is finite, the implementation must avoid treating Redis as the primary event store.

---

## Cloudflare R2 — evidence/artifact storage

Use R2 for:

* source snapshots
* evidence bundles
* execution logs
* reports
* replay artifacts
* screenshots/attachments
* generated architecture exports
* test output
* large JSON bundles
* downloadable audit packages

Current R2 free-tier allowances include 10 GB-month storage, 1M Class A operations and 10M Class B operations per month, with free internet egress for Standard storage.

All buckets should be private by default. Public access should use signed URLs.

---

## Apify — asynchronous ingestion and bounded sandbox execution

Use Apify for work that should not execute inside the public API process:

* website/document ingestion
* external-source harvesting
* repository analysis jobs
* controlled sandbox execution
* bounded source extraction
* long-running provider tasks

Apify's current free plan provides $5 of platform usage, supports up to 5 concurrent runs and charges platform compute at $0.20/CU.

Therefore Apify should be **asynchronous and selective**, not used for every page load or API request.

---

# 4. Repository implementation structure

Preserve the current core rather than moving it into a new framework.

```text
SOS/
│
├── src/
│   └── sos/                         ← existing semantic/control-plane core
│
├── tests/                           ← existing deterministic suite
│
├── apps/
│   └── web/                         ← NEW
│       ├── app/
│       ├── components/
│       ├── lib/
│       ├── hooks/
│       └── styles/
│
├── services/
│   └── api/                         ← NEW HTTP adapter
│       ├── main.py
│       ├── routes/
│       ├── auth/
│       ├── dependencies/
│       └── schemas/
│
├── providers/
│   ├── neon/                        ← NEW persistence adapter
│   ├── upstash/                     ← NEW coordination adapter
│   ├── r2/                          ← NEW artifact adapter
│   ├── apify/                       ← NEW execution/ingestion adapter
│   └── github/                      ← NEW source/identity adapter
│
├── execution/
│   └── adapters/                    ← maps provider -> W11 substrate
│
├── db/
│   ├── migrations/
│   └── seeds/
│
├── infra/
│   ├── render.yaml
│   ├── apify/
│   └── environment.example
│
├── docs/
│   └── deployment/
│
└── spec/
    └── deployment/
```

The key rule is:

```text
apps/web       → client
services/api   → transport
providers/*    → adapters
src/sos        → authority
```

The web application must never implement its own version of an SOS decision rule.

---

# 5. Public user experience

The first public release should expose the architecture through a coherent cockpit.

## Entry

```text
SOS
Mission-governed software evolution

[ Explore Demo ]
[ Sign in with GitHub ]
```

Anonymous users can inspect a prebuilt demo system.

Authenticated users can create their own tenant/workspace.

## Workspace

```text
┌─────────────────────────────────────────────────────┐
│ SOS                                                │
├───────────────┬─────────────────────────────────────┤
│ Mission       │ Mission: Reduce deployment failure │
│ Systems       │                                     │
│ Evidence      │ Current system state                │
│ Candidates    │                                     │
│ Experiments   │ Health / uncertainty / drift        │
│ Decisions     │                                     │
│ Memory        │ Next governed action                │
│ Activity      │                                     │
└───────────────┴─────────────────────────────────────┘
```

## Mission journey

```text
Mission
   ↓
Goals
   ↓
Outcomes
   ↓
Stakeholders
   ↓
Measures
   ↓
Constraints
   ↓
Preferences
   ↓
Approve Mission Revision
```

The user remains the mission authority.

## System onboarding

Two explicit modes:

```text
GREENFIELD
Mission only
   ↓
Formalize system hypothesis
   ↓
Initial System State

BROWNFIELD
GitHub repository / supported source
   ↓
Architecture recovery
   ↓
Evidence + uncertainty
   ↓
Recovered System State
```

The UI must clearly distinguish UNKNOWN, FAILED, UNAVAILABLE and UNSUPPORTED.

## Evidence

```text
Evidence
─────────────
Source revision
Runtime observation
Test result
Telemetry
Environment
Experiment
Business outcome

Each item:
  status
  provenance
  timestamp
  exact revision
  related system state
  confidence/uncertainty
```

Large evidence artifacts resolve to R2 objects rather than being embedded inside database rows.

## Candidate comparison

```text
Candidate A
 ├─ mission effect
 ├─ cost
 ├─ risk
 ├─ constraints
 ├─ evidence
 └─ reversibility

Candidate B
 ├─ mission effect
 ├─ cost
 ├─ risk
 ├─ constraints
 ├─ evidence
 └─ reversibility

Candidate C
 ...
```

Do not expose a fake single "AI score". The existing architecture requires multi-objective/Pareto reasoning.

## Decision surface

Every consequential action should make the governing decision visible:

```text
DECISION: EXPERIMENT

Why?
Evidence:
Authority:
Expected impact:
Risk:
Blast radius:
Reversibility:
Required approvals:

[Run experiment]
[Gather more evidence]
[Ask owner]
[Cancel]
```

`ASK` must be an actual UI state, not just an API enum.

---

# 6. Authentication and tenancy

## Initial authentication

Use GitHub OAuth.

Reason:

* matches the developer/software-system audience;
* naturally connects to GitHub repository onboarding;
* avoids adding another paid authentication dependency;
* works well with the public GitHub-oriented product.

Initial model:

```text
GitHub identity
      ↓
SOS User
      ↓
Organization / Workspace
      ↓
Projects
      ↓
Missions + Systems + Evidence
```

Every durable row must carry tenant/workspace ownership.

Never rely on the browser to provide the tenant identifier.

---

# 7. API design

Create a versioned public API:

```text
/api/v1/health

/api/v1/auth/*
/api/v1/me

/api/v1/workspaces
/api/v1/workspaces/{id}

/api/v1/missions
/api/v1/missions/{id}
/api/v1/missions/{id}/revisions

/api/v1/systems
/api/v1/systems/{id}
/api/v1/systems/{id}/recovery

/api/v1/evidence
/api/v1/hypotheses
/api/v1/candidates
/api/v1/assurance

/api/v1/decisions
/api/v1/authorizations

/api/v1/experiments
/api/v1/experiments/{id}

/api/v1/executions
/api/v1/executions/{id}

/api/v1/learning
/api/v1/memory

/api/v1/jobs
/api/v1/jobs/{id}

/api/v1/providers/*
```

The HTTP layer should be thin:

```text
HTTP request
   ↓
authenticate
   ↓
tenant authorization
   ↓
validate request
   ↓
call SOS domain service
   ↓
persist result
   ↓
return typed response
```

No architecture logic should live in route handlers.

---

# 8. Async job architecture

Because the free compute layer is constrained, long-running work must become jobs.

```text
POST /jobs
     │
     ▼
Neon: create Job
     │
     ▼
Upstash: enqueue/lock
     │
     ▼
Provider dispatcher
     │
     ├── local bounded operation
     └── Apify execution
             │
             ▼
        R2 artifacts
             │
             ▼
       signed callback
             │
             ▼
        Render API
             │
       ┌─────┴─────┐
       ▼           ▼
     Neon         Redis
```

Each job gets:

```text
job_id
tenant_id
type
requested_by
authority_snapshot
input_hash
source_revision
provider
status
started_at
completed_at
receipt
artifact_refs
error_state
```

Use idempotency keys so retries do not create duplicate experiments or deployments.

---

# 9. Execution-provider strategy

The W11 substrate already establishes the correct architectural seam.

The public deployment should introduce these providers:

```text
ExecutionSubstrate
       │
       ├── DemoProvider
       │
       ├── ApifyProvider
       │
       └── FutureProvider(s)
```

### DemoProvider

Always available.

Used for:

* public demo
* integration testing
* architecture walkthrough
* deterministic examples

It must never pretend to have performed a real external deployment.

### ApifyProvider

Used for bounded isolated jobs.

A request should contain:

```text
authorized action
exact source revision
allowed operation
resource limits
time limit
artifact policy
callback target
request hash
```

Apify returns:

```text
ExecutionReceipt
      ↓
Evidence
      ↓
Promotion / rollback state
```

The provider must never decide whether an action is authorized.

---

# 10. GitHub integration

Add a GitHub adapter for:

* repository discovery
* branch/commit lookup
* exact revision pinning
* source metadata
* pull request information
* CI status
* release/deployment evidence
* optional webhook events

For public onboarding:

```text
Paste repository URL
        ↓
Resolve repository
        ↓
Select exact ref
        ↓
Record immutable source reference
        ↓
Run architecture recovery
```

Never use "latest main" as an immutable evidence reference.

---

# 11. Database model

Minimum relational model:

```text
users
workspaces
workspace_members

missions
mission_revisions

value_models
value_model_revisions

contexts

systems
system_revisions
architecture_nodes
architecture_edges

evidence
evidence_artifacts

hypotheses
causal_hypotheses

candidates
candidate_evaluations

assurance_runs
assurance_results

decisions
authorizations

experiments
experiment_events

execution_requests
execution_receipts

learning_records
architecture_memory

jobs
audit_events
provider_events
```

Every entity needs immutable IDs and appropriate revision/provenance fields.

---

# 12. R2 artifact layout

Use deterministic object keys:

```text
tenants/{tenantId}/
  systems/{systemId}/
    revisions/{revisionId}/
    recovery/{jobId}/
    evidence/{evidenceId}/
    experiments/{experimentId}/
    executions/{executionId}/
      logs/
      reports/
      receipts/
      bundles/
```

Use content hashes whenever possible.

Do not expose the R2 secret directly to the browser.

Use signed upload/download URLs.

---

# 13. Rate limiting and free-tier protection

Upstash should enforce separate limits for:

```text
anonymous visitor
authenticated user
workspace
job type
provider
IP
```

Example policy:

```text
Anonymous:
  demo reads only

Authenticated:
  normal API reads
  bounded writes

Expensive operations:
  explicit quota

Apify jobs:
  low concurrency

Artifact uploads:
  size-limited

Repository recovery:
  rate-limited
```

This protects the application from a single public user consuming the free-tier budget.

---

# 14. Free-tier operating budget

The system should be designed around the provider ceilings rather than pretending they are unlimited.

| Provider           | Primary role           | Current free allowance relevant to SOS                                                                    |
| ------------------ | ---------------------- | --------------------------------------------------------------------------------------------------------- |
| Vercel Hobby       | Web UI                 | $0; 1M function invocations/month, 100 GB fast transfer; Hobby is for personal/non-commercial use         |
| Render Free        | Python API             | 0.1 CPU / 512 MB; free services sleep after 15 min idle; suitable for preview/demo rather than production |
| Neon Free          | Durable DB             | 100 CU-hours/project, 0.5 GB/project, 10 branches/project on the current Free plan                        |
| Upstash Redis Free | Cache/locks/jobs       | 256 MB, 500K commands/month, 10 GB bandwidth                                                              |
| Cloudflare R2 Free | Evidence/artifacts     | 10 GB-month, 1M Class A, 10M Class B, free egress for Standard storage                                    |
| Apify Free         | Ingestion/sandbox jobs | $5 platform usage, up to 5 concurrent runs; $0.20/CU platform rate                                        |

The practical consequence is:

```text
interactive UI         → cheap
normal API reads       → cheap
database state         → cheap
large artifacts        → R2
background computation → bounded jobs
expensive execution    → Apify only when explicitly needed
```

---

# 15. Implementation sequence

Do not modify the frozen W0-W15 roadmap.

Create a separate **Public Deployment Overlay**.

```text
PUB-00
Deployment contract + repository layout
        │
        ├──────────────┬────────────────────┐
        ▼              ▼                    ▼
   PUB-01 API      PUB-02 Web UI       PUB-03 Infra
        │              │                    │
        └──────────────┼────────────────────┘
                       ▼
                  PUB-04 Auth
                       │
                       ▼
               PUB-05 Persistence
                       │
                       ▼
               PUB-06 Async Jobs
                       │
                       ▼
             PUB-07 Apify Provider
                       │
                       ▼
             PUB-08 Full Integration
                       │
             ┌─────────┼──────────┐
             ▼         ▼          ▼
          security   journeys   load/limits
             └─────────┼──────────┘
                       ▼
                 PUB-09 Launch
                       │
                       ▼
               PUBLIC SOS v1
```

---

# 16. Three-worker implementation model

## TL / Architect

Owns:

* deployment architecture
* authority-boundary enforcement
* API contract review
* provider neutrality
* integration
* final launch gate

The TL does not independently redefine the frozen architecture.

---

## Worker A — Control plane + infrastructure

### PUB-01

Build:

* FastAPI application
* API versioning
* Neon adapter
* Redis adapter
* R2 adapter
* migration system
* environment configuration
* health/readiness endpoints

### PUB-05

Implement persistence mapping from existing SOS domain objects into durable records.

### PUB-06

Implement:

* job model
* idempotency
* retry policy
* provider dispatch
* callback validation

Worker A must never execute arbitrary user repository code directly.

---

## Worker B — Web product

### PUB-02

Build Next.js application:

* landing page
* sign-in
* workspace
* mission editor
* systems
* evidence explorer
* candidate comparison
* assurance
* decision panel
* ASK UI
* experiment lifecycle
* execution receipts
* learning/memory
* activity/audit trail

Build against typed API contracts and demo fixtures before backend completion.

### PUB-04

Implement:

* GitHub OAuth
* session management
* workspace membership
* tenant-aware navigation
* protected actions

---

## Worker C — Providers + deployment

### PUB-03

Implement:

* Render deployment
* Vercel deployment
* Neon setup
* Upstash setup
* R2 setup
* environment templates
* CI/CD deployment checks

### PUB-07

Implement:

* Apify actor
* provider adapter
* signed job callback
* artifact upload
* execution receipt conversion
* failure/timeout handling

### PUB-08

Run provider integration and adversarial tests.

---

# 17. Required repository artifacts

Before implementation starts, persist:

```text
docs/deployment/PUBLIC-DEPLOYMENT-DESIGN.md
spec/deployment/PUBLIC-DEPLOYMENT-CONTRACT.md
spec/deployment/PUBLIC-DEPLOYMENT-WORKERS.md
spec/deployment/PUBLIC-DEPLOYMENT-SECURITY.md
spec/deployment/PUBLIC-DEPLOYMENT-CHECKLIST.md
spec/development-state/public-deployment-state.json
infra/render.yaml
infra/environment.example
```

These become the source of truth for the deployment program.

The frozen W0-W15 artifacts remain authoritative for SOS semantics.

---

# 18. Acceptance tests

Public deployment is not complete merely because Vercel/Render return HTTP 200.

The final gate must demonstrate all of these journeys end-to-end.

### Journey 1 — Anonymous demo

```text
Landing
 → Demo workspace
 → Existing system
 → Architecture
 → Evidence
 → Candidate comparison
 → Decision explanation
```

### Journey 2 — New user

```text
Landing
 → GitHub login
 → Create workspace
 → Create mission
 → Approve mission
 → Create system
```

### Journey 3 — Brownfield

```text
GitHub repository
 → exact revision
 → architecture recovery
 → uncertainty
 → evidence
 → candidate set
```

### Journey 4 — Governed optimization

```text
Candidate
 → assurance
 → experiment
 → authorization
 → execution provider
 → receipt
 → evidence
 → promotion / rollback
```

### Journey 5 — ASK

```text
Insufficient authority
 → ASK
 → user sees exact decision
 → user approves/rejects/provides evidence
 → lifecycle continues
```

### Journey 6 — Failure

```text
provider fails
 → FAILED evidence
 → no false SUCCESS
 → rollback/recovery path
 → learning record
```

### Journey 6 — Provider isolation

Verify that:

```text
Apify cannot authorize itself
Render cannot redefine SOS policy
Vercel cannot create authoritative decisions
Redis cannot become evidence authority
R2 cannot become semantic state
```

---

# 19. Security gate

Before opening the deployment publicly:

```text
✓ No secrets in browser bundle
✓ No secrets in Git
✓ All R2 buckets private
✓ Signed artifact URLs
✓ Tenant isolation tested
✓ CSRF protection
✓ Authentication required for mutations
✓ API rate limiting
✓ Job idempotency
✓ Replay protection on provider callbacks
✓ Exact source revision recorded
✓ Provider cannot self-authorize
✓ Arbitrary code never executes in Render API
✓ Apify requests resource-bounded
✓ Artifact size limits
✓ Request payload limits
✓ Audit trail for consequential actions
✓ FAILED / UNKNOWN / UNAVAILABLE / UNSUPPORTED preserved
✓ ASK cannot silently become ACT
✓ ACT cannot bypass assurance
✓ Production-like demo cannot mutate another tenant
```

---

# 20. Deployment environments

Use three logical environments even on free infrastructure:

```text
LOCAL
  deterministic development

PREVIEW
  Vercel preview
  Neon branch
  isolated test data

PUBLIC
  Vercel production
  Render public API
  Neon production branch
  Upstash production database
  R2 production bucket
  Apify production actor
```

Neon branching is especially useful for preview environments because the Free plan supports multiple branches per project.

---

# 21. Launch strategy

## Stage A — private internal deployment

Expose only to the operator.

Verify:

```text
web → API → DB
web → API → Redis
web → API → R2
API → Apify
Apify → API
```

## Stage B — public read/demo mode

Allow everyone to:

* explore the demo
* inspect the architecture
* inspect evidence
* inspect decisions
* understand the product

Writes remain authenticated.

## Stage C — public authenticated beta

Enable:

* mission creation
* repository onboarding
* bounded recovery
* candidate generation
* experiments
* execution jobs

Keep expensive execution quotas deliberately low.

## Stage D — commercial hardening

When actual usage begins:

```text
Vercel Hobby → appropriate Vercel plan
Render Free → paid/other always-on compute
Apify free quota → paid or alternate execution provider
```

No semantic rewrite should be required.

---

# 22. Final product boundary

The first public SOS should **not** attempt to become an unlimited autonomous software engineer.

The public v1 should instead deliver this coherent experience:

```text
                 ┌───────────────────────────┐
                 │          SOS USER          │
                 └─────────────┬─────────────┘
                               │
                               ▼
                    ┌────────────────────┐
                    │      MISSION       │
                    └─────────┬──────────┘
                              ▼
                    ┌────────────────────┐
                    │    SYSTEM STATE    │
                    └─────────┬──────────┘
                              ▼
                    ┌────────────────────┐
                    │      EVIDENCE      │
                    └─────────┬──────────┘
                              ▼
                    ┌────────────────────┐
                    │    CANDIDATES      │
                    └─────────┬──────────┘
                              ▼
                    ┌────────────────────┐
                    │     ASSURANCE      │
                    └─────────┬──────────┘
                              ▼
                    ┌────────────────────┐
                    │ DECISION / ASK     │
                    └─────────┬──────────┘
                              ▼
                    ┌────────────────────┐
                    │    EXPERIMENT      │
                    └─────────┬──────────┘
                              ▼
                    ┌────────────────────┐
                    │ EXECUTION RECEIPT  │
                    └─────────┬──────────┘
                              ▼
                    ┌────────────────────┐
                    │     LEARNING       │
                    └────────────────────┘
```

That is the smallest deployment that makes the completed SOS architecture **visible, usable and demonstrable as a real public product**, while leaving the control plane intact.

## 23. Definition of public-deployment completion

```text
PUB-00  Repository deployment contract          ⬜
PUB-01  FastAPI control-plane adapter            ⬜
PUB-02  Next.js public cockpit                   ⬜
PUB-03  Free-tier infrastructure                 ⬜
PUB-04  GitHub authentication + tenancy          ⬜
PUB-05  Neon persistence                         ⬜
PUB-06  Upstash job/coordination layer           ⬜
PUB-07  R2 evidence/artifact layer               ⬜
PUB-08  Apify bounded execution provider         ⬜
PUB-09  Integrated user journeys                 ⬜
PUB-10  Security/adversarial verification        ⬜
PUB-11  Public demo deployment                   ⬜
PUB-12  Authenticated beta deployment            ⬜
PUB-13  Final deployment Architect gate          ⬜
```

The final state should be:

```text
SOS-v1 semantic roadmap
        🟢 W0 → ... → 🟢 W15
                         │
                         ▼
                PUBLIC DEPLOYMENT
                         │
          ┌──────────────┼───────────────┐
          ▼              ▼               ▼
       Vercel          Render           Neon
          │              │               │
          └──────┬───────┴───────┬──────┘
                 ▼               ▼
              Upstash           R2
                 │               │
                 └──────┬────────┘
                        ▼
                      Apify
                        │
                        ▼
              REAL PUBLIC SOS PRODUCT
```
