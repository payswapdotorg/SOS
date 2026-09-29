# W13 — SOS Self-Evolution / Meta-Adaptation (first bounded slice: the governed self-evolution proposal lifecycle)

**Status:** PREPARED — DISPATCH BLOCKED. The frozen-ledger dependencies are
authoritatively merged — W8 `65b84058aa204b3749e45b7e21ae433a4b138d83`, W9
`203cfb7590bd25244cabf3cc7299dd192b00948d` — but roadmap sequencing
(`spec/implementation-roadmap.md` frozen ledger: W13 comes after W12) requires
the W12 merge first; W12 is PR #19, open, unmerged (verified at preparation
time: live `main` is the W12 dispatch point
`e3a97b895ca6f6cc7206a50bde45b2b55c554195` and
`origin/work/w12-optimization-loop` is not an ancestor of `main`). This Work
Order MUST NOT be dispatched until the W12 Architect gate passes, the W12 merge
exists in Git, and canonical state records it.
**Dependencies (all authoritative):** W1 `091d4d10a38922fb2d9cadb103e7ba8caa7a1f20`; W4 `26060db57c24ba8b36315c1005466046810c5163`; W5 `2bfd0f89da129c6b3347d88b0d8da1b79dd04127`; W6 `b5171f70ca5ce85ca0be07cfdb3abf034c03c32f`; W7 `25f663cf444f92b3190074a9119619cbc53e9ece`; W8 `65b84058aa204b3749e45b7e21ae433a4b138d83`; W9 `203cfb7590bd25244cabf3cc7299dd192b00948d` (W8 + W9 are the frozen-ledger declared dependencies; W1/W4/W5/W6/W7 are the reused frozen authorities this slice composes)
**Roadmap sequencing gate (NOT an implementation dependency):** W12 — per the
frozen sequencing W12 → W13 → W14, dispatch requires the W12 merge and
canonical reconciliation. W13 MUST NOT depend on W12 implementation internals;
W12 is a sequencing precondition only (an unmerged branch is never a
dependency).
**Roadmap:** `spec/implementation-roadmap.md` — W13 (SOS self-evolution | W8 + W9 | "SOS evolves its own implementation and adaptation mechanisms safely"; this Work Order is its first bounded implementation slice)
**Primary requirements:** R7, R9, R13, R14, R15, R16, R19, R20, R21, R22, R23, R24 (R20 is the defining requirement)
**Base for Worker branch:** live `main` AFTER the W12 merge (exact base to be
recorded at dispatch; at preparation time live `main` is the W12 dispatch point
`e3a97b895ca6f6cc7206a50bde45b2b55c554195`, which is NOT the W13 base)

## Mission

Implement SOS self-evolution / meta-adaptation as a **governed proposal and
evaluation lifecycle** — the first bounded slice: the self-evolution PROPOSAL
machinery plus the governed-evaluation pipeline that COMPOSES the
already-merged authorities (W7 assurance, W8 experiment/promotion/rollback, W9
authority, W4 evidence, with W5/W6 provenance citations) over proposals that
target **SOS's own sources**.

**Critical boundary (normative, enforced by the acceptance criteria):**
self-evolution MUST NOT mean "SOS edits itself directly". It MUST mean: SOS
PROPOSES candidate changes to itself — represented as inert, typed DATA —
→ ordinary governance evaluates them → the W7/W8/W9 gates remain active and
binding → only governed promotion changes SOS. In this slice even a PROMOTED
proposal changes no source: the candidate change to SOS sources is a proposal
record (data), evaluated like any brownfield candidate, and adoption into SOS
sources remains an ordinary repository-governance act (Worker PR + Architect
gate) performed OUTSIDE this machinery; the machinery only records the governed
decision and, when it exists, the adoption revision citation.

The lifecycle this Work Order encodes (verbatim, normative):

```
SOS current System State
        ↓
self-improvement hypothesis
        ↓
candidate change to SOS
        ↓
W7 assurance
        ↓
W8 experiment
        ↓
W9 authority
        ↓
promotion / rollback
        ↓
evidence
        ↓
new SOS state
```

Stage mapping (each stage is machinery, not narrative):

- **SOS current System State** → the exact SOS source revision the proposal
  targets (`target_revision`: a real repository revision string, cited as
  data; the proposal is unconstructible without it);
