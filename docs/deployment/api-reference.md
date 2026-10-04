# SOS Public Deployment — API Reference (PUB-01)

**Base URL (LOCAL):** `http://127.0.0.1:8099` (any port; LOCAL mode boots with
zero env vars: `python3 -m uvicorn services.api.main:app --port 8099`)

**Surface:** exactly the directive §7 endpoint set under `/api/v1`, plus
`GET /api/v1/openapi.json` (FastAPI-generated) and `GET /api/v1/health`.
The generated schema is snapshot-tested (`tests/test_pub01_openapi_snapshot.py`).

## Wire rules (binding — contract §C)

- **Collections:** `{"items": [...], "nextCursor": string|null}` — cursor
  pagination (`?limit=1..100&cursor=...`; the cursor is opaque).
- **Errors:** `{"error": {"code", "message", "details"}}` with codes
  `UNAUTHENTICATED | FORBIDDEN | NOT_FOUND | VALIDATION | CONFLICT |
  RATE_LIMITED | PAYLOAD_TOO_LARGE | PROVIDER_UNAVAILABLE`. A reserved
  `INTERNAL` code exists ONLY as the last-resort fault barrier for unexpected
  exceptions (disclosed: it never carries resource semantics). Transport
  errors never masquerade as resource truth states.
- **Truth states on DTO `status` fields:** exactly
  `SUCCESS | EMPTY | FAILED | UNKNOWN | UNSUPPORTED | UNAVAILABLE` — the
  frozen `sos.model.TruthState` enum, imported verbatim and preserved
  end-to-end (DB → API → UI; never converted).
- **Every mutation writes an `audit_events` row** (actor/action/target/ts/meta).
  The activity trail surfaces on `GET /workspaces/{id}` as `recentActivity`.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/health` | `{"status": "ok"\|"degraded", "checks": {persistence, coordination, artifacts, execution}}` — each check reported TRUTHFULLY; exempt from rate limiting (readiness probe) |
| GET | `/api/v1/openapi.json` | generated schema |
| GET | `/api/v1/auth/session` | current session (stub in LOCAL) |
| POST | `/api/v1/auth/login` | LOCAL stub identities (`demo-owner`, `alice`, `bob`); refused outside `SOS_ENV=local` (real GitHub OAuth is PUB-04) |
| POST | `/api/v1/auth/logout` | clears the session cookie |
| GET | `/api/v1/me` | session identity (anonymous included) |
| GET/POST | `/api/v1/workspaces` | POST requires auth (membership; audited) |
| GET | `/api/v1/workspaces/{id}` | includes `recentActivity` (audit trail) |
| GET/POST | `/api/v1/missions` | POST validates the journey fields through the W1 `sos.model.Mission` authority |
| GET | `/api/v1/missions/{id}` | includes `currentRevision` |
| GET/POST | `/api/v1/missions/{id}/revisions` | propose revisions (approval state `pending`) |
| GET/POST | `/api/v1/systems` | brownfield POST pins the EXACT commit via the GitHub seam (S11) and recovers through the REAL `sos.recovery` pipeline; greenfield creates the shell |
| GET | `/api/v1/systems/{id}` | includes `currentRevision` with the architecture graph (W2 semantics) |
| GET/POST | `/api/v1/systems/{id}/recovery` | recovery status / run a recovery job (new revision + source evidence + job) |
| GET | `/api/v1/evidence` | filters: `workspaceId`, `systemId`, `kind` (7 wire kinds), `status` (6 truth states) |
| GET | `/api/v1/hypotheses` | causal structure + evidence refs |
| GET | `/api/v1/candidates` | multi-objective evaluations + paretoFront; NO single score |
| GET | `/api/v1/assurance` | checks[] + verdict (PASS/FAIL/UNKNOWN/BLOCKED) |
| GET | `/api/v1/decisions` | ACT/ASK/… with rationale, authoritySnapshot, risk, blastRadius, reversibility, requiredApprovals, askPayload |
| GET | `/api/v1/authorizations` | granted/denied |
| GET/POST | `/api/v1/experiments` | lifecycle (W8 vocabulary) + events[] |
| GET/POST | `/api/v1/executions` | POST = the governed W11 dispatch (authority gates BEFORE any provider call); receipts demo:true |
| GET | `/api/v1/executions/{id}` | |
| GET | `/api/v1/learning`, `/api/v1/memory` | learning records / architecture memory |
| GET/POST | `/api/v1/jobs` | directive §8 fields; idempotency keys dedup (same key → same job, no duplicate side effects); types: `system_recovery`, `experiment_execution`; status lifecycle `queued → running → succeeded/failed` (PUB-06). LOCAL executes inline (bounded); preview/public ENQUEUE only — the separate worker process executes (see [jobs.md](jobs.md)) |
| GET | `/api/v1/jobs/{id}` | |
| GET | `/api/v1/providers/status` | truthful per-seam introspection (mode, implementation, status, capabilities, demo flag) |
| GET | `/api/v1/providers/status/{name}` | |

### PUB-04 additions — authentication + tenancy (browser-flow endpoints;
### excluded from the frozen OpenAPI snapshot by design — documented here)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/auth/github/start?next=…` | Begins the OAuth web flow: creates the single-use state (+ server-held PKCE verifier) and 302s to github.com (live) or the LOCAL fake consent surface. `next` is validated as a relative path (open-redirect guard). §13 auth-bucket rate limited. |
| GET | `/api/v1/auth/github/callback?code&state` | Single-use state validation → PKCE code exchange → identity → user upsert → session (`sos_session` httpOnly/SameSite=Lax, Secure outside LOCAL) + `sos_csrf` readable cookie → 302 to `/signin/callback?status=ok`. Failures redirect with an honest `reason` — never a partial session. |
| GET | `/api/v1/auth/github/fake/authorize` | LOCAL ONLY — the clearly-labeled fake-GitHub consent page (deterministic fixture identities: demo-owner, alice, bob, octo-newcomer). 403 outside `SOS_ENV=local`. |
| POST | `/api/v1/auth/github/fake/consent` | LOCAL ONLY — the fake authorization decision (form-encoded `state` + `login`); issues the deterministic code and redirects to the real callback. |
| GET | `/api/v1/auth/account` | The signed-in user + their workspace memberships with roles (`owner`/`member`) — the tenant-aware navigation source. Derived ONLY from the server-side session. |

