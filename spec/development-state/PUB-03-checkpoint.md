# PUB-03 Checkpoint — Free-tier infrastructure

**Work item:** PUB-03 (contract `spec/deployment/PUBLIC-DEPLOYMENT-CONTRACT.md` §D PUB-03; directive §3, §16-C, §20, §21)
**Worker:** Worker C (session `pub-03-freetier-infra`)
**Status:** WAITING_FOR_ARCHITECT (review-ready; this is NOT completion)
**Branch:** `work/pub-03-freetier-infra`
**PR:** #26 (https://github.com/payswapdotorg/SOS/pull/26)
**Base SHA:** `7a3b1eb29df0c67cdc54dc4182e7911eefd52891` (live merged main at dispatch: PUB-00 `ad3bf5c` + PUB-01 `c98972a` + PUB-02 `9b8d031` + TL merge reconciliations)
**Implementation head (all code + docs; all verification below ran on this tree):** `126e6ef2f34459ea4a5bb8e656b1153f59a01d24`
**Final branch head:** the checkpoint/state commit that follows the implementation head (adds only this checkpoint + `public-deployment-state.json` PUB-03 status fields — no code).

## Traceability

- Directive §3 (free-tier provider selection: Vercel Hobby / Render Free /
  Neon / Upstash / R2 / Apify budgets and lane constraints), §16-C (Worker C
  lane), §20 (LOCAL/PREVIEW/PUBLIC environments), §21 (launch stages A→C);
  contract §A.4 (overlay roots), §B (repository layout), §D PUB-03 (this
  work order), §G (gate matrix); SECURITY gates S1/S2/S3/S10/S11/S12/S14
  (referenced where the infra artifacts encode them).
- Dependencies: PUB-00 (MERGED as `ad3bf5c` — verified by Git evidence
  before work started). **No unmerged sibling is a dependency.** Built
  against merged main + the contract text only (PUB-01/PUB-02 merged
  artifacts — environment.example names, apps/web env semantics,
  `services.api.main:app` import layout — were read from main, not from any
  sibling branch).

## Files changed (equals the §D PUB-03 allowed surface exactly)

Modified (2):
- `infra/render.yaml` — FINAL Render blueprint, superseding the PUB-00
  skeleton (see below).
- `infra/environment.example` — additive names only (backward-compatible):
  web client names `NEXT_PUBLIC_API_BASE` / `NEXT_PUBLIC_API_MODE` (PUB-02
  consumer names, wired on Vercel by this item) + a documented
  operator-setup-shell section (`NEON_API_KEY`, `SOS_NEON_PROJECT`,
  `SOS_NEON_BRANCH`, `SOS_NEON_API_BASE`, `UPSTASH_OWNER_*`,
  `UPSTASH_REDIS_REST_*` — commented, never app runtime vars).

New (18):
- `infra/README.md` — infra index (what/owner + offline verification).
- `infra/vercel/vercel.json` + `infra/vercel/README.md` — Vercel project
  config template (framework nextjs, `bun install` / `bun run build`, no
  long-running work) + operator runbook (Root Directory `apps/web`,
  origin-only `NEXT_PUBLIC_API_BASE` — no `/api/v1` suffix, Hobby budget,
  verification steps).
- `infra/neon/setup.py` + `infra/neon/README.md` — idempotent
  check-then-act provisioning/verification via the Neon REST API (stdlib
  only; `--dry-run` / `--selftest` / `--verify-only`; connection-URI scheme
  adaptation to `postgresql+asyncpg://` per the app contract; branch-name
  policy enforced, preview convention `preview-pr-<N>`).
- `infra/upstash/setup.py` + `infra/upstash/README.md` — verification by
  native RESP PING over TLS (stdlib socket/ssl) or the Upstash REST API;
  optional `--create` via the v2 management API (console-first documented;
  the script honestly states the management API does not return the
  password/REST token).
- `infra/r2/setup.py` + `infra/r2/README.md` — verification-only script
  (HeadBucket, Put/Get/Delete probe round-trip, and the **anonymous-read
  rejection assertion** — security gate S3 — with a stdlib S3 SigV4 signer
  carrying an offline AWS known-answer test; `--aws-cli` alternative mode;
  bucket creation documented as console/wrangler/aws-CLI steps).
- `infra/apify/.actor/actor.json`, `infra/apify/.actor/input_schema.json`,
  `infra/apify/src/main.py`, `infra/apify/requirements.txt`,
  `infra/apify/README.md` — actor SKELETON: package metadata, the bounded
  input schema (exact 40-hex source revision — S11; hard limits — S14;
  signed callback envelope — S10; closed operation enum; no
  self-authorization — S12), and a stdlib stub entry that validates the
  invariants and emits an explicitly-marked `"status": "stub"`
  acknowledgment (NOT an execution receipt — no false SUCCESS). **NO
  Dockerfile** — it lands with PUB-08 per contract §A.7 (the merged G09
  overlay-prefix reconciliation covers `infra/`, but this item's contract
  still forbids the Dockerfile here).
