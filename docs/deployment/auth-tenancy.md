# SOS Public Deployment — Authentication & Tenancy (PUB-04)

**Status:** ACTIVE — operator/developer guide for the GitHub authentication +
tenancy layer delivered by PUB-04 (contract §D PUB-04; directive §6, §16-B;
SECURITY threat notes).

## 1. What was delivered

| Capability | Mechanism |
|---|---|
| GitHub OAuth (web application flow) | Authorization code + **PKCE S256** + single-use `state` (CSRF) — `GET /api/v1/auth/github/start` → provider → `GET /api/v1/auth/github/callback` |
| Server-side sessions | Opaque `sos1.*` bearer tokens, **sha256-hashed at rest** in `auth_sessions` (migration 0004); 7-day absolute TTL |
| Session cookie | `sos_session` — **httpOnly + SameSite=Lax** always, **+ Secure** outside LOCAL |
| Logout | Server-side revocation (`revoked_at`); the old token is dead even if the cookie is replayed |
| CSRF (S6) | Double-submit: `sos_csrf` readable cookie + `x-sos-csrf` header == the stored per-session token (constant-time compare); enforced on real-session mutations (see §6 boundary) |
| Tenancy | `User → Workspace → workspace_members (owner\|member)`; the browser NEVER supplies the tenant identifier — the tenant scope derives from the server-side session (directive §6) |
| Account surface | `GET /api/v1/auth/account` — user + memberships with roles (tenant-aware navigation source) |
| LOCAL test mode | The deterministic **fake-GitHub provider** — the full flow with zero secrets and zero network (§4) |
| Rate limiting | §13 auth bucket on the flow endpoints (start/callback/consent) + the PUB-01 middleware buckets (per-IP, anonymous, auth for login/logout) |

## 2. Environment variables (infra/environment.example is the name authority)

| Variable | Required | Notes |
|---|---|---|
| `SOS_GITHUB_CLIENT_ID` / `SOS_GITHUB_CLIENT_SECRET` | preview/public only | The GitHub OAuth app credentials. **Fail-closed**: without them, non-LOCAL sign-in redirects with `reason=provider_unconfigured` — never a silent fallback to the fake provider. |
| `SOS_SESSION_SECRET` | preview/public only | Already enforced by PUB-01's config (32+ bytes). LOCAL boots with zero env. |
| `SOS_WEB_BASE_URL` | optional | Post-flow redirects default to the request origin (correct in the same-origin proxy topology); set this only for a split-origin deployment. |
| `SOS_API_PROXY_TARGET` (web server, **not** `NEXT_PUBLIC_*`) | web deployments | The origin the Next.js server proxies `/api/v1/*` to (see §5). |
| `NEXT_PUBLIC_API_BASE` | web deployments | Set-but-EMPTY (`""`) for the same-origin proxy topology (see §5). |

### GitHub OAuth app setup (operator, PUBLIC/preview)

1. GitHub → Settings → Developer settings → OAuth Apps → New OAuth App.
2. **Authorization callback URL**: `https://<web-origin>/api/v1/auth/github/callback`
   (the same-origin proxy forwards it to the API; the API derives
   `redirect_uri` from the browser-visible origin — `X-Forwarded-Host`/`-Proto`).
3. Requested scope: `read:user` (the API reads the identity once; the token
   is **never persisted** and never reaches the browser).
4. Set `SOS_GITHUB_CLIENT_ID` / `SOS_GITHUB_CLIENT_SECRET` on the API service.

## 3. The flow (browser, end to end)

```text
/web /signin ──link──▶ GET /api/v1/auth/github/start?next=/workspace
                          │ creates oauth_states row (state + PKCE verifier,
                          │ 10-min TTL, single-use) — SERVER-held
                          ▼
              302 github.com/login/oauth/authorize
              (client_id, redirect_uri, scope=read:user, state,
               code_challenge + method=S256)
                          │  LOCAL instead: 302 to the labeled fake consent
                          │  surface /api/v1/auth/github/fake/authorize
                          ▼
              GitHub (or the fake page) redirects back with code+state
                          ▼
              GET /api/v1/auth/github/callback?code&state
                1. state: single-use + unexpired (else honest error redirect)
                2. code exchange with the server-held verifier (PKCE)
                3. identity → persistence.upsert_user (idempotent by github_id)
                4. session row + cookies: sos_session (httpOnly) + sos_csrf (readable)
                5. audit auth.login
                          ▼
              302 /signin/callback?status=ok&next=…   (the cockpit page)
                          ▼
              the cockpit verifies the session (GET /auth/session) and
              routes into the workspace (tenant-aware)
```

Any failure redirects with `status=error&reason=<honest reason>`
(`invalid_state`, `replayed_state`, `expired_state`, `authorization_denied`,
`exchange_failed`, `identity_failed`, `provider_unconfigured`,
`auth_store_unavailable`, `invalid_request`) — never a fake success, never
a partial session.

## 4. LOCAL test mode: the deterministic fake-GitHub provider

`SOS_ENV=local` selects `FakeGitHubOAuth` (providers/github/oauth.py):

