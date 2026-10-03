# SOS Web Cockpit — UI guide (PUB-02)

**Status:** UI guide for `apps/web` (the SOS public cockpit). Part of the
Public Deployment Overlay docs; the frozen W0–W15 surface is untouched.
**Scope of this document:** what the cockpit renders, how it behaves, and
how operators configure it. (The API reference doc is owned by PUB-01.)

## 1. What this app is

A Next.js 16 (App Router) + TypeScript client for the SOS `/api/v1` wire
contract. It renders mission, systems, evidence, candidates, assurance,
decisions (with `ASK` as a first-class state), experiments, execution
receipts, learning/memory and the audit trail.

**What it is not:** it implements no SOS decision rule — no
autonomy-policy interpretation, no evidence-status invention, no promotion
logic, no single-score candidate ranking. The client renders what the API
(or, in demo mode, the typed fixtures) provide; LLM output stays proposal
material. (Frozen architecture §12; deployment contract §A.5.)

## 2. Running it

```bash
cd apps/web
bun install
bun run dev          # http://localhost:3000 (use -p to change the port)
bun run lint         # ESLint (next/core-web-vitals + next/typescript)
bun run typecheck    # tsc --noEmit
bun test             # typed client, fixtures honesty, key components
```

## 3. API mode vs. fixture/demo mode

The app speaks to **one typed client module** (`lib/api`) with **relative
URLs only** — no absolute API URL is ever hardcoded. Mode resolution:

| Environment | Behavior |
|---|---|
| `NEXT_PUBLIC_API_BASE` **unset** | **Fixture/demo mode** — the typed demo dataset (Journey-1 seed story) is served client-side so the whole cockpit is demonstrable standalone. The UI labels this state `DEMO DATA` everywhere. |
| `NEXT_PUBLIC_API_BASE=""` (set, empty) | **API mode, same-origin** — requests go to relative `/api/v1/...` paths. **The PUB-04 topology**: `next.config.ts` proxies `/api/v1/*` to `SOS_API_PROXY_TARGET` (default `http://127.0.0.1:8099`) so the OAuth flow and session cookies stay on ONE origin. Set `SOS_API_PROXY_TARGET` (server-side env, never `NEXT_PUBLIC_*`) on Vercel to the API origin. |
| `NEXT_PUBLIC_API_BASE=https://api.example.com` | **API mode, direct** — requests go to that origin + `/api/v1/...`. NOTE (PUB-04): credentialed browser auth needs CORS + `SameSite=None` cookies on the API, which is NOT configured — use the same-origin proxy topology above for authenticated deployments. |
| `NEXT_PUBLIC_API_MODE=fixtures` | Forces fixture mode regardless of base (useful for previews). |

In demo mode, the header shows a `DEMO DATA` badge, receipts from the
DemoProvider carry an explicit `DEMO` marker, owner actions (mission
approval, ASK responses) record **demo-local state only** and say so —
nothing is fabricated as persisted truth.

## 4. Surfaces (directive §5)

- **Landing** (`/`) — product name, tagline, `Explore Demo` +
  `Sign in with GitHub`.
- **Sign-in** (`/signin`) — PUB-04 wired: the button navigates to the
  API's OAuth start (`/api/v1/auth/github/start?next=…` — state + PKCE are
  server-held; the browser never sees a token). In fixture mode it explains
  the flow and performs no fake login.
- **Sign-in callback** (`/signin/callback`) — PUB-04: completes the flow —
  verifies the API-issued session client-side, routes into the workspace,
  and renders honest outcomes (success with the provider label — including
  the `LOCAL fake-GitHub` label — or the specific failure reason from the
  API; never a fake success).
- **Workspace shell** (`/workspace/*`) — left nav: Mission / Systems /
  Evidence / Candidates / Experiments / Decisions / Memory / Activity.
  PUB-04: the header is tenant-aware — a workspace switcher restricted to
  the SERVER-visible (tenant-scoped) workspaces, the account chip (user +
  provider label), **New workspace**, and **Sign out** (server-side
  revocation). The `?ws=` selection is carried across nav links and is
  never trusted from outside the server list.