- `.github/workflows/pub.yml` — NEW CI workflow (the pre-existing `tests`
  workflow is byte-untouched): the full §G matrix on PRs to `main`
  touching overlay roots (+ state JSON, `PUB-*.md` checkpoints,
  `pyproject.toml`, the workflow itself) and on `workflow_dispatch`;
  full-history checkout (G04 lineage, mirroring the `tests` workflow
  precedent); installs `-e ".[api]" pytest` so the PUB-01 API tests RUN;
  apps/web bun install/lint/typecheck/test job; concurrency group.
- `docs/deployment/deployment-runbook.md` — Stage A (private) → B (public
  read/demo) → C (authenticated beta) with the operator-held credential
  inputs listed per stage, truthful per-leg verification (the two Apify
  legs marked `BLOCKED_ON_PUB-08`), quota posture for Stage C, rollback
  discipline, environment quick-reference.
- `docs/deployment/preview-environments.md` — Vercel preview guidance
  (fixture-mode default), Neon `preview-pr-*` branch workflow, manual
  Render preview options, what previews must never do.
- `docs/deployment/ci-gates.md` — the two workflows' contract, why the pub
  matrix installs the api group, full-history rationale, trigger scope,
  local equivalents, and the render.yaml structural-validation recipe
  (the documented manual equivalent of `render blueprint validate`).
- `spec/development-state/PUB-03-checkpoint.md` (this file) and
  `spec/development-state/public-deployment-state.json` (PUB-03 status
  fields only).

### render.yaml — what changed vs the PUB-00 skeleton (and why)

