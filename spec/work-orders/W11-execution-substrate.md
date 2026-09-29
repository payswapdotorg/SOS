# W11 — Execution Substrate (first bounded slice of greenfield realization)

**Status:** DISPATCHED — WORKER AUTHORIZED
**Dependencies:** W1 authoritative merge `091d4d10a38922fb2d9cadb103e7ba8caa7a1f20`; W2 authoritative merge `587201d3e12a10ba9fac6da751d663a40c33dfb9`; W9 authoritative merge `203cfb7590bd25244cabf3cc7299dd192b00948d`; W10 authoritative merge `a1778653c35064eeb9d71563f17b30fb174d9429` (verified live main at dispatch)
**Roadmap:** `spec/implementation-roadmap.md` — W11 (Greenfield realization — this Work Order is its first bounded implementation slice)
**Primary requirements:** R6, R7, R8, R9, R13, R14, R15, R18, R22, R23, R24
**Base for Worker branch:** live `main` AFTER the W10 merge (exact base recorded at dispatch: `a1778653c35064eeb9d71563f17b30fb174d9429`)
**Preparation source (non-authoritative reference):** `PREP-W11-execution-substrate.md` work order and Worker B's verified design `docs/implementation/PREP-W11-EXECUTION-SUBSTRATE-DESIGN.md` (prep branch `work/w11-execution-substrate-prep` @ `816f62e58cffb23ead2208318c36a8f52c0762f7`, TL joint-review PASS, unmerged by design — the prep artifacts are source material, NOT dependencies)

## Mission

Implement the provider-neutral execution substrate as the first bounded slice
of W11 greenfield realization: the semantic boundary

`ExecutionRequest → ExecutionProvider → ExecutionReceipt → Evidence binding`

where SOS remains the authority and providers only execute already-authorized
bounded requests. The substrate is the realization mechanism through which a
mission-only onboarded system performs its first governed, observable,
rollback-bound execution steps — with **no live external execution** in this
slice (injected port objects only, exercised by deterministic stub providers
in tests).

The implementation MUST reuse, without redefining: W1 model/validation/
persistence authorities (`ModelValidationError`, `JsonModelStore`, traceability),
W2 system-state revision references, W4 evidence ingestion vocabulary,
W7 assurance references, W8 experiment/rollback references, W9
authorization/decision state. Providers and LLMs remain mechanisms; W9 stays
the only authorization authority; W4 `EvidenceGraph.ingest` stays the only
evidence authority.

## Contract to promote (authoritative reference shape)

The contract types, invariants, and 24 contract tests are specified
field-for-field by the PREP stub set (supplied to the Worker with the
dispatch envelope):

`ExecutionActionScope`, `ProviderCapability`, `ExecutionLifecycleState`,
`ExecutionRequest`, `ExecutionReceipt`, `SideEffect` (+ `SideEffectKind`),
`RollbackReference`, `ExecutionProviderPort` (protocol),
`ExecutionSubstrate` (core dispatcher with caller-supplied registries),
the lifecycle transition table, and the submit pipeline — plus the stub
providers (`StubWorkspaceExecutionProvider`, `StubReadOnlyExecutionProvider`)
which demonstrate two-provider neutrality.

## Required outcomes

1. **Contract module:** promote the contract into `src/sos/execution.py`,
   exported through `src/sos/__init__.py` (W11 exports only). Final naming is
   frozen by this Work Order to the stub names above.
2. **Error authority:** `ExecutionContractError` MUST subclass W1
   `ModelValidationError` (no competing error authority).
3. **W9 authorization is mechanically REQUIRED:** an `ExecutionRequest` is
   unconstructible without a W9 `AutonomyDecision` reference; submit resolves
   it against caller-supplied registries (SOS-owned state, never
   provider-supplied); ASK decisions cannot authorize; forged/mismatched ids
   and authority-chain mismatches are rejected before dispatch.
4. **Capability ≠ authorization:** a fully-authorized request without
   provider capability yields `OUTCOME_UNSUPPORTED` (a no-run receipt), not a
   rejection of the request's validity; provider self-authorization is
   impossible.
5. **Exact provenance:** receipts preserve exact source revision, environment,
   workspace, provider, and provider-supplied start/finish timestamps;
   receipt ids are content-addressed and deterministic.
6. **Distinct outcomes:** `OUTCOME_FAILED` / `OUTCOME_UNKNOWN` /
   `OUTCOME_UNAVAILABLE` / `OUTCOME_UNSUPPORTED` remain pairwise distinct;
   EMPTY is not a lawful outcome; no-run receipts cannot claim side effects;
   terminal lifecycle state and outcome must agree.
7. **Governed rollback:** DEPLOY requests require a bounded
   `RollbackReference` bound to the W8 experiment rollback chain; OBSERVE
   requests need none; rollback execution itself is governed (W9-authorized
   like any other request).
8. **Deterministic substrate:** one substrate instance is single-threaded;
   core logic stays clock-free (deadlines/timestamps are caller- or
   provider-supplied data); identical inputs produce identical results with
   zero network dependence.
9. **Persistence/traceability:** requests/receipts round-trip through the
   existing W1 `JsonModelStore`; re-ingesting an identical content-addressed
   receipt is idempotent (W4 dedup pattern). No new persistence authority.
10. **Port boundary:** `src/sos/execution.py` contains only the port
    protocol, capability enum, contract types, and substrate. Concrete
    provider adapters live outside `src/sos/` or are injected as port objects
    (tests inject the two stub providers).

## Resolutions of the PREP open questions (frozen by this Work Order)

- Enum naming: keep the stub names (`ExecutionActionScope` with its members).
- `OBSERVE` scope accepts decisions in `GATHER_EVIDENCE` or `ACT` state
  (stub behavior kept).