- **self-improvement hypothesis** → a typed `SelfImprovementHypothesis` record
  (rationale, W4 trigger evidence ids, optional W5 `CausalHypothesis` ids as
  priors, predicted effects as DATA — never evidence);
- **candidate change to SOS** → the `SelfEvolutionProposal` carrying a
  diff-shaped `SourceChange` payload (path, base revision, change kind,
  payload text — inert DATA, never applied);
- **W7 assurance** → a W7 `AssuranceResult` with status PASS bound to the
  exact proposal/revision chain;
- **W8 experiment** → W8 `Experiment`/`ExperimentEvaluation` with a
  `PromotionGate`/`PromotionDecision` result and bounded `RollbackPath`
  and `StopCondition`s bound to the same chain;
- **W9 authority** → a resolved W9 `AutonomyDecision` (ACT / ASK / REJECT /
  ROLLBACK) evaluated under an `AutonomyRequest` policy;
- **promotion / rollback** → governed lifecycle states `PROMOTED` /
  `ROLLED_BACK` (decision records, never execution);
- **evidence** → W4 verbatim evidence entries appended at every consequential
  step through the existing W4 vocabulary and ingestion path;
- **new SOS state** → the adoption revision citation (`adoption_revision`:
  the new SOS source revision produced by the ordinary governed merge,
  recorded as data when it exists; never fabricated).

The implementation MUST reuse, without redefining: W1 model/validation/
persistence (`ModelValidationError`, `Traceability`, `TruthState`,
`TruthfulValue`, `JsonModelStore`), W4 `Evidence`/`EvidenceKind`/
`EvidenceProvenance`/`EvidenceGraph` ingestion, W5 `CausalHypothesis`/
`ArchitectureMemory` citation types, W6 `CandidateProposal`/
`SubgraphMutation` citation types, W7 `AssuranceResult`/`AssuranceStatus`/
`assure_candidate`, W8 `Experiment` lifecycle/`ExperimentEvaluation`/
`PromotionGate`/`PromotionDecision`/`RollbackPath`/`StopCondition`, W9
`AutonomyRequest`/`PolicyCeiling`/`AutonomyDecision`/`AutonomyDecisionState`/
`evaluate_autonomy`. No new authority class may be created (architecture §12).

## Required outcomes

1. **Proposal record model:** a typed, frozen, construction-validated,
   content-addressed `SelfEvolutionProposal` record carrying: the exact SOS
   source revision it proposes to change (`target_revision`); the target
   paths; the change payload as inert diff-shaped DATA (`SourceChange`
   records: path, base revision, change kind CREATE/MODIFY/DELETE, payload
   text); the self-improvement hypothesis (rationale, W4 trigger evidence
   ids, optional W5 causal hypothesis ids, predicted effects as DATA); the
   untrusted proposal origin (MODEL_GENERATED / HUMAN_GENERATED /
   EVIDENCE_TRIGGERED); the recursion-bound fields (`meta_depth`,
   `ancestor_proposal_id`); the declared rollback reference; W1 traceability;
   JSON round-trip via W1 `JsonModelStore`.
2. **Deterministic lifecycle state machine:** a frozen state enum
   (`PROPOSED`, `UNDER_ASSURANCE`, `UNDER_EXPERIMENT`, `UNDER_AUTHORITY`,
   `PAUSED_ASKING`, `PROMOTED`, `REJECTED`, `ROLLED_BACK`) with a frozen
   FROM→TO transition table and an explicit validation function (W8
   `transition_experiment` / W9 `validate_decision_transition` style) — no
   free-form narrative transitions. Gate requirements are frozen in code and
   are never data-configurable.
3. **W7 → W8 → W9 ordering invariant (mechanically enforced):** a proposal
   cannot enter `UNDER_EXPERIMENT` without a W7 `AssuranceResult` with
   status PASS bound to the exact proposal id / target revision chain; cannot
   enter `UNDER_AUTHORITY` without a W8 `PromotionDecision` (promoted) backed
   by a governed experiment and a bounded `RollbackPath` bound to the same
   chain; cannot become `PROMOTED` without a resolved W9 `AutonomyDecision`
   in state ACT bound to the same chain. Any skipped stage is rejected at
   construction/transition time.
4. **W9 authority gate at the only promotion point:** ACT → `PROMOTED` only;
   ASK → `PAUSED_ASKING` with an explicit pending-authorization record
   (leaving the pause requires a NEW resolved decision; never a silent
   default, never an auto-approve, never a timeout-to-ACT); REJECT →
   `REJECTED`; ROLLBACK → `ROLLED_BACK` with governed recovery evidence;
   non-resolving W9 states (GATHER_EVIDENCE, EXPERIMENT) leave the proposal
   in its current state with an explicit pending record (no advancement, no
   refusal).
