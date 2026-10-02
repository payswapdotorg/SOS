# SOS Public Deployment Runbook — Stage A → B → C (PUB-03)

Operator-executed deployment runbook (directive §21 launch strategy, §20
environments; contract §D PUB-03). **Every credential below is
operator-held**: created in the provider console, stored in the provider
dashboard (Render/Vercel env settings) or the operator's shell — NEVER in
Git, never in PR text, never in the browser bundle (security gates S1/S2).

Infrastructure owners: `infra/render.yaml` (API), `infra/vercel/` (web),
`infra/neon/` + `infra/upstash/` + `infra/r2/` (state planes + setup
scripts), `infra/apify/` (execution actor skeleton). Provider adapter code
lands with PUB-05/06/07/08; until then the honest state is: the PUBLIC
deployment runs the seams that exist, and the health endpoint reports the
truth about the rest.

## 0. Prerequisites (operator accounts + credentials)

| Provider | Account | Credential the operator holds | Used for |
|---|---|---|---|
| GitHub | payswapdotorg | repo access (already held) | source, CI, OAuth (PUB-04) |
| Render | operator account | dashboard access | API service `sos-api` (free plan) |
| Vercel | operator account | dashboard access | web project (Hobby plan) |
| Neon | console.neon.tech | `NEON_API_KEY` (shell only) | durable Postgres |
| Upstash | console.upstash.com | database password (from console) | Redis coordination |
| Cloudflare | dash.cloudflare.com | R2 Access Key ID + Secret (from console) | artifact storage |
| Apify | console.apify.com | `APIFY_TOKEN` (from console) | bounded execution (PUB-08) |

Stage-by-stage requirements are listed per stage below. Missing credentials
for a stage = the stage is `BLOCKED_ON_OPERATOR_INPUT` — record it honestly;
never fabricate a deployed state.

## 1. Stage A — private internal deployment (operator-only)

Goal: prove the full wiring **privately** before public exposure. Directive
§21 Stage A verification legs:

```text
web → API → DB          Vercel → Render → Neon
web → API → Redis       Vercel → Render → Upstash
web → API → R2          Vercel → Render → R2
API → Apify             Render → Apify (PUB-08: the actor is a skeleton until then)
Apify → API             Apify signed callback → Render (PUB-08)
```

Honest stage marking: at PUB-03 time the first three legs are fully
wireable. The two Apify legs are forward dependencies on PUB-08 (the actor
under `infra/apify/` is a package-metadata + input-schema + stub skeleton by
design); until PUB-08 merges, `SOS_EXECUTION=demo` and the DemoProvider
carries execution truthfully (receipts explicitly marked demo). Record the
Apify legs as `BLOCKED_ON_PUB-08` in the deployment record — do not skip
silently.

Operator steps:

1. **Provision state planes** (idempotent scripts; see each README):

   ```bash
   export NEON_API_KEY=…;  python3 infra/neon/setup.py     # prints SOS_DATABASE_URL
   # Upstash: create DB in console → export SOS_REDIS_URL → python3 infra/upstash/setup.py
   # R2: create bucket in console → export SOS_R2_* → python3 infra/r2/setup.py
   ```

2. **Deploy the API on Render** from `infra/render.yaml`
   (Blueprint → New → Blueprint instance, or dashboard parity): free plan,
   Python runtime, rootDir `services/api`, health check `/api/v1/health`.
   Set the dashboard secrets exactly as wired in the blueprint:
   `SOS_DATABASE_URL`, `SOS_REDIS_URL`, `SOS_R2_ENDPOINT`,
   `SOS_R2_ACCESS_KEY_ID`, `SOS_R2_SECRET_ACCESS_KEY`, `SOS_R2_BUCKET`,
   `SOS_SESSION_SECRET` (32+ random bytes), plus `SOS_API_BASE_URL`
   (`https://<service>.onrender.com`) and `SOS_WEB_BASE_URL`.
   GitHub/R2-callback secrets (`SOS_GITHUB_CLIENT_*`,
   `SOS_JOB_CALLBACK_SECRET`, `SOS_APIFY_*`) can wait for PUB-04/PUB-08 —
   the config module fails closed on them ONLY when the matching mode is
   selected.
3. **Deploy the web tier on Vercel** per `infra/vercel/README.md`
   (Root Directory `apps/web`, framework Next.js, `NEXT_PUBLIC_API_BASE`
   = the Render origin, no `/api/v1` suffix).
4. **Restrict to private**: Stage A stays operator-only — do not announce
   URLs; Vercel Production and the Render service are naturally unlisted.
   (Password protection is available on both providers if stricter privacy
   is required; it is a dashboard toggle, not a code change.)
5. **Verify each leg truthfully**:

   ```bash
   # API alive + truthful readiness (never a fake ok):
   curl -s https://<render>.onrender.com/api/v1/health | python3 -m json.tool
   # web → API (browser): open the Vercel URL → the demo workspace renders
   # LIVE data (no "fixture/demo mode" badge) → Journey 1 walkthrough.
   ```

   The `checks` map in the health response is the per-leg evidence:
   persistence (Neon), coordination (Upstash), artifacts (R2), execution
   (demo) — each `SUCCESS` or a REAL degraded state. A degraded component
   is a finding to fix, never something to paper over.