- `buildCommand`: `pip install -r requirements.txt` (a placeholder — no
  such file exists under `services/api`) → `pip install --upgrade pip &&
  pip install -e '../..[api]'` (the repo-root pyproject owns the `[api]`
  group; PUB-01's documented venv bootstrap is the same install).
- `startCommand`: `uvicorn main:app …` (wrong module path) →
  `uvicorn services.api.main:app --app-dir ../.. --host 0.0.0.0 --port
  $PORT`. **Verified in-sandbox:** the editable install exposes only the
  `src/`-layout `sos` package, NOT `services.*`; `--app-dir ../..` puts the
  repo root on `sys.path` from the `rootDir: services/api` working
  directory (import verified with cwd inside `services/api`).
- Env wiring completed: PYTHON_VERSION pin (3.12.4, matching CI's 3.12
  major.minor), the five mode switches at PUBLIC values, 15 `sync:false`
  secrets, the eight §13 rate-limit names with baseline values,
  LOCAL-only names deliberately not wired (documented in-file).
- Spin-down/no-local-state/no-long-running-work notes kept and expanded
  (free instance sleeps after 15 min idle, ~1 min wake; health must stay
  truthful; no fake keep-alive traffic).

**Frozen surface untouched:** `src/sos/**` byte-identical (G02 PASS); all
frozen docs byte-identical (G01 PASS); `implementation-state.json`
untouched (G03 PASS); `tools/final_gate_check.py` + `tests/**` untouched
(zero diff vs base); `.github/workflows/test.yml` byte-untouched (zero diff
vs base — verified directly).

## Verification (§G gate matrix — real outputs, run at the implementation head tree)

Environment: Python 3.12.14, venv with `-e ".[api]"` + pytest
(fastapi 0.142.2, pydantic 2.13.5, pydantic_core 2.46.5, starlette 1.7.0,
uvicorn 0.54.0, httpx 0.28.1); bun on PATH for the web gates.

1. `python -m pytest` → **1 failed, 605 passed** in 10.98s. The single
   failure is `tests/test_pub01_openapi_snapshot.py::test_openapi_is_deterministic_and_snapshotted`
   — **the known env-drift finding pre-disclosed in the dispatch packet**:
   digest-only mismatch (observed
   `ead657cb967136806e9137acff31382a8e9d6a4ad9c5bf9a201cfb346af171ed` vs
   pinned `6469732c4b6488d08cc5cbebad31fa57b59aec7dd693b909ea147a56ec6c40ba`);
   the determinism-across-boots assertion inside the same test PASSES (the
   failure is at the digest assertion only). **Proof of env drift, not a
   PUB-03 regression:** the identical failure reproduces at the pristine
   base `7a3b1eb` (clean `git worktree`, same venv, 1 failed / same
   assertion), and `git diff 7a3b1eb -- src/ services/ tests/ providers/
   execution/ db/ tools/ apps/` is EMPTY on this branch. Per the packet
   instruction: `OPENAPI_SNAPSHOT_SHA256` NOT changed; digest update is a
   review-time decision. Matrix marked **605/606 with the known env-drift
   finding**. (Bisect note: the digest is byte-identical under fastapi
   0.141.1/0.142.2 × pydantic 2.12.5/2.13.4/2.13.5 — the pinned snapshot's
   exact pre-reset library stack is not recoverable from a fresh venv.)
2. `python -m compileall -q src tests services providers execution` →
   clean, exit 0.
3. `python tools/final_gate_check.py` (full/report mode) → **OVERALL: FAIL
   — 10/12 checks PASS (2 FAIL, 0 DEFERRED)**, exit 1. G06 SUITE_GREEN
   FAIL is the same single known test (the gate runs pytest as a
   subprocess); G11 FRESH_AGENT_RECOVERABLE FAIL is the documented
   mechanical cascade of G06 ("recovery chain broken: G06"). All structural
   checks PASS: G01, G02, G03, G04, G05, G07, G08, G09 (overlay-scoped,
   frozen surface clean + governed overlay prefixes), G10, G12.
   `python tools/final_gate_check.py --check-only` (no subprocesses) →
   **OVERALL (check-only): PASS — 11/12 (0 FAIL, 1 DEFERRED; G06 DEFERRED
   tolerated), exit 0.** Note: full/report mode rewrites
   `spec/development-state/W15-gate-report.json` (frozen) as its runtime
   output; the working-tree copy was restored after each run — the
   committed file is byte-identical to base.
4. `cd apps/web && bun install && bun run lint && bun run typecheck &&
   bun test` → install 362 packages [3.98s]; lint exit 0; typecheck exit 0;
   **80 pass / 0 fail** (581 expect() calls, 4 files) [2.05s].
5. Offline infra verification (real runs):
   - `python3 infra/neon/setup.py --selftest` → OK (scheme adaptation,
     branch-name policy); `--dry-run` (also auto when `NEON_API_KEY`
     unset) → plan printout, no network, no creation.
   - `python3 infra/upstash/setup.py --selftest` → OK (RESP framing, reply
     parsing, URL policy); `--dry-run` with a `rediss://` URL → PING plan;
     a `https://` URL is rejected (contract scheme enforcement).
   - `python3 infra/r2/setup.py --selftest` → OK (**AWS SigV4 known-answer
     vector** — the documented AWS example signature — plus S3 uri-encoding
     policy); `--dry-run` → verification plan.
   - `python3 infra/apify/src/main.py` with a valid bounded input →
     `"status": "stub", "accepted": true`, exit 0; a mutable revision
     ("latest-main") → rejected (S11 message), exit 1; a limit above the
     schema maximum → rejected (S14 message), exit 1.
   - render.yaml structural validation per the documented manual recipe
     (`docs/deployment/ci-gates.md`): PASS — YAML parses; the service
     carries type/runtime/plan/rootDir/healthCheckPath exactly; build/start
     commands match the verified install/import semantics; **28 env names
     reconciled 1:1 against `infra/environment.example`** (15 `sync:false`
     secrets + 13 valued + the PYTHON_VERSION runtime pin); LOCAL-only
     names correctly absent. `render blueprint validate` itself requires
     the authenticated Render CLI and is recorded as a Stage A
     operator-input check.

## Unresolved findings, known limitations, external blockers

- **Known env-drift finding (pre-disclosed, not introduced here):** the
  OpenAPI snapshot digest test — see Verification §1. Handled exactly per
  the dispatch instruction; the digest constant is untouched.
- **Operator-input steps (honest blockers, not failures):** live Neon
  provisioning, Upstash PING, R2 round-trip, `render blueprint validate`,
  the Vercel project import, and the Stage A→C deploys themselves all
  require operator-held credentials/accounts — documented as such in the
  runbooks; nothing is fabricated as executed.
- **BLOCKED_ON_PUB-08 (by contract):** the actor's Dockerfile, real
  bounded execution, and the two Apify Stage-A verification legs
  (API→Apify, Apify→API) — the runbook records this explicitly.
- Setup scripts' live paths (Neon REST calls, RESP/REST PING, S3 round-trip)
  could not be exercised without credentials; their offline paths
  (selftests with known-answer vectors, dry-runs, input validation) all
  ran green, and the R2 signer is verified against the published AWS SigV4
  example vector.

## Statements

- **No unmerged sibling is a dependency** (PUB-00 dependency verified
  merged by Git evidence; everything else built from merged main + the
  contract text).
- **No frozen surface touched** (see Files changed / gate G01–G03 above;
  token/secret scans of the full staged diff: clean).
- **No merge performed** — this checkpoint is the `WAITING_FOR_ARCHITECT`
  stop state; review corrections land on PR #26 (same branch).