5. **Governed rollback:** every promotion-carrying transition requires a
   bounded W8 `RollbackPath` whose reference binds to the proposal's declared
   rollback reference; `PROMOTED → ROLLED_BACK` is valid only through a
   governed recovery transition backed by evidence; no code path strips,
   defaults, or weakens the rollback binding.
6. **W4 evidence at every consequential step:** each governed transition
   appends verbatim evidence entries through the existing W4 evidence
   vocabulary/ingestion path (observed, not inferred; no new evidence kinds);
   hypothesis predictions and payload contents are never ingested as
   evidence.
7. **W5/W6 provenance (optional seams):** the hypothesis cites W5
   `CausalHypothesis` ids and the proposal cites W6 `CandidateProposal`/
   `SubgraphMutation` ids where present; citations are validated against
   caller-supplied registries; memory is used as a prior, never as proof.
8. **Bounded recursion (no unbounded recursive self-modification):** a fixed
   `MAX_META_DEPTH` constant; `meta_depth` validated at construction; an
   ancestor chain (resolved from caller-supplied `known_proposals`) that
   exceeds the bound is rejected; the evaluation surface exposes NO
   proposal-generation path — it evaluates proposals, it never creates,
   mutates, or re-generates them; one call advances exactly one proposal (no
   nesting, no autonomous chaining).
9. **Bounded, deterministic machinery:** single-threaded, clock-free core
   (timestamps are caller-supplied data), deterministic ordering, identical
   inputs → identical records (content-addressed ids), zero network, zero
   subprocess, zero file mutation, zero `git` invocation.
10. **Explainability:** the final lifecycle record preserves the full chain —
    hypothesis and trigger evidence, proposal payload, assurance results,
    experiment evaluations, promotion decision, W9 decisions, uncertainty
    distinctions (FAILED/UNKNOWN/UNAVAILABLE/UNSUPPORTED never collapse),
    and (when it exists) the adoption revision citation.

## Allowed implementation surface

Worker MUST limit implementation to these five files unless an
Architect-approved correction expands scope:

- `src/sos/selfevolution.py`
- `src/sos/__init__.py` (W13 exports only)
- `tests/test_w13_selfevolution.py`
- `docs/implementation/W13-SELF-EVOLUTION-DESIGN.md` (reconcile the PREPARED
  design to the implemented contract — extend, never weaken)
- `spec/development-state/W13-checkpoint.md` (fill the PREPARATION TEMPLATE
  that already exists at this path)

Do not modify frozen authority artifacts, roadmap semantics, Work Order
machinery, or W1–W12 source files.

## Explicit exclusions

W13 (this slice) MUST NOT implement:

- any direct self-modification execution: no source mutation, no file writes,
  no patch application, no `git` invocation, no subprocess, no network — the
  candidate payload is inert DATA; `PROMOTED` is a decision record, not an
  action; adoption stays with ordinary repository governance;
- **self-authorizing changes** (no code path grants, mints, or upgrades
  authority; promotion requires an external resolved W9 ACT decision; no
  record field is an authorization token);
- **bypassing W7/W8/W9** (no transition skips a gate; gate requirements are
  frozen in code; the lifecycle machine never reads gate requirements from
  data);
- **changing the Constitution silently** (or any frozen authority artifact:
  `spec/constitution.md`, `spec/architecture.md`, `spec/architecture-lock.md`,
  `spec/architecture-change-process.md`, `spec/implementation-roadmap.md`,
  `spec/requirements.md`, frozen Work Orders) — proposals targeting frozen
  authority paths are rejected at intake; such changes require the governed
  architecture change process, which this machinery never replaces;
- **deleting assurance** (no payload may DELETE an authority-implementation
  module — the `src/sos/` modules that implement the W1/W4/W5/W6/W7/W8/W9
  authorities; authority deletion is a governed architecture change, not a
  self-evolution proposal) — and no code path may remove or weaken the
  lifecycle machine's own gate requirements;
- **weakening rollback** (every promotion path requires a bounded W8
  `RollbackPath`; rollback is itself governed; no defaulting, no stripping);
