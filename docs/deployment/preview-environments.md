# Preview Environments (PUB-03)

Guidance for PREVIEW (directive §20): isolated, per-PR verification
environments on the free tier. Two lanes: **web previews** (automated,
cheap) and **API/state previews** (manual, deliberate). Previews are for
verification only — never a stage on the way to production, and never
pointed at production state.

## Web previews (Vercel)

- Vercel creates a preview deployment for every PR automatically once the
  project is imported (see `infra/vercel/README.md`; Root Directory
  `apps/web`, framework Next.js, `bun install` / `bun run build`).
- Preview environment variables (project settings → Preview scope):
  - `NEXT_PUBLIC_API_MODE=fixtures` — the DEFAULT recommendation: every
    preview runs the typed demo fixtures, so UI review needs zero
    infrastructure and can never touch real data. The cockpit labels this
    mode honestly ("fixture/demo mode" badge).
  - Live-data preview (optional, for API-integration review): set
    `NEXT_PUBLIC_API_BASE` to a preview API origin (below) instead.
- Preview URLs are unlisted but network-reachable — never configure
  secrets into preview-scope variables beyond `NEXT_PUBLIC_*` public
  values (security gate S1).

## Neon branches (data isolation)

Neon's free plan supports 10 branches per project — the natural preview
data layer:

```bash
export NEON_API_KEY=…
export SOS_NEON_BRANCH=preview-pr-31
python3 infra/neon/setup.py        # idempotent: creates branch + database + role
```

- Point the PREVIEW stack at that branch's connection URI
  (`SOS_DATABASE_URL` on the preview API service) — never at `main`.
- Migrations run at app boot, so the branch schema self-materializes.
- Cleanup: when the PR closes, delete the branch in the console or via
  `DELETE /projects/{id}/branches/{branch_id}` (Neon API). Stale preview
  branches consume the 10-branch budget — delete deliberately.

## API previews (Render — manual by design)

Render does not create per-PR free services automatically; the free tier
is also capped (one free web service per account on the classic limit;
blueprint preview environments require paid instance classes). The honest
options, in order of preference:

1. **LOCAL API against preview state** (most common): run
   `uvicorn services.api.main:app` locally with the preview branch wired
   (`SOS_ENV=preview`, `SOS_PERSISTENCE=neon`, `SOS_DATABASE_URL=<preview
   branch URI>`, `SOS_SESSION_SECRET=<dev secret>`); point the Vercel
   preview's `NEXT_PUBLIC_API_BASE` at it via a tunnel if browser-level
   verification is needed. Zero Render footprint.
2. **Manual Render preview service**: create a second free-tier service
   from the PR branch (if the account budget allows), wire the preview
   Neon branch, and delete it after review. Manual, disclosed, and never
   left running.
3. **Fixture-only previews**: for pure UI work, option 0 —
   `NEXT_PUBLIC_API_MODE=fixtures` — needs no API at all.

## What previews must never do

- Never point at the Neon production branch (`main`) — previews use
  `preview-pr-*` branches only.
- Never share the production `SOS_SESSION_SECRET` / `SOS_JOB_CALLBACK_SECRET`.
- Never run Apify billable jobs against preview data (`SOS_EXECUTION=demo`
  in every preview until PUB-08 explicitly changes this).
- Never persist anything in preview that production depends on (Render
  free instances are ephemeral by nature — that is the design, not a bug).

## CI as the primary preview gate

For most PRs the `pub` workflow (`.github/workflows/pub.yml`) is the
functional preview: the full §G matrix (pytest with the api group,
compileall, 12/12 final gate, apps/web lint/typecheck/bun test) runs on
every PR touching the overlay roots. Spin up a live preview environment
only when human verification of rendered behavior is genuinely needed.
