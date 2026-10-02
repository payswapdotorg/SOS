# SOS Public Deployment — Security Gate

**Status:** ACTIVE — security requirements authority (Public Deployment Overlay)
**Directive source:** operator directive §19 (verbatim in
`spec/deployment/PUBLIC-DEPLOYMENT-DIRECTIVE.md`); §6 (tenancy), §12 (R2), §13
(rate limits).
**Enforcement:** every item below must be verifiable by an executable check
(PUB-10 battery) or an honestly recorded operator-input blocker. The gate is
evaluated before PUB-11 (public exposure) and re-verified at PUB-13.

## 1. The 21 directive checks (each: requirement → mechanism → check)

| # | Directive line | Mechanism (binding) | Check (PUB-10) |
|---|----------------|---------------------|----------------|
| S1 | No secrets in browser bundle | `NEXT_PUBLIC_*` allowlist; secrets only server-side; env audit | build-output scan for secret-shaped strings |
| S2 | No secrets in Git | `infra/environment.example` uses placeholders only; pre-commit + CI secret scan | gitleaks-style scan of full history + working tree |
| S3 | All R2 buckets private | bucket policy private-by-default in setup runbook + adapter | adapter refuses unsigned public URLs; setup script asserts policy |
| S4 | Signed artifact URLs | time-bounded, key-scoped signed URLs only | unsigned/expired/out-of-scope URL rejected |
| S5 | Tenant isolation tested | tenant scoping enforced in the persistence adapter (not per-route); server-side session identity only | cross-tenant read/write probes → 403/404, zero rows returned |
| S6 | CSRF protection | session cookie sameSite + per-mutation CSRF token (double-submit) | mutation without token → 403 |
| S7 | Authentication required for mutations | route-level dependency, fail-closed | anonymous mutation probes → 401 on every non-demo mutation |
| S8 | API rate limiting | directive §13 buckets (anonymous demo-reads-only, user, workspace, job type, provider, IP) | bucket exhaustion tests per class |
| S9 | Job idempotency | idempotency-key dedup at job creation | duplicate POST /jobs with same key → single job, single side-effect set |
| S10 | Replay protection on provider callbacks | HMAC envelope + nonce + timestamp window, validated before state mutation | tampered/replayed/expired callbacks rejected with no state change |
| S11 | Exact source revision recorded | immutable sourceRef at onboarding; "latest main" forbidden | brownfield records carry 40-hex SHAs; no mutable refs persisted |
| S12 | Provider cannot self-authorize | authorization decisions only via `src/sos` autonomy services; providers carry authorization snapshots, never grant them | adversarial probe: callback claiming granted-authority → rejected |
| S13 | Arbitrary code never executes in Render API | providers/apify actor is the only place external code runs; API process runs no dynamic execution of user-supplied code | static scan for exec/eval/subprocess on user input + runtime probe |
| S14 | Apify requests resource-bounded | request carries resource/time limits; actor enforces them | actor config + adapter tests assert bounds present |
| S15 | Artifact size limits | upload endpoint + store enforce max size | oversize upload → 413 |
| S16 | Request payload limits | API-level body size limits | oversize request → 413 |
| S17 | Audit trail for consequential actions | every mutation writes `audit_events` (actor/action/target/ts/meta) | journey audits assert complete trails |
| S18 | FAILED/UNKNOWN/UNAVAILABLE/UNSUPPORTED preserved | 6-state enum end-to-end; no silent conversion | fault-injection: provider down → UNAVAILABLE evidence (not empty, not success) |
| S19 | ASK cannot silently become ACT | decision transitions validated by `src/sos` autonomy services; ASK requires explicit owner action | unauthorized ASK→ACT transition rejected |
| S20 | ACT cannot bypass assurance | promotion gates re-validated in domain services | ACT without assurance verdict → rejected |
| S21 | Production-like demo cannot mutate another tenant | demo workspace is read-only to anonymous; tenant scoping S5 | demo session mutation probes → 401/403, other-tenant rows untouched |

## 2. Threat notes (binding design constraints)

- **Provider boundaries:** Apify cannot authorize itself; Render cannot define
  SOS policy; Vercel cannot create authoritative decisions; Redis is never
  evidence authority; R2 is never semantic state (directive §18 Journey 7 /
  provider isolation — probed adversarially in PUB-08/PUB-10).
- **Auth:** OAuth state + PKCE; httpOnly/secure/sameSite session cookies; logout
  invalidates server-side; tokens never in localStorage; LOCAL fake-GitHub is
  clearly labeled and never enabled by `SOS_ENV=public`.
- **Tenancy:** the browser NEVER supplies the tenant identifier (directive §6);
  all tenant context derives from the server-side session.
- **Fail-closed config:** missing required env (secrets, mode switches) refuses
  boot with a precise error; no insecure defaults.
- **Callback surface:** only the signed provider-callback route accepts
  provider input; it authenticates BEFORE parsing application semantics.
- **Audit:** audit events are append-only; consequential actions (mutations,
  decisions, job dispatch, artifact ops) always audited.

## 3. Honest blockers

Checks that require live provider credentials (S3/S4 live-policy assertions,
public-URL probes) are recorded as operator-input blockers until PUB-11; the
mechanism + LOCAL-mode checks must already pass. A blocked check is recorded as
`BLOCKED_ON_OPERATOR_INPUT` in the PUB-10 evidence — never silently passed.
