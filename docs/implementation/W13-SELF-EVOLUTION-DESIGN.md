# W13 Self-Evolution / Meta-Adaptation Design (first bounded slice: the governed self-evolution proposal lifecycle)

**Status:** RECONCILED TO THE IMPLEMENTATION (W13 Worker, review iteration 1).
This was the PREPARED design reference; §§1–12 below are preserved as prepared
and §13–§15 record the implemented contract reconciliation (extend, never
weaken — the Work Order remains the authority where the two differ).
**Work Order:** `spec/work-orders/W13-self-evolution.md` (authoritative;
dispatched at the post-W12-merge base `0da1ca09885b0cc618cdddebc6da5acfc3f0c978`)
**Dependencies:** W1 merged `091d4d10`; W4 merged `26060db`; W5 merged
`2bfd0f8`; W6 merged `b5171f7`; W7 merged `25f663c`; W8 merged `65b84058`;
W9 merged `203cfb7` (W8 + W9 are the frozen-ledger declared dependencies).
Roadmap sequencing gate: W12 — merged (PR #19) before W13 dispatch; W13 does
not depend on W12 implementation internals.
**Module (implemented):** `src/sos/selfevolution.py` (2097 lines); W13 exports
in `src/sos/__init__.py` (+25 lines, 23 names); contract tests
`tests/test_w13_selfevolution.py` (78 test items in 42 test functions)

## 1. Overview and positioning

W13 is governed meta-adaptation of SOS itself (architecture §11, requirement
R20). W12 composed the merged authorities into a governed optimization loop
for **recovered external systems**; W13 turns the same governance onto **SOS's
own implementation and adaptation mechanisms**. The composed control model is
the Work Order's frozen lifecycle, verbatim:

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

**Critical boundary.** Self-evolution in SOS does NOT mean "SOS edits itself
directly". It means: SOS PROPOSES candidate changes to itself as inert, typed
DATA → ordinary governance evaluates the proposal like any brownfield
candidate → the W7 assurance, W8 experiment/promotion/rollback, and W9
authority gates remain active and binding → only governed promotion changes
SOS. In this first bounded slice even a `PROMOTED` proposal changes nothing by
itself: adoption into SOS sources remains an ordinary repository-governance
act (Worker PR + Architect gate) performed outside this machinery. The
machinery records the governed decision and, when it exists, the adoption
revision citation (`adoption_revision`) as data. This mirrors W12's bounded
first slice ("the governed orchestrator", simulation-level, no live
execution): W13's bounded first slice is **the governed self-evolution
proposal and evaluation machinery** — no self-modification execution, no
direct source mutation.

Scope of the first slice, precisely:

- IN: the proposal record model (`SelfEvolutionProposal` and its frozen
  vocabulary); the deterministic lifecycle state machine; the governed
  evaluation surface that COMPOSES W7/W8/W9 (with W4 evidence recording and
  W5/W6 provenance citations); the recursion bound; W1 persistence.
- OUT: everything in the Work Order's Explicit exclusions — in particular all
  self-modification execution, all live execution (W11 substrate dispatch),
  W14 verification, autonomous proposal generation, and any new authority.

## 2. Composed-authority map (referenced, never recreated)

| Contract element | Owning authority (reused by identity) | W13 binding |
| --- | --- | --- |
| Validation-error family | W1 `ModelValidationError` | `SelfEvolutionContractError` subclasses it (W11 `ExecutionContractError` pattern) |
| Truth states / truthful values | W1 `TruthState`, `TruthfulValue` | evidence evaluation and lifecycle outcomes preserve distinctions end-to-end |
| Traceability | W1 `Traceability` | every proposal and step record carries it (value + context required) |
| Persistence | W1 `JsonModelStore` | W13 records round-trip; no new persistence authority |
| Evidence identity/ingestion | W4 `Evidence`/`EvidenceKind`/`EvidenceProvenance`/`EvidenceGraph` | every consequential step appends verbatim (observed, not inferred); no new evidence kinds; the package-internal assembly helper is reused, never reimplemented |
| Causal priors | W5 `CausalHypothesis`, `ArchitectureMemory` | cited as provenance (optional seam); memory is a prior, never proof |
| Candidate machinery | W6 `CandidateProposal`, `SubgraphMutation` | cited where a proposal implicates SOS's own architecture graph (optional seam); no candidate-search recreation |
| Assurance gate | W7 `AssuranceResult`/`AssuranceStatus`/`assure_candidate` | `UNDER_EXPERIMENT` requires PASS bound to the exact proposal/revision chain; W7 stays non-authorizing |
| Experiment/promotion/rollback | W8 `Experiment`/`ExperimentEvaluation`/`PromotionGate`/`PromotionDecision`/`RollbackPath`/`StopCondition` | `UNDER_AUTHORITY` requires a promoted `PromotionDecision` + bounded `RollbackPath`; stop conditions typed |
| Authorization | W9 `AutonomyRequest`/`PolicyCeiling`/`AutonomyDecision`/`AutonomyDecisionState`/`evaluate_autonomy` | the ONLY authorization source; ACT/ASK/REJECT/ROLLBACK gate the only promotion point |
| Execution | W11 `ExecutionSubstrate` | NOT composed in this slice — adoption is external repo governance, never a live dispatch |

What W13 must NOT recreate: any assurance evaluation, experiment semantics,
promotion math, autonomy policy, evidence identity, or persistence of its own;
any LLM-as-authority path (constitution principle 5); any fifth authority
class (architecture §12 — see §8 below).

## 3. Record model

All records are frozen dataclasses, construction-validated (W1
`ModelValidationError` family), content-addressed (`selfevo-<sha256[:16]>`
style over their own material), clock-free (timestamps, when present, are
caller-supplied data), and JSON round-trippable through W1 `JsonModelStore`.

- **`SelfEvolutionContractError(ModelValidationError)`** — the W13 error
  authority anchor (no bare `ValueError` family).
- **`ProposalOrigin`** (frozen enum) — `MODEL_GENERATED` |
  `HUMAN_GENERATED` | `EVIDENCE_TRIGGERED`. Untrusted provenance data: no gate
  ever reads it (C9; constitution principle 5).
- **`SourceChangeKind`** (frozen enum) — `CREATE` | `MODIFY` | `DELETE`.
- **`SourceChange`** — one diff-shaped payload entry AS DATA: repo-relative
  `path` (non-empty, no absolute paths), `base_revision` (the exact revision
  the change applies against), `kind`, `payload` (diff-shaped text/hunks for
  CREATE/MODIFY; empty for DELETE). Validation rejects authority-path
  targets and authority-module DELETE at construction (§5 P3/P4).
- **`SelfImprovementHypothesis`** — the "self-improvement hypothesis" stage:
  `rationale` (non-empty), `trigger_evidence_ids` (W4 evidence ids, validated
  against caller-supplied registries), `causal_hypothesis_ids` (W5 ids,
  optional), `predicted_effects` (tuple, DATA — never evidence, never
  truth), `uncertainty` (truthful distinction, never favorable-collapsed).
- **`SelfEvolutionProposal`** — the "candidate change to SOS" stage:
  `id`, `target_revision` (the exact SOS source revision the proposal
  proposes to change — a real repository revision string, cited as data),
  `target_paths` (tuple of repo-relative paths), `changes`
  (tuple[SourceChange, …]), `hypothesis` (SelfImprovementHypothesis),
  `origin` (ProposalOrigin), `rollback_ref` (declared rollback reference —
  must bind to the W8 rollback chain at promotion time), `meta_depth` (int ≥
  0, ≤ MAX_META_DEPTH), `ancestor_proposal_id` (str | None), optional W6
  `candidate_ref` citation, `state` (SelfEvolutionState, default PROPOSED),
  accumulated gate references as the lifecycle advances
  (`assurance_result_id`, `experiment_id`, `evaluation_id`, `promotion_id`,
  `autonomy_decision_id`, `evidence_ids`, pending-authorization /
  pending-evidence markers, `adoption_revision`), and W1 `traceability`.
- **`SelfEvolutionStep`** (recommended) — one consequential transition record
  emitted per governed step, convertible verbatim into W4 `Evidence` (W11
  `receipt_to_w4_evidence` precedent). Exact helper naming is Worker latitude
  within the frozen contract.

## 4. Lifecycle state machine (deterministic, no free-form transitions)

`SelfEvolutionState` = `PROPOSED | UNDER_ASSURANCE | UNDER_EXPERIMENT |
UNDER_AUTHORITY | PAUSED_ASKING | PROMOTED | REJECTED | ROLLED_BACK`.

Frozen FROM→TO table (normative; a `validate_transition`-style function
enforces it, W8/W9 pattern; gate bindings are listed in §5/§6 and frozen in
code, never data):

```text
PROPOSED        → {UNDER_ASSURANCE, REJECTED}
UNDER_ASSURANCE → {UNDER_EXPERIMENT, REJECTED}
UNDER_EXPERIMENT→ {UNDER_AUTHORITY, REJECTED, ROLLED_BACK}
UNDER_AUTHORITY → {PROMOTED, PAUSED_ASKING, REJECTED, ROLLED_BACK}
PAUSED_ASKING   → {UNDER_AUTHORITY, REJECTED}
PROMOTED        → {ROLLED_BACK}
REJECTED        → {}   (terminal)
ROLLED_BACK     → {}   (terminal)
```

Semantics:

- `PROPOSED → UNDER_ASSURANCE`: intake validation has passed (payload shape,
  path policy, recursion bound, traceability). This is the only entry.
- `UNDER_ASSURANCE → UNDER_EXPERIMENT`: requires a W7 `AssuranceResult` with
  status PASS bound to the exact chain (proposal id, target revision). A
  FAIL/UNKNOWN/BLOCKED result can never advance the proposal (they stay
  distinguishable; the proposal may be REJECTED on a resolved non-PASS).
- `UNDER_EXPERIMENT → UNDER_AUTHORITY`: requires a W8 `PromotionDecision`
  produced by `PromotionGate` from a governed experiment + evaluation bound
  to the same chain, plus a bounded `RollbackPath` whose reference matches
  the proposal's declared `rollback_ref`. Fired W8 `StopCondition`s cannot
  be offset (the transition is refused).
- `UNDER_AUTHORITY → PROMOTED`: requires a resolved W9 `AutonomyDecision` in
  state ACT bound to the exact chain. This is the ONLY promotion point.
- `UNDER_AUTHORITY → PAUSED_ASKING`: the resolved W9 decision is ASK — an
  explicit pending-authorization record is attached; leaving the pause
  (`PAUSED_ASKING → UNDER_AUTHORITY`) requires a NEW resolved decision
  (human authority). Never auto-approve, never timeout-to-ACT.
- Non-resolving W9 states (GATHER_EVIDENCE, EXPERIMENT): no state change; an
  explicit pending-evidence record is attached (truthful deferral, no
  refusal).
- `UNDER_AUTHORITY/UNDER_EXPERIMENT → ROLLED_BACK` and `PROMOTED →
  ROLLED_BACK`: governed recovery only, backed by W8 recovery evidence.
- `REJECTED`/`ROLLED_BACK` are terminal; no record is ever silently re-opened.

The "evidence" and "new SOS state" tail of the composed model: every
consequential step appends W4 evidence (verbatim); a `PROMOTED` record may
carry `adoption_revision` — the new SOS source revision produced by the
ordinary governed merge, cited as data when it exists, never fabricated, and
never produced by this module.

## 5. Governance invariants — the eight prohibitions as mechanical checks

| # | Prohibition | Mechanical check (construction/transition validation) | Test proof |
| --- | --- | --- | --- |
| P1 | No self-authorizing changes | `PROMOTED` unreachable without a resolved external W9 `AutonomyDecision` (ACT) from caller-supplied `known_decisions`; no record field is an authorization token; the module exposes no method that mints authority | promotion-without-decision rejection; source scan for authority-minting surface |
| P2 | No bypassing W7/W8/W9 | frozen transition table; each stage transition requires its gate binding (PASS result / promoted decision / ACT decision) chain-checked; gate logic frozen in code, never data-configurable | every skip attempt raises `SelfEvolutionContractError` |
| P3 | No silent Constitution change | intake path policy: `target_paths` intersecting the frozen authority set (`spec/constitution.md`, `spec/architecture.md`, `spec/architecture-lock.md`, `spec/architecture-change-process.md`, `spec/implementation-roadmap.md`, `spec/requirements.md`, frozen Work Orders) → construction rejection; such changes belong to the governed architecture change process | constitution-targeting proposal rejected at construction |
| P4 | No deleting assurance | DELETE-class `SourceChange` on an authority-implementation module (the `src/sos/` modules implementing the W1/W4/W5/W6/W7/W8/W9 authorities) → construction rejection; and the lifecycle machine's own gate requirements are frozen code no record can amend | authority-module DELETE rejection; no data-driven gate config |
| P5 | No weakening rollback | every promotion-carrying transition binds a bounded W8 `RollbackPath` matching the proposal's `rollback_ref`; `ROLLED_BACK` requires governed recovery evidence; no defaulting/stripping path exists | promotion-without-rollback rejection; rollback-without-evidence rejection |
| P6 | No redefining truth | W1 `TruthState`/`TruthfulValue` preserved end-to-end; W4 entries verbatim (observed, not inferred); hypothesis `predicted_effects` are DATA and never ingested as evidence; FAILED/UNKNOWN/UNAVAILABLE/UNSUPPORTED pairwise distinct | distinction-preservation tests; predictions-never-evidence test |
| P7 | No model output as authority | `origin` is provenance data no gate reads; MODEL_GENERATED proposals pass/fail identically to other origins given identical inputs | origin-irrelevance equivalence test |
| P8 | No unbounded recursive self-modification | fixed `MAX_META_DEPTH`; `meta_depth` construction-checked; ancestor chain resolved from `known_proposals` and rejected on overflow; the evaluation surface has NO proposal-generation path; one call advances exactly one proposal | depth-overflow rejection; API-surface scan; no-generation test |

## 6. SOS-source-as-candidate representation (data, never applied)

The "candidate change to SOS" is represented exactly like any brownfield
candidate, except its target is SOS itself:

- `target_revision` cites the exact SOS source revision the proposal proposes
  to change (the "SOS current System State" head of the composed model). The
  proposal is unconstructible without it; it is a citation, never a checkout.
- The payload is a tuple of `SourceChange` records — diff-shaped DATA (path,
  base revision, kind, payload text/hunks). It is never applied: the module
  contains no file-write, no patch, no `git`, no subprocess, no network path
  (C11/C12 source scans enforce this mechanically).
- Where a proposal implicates SOS's own architecture graph, it cites the W6
  `CandidateProposal`/`SubgraphMutation` id (optional seam, validated against
  caller-supplied registries).
- Evaluation treats the proposal like any brownfield candidate: W7 assurance
  over the chain, W8 governed experiment/promotion/rollback, W9 authority.
- `PROMOTED` is a governed decision record. `adoption_revision` cites the new
  SOS state produced by the ordinary governed merge (external, human-gated);
  the machinery itself stops at the decision.

## 7. Determinism and persistence strategy

- **Persistence:** W1 `JsonModelStore` only — proposals, steps, and lifecycle
  records round-trip; no new persistence authority (C12). Registries
  (`known_assurance`, `known_experiments`, `known_evaluations`,
  `known_promotions`, `known_decisions`, `known_evidence`,
  `known_proposals`) are caller-supplied in-memory dictionaries (W11
  `ExecutionSubstrate` precedent).
- **Identity:** content-addressed ids (`selfevo-<sha256[:16]>` over own
  material; W8/W9/W11 pattern); identical inputs → byte-identical records.
- **Clocks:** the core consults no clock, no randomness, no network; all
  timestamps are caller-supplied data (W4 `EvidenceProvenance.timestamp`
  stays data; None is truthful).
- **Threading:** single-threaded machinery (dict registries, no locks/queues)
  — the recommended deterministic policy.
- **Bounds:** one governed transition per call; fixed `MAX_META_DEPTH`;
  fixed terminal states; no iteration loops (W12's loop bound is not needed —
  W13's shape is a gated pipeline, not a search loop).

## 8. Relationship to architecture §12 (no new authority class)

Architecture §12 defines exactly four authority classes — Intent
(Constitution/Mission/approved Value commitments), Knowledge (System/
Evidence/Causal/Memory models), Execution (deployment/runtime mechanisms),
Assurance (trusted policy/checking/rollback). W13 introduces none:

- W13's records (proposals, hypotheses, steps, lifecycle states) are
  **Knowledge-class artifacts** — governed, versioned, evidence-linked data
  about a proposed change, not a new truth source.
- Authorization remains W9 (+ the human authority above it); W13 never
  mints `AutonomyDecision`s.
- Assurance remains W7/W8; W13 never re-implements a gate.
- Execution authority is NOT invoked: adoption of a promoted proposal is an
  ordinary repository-governance act performed by humans (Worker PR +
  Architect gate) outside this module. The LLM proposal layer stays inside
  the untrusted proposal mechanism (constitution principle 5): it can
  produce PROPOSED records, never authority. Architecture §13 invariant 12
  ("SOS may evolve itself, but not by escaping its own Constitution and
  assurance boundary") is therefore structurally satisfied: the lifecycle
  machine is under the same gates it proposes to evolve.

## 9. Test strategy outline

`tests/test_w13_selfevolution.py` (the only test file) must cover the Work
Order's required regression list. Organization (W11/W12 contract-suite
style, extend-never-weaken):

1. **Happy path** — full governed lifecycle on fixture chains (deterministic;
   byte-identical re-run; content-addressed ids).
2. **Gate mechanics** — W7 non-PASS / missing rejection; W8
   promotion-missing rejection; W9 missing/unresolved rejection; stage-skip
   rejection; ASK pause + resume-only-via-new-decision; GATHER_EVIDENCE
   deferral; REJECT refusal; ROLLBACK with recovery evidence.
3. **Intake policy** — frozen-path rejection; authority-module DELETE
   rejection; invalid paths; recursion-depth overflow.
4. **Prohibition proofs** — origin-irrelevance equivalence; predictions-
   never-evidence; distinction preservation; no-authority-minting surface
   scan; no-proposal-generation surface scan.
5. **Composition identity** — every referenced authority symbol asserted
   identical to its owning module's object (W11 pattern).
6. **Persistence/determinism** — `JsonModelStore` round-trip; identical runs
   → identical ids; source scan of `src/sos/` for write/subprocess/git/
   network tokens; absence of W14 symbols.

## 10. Explicit non-goals (Work Order exclusions restated)

No self-modification execution of any kind (no source mutation, patch
application, file writes, `git`, subprocess, network); no W11 substrate
dispatch / live execution; no autonomous proposal generation (the evaluation
surface never creates proposals); no LLM/model output as authorization,
truth, or evidence; no mission/Constitution/frozen-spec changes (intake
rejects them; they belong to the governed architecture change process); no
new authority class; no W14 dogfood/adversarial verification; no weakening
of W7/W8/W9 gates or rollback; no modification of frozen W1–W12 semantics.

## 11. Requirement traceability

R7 (the lifecycle starts from SOS's versioned System State — the exact
`target_revision` citation); R9 (W4 evidence at every consequential step,
verbatim); R13 (W7 assurance gates before promotion); R14 (bounded W8
`RollbackPath` on every promotion); R15 (W9 policy-governed authority);
R16 (ASK first-class: `PAUSED_ASKING` + pending-authorization record); R19
(W5 causal/memory priors cited; outcomes recorded as evidence for future
priors — memory as prior, not proof); R20 (the defining requirement:
mission-directed self-evolution under the Constitution and assurance
boundary); R21 (truthful failure states preserved end-to-end); R22 (explicit
human authority: ASK pause, human-gated adoption); R23 (explainability by
evidence: the full chain — hypothesis, payload, assurance, experiment,
promotion, decision, uncertainty, adoption citation — is preserved in the
final record); R24 (repository-governed implementation: this design + the
Work Order + the checkpoint are the review artifacts).

Architecture sections: §2 (core invariant chain — the composed lifecycle is
exactly that chain applied to SOS itself), §4 (control-plane capabilities
6–10 composed, never duplicated), §5 (decision policy via W9), §9 (safe
evolution gated lifecycle), §11 (SOS self-evolution / meta-adaptation — the
governing section), §12 (trust boundaries, no fifth authority), §13
(invariants 2, 4, 6, 7, 8, 9, 10, 12). Constitution principles: 2, 4, 5, 6,
8, 9, 10.

## 12. Recommended frozen defaults (Worker resolves; extend, never weaken)

| Open question | Recommended default (non-binding until implemented; the Work Order criteria are binding) |
| --- | --- |
| Module path | `src/sos/selfevolution.py` (Work Order allowed surface) |
| Transition API shape | module-level `transition_self_evolution(proposal, new_state, *, known_...)` free function (W8 `transition_experiment` precedent); a thin engine class is Worker latitude — it must expose no proposal-generation method |
| Error type | `SelfEvolutionContractError(ModelValidationError)` (W11 precedent) |
| State names | exactly the eight states in §4 (no WITHDRAWN in this slice) |
| `MAX_META_DEPTH` | 3 (any fixed small constant ≥ 1 satisfies C10; the value must be a named constant, not a magic number) |
| Adoption citation field | `adoption_revision: str | None` on the proposal record (data; None is truthful) |
| W4 binding helper | `SelfEvolutionStep` + a verbatim converter into W4 `Evidence` reusing the existing evidence vocabulary and the package-internal assembly helper (W11 `receipt_to_w4_evidence` precedent — one content-addressing algorithm) |
| Origin enum members | `MODEL_GENERATED` / `HUMAN_GENERATED` / `EVIDENCE_TRIGGERED` (extensible only via governed change) |
| Frozen authority path set | a named constant listing `spec/constitution.md`, `spec/architecture.md`, `spec/architecture-lock.md`, `spec/architecture-change-process.md`, `spec/implementation-roadmap.md`, `spec/requirements.md`, `spec/sos-meta-model.md`, frozen `spec/work-orders/*`, and `spec/development-state/implementation-state.json` (the Worker may extend the constant only with Architect-approved additions) |
| Authority-module set | a named constant listing the `src/sos/` modules implementing W1/W4/W5/W6/W7/W8/W9 authorities (DELETE-class prohibition target) |

## 13. Implementation reconciliation (filled by the W13 Worker — extend, never weaken)

The implemented contract follows §§1–12 with the resolutions below. Every
deviation from a §12 recommended default is honest and recorded; none weakens
a Work Order criterion.

### 13.1 Implemented surface (exactly the five allowed files)

- `src/sos/selfevolution.py` (NEW): `SelfEvolutionContractError(ModelValidationError)`;
  frozen constants `MAX_META_DEPTH = 3`, `FROZEN_AUTHORITY_PATHS`,
  `FROZEN_AUTHORITY_PATH_PREFIXES` (the frozen Work Orders directory),
  `AUTHORITY_MODULE_PATHS`, `SELF_EVOLUTION_TERMINAL_STATES`;
  `ProposalOrigin`, `SourceChangeKind`, `SourceChange`,
  `SelfImprovementHypothesis`, `SelfEvolutionState` + frozen transition table
  + `validate_self_evolution_transition`, `SelfEvolutionGate`,
  `PendingResolution`, `PendingProposalAuthorization`, `PendingProposalEvidence`,
  `SelfEvolutionProposal` (content-addressed over the INTAKE material — stable
  identity across the lifecycle, the W8 `Experiment` precedent; tamper-evident
  id-integrity check in `validate`), `resolve_meta_chain`, `SelfEvolutionStep`
  (table-validated at construction), `step_to_w4_evidence` (reuses the W4
  package-internal `_build_evidence` — one content-addressing algorithm),
  `SelfEvolutionTransitionResult`, `transition_self_evolution`,
  `defer_self_evolution`. No engine class; the free-function surface is the
  W8 `transition_experiment` precedent.
- `src/sos/__init__.py`: W13 exports only (23 names); zero other changes.
- `tests/test_w13_selfevolution.py` (NEW): 78 deterministic offline test items
  in 42 test functions; the happy path runs the REAL W3 recovery + REAL W7
  `assure_candidate` (over a W6 candidate projection carrying the proposal's
  explicit id) + REAL W8 lifecycle/evaluation/`PromotionGate` + REAL W9
  `evaluate_autonomy` before the lifecycle consumes the records; boundary
  tests use directly-constructed W7/W8/W9 records (the W12 `assurance_record`
  precedent).

### 13.2 Design resolutions (Worker latitude, resolved)

1. **Stable proposal identity.** The proposal id is content-addressed over
   the intake material ONLY (revision, paths, changes, hypothesis, origin,
   rollback ref, recursion fields, W6 citation, traceability); state, gate
   references, pendings, adoption citation, and evidence ids are EXCLUDED —
   so every governed transition returns a record with the SAME id and the
   W7/W8/W9 chain bindings remain exact across the lifecycle. `validate`
   re-derives the id (tamper-evident).
2. **The W7/W9 engines are composed by the caller; the W8 promotion gate
   engine is re-run by the core.** The lifecycle CONSUMES W7 `AssuranceResult`
   and W9 `AutonomyDecision` records from the caller-supplied registries
   (C4's exact mandate: "from caller-supplied `known_decisions`") and
   chain-checks them (proposal id + target revision + decision chain). The
   REAL W8 `PromotionGate().evaluate` is additionally RE-RUN inside
   `transition_self_evolution` at both the UNDER_AUTHORITY entry and the
   PROMOTED promotion point, so a supplied `PromotionDecision` can never
   outrank the real authority. The real `assure_candidate` and
   `evaluate_autonomy` engines are exercised end-to-end by the test suite
   (the Work Order's "injected W7/W8/W9 records" evaluation model); the
   module imports the record/status types it binds.
3. **W6 citation seam.** `candidate_ref` cites a real W6 `CandidateProposal`
   id (validated against `known_candidates`); W6's `SubgraphMutation` carries
   no independent id of its own, so the candidate citation IS the
   mutation citation (the cited candidate's mutation is thereby cited).
4. **Rejection grounds, one gate per source state (deterministic, frozen):**
   PROPOSED→REJECTED requires a W9 REJECT decision (empty chain);
   UNDER_ASSURANCE→REJECTED requires a supplied W7 result with a resolved
   NON-PASS status (distinct statuses preserved verbatim:
   FAIL→FAILED, UNKNOWN→UNKNOWN, BLOCKED→UNAVAILABLE);
   UNDER_EXPERIMENT→REJECTED requires the W8 gate decision (promoted=False,
   cross-checked against the real PromotionGate re-run);
   UNDER_AUTHORITY/PAUSED_ASKING→REJECTED requires a W9 REJECT decision.
5. **Rollback grounds (frozen):** UNDER_EXPERIMENT→ROLLED_BACK requires the
   W8 experiment lifecycle itself in `ROLLED_BACK` state (W8-governed
   recovery) plus the bounded `RollbackPath` bound to the declared
   `rollback_ref` with SUCCESS recovery evidence provenance-bound to the
   target revision; UNDER_AUTHORITY/PROMOTED→ROLLED_BACK requires a resolved
   W9 ROLLBACK decision plus the same recovery binding. `adoption_revision`
   is preserved on PROMOTED→ROLLED_BACK as historical data.
6. **Resume semantics.** PAUSED_ASKING→UNDER_AUTHORITY requires a NEW
   resolved W9 ACT decision (the old ASK decision, a GATHER_EVIDENCE
   decision, or no decision all refuse); the resumed record clears the pause
   marker and carries the resuming decision id. The promotion transition
   then requires its own supplied ACT decision as usual.
7. **Evidence kinds.** Steps convert verbatim into W4 evidence:
   ROLLED_BACK-targeting steps become `rollback`-kind evidence, every other
   step an `observation`; only existing W4 kinds; availability is always
   SUCCESS (the step was captured) while the observed outcome state is
   preserved verbatim (pause/deferral steps are truthful UNKNOWN).
8. **Deferral API.** Non-resolving W9 states (GATHER_EVIDENCE, EXPERIMENT) go
   through `defer_self_evolution` (a state-KEEPING step: explicit
   pending-evidence record, truthful UNKNOWN evidence, no advancement, no
   refusal) — the state machine itself has no self-transitions.
9. **Construction strictness (extends the prepared contract).** In addition
   to the prepared rules: `target_paths` must be sorted/deduplicated and
   exactly match the change paths; every change's `base_revision` must equal
   the proposal's `target_revision`; the hypothesis must cite ≥1 trigger
   evidence id and ≥1 predicted effect and may never claim SUCCESS
   uncertainty; id-integrity is re-verified in `validate` (tamper-evident
   records); the intake transition REFUSES citations that cannot be
   validated (registry not supplied).
10. **`AUTHORITY_MODULE_PATHS` extension.** The prepared §12 default named
    the W1/W4/W5/W6/W7/W8/W9 authority modules; the implemented constant
    additionally protects `src/sos/selfevolution.py` (the lifecycle machine's
    own module) and `src/sos/__init__.py` (the package export boundary) from
    DELETE-class changes — "no code path may remove or weaken the lifecycle
    machine's own gate requirements". MODIFY-class changes on authority
    modules remain lawful proposals (still fully gated); DELETE-class changes
    on non-authority `src/sos` modules remain lawful proposals (still fully
    gated, adoption still external).

### 13.3 Honest deviations from the §12 recommended defaults

- **Transition API shape:** implemented exactly as recommended (module-level
  `transition_self_evolution(proposal, new_state, *, known_...)`); no engine
  class was added.
- **Error type / state names / `MAX_META_DEPTH` / adoption field / W4 binding
  helper / origin members / frozen path set:** implemented exactly as
  recommended (`MAX_META_DEPTH = 3`).
- **Naming deviations (documented, no semantic change):** the pending records
  are `PendingProposalAuthorization`/`PendingProposalEvidence` with a W13-owned
  `PendingResolution` (PENDING-only) — W12's `PendingAuthorization`/
  `AuthorizationResolution` are W12-owned and W13 must not depend on W12
  internals; the step converter is `step_to_w4_evidence`; the promotion
  reference is the W12-canonical `"<experiment-id>:<evaluation-id>"` string
  stored in `promotion_id`.
- **§3 field list extensions:** the implemented `SelfEvolutionProposal` also
  carries `assurance_status` (the bound W7 status — W7 distinctness visible
  on the record), `pending_evidence` (the deferral marker), and
  `SELF_EVOLUTION_TERMINAL_STATES` is exported. Nothing was removed.

## 14. Acceptance criteria → implementation → test mapping (C1–C12)

| Criterion | Implementation anchor | Primary tests |
|---|---|---|
| C1 composed-authority integrity | import-identity reuse; chain-check helpers re-resolve every W7/W8/W9 reference; real `PromotionGate` re-run; `Experiment.validate(known_assurance=...)` delegated | `test_w13_references_frozen_authorities_without_redefining`, `test_full_governed_happy_path_produces_deterministic_promoted_record`, `test_missing_or_unresolved_w9_reference_is_rejected` |
| C2 proposal-as-data integrity | inert `SourceChange` payload; exact `target_revision` citation; untrusted origin; W1 traceability; content-addressed id; `JsonModelStore` round-trip; no apply path (source scans) | `test_full_governed_happy_path_produces_deterministic_promoted_record`, `test_records_round_trip_through_w1_json_store`, `test_selfevolution_module_scan_is_clean` |
| C3 W7→W8→W9 ordering | frozen table + state-dependent field presence + per-transition gate bindings | `test_lifecycle_state_machine_rejects_free_form_transitions`, `test_under_experiment_requires_w7_pass_bound_to_exact_chain`, `test_stage_skip_attempts_are_rejected_at_the_transition_boundary`, `test_promotion_requires_the_w8_promotion_gate_decision` |
| C4 no self-authorization | `PROMOTED` only via a supplied resolved ACT decision; no authority minting anywhere; PENDING-only pending records | `test_missing_or_unresolved_w9_reference_is_rejected`, `test_pending_authorization_can_never_auto_approve`, `test_evaluation_surface_exposes_no_proposal_generation_path` |
| C5 ASK pause mechanics | `PAUSED_ASKING` + `PendingProposalAuthorization`; resume only via a NEW ACT decision; `defer_self_evolution` for GATHER_EVIDENCE/EXPERIMENT | `test_w9_ask_pauses_with_explicit_pending_authorization_record`, `test_ask_pause_leaves_only_via_a_new_resolved_act_decision`, `test_w9_gather_evidence_defers_with_explicit_pending_record`, `test_w9_experiment_decision_defers_and_deferral_is_gated`, `test_deferral_while_paused_keeps_the_pause_state` |
| C6 Constitution/authority protection | `FROZEN_AUTHORITY_PATHS`/`PREFIXES` + `AUTHORITY_MODULE_PATHS` enforced at BOTH `SourceChange` and proposal construction; gate logic frozen code | `test_frozen_authority_target_paths_are_rejected_at_intake`, `test_delete_on_authority_implementation_modules_is_rejected_at_intake`, `test_non_authority_delete_and_authority_modify_remain_lawful_proposals` |
| C7 governed promotion/rollback | bounded `RollbackPath` bound to `rollback_ref` with SUCCESS provenance-bound recovery evidence at BOTH the UNDER_AUTHORITY and PROMOTED transitions; W8/W9-governed rollback paths | `test_promotion_requires_a_bounded_rollback_path_bound_to_the_declared_reference`, `test_w9_rollback_from_authority_rolls_back_with_recovery_evidence`, `test_promoted_record_rolls_back_through_governed_recovery`, `test_w8_experiment_rollback_from_under_experiment_requires_governed_recovery` |
| C8 truth preservation | injective W7-status→truth map; verbatim `TruthfulValue` outcomes into W4 evidence; predictions/payloads never ingested | `test_rejection_on_resolved_non_pass_w7_preserves_distinctions` (×3), `test_truth_distinctions_are_preserved_through_the_lifecycle`, `test_predictions_and_payloads_are_never_ingested_as_evidence` |
| C9 origin never authorizes | origin is identity material only; no gate reads it (structural + behavioral proofs) | `test_origin_never_authorizes_identical_gates_for_every_origin`, `test_no_gate_reads_the_proposal_origin` |
| C10 bounded recursion | `MAX_META_DEPTH=3`; construction + `resolve_meta_chain` checks; no generation path; one call one proposal | `test_recursion_depth_overflow_is_rejected`, `test_ancestor_chain_must_resolve_completely_from_known_proposals`, `test_evaluation_surface_exposes_no_proposal_generation_path` |
| C11 determinism and bounds | clock-free core; caller-supplied timestamps; sha256 content addressing; byte-identical re-runs; token scans | `test_identical_runs_produce_byte_identical_records_and_ids`, `test_no_self_modification_execution_tokens_anywhere_in_src`, `test_selfevolution_module_scan_is_clean` |
| C12 persistence and bounded surface | W1 `JsonModelStore` round-trip; exports only through `sos`; no W14 symbols | `test_records_round_trip_through_w1_json_store`, `test_w13_exports_only_through_the_package_surface`, `test_no_w14_or_successor_symbols` |

## 15. Required regression coverage mapping (Work Order list → tests, one-to-one)

| Work Order required scenario | Test(s) |
|---|---|
| full governed happy path (…→PROMOTED, evidence every step, deterministic, byte-identical re-run) | `test_full_governed_happy_path_produces_deterministic_promoted_record`, `test_identical_runs_produce_byte_identical_records_and_ids` |
| W9 ASK pause + resume only via new resolved decision | `test_w9_ask_pauses_with_explicit_pending_authorization_record`, `test_ask_pause_leaves_only_via_a_new_resolved_act_decision` |
| W9 GATHER_EVIDENCE deferral | `test_w9_gather_evidence_defers_with_explicit_pending_record` (+ `test_deferral_while_paused_keeps_the_pause_state`) |
| W9 REJECT refusal | `test_w9_reject_refuses_the_proposal` |
| W9 ROLLBACK with recovery evidence | `test_w9_rollback_from_authority_rolls_back_with_recovery_evidence`, `test_promoted_record_rolls_back_through_governed_recovery`, `test_w8_experiment_rollback_from_under_experiment_requires_governed_recovery` |
| missing/unresolved W9 reference rejection | `test_missing_or_unresolved_w9_reference_is_rejected` |
| W7-missing / W7 non-PASS stage-advance rejection | `test_under_experiment_requires_w7_pass_bound_to_exact_chain` (×3 statuses + missing/chain-mismatch/non-record) |
| promotion without PromotionGate/PromotionDecision rejection | `test_promotion_requires_the_w8_promotion_gate_decision` (missing/unknown/refused/forged-vs-real-gate), `test_rejection_at_the_experiment_stage_records_the_refused_gate` |
| promotion without bounded RollbackPath rejection | `test_promotion_requires_a_bounded_rollback_path_bound_to_the_declared_reference` (none/wrong-ref/missing-ev/failed-ev/wrong-revision) |
| stage-skip attempts rejected | `test_lifecycle_state_machine_rejects_free_form_transitions` (exhaustive), `test_stage_skip_attempts_are_rejected_at_the_transition_boundary` (×9) |
| intake rejection of frozen-authority target paths | `test_frozen_authority_target_paths_are_rejected_at_intake` (×12, incl. the work-orders prefix) |
| intake rejection of DELETE on authority-implementation modules | `test_delete_on_authority_implementation_modules_is_rejected_at_intake` (×9) |
| recursion-depth overflow rejection | `test_recursion_depth_overflow_is_rejected`, `test_ancestor_chain_must_resolve_completely_from_known_proposals` |
| origin irrelevance | `test_origin_never_authorizes_identical_gates_for_every_origin`, `test_no_gate_reads_the_proposal_origin` |
| truth preservation through the lifecycle | `test_truth_distinctions_are_preserved_through_the_lifecycle`, `test_rejection_on_resolved_non_pass_w7_preserves_distinctions` (×3), `test_predictions_and_payloads_are_never_ingested_as_evidence` |
| W5/W6 citation validation | `test_w5_w6_citations_are_validated_against_caller_supplied_registries` (incl. the W5 `ArchitectureMemory` prior seam) |
| determinism (identical runs → identical ids) | `test_identical_runs_produce_byte_identical_records_and_ids`, `test_full_governed_happy_path_produces_deterministic_promoted_record` |
| JSON round-trip through W1 `JsonModelStore` | `test_records_round_trip_through_w1_json_store` (proposal, step, pending, paused) |
| source scan for self-modification execution tokens | `test_no_self_modification_execution_tokens_anywhere_in_src`, `test_selfevolution_module_scan_is_clean` |
| absence of W14 symbols | `test_no_w14_or_successor_symbols` |
| absence of proposal-generation methods on the evaluation surface | `test_evaluation_surface_exposes_no_proposal_generation_path` |
| authority-symbol identity assertions | `test_w13_references_frozen_authorities_without_redefining`, `test_w13_exports_only_through_the_package_surface` |
