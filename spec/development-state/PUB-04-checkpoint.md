# PUB-04 Checkpoint — GitHub authentication + tenancy

**Work item:** PUB-04 (contract §D PUB-04) · **Owner:** Worker B (web product)
**Status:** `WAITING_FOR_ARCHITECT` (review-ready; this worker never merges)
**Branch:** `work/pub-04-github-auth` · **PR:** #28 (`work/pub-04-github-auth` → `main`)

## Exact revisions

| Field | Value |
|---|---|
| Base (dispatched, verified = live merged main) | `3eeefad72b502d678918e141d70b4f398b1ca9c0` |
| Implementation head | `1b119639f35350dc05c96a3a4ac90dadf0333b03` |
| Branch tip after this checkpoint commit | the commit that adds this file (checkpoint + state-record only; no code) |
| Dependencies (verified MERGED in `public-deployment-state.json`) | PUB-01 (`c98972a`), PUB-02 (`9b8d031`) — PUB-03 (`b389018`) also merged at base |

## Files changed (all inside the §D PUB-04 allowed surface)

**`apps/web/**`** (17 files: 12 modified, 5 new)
`app/signin/page.tsx` (live flow wiring), `app/signin/callback/page.tsx` (NEW),
`app/workspace/new/page.tsx` (NEW), `app/workspace/layout.tsx`,
`app/workspace/page.tsx`, `app/workspace/mission/page.tsx`,
`components/shell/account-menu.tsx` (NEW), `components/shell/workspace-header-bar.tsx`
(NEW), `components/shell/workspace-header.tsx`, `components/shell/workspace-nav.tsx`
(`?ws=` preservation), `components/shell/site-footer.tsx` (mode-truthful copy),
`components/workspace/overview-view.tsx` + `mission-view.tsx` (dynamic workspace
selection + honest fresh-workspace empty states), `hooks/use-workspace-selection.ts`
(NEW), `lib/api/{client,endpoints,types}.ts` (session/account/logout/createWorkspace,
CSRF mutationHeaders, `githubStartUrl`, `me()` SessionDTO mapping fix),
`next.config.ts` (same-origin `/api/v1` rewrite proxy), `tests/auth.test.ts` (NEW),
`tests/components.test.tsx` (one outdated copy assertion updated — the sign-in
copy changed because PUB-04 landed; apps/web is this item's surface).

**`services/api/auth/**`** — `session.py` (real `sos1.*` token resolution +
PUB-01 stub byte-compatibility + cookie-flag authority), `store.py` (NEW:
AuthStore port + LOCAL SQLite impl + fail-closed non-LOCAL refusal),
`csrf.py` (NEW: double-submit enforcement).

**`services/api/routes/auth.py`** — PUB-01 session endpoints kept
(shape-identical; logout upgraded: CSRF + server-side revocation + audits) +
NEW `include_in_schema=False` endpoints: `/auth/github/start`,
`/auth/github/callback`, `/auth/github/fake/authorize`,
`/auth/github/fake/consent`, `/auth/account` (route-local DTOs per the
PUB-01 `CreateWorkspaceRequest` precedent; §C.3 minimums stay in
`services/api/schemas`).

**`providers/github/oauth.py`** (NEW) — `FakeGitHubOAuth` (deterministic,
labeled, LOCAL-only) + `LiveGitHubOAuth` (httpx, PKCE S256, `read:user`) +
fail-closed `build_github_oauth` + PKCE helpers.

**`db/migrations/0012_auth_sessions_oauth_states.{up,down}.sql`** (NEW,
reversible pair; renumbered from 0004 in the PUB-05 sibling merge reconciliation —
the dispatch base 3eeefad predated PUB-05's 0004-0011, and the number-keyed
migration runner cannot carry duplicate numbers).

**`tests/test_pub04_*.py`** (NEW only: 3 files, 32 tests).

**`docs/deployment/`** — `auth-tenancy.md` (NEW), `api-reference.md`
(PUB-04 endpoint section), `UI-GUIDE.md` (topology + surfaces).

**`spec/development-state/public-deployment-state.json`** — PUB-04 status
fields only (this commit).

No file outside the allowed surface is modified. `src/sos/**` untouched;
all §A.2 frozen documents byte-identical (the transiently-regenerated
`W15-gate-report.json` was restored before commit).

## Traceability

- **Directive §6** (authentication and tenancy): GitHub OAuth; identity →
  user → workspace tenancy; every durable row carries tenant ownership
  (PUB-01 migrations); the browser never supplies the tenant identifier
  (the account surface derives memberships from the session only — tested).
- **Directive §16-B (PUB-04)**: GitHub OAuth ✓, session management ✓
  (server-side store, revocation, cookie flags), workspace membership ✓
  (owner/member roles surfaced), tenant-aware navigation ✓ (switcher +
  `?ws=` + roles), protected actions ✓ (unauthenticated mutations 401;
  workspace creation requires a session; CSRF pair on the client's every
  mutation).
- **SECURITY**: S1 (no secrets in the browser — only `NEXT_PUBLIC_API_BASE`
  reaches the bundle; the OAuth token is server-only, used once), S2 (no
  secrets in Git), S5 (tenant isolation unchanged — enforced in the
  persistence adapter; re-verified), S6 (CSRF: sameSite + double-submit;
  see boundary 1), S7 (auth-required mutations — re-verified 401), S17
  (auth login/logout audited, append-only).

## Verification (run at the exact implementation head `1b11963`)

| Command | Result |
|---|---|
| `python3 -m pytest` | **638 passed** (606 baseline + 32 PUB-04; the frozen `tests/test_pub01_*` suite untouched and green — the OpenAPI snapshot hash is byte-identical) |
| `python3 -m compileall -q src tests services providers execution` | clean |
| `python3 tools/final_gate_check.py` | **OVERALL PASS — 12/12** |
| `cd apps/web && bun install` | ok (lockfile unchanged) |
| `bun run lint` / `bun run typecheck` | clean / clean |
| `bun test` | **99 pass** (80 baseline + 19 PUB-04) |

**Acceptance journey (LOCAL, fake-GitHub) — API level** (`tests/test_pub04_sessions_tenancy.py::test_journey2_login_workspace_isolation_logout`):
login (new user `octo-newcomer`) → account shows no workspaces → workspace
create (`ws-newco-lab`, role **owner**) → tenant-aware navigation
({demo, newco-lab} only; seeded `alice-lab`/`bob-lab` invisible) →
cross-tenant read 404 / collections zero rows / cross-tenant mutation 404 →
own-workspace mutation 200 + audited → logout without CSRF **403** →
logout with CSRF 200 → **old token replay dead (server-side revocation)** →
post-logout mutations 401, reads demo-only.

**Acceptance journey — browser level** (uvicorn :8099 + `next dev` with
`NEXT_PUBLIC_API_BASE=""`, same-origin proxy; headless Chromium): the full
flow was driven click-by-click — sign-in → live "Continue with GitHub" →
the labeled fake consent page → identity pick → callback completion →
auto-redirect into `/workspace` with the tenant-aware header (workspace
switcher with demo + created workspaces, "octo-newcomer · LOCAL
fake-GitHub" chip, New workspace, Sign out), `?ws=` switching + nav-link
preservation, workspace creation through the UI (auto-slug, redirect into
the fresh workspace, honest "No mission yet" empty state), and sign-out
(cookies cleared, session dead). Cookies, redirects and `Set-Cookie`
passthrough through the Next rewrite proxy were verified with curl at each
hop.

## Known limitations / disclosed boundaries

1. **CSRF scope (S6):** the double-submit pair is enforced on the
   auth-surface mutations PUB-04 owns (logout; the OAuth consent is
   state-protected). The frozen PUB-01 tests exercise stub-session
   mutations without the header (stubs = LOCAL test facility, exempt,
   never enabled for public), and the per-mutation dependency wiring for
   the remaining routes lives in `services/api/dependencies/**` — outside
   PUB-04's allowed surface. The web client already sends `x-sos-csrf` on
   every mutation; SameSite=Lax blocks cross-site cookie carriage
   meanwhile. The natural completion lane is PUB-06/PUB-10.
2. **Auth store persistence mode:** `auth_sessions`/`oauth_states` are
   served by the PUB-04 auth store over the LOCAL SQLite database. With
   `SOS_PERSISTENCE=neon` the store fails closed (passive resolution →
   anonymous; active auth endpoints → honest
   `reason=auth_store_unavailable`) until PUB-05 unifies the auth tables
   into the Neon seam (`providers/neon/**` is Worker A's lane).
3. **Web topology reconciliation:** PUB-04 ships + verifies the same-origin
   proxy topology (`NEXT_PUBLIC_API_BASE=""` + `SOS_API_PROXY_TARGET`;
   `next.config.ts` rewrite). The direct cross-origin topology documented
   in `infra/vercel/README.md` (PUB-03) would require CORS on the API
   (outside PUB-04's surface). The runbook reconciliation is flagged for
   the TL (infra/** is PUB-03's lane); documented in
   `docs/deployment/auth-tenancy.md` §5.
4. **Device flow:** the directive's browser cockpit is served by the web
   application flow (authorization code + PKCE). A device flow is not
   implemented (no surface in the cockpit requires it); noted for
   interpretation, not as a gap.
5. **Next 16 dev origin note:** local browser verification must use
   `http://localhost:<port>` (Next dev blocks hydration for raw-IP hosts
   like `127.0.0.1`) — documented in the LOCAL walkthrough.

## Explicit statements

- **No unmerged sibling is a dependency** (PUB-01 and PUB-02 are verified
  merged at the base; PUB-05/PUB-06/PUB-07 are parallel and untouched).
- **No frozen surface touched** (`src/sos/**` untouched; all §A.2 frozen
  documents byte-identical; existing test files other than the one
  apps/web copy assertion inside PUB-04's own surface are untouched; the
  OpenAPI snapshot hash unchanged).
- **No merge performed**; review corrections will stay on this PR.
- Stop state: **WAITING_FOR_ARCHITECT**.