- **redefining truth** (W1 `TruthState`/`TruthfulValue` distinctions preserved
  end-to-end; W4 evidence recorded verbatim; hypothesis predictions never
  become evidence; no new evidence kinds; FAILED/UNKNOWN/UNAVAILABLE/
  UNSUPPORTED never collapse to a favorable value);
- **turning model output into authority** (proposal origin is recorded as
  untrusted data and is never consulted by any gate; MODEL_GENERATED
  proposals follow exactly the same gates as any other origin; model output
  can at most produce a PROPOSED record — never a PROMOTED one);
- **unbounded recursive self-modification** (fixed `MAX_META_DEPTH`; ancestor
  overflow rejected; no proposal generation inside the evaluation surface; no
  autonomous chaining);
- live production access, network I/O, subprocess spawning, W11
  `ExecutionSubstrate` dispatch (no live execution in this slice), or
  deployment;
- W14 integrated dogfood/adversarial verification;
- a new mission/value/context/evidence/causal/candidate/assurance/experiment/
  autonomy/execution/error/persistence authority — self-evolution lifecycle
  records are ordinary governed records composed UNDER the existing
  authorities; no fifth authority class (architecture §12);
- LLM/model output as authorization, truth, or evidence;
- mutation of the Constitution, frozen specs, or the roadmap.

## Acceptance criteria

### C1 — Composed-authority integrity
The lifecycle composes only through the real W1/W4/W5/W6/W7/W8/W9 types;
every cross-authority reference is chain-checked (same proposal/revision/
decision chain); no authority is duplicated, bypassed, or re-defined
(identity of every referenced authority symbol is asserted against its
owning module in tests).

### C2 — Proposal-as-data integrity
The candidate change to SOS sources is inert DATA: exact `target_revision`
citation, typed `SourceChange` payload (path/kind/base revision/payload
text), untrusted origin, W1 traceability; content-addressed id; round-trips
through W1 `JsonModelStore`. No code path applies a payload.

### C3 — W7→W8→W9 ordering invariant (no bypass)
Each stage transition is unconstructible without its gate's binding:
`UNDER_EXPERIMENT` requires W7 PASS bound to the exact chain;
`UNDER_AUTHORITY` requires a W8 promoted `PromotionDecision` + bounded
`RollbackPath` bound to the same chain; `PROMOTED` requires a resolved W9
ACT decision. Skipped, free-form, or out-of-table transitions are rejected
(construction-validated).

### C4 — No self-authorization
`PROMOTED` is unreachable without a resolved W9 `AutonomyDecision` in state
ACT from caller-supplied `known_decisions`, bound to the exact chain; no
record field, engine method, or code path grants, mints, or upgrades
authorization; the module cannot construct authority.

### C5 — ASK pause mechanics
An ASK decision yields `PAUSED_ASKING` with an explicit
pending-authorization record; leaving the pause requires a new resolved
decision; no silent default, no auto-approve, no timeout-to-ACT;
GATHER_EVIDENCE/EXPERIMENT decisions defer with an explicit pending record
(no advancement, no refusal).

### C6 — Constitution and authority protection (no silent change, no assurance deletion)
Proposals whose target paths intersect the frozen authority path set are
rejected at construction; DELETE-class changes on authority-implementation
modules are rejected at construction; no code path weakens or removes a
lifecycle gate requirement (gate logic is frozen code, not data).

### C7 — Governed promotion/rollback (no weakened rollback)
Promotion requires the W8 `PromotionGate`/`PromotionDecision` result; every
promotion-carrying transition binds a bounded `RollbackPath` matching the
proposal's declared rollback reference; `ROLLED_BACK` requires governed
recovery evidence; stop conditions are W8 `StopCondition`-typed and cannot
be offset by favorable objectives.

### C8 — Truth preservation (no redefined truth)
W1 truth distinctions and W4 verbatim evidence recording are preserved
end-to-end; hypothesis predictions and payload contents never appear as
evidence; FAILED/UNKNOWN/UNAVAILABLE/UNSUPPORTED remain pairwise distinct
and never collapse to a favorable value.

### C9 — Origin never authorizes (no model output as authority)
A MODEL_GENERATED-origin proposal passes and fails exactly the same gates as
a HUMAN_GENERATED or EVIDENCE_TRIGGERED one (identical inputs → identical
outcomes); origin is never read by any gate; no code path converts model
output into an authorization, a truth, or evidence.

