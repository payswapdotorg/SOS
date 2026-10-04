# PUB-07 Checkpoint — R2 evidence/artifact layer

**Status:** WAITING_FOR_ARCHITECT (review-ready at the exact head below)
**Worker:** Worker C (providers + deployment lane)
**Branch:** `work/pub-07-r2-artifacts` (one bounded slice, one PR)

## Item + base + head

- **Work item:** PUB-07 — R2 evidence/artifact layer
  (contract §D PUB-07; directive §12, §13 "Artifact uploads: size-limited",
  §16-C, §3-R2; design §5)
- **Exact base SHA:** `bbf997f68f026842205eae19d35556acb0b7717c`
  (verified: live merged `origin/main` at dispatch, not advanced — no
  STALE_BASE; dependency PUB-01 MERGED as `c98972a` per
  `spec/development-state/public-deployment-state.json` — dependency
  satisfied from actual Git facts, not conversation. The base also
  carries PUB-02/03/04/05/06 all MERGED.)
- **Implementation head:** `fd55cb04f1ceb7fa48364fd8d1723b5813a789b1`
- **Final branch tip:** this checkpoint/state commit (adds ONLY this
  checkpoint + the PUB-07 status fields in
  `spec/development-state/public-deployment-state.json` — no code after
  the implementation head; the PUB-05/PUB-06 two-commit pattern).
- **PR:** `work/pub-07-r2-artifacts` → `main` (one PR per item).

## Files/artifacts changed vs the §D allowed surface

| Path | Kind | §D surface clause |
|---|---|---|
| `providers/r2/layout.py` | new | `providers/r2/**` |
| `providers/r2/seam.py` | modified (port extended: put_by_key/head/resolve_grant + shared exceptions; PUB-01 methods unchanged) | `providers/r2/**` |
| `providers/r2/local.py` | modified (hardened: size limits, traversal defense, actor-bound grants, put_by_key/head) | `providers/r2/**` |
| `providers/r2/cloud.py` | modified (fail-closed placeholder → real R2 S3 SigV4 adapter) | `providers/r2/**` |
| `providers/r2/__init__.py` | modified (exports) | `providers/r2/**` |
| `services/api/routes/artifacts.py` | new (the artifact routes) | `services/api` artifact routes |
| `services/api/routes/__init__.py` | modified (router registration, 2 lines) | `services/api` artifact routes wiring |
| `services/api/dependencies/rate_limit.py` | modified (scoped S16 exemption + the object-path constant) | `services/api` artifact routes wiring — disclosed judgment call 2 |
| `services/api/main.py` | modified (artifacts block: signing key + max_bytes) | `services/api` artifact routes wiring — disclosed judgment call 1 |
| `services/api/jobs/worker.py` | modified (same artifacts construction, mirrors main.py) | `services/api` artifact routes wiring — disclosed judgment call 1 |
| `docs/deployment/artifacts.md` | new | docs |
| `docs/deployment/api-reference.md` | modified (PUB-07 additions section; cloud-mode row updated) | docs |
| `tests/test_pub07_local_store.py` | new (13 tests) | `tests/test_pub07*.py` (new files only) |
| `tests/test_pub07_r2_adapter.py` | new (10 tests) | `tests/test_pub07*.py` (new files only) |
| `tests/test_pub07_artifact_routes.py` | new (18 tests) | `tests/test_pub07*.py` (new files only) |
| `spec/development-state/PUB-07-checkpoint.md` | new (this file) | checkpoint |
| `spec/development-state/public-deployment-state.json` | modified (PUB-07 status fields only) | state |

**Nothing outside the §D surface was touched.** In particular:

- `src/sos/**` — zero changes (G02 holds; adapters import, never edit).
- Frozen documents — zero changes (byte-identical; the gate's frozen-digest
  checks pass 12/12).
- `tools/final_gate_check.py` + `tests/test_w15_final_gate_check.py` — zero
  changes.