- Stream references: provider-supplied opaque reference strings — the
  contract requires a reference, never contents.
- `ExecutionLifecycleState.REQUESTED/REJECTED` remain explicit enum states
  for state-machine completeness (rejection raises before dispatch).
- No containment-exception field in this slice: the DEPLOY-requires-rollback
  invariant stands; a governed exception would need an Architecture Change
  Request.

## Allowed implementation surface

Worker MUST limit implementation to these five files unless an
Architect-approved correction expands scope:

- `src/sos/execution.py`
- `src/sos/__init__.py` (W11 exports only)
- `tests/test_w11_execution.py`
- `docs/implementation/W11-EXECUTION-SUBSTRATE-DESIGN.md`
- `spec/development-state/W11-checkpoint.md`

Do not modify frozen authority artifacts, roadmap semantics, Work Order
machinery, or W1–W10 source files.

## Explicit exclusions

W11 (this slice) MUST NOT implement:

- live execution, network I/O, subprocess spawning, or any external side
  effect inside `src/sos/`;
- provider-specific semantics in SOS core (no provider names, SDKs,
  transports, URLs, or credentials in `src/sos/` — provider identifiers
  appear only as stub names in tests);
- OpenMuse/Code-OSS integration (seam stays as the PREP-provider-cockpit
  design — a later slice);
- brownfield optimization loops (W12) or SOS self-evolution (W13);
- a new mission/value/context/evidence/assurance/experiment/rollback/
  autonomy/error/persistence authority;
- any execution path that bypasses W9/W7/W8 gates;
- inferred evidence (receipts convert to W4 evidence verbatim — observed,
  not inferred; UNAVAILABLE may never render as success downstream);
- modification of frozen W1–W9 semantics (a collision, e.g. a new truth
  state or changed `TruthfulValue` rule, requires a governed Architecture
  Change Request instead).

## Acceptance criteria

### C1 — W9 pre-execution authorization
No request without a resolvable W9 decision reference can reach a provider;
ASK decisions cannot authorize; the request's authority chain must match the
W9 decision's chain.

### C2 — DEPLOY assurance binding
DEPLOY requests must carry a W7-pass assurance reference bound to the exact
same authority chain (stub-verifiable).

### C3 — Capability separation
Provider capability checks are separate from authorization: unsupported
capability yields a no-run `OUTCOME_UNSUPPORTED` receipt; providers cannot
self-authorize.

### C4 — Exact provenance and content addressing
Receipts preserve exact revision/environment/workspace/provider/time
provenance; ids are content-addressed; identical receipts are idempotent
under re-ingestion.

### C5 — Distinct failure outcomes
FAILED / UNKNOWN / UNAVAILABLE / UNSUPPORTED are pairwise distinct; EMPTY is
unlawful; no-run receipts carry no side effects; lifecycle terminal states
agree with outcomes.

### C6 — Governed rollback
RollbackReference binds to the W8 experiment rollback chain; DEPLOY requires
it; rollback execution is itself W9-governed.

### C7 — Two-provider neutrality
Two structurally-different stub providers implement the same contract;
switching providers changes only the provider-attributed receipt fields.

### C8 — Determinism
Identical inputs → identical results; no clock, network, or provider
dependence in core logic.

### C9 — W1 persistence round-trip
Requests/receipts round-trip through `JsonModelStore`; no new persistence
authority.

### C10 — Bounded authority surface
No W12/W13 symbols, no OpenMuse/Code-OSS integration symbols, no duplicate
W1/W4/W7/W8/W9 authorities; `ExecutionContractError` anchored in the W1
validation-error family.

## Required regression coverage

Tests MUST be the promoted PREP contract tests (`tests/test_w11_execution.py`)
KEEPING EVERY INVARIANT NAME AND ASSERTION from
`tests/test_prep_w11_execution_contract.py`, adapted to the real module —
extended where useful, never weakened. At minimum the suite still covers:
W9 reference enforcement (absent/unresolved/ASK/chain-mismatch); DEPLOY
assurance binding; provider non-self-authorization; capability separation;
exact provenance; content-addressed ids; distinct outcomes; unavailable
providers; unlawful EMPTY; no-run side-effect prohibition; terminal
lifecycle agreement; DEPLOY rollback requirement; OBSERVE rollback exemption;
rollback governance; two-provider neutrality; provider-switch isolation;
governed lifecycle state machine; W9 REJECT refusal; UNKNOWN timeout path;
W1 round-trip; and absence of W12/W13/integration symbols.

## Deterministic verification

Worker MUST run and report exact-head results for:

```text
python -m pytest
python -m compileall -q src tests
```

No network/provider dependency may be required for the deterministic
acceptance suite.

## Evaluation / real-system evidence

This slice is contract evidence, not deployment evidence: the substrate is
exercised exclusively through injected stub providers in deterministic
tests. No live provider, credential, or external system may be touched.

## Risk / rollback

**Risk:** boundary leakage — an execution path that could bypass W9
authorization or render provider output as evidence/truth. The contract
invariants (C1–C10) exist to make such leakage impossible mechanically; the
promoted tests are the executable proof.

**Rollback:** ordinary Git revert of the merged W11 change. No deployment,
network side effect, or data migration is permitted in this slice.

## Completion / reconciliation protocol

When implementation is complete, the Worker MUST:

1. checkpoint exact base/head SHAs and verification evidence;
2. report the exact pytest and compileall results;
3. remain at `WAITING_FOR_ARCHITECT`;
4. stop without merging, without dispatching W12, and without modifying
   canonical state;
5. await Architect review. Corrections stay on the same PR.

W11 completion requires the Architect gate, actual Git merge, and canonical
reconciliation recording the W11 merge and next frontier.
