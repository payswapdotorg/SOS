# PUB-02 Implementation Checkpoint (Next.js public cockpit)

**Work Order:** `spec/deployment/PUBLIC-DEPLOYMENT-CONTRACT.md` §D item
PUB-02 (binding), traceable to directive §5 (public user experience), §16-B
(Worker B — web product), design §1 (architecture: apps/web as
presentation/client surface) and design §13 (product boundary).
**State:** `WAITING_FOR_ARCHITECT` (review iteration 1)
**Branch:** `work/pub-02-nextjs-cockpit` (from live `main` HEAD `7b1adb4a…`,
the post-PUB-10-reconciliation commit; PUB-00 — the only declared
dependency — is MERGED as `ad3bf5c` (PR #23), verified by live Git history)
**Base SHA (dispatch commit, live main):**
`7b1adb4a6461565d54d689a05bda159474646966`
**Implementation head (code, tests, docs):**
`53cf06c777820d57526b40bc53dd25cf5a50fda7`
**Branch tip:** the commit carrying this checkpoint plus the
`public-deployment-state.json` status update (a documentation-only delta
from the implementation head above; a commit cannot embed its own SHA —
the authoritative review head is recorded in the worker report). All
verification below was produced at the implementation head and re-verified
at the tip (identical results — the tip adds state files only).

## Dependency proof (verified by the Worker from live Git history at the base)

- PUB-00 merged as `ad3bf5c86495fc4e920460a5fed6a3d3143bb260` (PR #23),
  ancestral to the base `7b1adb4` (the base is the PUB-10 reconciliation
  commit recorded on top of that merge).
- **No unmerged sibling dependency:** PUB-02 builds against the typed API
  CONTRACT (contract §C) and demo FIXTURES only — zero references to
  PUB-01's unmerged branch, code or schemas (house law: an unmerged sibling
  is never a dependency). The client's wire shapes are the contract §C.3
  DTO minimums (field names binding); the fixtures are typed demo data.

## Scope implemented (exactly the allowed surface)

Everything created lives in `apps/web/**` (55 files committed) plus this
checkpoint, the PUB-02 status fields in
`spec/development-state/public-deployment-state.json`, and
`docs/deployment/UI-GUIDE.md` (UI guide only — the docs/deployment doc
PUB-02 is allowed to add). No file outside that surface was created,
modified or deleted.

`apps/web` contents (directive §4 layout: `app/`, `components/`, `lib/`,
`hooks/`, `styles/`):

- `lib/api/` — THE typed client module (law §8): `types.ts` (full contract
  §C mirror: 6 truth states, 8 error codes, collection + error envelopes,
  all DTO minimums with binding field names), `endpoints.ts` (directive §7
  endpoint map, relative `/api/v1` paths only), `errors.ts` (`ApiError` +
  envelope guard), `client.ts` (fetch wrapper honoring
  `NEXT_PUBLIC_API_BASE` — unset ⇒ fixture/demo mode, empty ⇒ same-origin,
  configured ⇒ that origin; error-envelope parsing; transport failures
  surface as `ApiError` with `code = null`, never as resource truth
  states), `index.ts` (the single barrel). `fetch(` appears in exactly this
  module; no absolute API URL anywhere in source (fixture repo URLs are
  data/provenance per the contract `sourceRef` DTO; a doc example and a
  form placeholder are the only other http strings).
- `lib/fixtures/demo.ts` — the typed demo dataset (Journey-1 seed story):
  one demo workspace, mission + approved revision, 4 brownfield systems
  with recovery truth states SUCCESS / UNKNOWN (running) / FAILED /
  UNSUPPORTED and a recovered architecture graph (9 nodes, 11 edges),
  evidence across all 7 kinds and all 6 truth states, 3 candidates with
  multi-objective evaluations (two on the Pareto front, one dominated; no
  score/rating/overall field anywhere), an assurance run whose FAILED
  rollback-drill check yields an honest CONDITIONAL_PASS verdict, decisions
  covering all six actions including an ASK awaiting owner action (full
  askPayload: decision, 3 alternatives, evidence quality, uncertainty,
  tradeoffs), an experiment with events (incl. an UNKNOWN canary-health
  event), a DemoProvider execution receipt (`demo: true`), jobs (incl. a
  FAILED one with errorState), a learning record (PARTIALLY_CONFIRMED), an
  architecture-memory entry (PENDING, actual effects EMPTY), and a
  chronological activity trail.
- `hooks/` — `useResource` (light data layer with honest
  loading/error/data; loading is derived, refetch reloads), demo-local
  interaction state (mission approval, ASK responses — labeled demo,
  never presented as persisted).
- `app/` — landing (`/`), sign-in route wired for PUB-04 (fixture mode
  explains the flow; performs no fake login), workspace shell
  (`/workspace/*`) with the eight directive §5 sections: overview, mission
  journey editor, systems (+ onboarding with two explicit
  GREENFIELD/BROWNFIELD modes + architecture graph rendering), evidence
  explorer (filters by kind + truth state), candidates (six trade-off
  dimensions side-by-side + multi-objective table + Pareto membership +
  assurance view), experiments (lifecycle track + events + executions +
  receipts), decisions (governing-decision panel; ASK first-class with
  approve/reject/provide-evidence), memory, activity. Plus a demo-artifact
  route so fixture signed-URL links resolve to an honest explanation
  instead of a 404.
- `components/` — UI primitives (badge, button, card, key-value,
  state-pill with six visually distinct truth states, honest
  loading/error/empty states, timeline), shell (header, nav, sticky
  footer, GitHub mark) and the section views.
- `styles/globals.css` — Tailwind 4 + a11y details (skip link, focus
  outlines, scroll areas, reduced-motion).
- `tests/` — the bun test suite (below).
- `package.json` defines `lint`, `typecheck`, `test` (and `dev`, `build`,
  `start`); runnable with bun (bun install / bun run lint /
  bun run typecheck / bun test). Dependencies: next 16, react 19,
  lucide-react; dev: typescript 5, eslint 9 + eslint-config-next 16,
  tailwind 4, bun-types.

Semantic boundary honored (law §4, contract §A.5): the app renders what
the contract provides — no autonomy-policy interpretation, no
evidence-status invention, no promotion logic, no single-score ranking;
truth states are preserved visually (distinct pills, EMPTY ≠ UNKNOWN);
the user is presented as the mission authority; demo actions are labeled
demo-local and fabricate nothing.

## Verification (run at the exact head; recorded verbatim)

```text
$ cd apps/web && bun install
Checked 367 installs across 438 packages (no changes) [13.00ms]
$ bun run lint
$ eslint .
(exit code 0; no output — clean)
$ bun run typecheck
$ tsc --noEmit
(exit code 0; no output — clean)
$ bun test
 59 pass
 0 fail
 526 expect() calls
Ran 59 tests across 3 files. [2.04s]
(exit code 0)
$ cd /home/z/SOS && python3 -m pytest
551 passed in 10.75s
```

Test counts: 59 bun tests across 3 files — typed client (runtime
resolution, URL building, endpoint map, error-envelope parsing,
fixture-mode serving incl. NOT_FOUND, mocked API-mode fetch incl. the
no-masquerade transport-error rules), fixtures honesty (7 kinds × 6 truth
states with EMPTY/UNKNOWN distinctness, Pareto + no-score scan, ASK
payload completeness, demo-receipt badges, honest CONDITIONAL_PASS,
directive §8 job field set, chronological audit), key components (six
distinct truth-state renderings, decision panel fields, ASK panel with
owner actions, candidate trade-offs without any AI score, evidence card
fields, execution receipts incl. the UNKNOWN-running case, architecture
graph, landing/sign-in honesty, eight nav sections, sticky footer).

**Fixture-mode smoke (self-verified with a headless browser — agent-browser
against the dev server on localhost:3100):** landing renders (name,
tagline, both actions, DEMO disclosure); Explore Demo lands on the
workspace; every section renders with data from the fixtures — mission
journey (all 7 stages, edit → propose → approve updates approval state
with who/when, labeled demo-local), systems (both onboarding modes with
the brownfield form; recovery states SUCCESS/UNKNOWN/FAILED/UNSUPPORTED
each rendered distinctly; graph diagram 9 nodes/11 edges + exact
node/edge lists; recovery job card with error state), evidence (all 7
kinds; state filter shows EMPTY vs UNKNOWN distinctly; signed artifact
links resolve to the demo-artifact page), candidates (six trade-off
dimensions per candidate; multi-objective table; Pareto front vs
dominated; assurance CONDITIONAL_PASS with the FAILED check), experiments
(CANARY lifecycle track, events incl. the UNKNOWN canary event, DEMO
receipt badge, request hash, artifact links), decisions (all six actions;
the ASK panel shows the exact decision, alternatives, evidence quality,
uncertainty; Approve records a demo-local authorization + session-local
activity entry, honestly labeled), memory (learning + architecture
memory), activity (chronological audit trail incl. the rollback story),
sign-in (PUB-04 flow explained; no fake login). No console errors or page
errors during the walk (React DevTools/HMR dev-noise only). Responsive:
no horizontal overflow at 390px; left nav collapses to a horizontal
scroll rail; footer sticks to the bottom on a tall viewport (measured
gap 0 between footer bottom and viewport bottom) and is pushed down
naturally on overflow pages.

## Honest deviations and findings

1. **Audit-trail endpoint path is provisional.** Directive §7 lists no
   explicit audit-events route, while contract §C.2 mandates persisted
   audit events (actor/action/target/timestamp/meta) and directive §5
   requires the Activity surface. The client's endpoint map references
   `/api/v1/audit` as a clearly-commented provisional path, to be
   reconciled against PUB-01's finalized wire surface. In fixture mode
   the Activity surface is fully served; in API mode an honest error
   state would show if the final API exposes it elsewhere. Disclosed for
   the Architect; no silent assumption is made.
2. **Client-side extensions pending PUB-01 full schemas.** The contract
   §C.3 DTO minimums are field-name binding, and full richer types are
   owned by `services/api/schemas`. The demo cockpit needs a few
   additional fields (e.g. `Decision.candidateId/candidateName/status/
   createdAt`, `AssuranceRun.verdictNote`, `Experiment.candidateName`) and
   richer inner shapes for journey arrays (goals/outcomes/stakeholders/
   measures/constraints/preferences). These are additive and documented;
   the binding minimum field names are exactly as bound. When PUB-01
   lands, the typed mirror should be regenerated/validated against the
   OpenAPI document (design D4) — a reconciliation task for the review.
3. **Demo-mode mutations are local-only.** With no backend configured,
   owner actions (mission approval, ASK responses) update session-local
   state and are labeled as such ("demo-local, not persisted; nothing is
   fabricated"). No optimistic fake persistence, no invented server
   confirmations.
4. **Fixture latency.** Fixture serving adds a 180ms simulated latency so
   the honest loading states are actually visible in the demo. Data
   content is unaffected; tests bypass nothing (the latency is real for
   tests too — suite runs ~2s).
5. **The demo dataset includes four brownfield systems** (the work-order
   fixture minimum asks for the recovered one; three more demonstrate the
   required truth-state distinctions in recovery progress states —
   UNKNOWN running, FAILED, UNSUPPORTED). No greenfield system row is
   included; greenfield onboarding is demonstrated as the explicit UI
   flow it is (mode card + hypothesis form), matching directive §5's
   two-mode onboarding requirement.

## Known limitations

1. API mode is exercised by unit tests with a mocked `fetch` — no live
   FastAPI exists to integrate against yet (PUB-01 unmerged; building
   against an unmerged sibling is forbidden). The wire paths, envelopes
   and error handling are tested; end-to-end integration lands when
   PUB-01 merges and PUB-03 deploys.
2. `next build` / production-start are defined as scripts but not part of
   the gate (the acceptance criteria are lint/typecheck/test + fixture
   smoke, both satisfied); Vercel build configuration is PUB-03's item.
3. The workspace is single-workspace (the demo workspace) — multi-workspace
   navigation and real tenancy arrive with PUB-04 (GitHub OAuth +
   tenancy); the sign-in route already explains the flow.
4. Query-parameter names for collection scoping (`?workspace=`,
   `?candidate=`, `?projection=current-revision`) are reasonable client
   references pending PUB-01's OpenAPI; they are transport details, not
   semantics, and trivially reconcilable.

## Risk / rollback

**Risk:** the client could drift from the real wire contract once PUB-01
lands. Mitigation: the typed mirror is the single source (design D4 —
regenerate/validate against the OpenAPI document at review); fixtures are
typed against the same types; tests pin the contract essentials (enums,
envelopes, endpoint paths, DTO minimums). **Rollback:** ordinary Git
revert of the three PUB-02 commits — the app is a new additive overlay
directory (`apps/web/`) touching no frozen file, no `src/sos` code, no
gate logic, no CI semantics.

## Completion state

`WAITING_FOR_ARCHITECT`. No merge performed, no self-approval, no
successor work, no frozen-surface modification (python suite re-run at
the head: 551 passed — identical to the verified baseline), no secrets in
any file or commit, PR #24 open for Architect review. Corrections stay
on the same branch/PR.