- **Clearly labeled** — the consent page banner states "This is NOT
  github.com"; the session `provider` is `fake-github` (surfaced in the UI
  account chip and the sign-in callback page).
- **Refused outside LOCAL** — the fake authorize/consent endpoints return
  403 FORBIDDEN when `SOS_ENV != local` (fail-closed, SECURITY notes).
- **Deterministic fixture identities** (github_id collides with the seeded
  accounts, so the flow maps onto the SAME users):

  | login | github_id | behavior |
  |---|---|---|
  | `demo-owner` | 900001 | the demo workspace owner |
  | `alice` | 900002 | owner of `alice-lab` (seeded) |
  | `bob` | 900003 | owner of `bob-lab` (seeded) |
  | `octo-newcomer` | 910001 | the Journey-2 NEW user (auto-provisioned on first sign-in) |

- **Deterministic codes** — the consent step issues `fake:<state>:<login>`;
  the exchange validates the format + the single-use state row.

Full LOCAL walkthrough (zero env vars):

```bash
# terminal 1 — the API (LOCAL mode boots with zero env)
python3 -m uvicorn services.api.main:app --port 8099

# terminal 2 — the web (API mode, same-origin through the rewrite proxy)
cd apps/web
NEXT_PUBLIC_API_BASE="" bun run dev -- --port 3000
#   NOTE: use http://localhost:3000 in the browser (Next dev origin
#   protection blocks hydration for 127.0.0.1-style hosts)

# browser: http://localhost:3000/signin → Continue with GitHub →
#          the labeled fake consent page → pick an identity →
#          signed in, tenant-aware workspace shell
```

## 5. Web topology (PUB-04): same-origin proxy

Browser credentialed API calls need ONE origin for the session cookies. The
API ships no CORS middleware (its control plane is not cross-origin by
design), so `apps/web/next.config.ts` proxies:

```text
/api/v1/:path*  ──▶  ${SOS_API_PROXY_TARGET ?? http://127.0.0.1:8099}/api/v1/:path*
```

- Web env (Vercel project): `NEXT_PUBLIC_API_BASE=""` (set-but-empty —
  same-origin) + `SOS_API_PROXY_TARGET=https://<api-origin>` (server-side
  only; never `NEXT_PUBLIC_*` — SECURITY S1).
- The whole OAuth chain stays on the web origin (the API derives the
  GitHub `redirect_uri` and the post-flow redirect from the forwarded
  origin headers).
- Reconciliation note (TL/PUB-03): `infra/vercel/README.md` currently
  documents the direct-origin topology (`NEXT_PUBLIC_API_BASE=<api-url>`).
  That topology needs API-side CORS (outside PUB-04's allowed surface);
  the proxy topology above is the PUB-04-tested wiring — infra/** is
  PUB-03's lane, so the runbook reconciliation is left for the TL.

## 6. Security properties + honest boundaries

- OAuth `state` is single-use, 10-minute, server-held; PKCE verifier never
  leaves the server; the access token is used once and discarded.
- Session tokens: 32 random bytes, url-safe, **sha256 at rest**; logout
  revokes server-side; expiry fails closed to anonymous.
- CSRF: double-submit with the DB-backed expected value. **Boundary
  (disclosed)**: PUB-04 enforces the pair on the auth-surface mutations it
  owns (logout) — the frozen PUB-01 tests exercise stub-session mutations
  without the header (stubs are the LOCAL test facility and exempt), and
  the per-mutation dependency wiring for the remaining routes lives in
  `services/api/dependencies` (outside PUB-04's allowed surface — the
  natural lane is PUB-06/PUB-10). The web client already sends
  `x-sos-csrf` on every mutation, and SameSite=Lax blocks cross-site
  cookie carriage meanwhile.
- Tenant isolation is unchanged from PUB-01 (enforced in the persistence
  adapter; cross-tenant → 404/zero rows) — PUB-04 adds the account surface
  that derives memberships (with roles) from the session only.
- **Auth store boundary (disclosed)**: `auth_sessions`/`oauth_states` live
  in the PUB-04 auth store over the LOCAL SQLite database; with
  `SOS_PERSISTENCE=neon` the store fails closed (passive resolution →
  anonymous; active auth endpoints → honest
  `reason=auth_store_unavailable`) until PUB-05 unifies the auth tables
  into the Neon seam (providers/neon/** is Worker A's lane).
- OpenAPI: the PUB-04 endpoints are `include_in_schema=False` so the
  frozen PUB-01 OpenAPI snapshot stays byte-identical; they are documented
  HERE and in `docs/deployment/api-reference.md` instead.

## 7. Verification map (all runnable from the repo)

| Property | Check |
|---|---|
| Flow, cookies, state/PKCE, provider fail-closed, rate limit, audits | `tests/test_pub04_oauth_flow.py` |
| Journey-2 (login → workspace create → isolation 403/404 → logout/revocation), stub compat | `tests/test_pub04_sessions_tenancy.py` |
| Store semantics + migration 0004 round-trip | `tests/test_pub04_auth_store_migrations.py` |
| Client auth surface, CSRF header, open-redirect guard, tenant-aware nav | `apps/web/tests/auth.test.ts` |
