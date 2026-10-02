# Vercel — `apps/web` project configuration (PUB-03)

Operator-runbook for the public web tier (directive §3 Vercel lane, §20
PUBLIC environment). Vercel **Hobby** ($0) is approved for the initial
non-commercial public deployment only; commercial use must move to an
appropriate paid plan (Stage D).

**No long-running SOS work runs on Vercel** (directive §3): the web tier is
presentation/client surface only — landing, auth callbacks, cockpit UI,
health/status. Jobs, execution, and provider orchestration belong to the
Render API + the PUB-06 job layer. Do not add cron jobs, background
functions, or other long-running work to this project.

## What lives where

| Artifact | Location | Owner |
|---|---|---|
| This runbook + project template | `infra/vercel/` | PUB-03 (Worker C) |
| `vercel.json` template for the app root | `infra/vercel/vercel.json` | PUB-03 (Worker C) |
| The application itself | `apps/web/` | PUB-02 (Worker B) |

`apps/web/**` is outside PUB-03's allowed surface, so the project config is
kept here as the canonical template and applied by the operator (below) —
it is NOT committed into `apps/web/` by this work item.

## Applying the config (operator, one-time + idempotent)

1. Import the repository in Vercel (Add New → Project → `payswapdotorg/SOS`).
2. Framework preset: **Next.js** (auto-detected).
3. **Root Directory: `apps/web`** — required: the repo root is a monorepo.
4. Build settings (either confirm the dashboard shows these, or apply the
   template by copying `infra/vercel/vercel.json` to `apps/web/vercel.json`
   in an operator-side change — it is the same config):
   - Install Command: `bun install` (Vercel detects `bun.lock`)
   - Build Command: `bun run build`
   - Output: Next.js default (`.vercel/output` — no config needed)
5. Do not set a custom Development Command.

## Environment variables (project settings — values are operator-held)

These are **build-time inlined** into the client bundle by Next.js, so they
must be set in Vercel (Production + Preview scopes), never on Render. Only
`NEXT_PUBLIC_*` names may ever be exposed to the browser (security gate S1).

| Name | Production value | Preview value |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` | `https://<render-service>.onrender.com` — ORIGIN only, **no `/api/v1` suffix** (the typed client in `apps/web/lib/api/client.ts` owns the version prefix) | preview API origin, or leave unset for fixture/demo mode (see `docs/deployment/preview-environments.md`) |
| `NEXT_PUBLIC_API_MODE` | unset (normal resolution) | `fixtures` when the preview should run standalone demo data |

Misconfiguration symptoms (honest states, by design): unset
`NEXT_PUBLIC_API_BASE` + unset mode → the cockpit boots in **fixture/demo
mode**, clearly labeled; an empty-string base → same-origin `/api/v1`
(useful when Vercel rewrites proxy the API — not used in the current
topology).

## Free-tier (Hobby) budget notes

- 1M function invocations/month, 100 GB/month fast data transfer,
  4 hours/month Fluid active CPU — ample for Stage A/B read/demo traffic;
  watch it at Stage C.
- Non-commercial use only (Vercel terms); Stage D upgrades.
- No server-side secrets in this project: the web tier holds zero
  `SOS_*` secrets; auth flows redirect through the Render API.

## Verification (after first deploy)

1. Production URL serves the landing page (`/`).
2. With `NEXT_PUBLIC_API_BASE` set: the demo workspace renders LIVE data
   (no "fixture/demo mode" badge) and `GET <base>/api/v1/health` returns
   `{"status": "ok"|"degraded", ...}` truthfully.
3. With it unset: the cockpit renders the labeled fixture demo (Journey 1
   still demonstrable — honest degraded mode, never a fake live claim).
4. `bun run lint && bun run typecheck && bun test` green in CI on every
   PR touching `apps/web/**` (the `pub` workflow, `.github/workflows/pub.yml`).