**Stage A credential inputs (operator-held):** `NEON_API_KEY`, Upstash
database password, R2 Access Key ID + Secret, `SOS_SESSION_SECRET` value,
Render + Vercel dashboard access. Nothing of these is ever committed.

## 2. Stage B — public read/demo mode (PUB-11)

Goal: everyone can explore the demo (landing → demo workspace →
architecture → evidence → candidates → decision explanation — Journey 1);
**writes remain authenticated** (anonymous = demo-reads-only, security
gate S7/S21).

1. Preconditions (PUB-11 contract): PUB-04..PUB-10 merged — real auth,
   Neon persistence, jobs, artifacts, Apify execution, journeys, security
   battery.
2. Keep the same topology as Stage A; no new credentials beyond those
   already wired, plus `SOS_GITHUB_CLIENT_ID`/`SOS_GITHUB_CLIENT_SECRET`
   (GitHub OAuth app, PUB-04) so "Sign in with GitHub" is honest.
3. Verify from the public internet (not the operator's session): Journey 1
   read-only walkthrough; anonymous write attempts → 401/403; demo
   workspace read-only to anonymous users.
4. Record the deployment record: public URLs, deployed revisions (exact
   SHAs), and evidence (health output + journey transcript) under
   `docs/deployment/` per the PUB-11 contract.

**Stage B credential inputs:** the Stage A set, plus GitHub OAuth app
credentials.

## 3. Stage C — authenticated beta (PUB-12)

Goal: enable authenticated flows — mission creation, repository
onboarding, bounded recovery, candidates, experiments, execution jobs —
with **deliberately low expensive-execution quotas**.

1. Preconditions: PUB-12 contract (PUB-11 verified + quota policy agreed).
2. Quota posture (tune the non-secret env values on Render — baseline
   values live in `infra/render.yaml`):
   - `SOS_RATE_JOB_PER_HOUR=10` (per workspace; lower if budget tightens)
   - `SOS_RATE_RECOVERY_PER_HOUR=2` (recovery is the expensive path)
   - `SOS_APIFY_MAX_CONCURRENT=2` (S14 low-concurrency semaphore)
   - `SOS_RATE_ARTIFACT_MAX_MB=50`, `SOS_RATE_BODY_MAX_MB=1` (S15/S16)
3. Apify execution goes live only here: set `SOS_EXECUTION=apify` +
   `SOS_APIFY_TOKEN` + `SOS_APIFY_ACTOR_ID` (the actor is PUB-08's
   deliverable; its Dockerfile lands with PUB-08 — `infra/apify/` holds the
   skeleton until then).
4. Monitor honestly: Render metrics (memory/CPU — free tier is 512 MB),
   Neon storage (0.5 GB), Upstash command budget (500K/month), R2 Class A
   ops, Apify usage ($5 free). Quota-incident runbook: lower the
   `SOS_RATE_*` values on Render first (no deploy needed for env-only
   changes; a service restart applies them).
5. Verify Journeys 2–5 live (or record honest external-input blockers),
   per the PUB-12 contract.

**Stage C credential inputs:** the Stage B set, plus `SOS_APIFY_TOKEN` and
the actor ID from console.apify.com.

## 4. Stage D — commercial hardening (forward note, not a PUB-03 stage)

When real usage begins: Vercel Hobby → paid plan, Render Free → always-on
compute, Apify quota → paid/alternate provider (directive §21 Stage D).
**No semantic rewrite is required** — provider swaps ride the same seams.

## 5. Rollback (overlay discipline)

- Code: every overlay merge keeps `pytest` green + `final_gate_check.py`
  12/12 — the overlay is revertable by ordinary Git (design §11).
- Environment: reverting a stage is a dashboard action (unset env values /
  flip mode switches); the config module fails closed rather than
  half-booting.
- Data: Neon branches are the isolation boundary (production branch is
  never the preview target); R2 artifacts are content-addressed and safe to
  leave in place across reverts.
- The frozen W0–W15 surface is byte-identical throughout (G01/G02) —
  rollback never touches `src/sos`.

## 6. Environment quick-reference (directive §20)

| Mode | Web | API | Persistence | Coordination | Artifacts | Execution |
|---|---|---|---|---|---|---|
| LOCAL | local dev server | local FastAPI | SQLite (temp dir) | in-process | local FS | DemoProvider |
| PREVIEW | Vercel preview | Render (manual preview or local) | Neon branch | Upstash (shared) or local | R2 (scoped keys) or local | demo |
| PUBLIC | Vercel production | Render `sos-api` | Neon `main` branch | Upstash | R2 private bucket | demo → apify (PUB-08) |

See `infra/environment.example` (the naming authority) and
`docs/deployment/preview-environments.md`.