`POST /api/v1/auth/login` / `POST /api/v1/auth/logout` / `GET /api/v1/auth/session`
keep their PUB-01 wire shapes; logout now also enforces the double-submit
CSRF pair for real (non-stub) sessions and revokes the session server-side.
Full guide: `docs/deployment/auth-tenancy.md`.

### PUB-07 additions — the evidence/artifact layer (excluded from the
### frozen OpenAPI snapshot by design — documented here)

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/artifacts/uploads` | Request a signed upload slot. Body: `{workspaceId, systemId, category, contextId, subcategory?, filename?, contentType?, sizeBytes, sha256}`. Authenticated + workspace MEMBERSHIP + §13 write bucket + CSRF (real sessions). `sizeBytes` is validated against `SOS_RATE_ARTIFACT_MAX_MB` (413 `PAYLOAD_TOO_LARGE`, `maxArtifactMb`); `sha256` is the content address of the §12 key. Returns `{key, method: "PUT", url, expiresAt, maxBytes, store}` — R2 mode: a SigV4 presigned PUT (direct-to-bucket, secret never in the browser); LOCAL: a token redeemed at `/artifacts/object`. |
| POST | `/api/v1/artifacts/downloads` | Request a signed download URL. Body: `{key}`. Authenticated + read-scope tenant check (the evidence read surface; cross-tenant keys 404) + CSRF. Returns `{key, method: "GET", url, expiresAt, store}`. |
| GET/PUT | `/api/v1/artifacts/object?token=…` | The LOCAL token redemption (byte transfer). The grant — not a session — authorizes: time-bounded, scoped to ONE key + ONE mode, HMAC-signed. PUT enforces the artifact size cap and the content address (bytes' sha256 MUST equal the key's hash; 422 otherwise); exempt from the generic S16 body cap (the artifact cap applies); audits `artifact.upload_completed`. GET serves the bytes with the stored content type + sha256 ETag; audits `artifact.download_served`. |

Signed-URL lifetimes: 600 s (upload), 300 s (download). Artifact audit
actions: `artifact.upload_authorized`, `artifact.upload_completed`,
`artifact.download_authorized`, `artifact.download_served`. Full guide:
[artifacts.md](artifacts.md).

## Auth/tenant boundary (directive §6; SECURITY S5/S7/S21)

- **Sessions are server-side** — the browser NEVER supplies tenant
  identifiers; the tenant scope derives from the session (LOCAL: stub
  cookie or the fake-GitHub flow; PUBLIC: GitHub OAuth with PKCE — PUB-04,
  see `auth-tenancy.md`).
- **Anonymous** = read-only demo-workspace access; all mutations → 401.
- **Authenticated users** read the demo workspace + their member
  workspaces; **mutations require membership** (the demo workspace is
  mutable only by its members).
- **Cross-tenant** access → 404 (existence hidden; zero rows leaked —
  scoping is enforced in the persistence adapter, not per-route).

## Rate limiting (directive §13; LOCAL in-process behind the coordination seam)

Buckets: per-IP (all traffic), anonymous (per-IP/min), authenticated user
(per-user/min), writes (per-user/min), job type (per-workspace/hour;
recovery has its own lower quota), provider concurrency (PUB-06/PUB-08).
Request body cap: `SOS_RATE_BODY_MAX_MB` (413 `PAYLOAD_TOO_LARGE`).
`/api/v1/health` is exempt (readiness). If the coordination plane itself is
down, protected traffic fails CLOSED (503 `PROVIDER_UNAVAILABLE`) — only
health answers, truthfully.

## Evidence wire kinds ↔ domain mapping

The public 7-kind vocabulary (directive §5) maps to the frozen
`sos.evidence.EvidenceKind` as documented in
`services/api/orchestration.py` (`DOMAIN_TO_WIRE_EVIDENCE_KIND`):
`source_revision←static-analysis`, `runtime_observation←observation`,
`test_result←test`, `telemetry←observation`, `environment←observation`,
`experiment←experiment` (and simulation/replay/shadow/canary),
`business_outcome←business-outcome/user-outcome`; deployment/rollback
receipts (via `receipt_to_w4_evidence`) classify as `runtime_observation`
with exact provenance preserved. The mapping is classification only —
provenance, results and truth states pass through verbatim.

## LOCAL vs cloud modes

`SOS_PERSISTENCE|SOS_COORDINATION|SOS_ARTIFACTS|SOS_EXECUTION` select the
seam implementations (default: all LOCAL — SQLite, in-process, local-FS
content-addressed store with the directive §12 key layout, DemoProvider).
Cloud adapters: Neon (PUB-05), Upstash (PUB-06), R2 (PUB-07 — real,
`SOS_ARTIFACTS=r2` boots the S3 SigV4 adapter), Apify (PUB-08, pending —
selecting it fails closed with a precise error, never a silent fallback).