- **Workspace creation** (`/workspace/new`) — PUB-04: a signed-in owner
  action (name + slug with the server's exact validation rule); the creator
  becomes the owner and lands in the fresh workspace. In fixture mode the
  form renders disabled with an honest explanation (no server to mutate).
- **Mission journey** (`/workspace/mission`) — Mission → Goals → Outcomes →
  Stakeholders → Measures → Constraints → Preferences → *Approve Mission
  Revision*. The user remains the mission authority; approval state
  (proposed/approved, who, when) is visible.
- **Systems** (`/workspace/systems`) — system list + detail, onboarding with
  two explicit modes (GREENFIELD / BROWNFIELD), recovery states rendered
  with the six truth states, architecture graph as a diagram + exact
  node/edge list, recovery job card.
- **Evidence explorer** (`/workspace/evidence`) — all 7 kinds, all 6 truth
  states (honestly labeled; `EMPTY` ≠ `UNKNOWN`), provenance, timestamps,
  exact revisions, related system state, confidence, artifact signed-URL
  links.
- **Candidates** (`/workspace/candidates`) — side-by-side comparison across
  the six trade-off dimensions (mission effect / cost / risk / constraints /
  evidence / reversibility), a multi-objective evaluation table with
  Pareto-front membership, and the assurance view (checks + verdict per
  candidate). **No single "AI score" exists by design.**
- **Decisions** (`/workspace/decisions`) — every consequential action shows
  the governing decision (why, evidence, authority, expected impact, risk,
  blast radius, reversibility, required approvals). `ASK` is a first-class
  state with the exact decision requested, alternatives with expected
  outcomes and trade-offs, evidence quality, uncertainty, and
  approve / reject / provide-evidence owner actions.
- **Experiments** (`/workspace/experiments`) — lifecycle stage track
  (PROPOSED → … → CANARY …, ROLLED_BACK shown honestly), event timeline,
  executions with provider (demo/apify), request hash and receipts (demo
  receipts badged `DEMO`).
- **Memory** (`/workspace/memory`) — learning records + architecture memory
  (context, predicted vs actual effects, uncertainty, verdict, lessons).
- **Activity** (`/workspace/activity`) — chronological audit trail
  (actor / action / target / timestamp / meta).

## 5. Truth states and honesty rules

`SUCCESS / EMPTY / FAILED / UNKNOWN / UNSUPPORTED / UNAVAILABLE` render as
six visually distinct pills (color + glyph), are never converted into each
other, and `EMPTY` is always labeled "observed, none" to stay distinct from
`UNKNOWN`. Transport/API failures surface as typed errors (`ApiError` with
the contract error envelope codes) — never as fake resource states. Loading,
error and empty states are implemented everywhere and are honest.

## 6. Accessibility & responsiveness

Semantic landmarks (`header`, `nav`, `main`, `footer`), a skip-to-content
link, keyboard-focus outlines, ARIA roles on status/alert regions, 44px+
touch targets, long lists inside scroll areas (`max-height` +
`overflow-y`), mobile-first layouts (the left nav collapses to a horizontal
scroll bar on small screens), and a footer that sticks to the bottom on
short pages and is pushed down naturally on long ones
(`min-h-screen flex-col` + `mt-auto`).

## 7. Developer notes

- All API access flows through `lib/api` (types, endpoint map, fetch
  wrapper, fixture serving). Components never call `fetch` directly.
- The typed contract mirrors the PUBLIC-DEPLOYMENT-CONTRACT §C DTO minimums
  (field names binding). Where the directive §7 surface defines no `{id}`
  route, the client fetches the collection and narrows — transport mapping
  only.
- The audit-trail endpoint reference (`/api/v1/audit`) is provisional until
  PUB-01 finalizes the wire surface (disclosed in the PUB-02 checkpoint).
- Tests: `bun test` covers the typed client (mode resolution, URL building,
  envelope parsing, mocked API fetch), fixture honesty (7 kinds × 6 states,
  Pareto/no-score, ASK payload, demo receipts) and key components
  (truth-state pills, decision/ASK panels, candidate comparison, evidence
  cards, receipts, graph, landing/sign-in).