- Every pre-existing test file — zero changes (all 41 new tests are in
  three NEW `tests/test_pub07*.py` files; the frozen PUB-01 OpenAPI
  snapshot test passes UNCHANGED — the canonicalized digest is asserted
  byte-identical inside `test_pub07_artifact_routes.py`).
- `providers/neon/**`, `providers/github/**`, `providers/upstash/**`,
   `execution/**`, `db/**`, `services/api/schemas/**`,
   `services/api/orchestration.py`, `services/api/container.py`,
   `services/api/testing.py`, `services/api/config.py`,
   `infra/**`, `pyproject.toml`, `.github/**`, `apps/web/**` — zero
   changes.
- No new migration: `evidence_artifacts` (migration 0006, PUB-05) already
  carries the metadata model; PUB-07's bytes-in-store/metadata-in-DB
  wiring rides the existing projection (`db/mapping.py` — untouched).
- `spec/development-state/W15-gate-report.json` — regenerated in the
  working tree by every `final_gate_check.py` run and left UNCOMMITTED
  (the W15/PUB precedent: it is the tool's output, not worker surface).

## What was delivered

1. **The deterministic §12 key layout as a single authority**
   (`providers/r2/layout.py`): `build_key` mints exactly
   `tenants/{tenantId}/systems/{systemId}/{category}/{contextId}
   [/{subcategory}]/{sha256}[-{filename}]`; `parse_key` fully validates
   the tree (category vocabulary, execution subcategories, exact depth,
   segment rules — the LOCAL store's path-traversal defense);
   `key_content_hash` enforces the 64-hex content address on WRITE paths.
   Both adapters build/validate the SAME keys (parity-tested).
2. **LOCAL store hardened** (`providers/r2/local.py`): in-store size
   limits (`max_bytes`, S15) on `put` AND `put_by_key`; traversal-safe
   reads; `put_by_key` verifies the content address (the signed-URL
   redemption path); `head` metadata; richer grants — tokens bind the
   requesting actor and `resolve_grant` returns the full grant
   (key/mode/actor/expiry); `resolve_signed_url` keeps the PUB-01 shape.
3. **The R2 adapter** (`providers/r2/cloud.py`, replacing the fail-closed
   placeholder): stdlib-only S3 SigV4 signed requests (PutObject/
   GetObject/HeadObject/HeadBucket) with an injectable transport (the
   PUB-06 Upstash precedent — the test suite runs command semantics
   against a scripted fake, no network); SigV4 presigned GET/PUT URLs
   (time-bounded, key-scoped, method-signed) with LOCAL verification
   (`resolve_grant` recomputes the canonical-request signature — tamper/
   expiry/wrong-endpoint/mode-confusion all rejected); the same layout
   and size caps; fail-closed configuration naming PUB-07 and the
   `SOS_R2_*` names (never a silent LOCAL fallback — the frozen PUB-01
   config test's expectation is preserved and re-tested).
4. **The transport routes** (`services/api/routes/artifacts.py`, all
   `include_in_schema=False` — see judgment call 3):
   `POST /artifacts/uploads` (authenticated + workspace MEMBERSHIP + §13
   write bucket + CSRF for real sessions + size pre-declaration 413 +
   system-in-workspace check → the §12 key + a signed put URL — R2:
   presigned direct-to-bucket, LOCAL: an HMAC token URL);
   `POST /artifacts/downloads` (authenticated + read-scope tenant check —
   the evidence read surface; cross-tenant keys 404 → a signed get URL);
   `GET/PUT /artifacts/object?token=…` (the LOCAL redemption: the grant,
   not a session, authorizes — one key, one mode, time-bounded; PUT
   enforces the artifact cap at both Content-Length and post-read, and
   the content address (422 on mismatch); GET serves bytes with the
   stored content type and a sha256 ETag).
5. **Audit events** for every artifact operation (S17):
   `artifact.upload_authorized` (slot), `artifact.upload_completed`
   (redemption, actor from the grant), `artifact.download_authorized`,
   `artifact.download_served` — surfaced on workspace `recentActivity`
   (test-asserted).
6. **Signing-key hardening for non-LOCAL deployments**: the app factory
   and the job worker wire `SOS_SESSION_SECRET` as the LOCAL store's
   signing key outside LOCAL mode (the deterministic DEMO key is
   LOCAL-only and clearly labeled); a token forged with the public demo
   key material is refused under a real signing key (test-asserted).
7. **Docs**: `docs/deployment/artifacts.md` (the full PUB-07 guide) and
   the api-reference PUB-07 additions section.

## Surface judgment calls (disclosed for review)

1. **`services/api/main.py` + `services/api/jobs/worker.py` (the
   artifacts construction block only).** The §D text lists "services/api
   artifact routes"; the stores' `max_bytes` bound and the non-LOCAL
   signing key must be wired at the composition root or they do not
   exist at runtime. Precedent: PUB-05 modified `main.py`'s persistence
   block under "services/api persistence wiring"; the worker file itself
   instructs "Keep the two aligned". The edits are strictly the artifacts
   block; no other logic touched; the worker mirrors the factory
   selection-for-selection.
2. **`services/api/dependencies/rate_limit.py` (S16 exemption, scoped to
   one exact path).** Artifact transfers are raw bytes up to the artifact
   cap (50 MB default) and cannot pass the generic JSON body cap (1 MB);
   `/api/v1/artifacts/object` is therefore exempt from the GENERIC cap
   and enforces the artifact-specific cap itself (both a Content-Length
   pre-check and the post-read length — test-asserted from both sides:
   a >1MB artifact PUT succeeds under a 2MB artifact cap, while a >1MB
   JSON POST elsewhere still gets the generic 413). Precedent: PUB-06
   modified this same file for its buckets.
3. **All four routes are `include_in_schema=False`.** Directive §7's
   listed set has no artifact paths; the frozen PUB-01 OpenAPI snapshot
   (an existing test file — untouchable surface) pins the canonicalized
   digest. This is exactly the PUB-04 precedent for post-§7 endpoints;
   the digest is asserted byte-identical in
   `test_pub07_artifact_routes.py` and the routes are fully documented in
   `docs/deployment/api-reference.md` + `artifacts.md`.
4. **Key-name law split (read vs write).** Directive §12 says "use
   content hashes WHENEVER POSSIBLE". PUB-07's write paths enforce full
   64-hex content addressing; the READ paths accept any SAFE object name
   under the governed tree because the pre-PUB-07 demo seed already
   records short-hash receipt references (`{16-hex}.json`) — those keys
   are honest 404s on download (bytes never stored), not unlawful keys
   (test-asserted). `key_content_hash` refuses non-addressed names on
   writes.
5. **LOCAL token redemption is token-authoritative, not
   session-authoritative** (mirroring S3 presigned-URL semantics: no
   ambient cookie authority is consulted; the per-IP/anonymous
   middleware buckets still apply). R2 presigned URLs carry no actor
   (the S3 pattern) — issuance-side audit covers accountability;
   disclosed in `artifacts.md`.

## Requirement traceability

- Directive §12 (layout, content hashes, no browser secret, signed URLs):
  layout.py + both adapters + tests (structure, determinism, parity,
  tamper/expiry/scope/mode, secret-never-in-URL).
- Directive §13 "Artifact uploads: size-limited": slot pre-declaration
  413 + redemption double check + in-store bound (S15), all tested.
- Directive §3-R2 / SECURITY S3/S4 (private buckets, signed URLs): no
  public-URL surface on the adapter; every transfer signed; presigned
  URLs only; `infra/r2/README.md` (PUB-03) remains the bucket-posture
  runbook.
- SECURITY S16: generic body cap preserved everywhere except the one
  artifact path (which enforces its own cap) — tested from both sides.
- SECURITY S17: four audit actions, test-asserted on `recentActivity`.
- Contract §C.2: all errors through the envelope (VALIDATION 422,
  PAYLOAD_TOO_LARGE 413 with `maxArtifactMb`, NOT_FOUND 404, FORBIDDEN
  403 on grant failures — one honest code, no which-check oracle);
  truth states untouched by the transport layer (no status invention).
- Contract §D PUB-07 scope line-by-line: seam implementations (LOCAL +
  R2) ✓; deterministic §12 layout ✓; signed upload/download URLs
  (time-bounded, exact-key scoped) ✓; private-bucket defaults ✓;
  artifact size limits ✓; `evidence_artifacts` wiring (metadata in DB —
  the PUB-05 projection these keys populate; bytes in the store) ✓;
  upload/download endpoints (authenticated, tenant-scoped,
  rate-limited) ✓; audit events ✓.

## Verification (run at the EXACT implementation head fd55cb0)

- `python3 -m pytest` → **764 passed, 38 skipped (truthful PUB-05
  pg-parity skips), 0 failed** (723 baseline + 41 new PUB-07 tests:
  13 local-store, 10 r2-adapter, 18 routes).
- `python3 -m compileall -q src tests services providers execution` →
  clean, exit 0.
- `python3 tools/final_gate_check.py` → **OVERALL PASS 12/12** at
  fd55cb0 (overlay-scoped G09 per the PUB-01 reconciliation).
- `cd apps/web && bun install && bun run lint && bun run typecheck &&
  bun test` → lint clean, typecheck clean, **99 tests / 0 fail**.
- Additional (beyond the matrix, for the §D acceptance): a REAL
  `uvicorn` LOCAL boot with zero env vars — truthful per-adapter health,
  login → upload slot → PUT redemption 201 (content address verified) →
  download slot → GET 200 with byte-identical content, and OpenAPI
  unaffected (0 artifact paths).
- Acceptance criteria from §D: LOCAL store round-trip tests ✓
  (test_pub07_local_store); key-layout determinism tests ✓ (both files,
  incl. LOCAL↔R2 parity); signed-URL expiry/scope tests ✓ (both
  adapters: expiry, tamper, key-scope, mode-scope, wrong-endpoint);
  size-limit rejection tests ✓ (store-level, slot-level,
  redemption-level, both layers of the S16 interaction).

## Known limitations / unresolved findings (truthful)

- **Live R2 I/O** against a real bucket is operator-input-gated (PUB-11
  stage): verified here only through the scripted fake transport +
  locally-recomputed signature verification (command semantics, signing,
  and URL structure fully covered; no network was touched — hermetic
  suite).
- **The demo seed's `artifactRef`s are references without stored bytes**
  (pre-PUB-07 seed shape): downloads of those keys return honest 404s
  (test-asserted). Seeding actual bytes would touch `db/seeds/**`
  (outside this item's surface).
- **R2 presigned-URL transfers are client↔R2**: the API audits slot
  issuance but cannot observe the transfer itself (the S3 pattern; R2
  access logs are operator-side). Disclosed in `artifacts.md`.
- **Signed-URL TTLs are module constants** (600 s upload / 300 s
  download), not new env names — adding config names would widen the
  surface beyond §D; a PUB-09/PUB-11 operator need can revisit.
- **No artifact deletion/retention surface** (not in §7/§D PUB-07);
  unreferenced objects persist until an operator acts (free-tier budget
  note in `artifacts.md`).

## Worker discipline statements (binding)

- No unmerged sibling is a dependency (base = merged main bbf997f; all
  six prior PUB items MERGED at dispatch).
- No frozen surface touched (`src/sos/**`, frozen docs, gate logic,
  pre-existing tests — all byte-identical; final gate 12/12).
- No merge performed, no self-approval, no successor work items; this
  checkpoint + push + PR is the stop state.