### C10 — Bounded recursion
Fixed `MAX_META_DEPTH`; construction rejects out-of-range `meta_depth`;
evaluation rejects ancestor chains that exceed the bound (resolved from
caller-supplied `known_proposals`); the evaluation surface exposes no
proposal-generation path; one call advances exactly one proposal.

### C11 — Determinism and bounds
Single-threaded, clock-free core; timestamps caller-supplied; deterministic
ordering; identical inputs → byte-identical records (content-addressed
ids); zero network, zero subprocess, zero file mutation, zero `git`
invocation anywhere in `src/sos/`.

### C12 — Persistence and bounded authority surface
W13 records round-trip through W1 `JsonModelStore` (no new persistence
authority); no W14 symbols; no live-execution/self-modification symbols
(source scan of `src/sos/` for write/subprocess/git/network tokens,
mirroring the W11 no-integration-symbol test pattern); W13 exports only
through `src/sos/__init__.py`.

## Required regression coverage

Tests MUST include, at minimum: full governed happy path (PROPOSED → W7 PASS
→ W8 promoted → W9 ACT → PROMOTED with evidence at every step; deterministic
record; byte-identical re-run); W9 ASK pause with pending-authorization
record and resume only via a new resolved decision; W9 GATHER_EVIDENCE
deferral; W9 REJECT refusal; W9 ROLLBACK with recovery evidence; missing or
unresolved W9 reference rejection; W7-missing or W7 non-PASS
(FAIL/UNKNOWN/BLOCKED) stage-advance rejection; promotion without
`PromotionGate`/`PromotionDecision` rejection; promotion without bounded
`RollbackPath` rejection; stage-skip attempts (e.g. PROPOSED→
UNDER_EXPERIMENT, PROPOSED→PROMOTED) rejected; intake rejection of
frozen-authority target paths; intake rejection of DELETE on
authority-implementation modules; recursion-depth overflow rejection
(ancestor chain longer than `MAX_META_DEPTH`); origin irrelevance
(MODEL_GENERATED vs HUMAN_GENERATED identical outcomes); truth preservation
through the lifecycle (distinctions never collapse; predictions never
ingested as evidence); W5/W6 citation validation; determinism (identical
runs → identical content-addressed ids); JSON round-trip through W1
`JsonModelStore`; source scan of `src/sos/` for self-modification execution
tokens (file-write/subprocess/git/network); absence of W14 symbols; absence
of proposal-generation methods on the evaluation surface; authority-symbol
identity assertions.

## Deterministic verification

Worker MUST run and report exact-head results for:

```text
python -m pytest
python -m compileall -q src tests
```

No network/provider dependency may be required for the deterministic
acceptance suite. Reference baseline at preparation time on live `main`
`e3a97b895ca6f6cc7206a50bde45b2b55c554195` (the W12 dispatch point): 327
passed, `compileall` clean. The Worker's baseline is the exact pass count at
the recorded post-W12-merge dispatch base.

## Evaluation / real-system evidence

This slice is proposal/contract evidence: the lifecycle is exercised on
fixture proposals with injected W7/W8/W9 records and W4 evidence
(deterministic stub/fixture chains), mirroring W12's simulation-level
composition. Real self-evolution adoption — an actual governed merge of a
W13-promoted proposal into SOS sources — stays out of this slice and remains
ordinary repository governance (Worker PR + Architect gate).

## Risk / rollback

**Risk:** boundary leakage — a self-evolution path that self-authorizes,
bypasses a gate, weakens rollback, or mutates sources. The mechanical
construction-validation invariants (C1–C12) are the guard; the tests are the
executable proof. Secondary risk: the slice is mistaken for self-modification
capability — the design doc and this Work Order define it as proposal and
governed-evaluation machinery only; the payload is inert data and the
evaluation surface has no generation path.

**Rollback:** ordinary Git revert of the merged W13 change. No deployment or
data migration is permitted in this slice.

## Completion / reconciliation protocol

When implementation is complete, the Worker MUST:

1. checkpoint exact base/head SHAs and verification evidence (fill
   `spec/development-state/W13-checkpoint.md`);
2. report the exact pytest and compileall results;
3. remain at `WAITING_FOR_ARCHITECT`;
4. stop without merging, without dispatching W14, and without modifying
   canonical state;
5. await Architect review. Corrections stay on the same PR.

W13 completion requires the Architect gate, actual Git merge, and canonical
reconciliation recording the W13 merge and next frontier.
