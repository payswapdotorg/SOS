# W13 Implementation Checkpoint (first bounded slice)

**Work Order:** `spec/work-orders/W13-self-evolution.md` (frozen, authoritative)
**State:** `WAITING_FOR_ARCHITECT` (review iteration 1)
**Branch:** `work/w13-self-evolution` (from live `main` AFTER the W12 merge)
**Base SHA (dispatch commit, live `main` AFTER the W12 merge):**
`0da1ca09885b0cc618cdddebc6da5acfc3f0c978` — "Reconcile W12 completion (merge
933e1e9, operator-delegated TL gate on PR #19) and open the W13 frontier",
the exact post-W12-merge `main` recorded at dispatch; NOT
`e3a97b895ca6f6cc7206a50bde45b2b55c554195`, which was the W12 dispatch point.
**Exact implementation head (contract code, exports, tests):**
`8750cf9e638557a6ca96a9244d33de16d6fd426d`
**Exact branch tip:** the commit carrying this checkpoint (a documentation-only
delta from the implementation head above; a commit cannot embed its own SHA —
the authoritative review head is recorded in the worker report). The
verification outputs below were produced at the implementation head
`8750cf9e` and re-run at the tip (identical counts; the tip adds this file
only).

## Dependency proof (verified by the Worker from live state at dispatch)

Frozen-ledger declared dependencies (verified from
`spec/development-state/implementation-state.json` and Git at the base commit
`0da1ca0`):

- W8 merged `65b84058aa204b3749e45b7e21ae433a4b138d83`
- W9 merged `203cfb7590bd25244cabf3cc7299dd192b00948d`

Reused frozen authorities (verified in the branch ancestry):

- W1 `091d4d10a38922fb2d9cadb103e7ba8caa7a1f20`
- W4 `26060db57c24ba8b36315c1005466046810c5163`
- W5 `2bfd0f89da129c6b3347d88b0d8da1b79dd04127`
- W6 `b5171f70ca5ce85ca0be07cfdb3abf034c03c32f`
- W7 `25f663cf444f92b3190074a9119619cbc53e9ece`

Roadmap sequencing gate (NOT an implementation dependency; satisfied before
dispatch):

- W12 merged as `933e1e9` (the actual Git merge of PR #19; the Worker's base
`0da1ca0` is the post-W12-merge reconciliation commit that dispatched W13 —
one commit after the merge, all W12 content in the ancestry). No unmerged
branch content was used as a dependency, and no W12 implementation internal
is depended upon (W13 composes W1/W4/W5/W6/W7/W8/W9 only; the W12-owned
pending-record types were deliberately NOT reused for that reason).

Baseline verified by the Worker before any work: exactly **360 passed**,
`compileall` clean, at the base `0da1ca0` on Python 3.12.14.

## Scope implemented (exactly the five allowed files — filled)

- `src/sos/selfevolution.py` (NEW, 2107 lines): the governed self-evolution
  proposal lifecycle — `SelfEvolutionContractError(ModelValidationError)`;
  frozen constants `MAX_META_DEPTH = 3`, `FROZEN_AUTHORITY_PATHS`,
  `FROZEN_AUTHORITY_PATH_PREFIXES`, `AUTHORITY_MODULE_PATHS`,
  `SELF_EVOLUTION_TERMINAL_STATES`; the record model (`SourceChange`,
  `SelfImprovementHypothesis`, `SelfEvolutionProposal` content-addressed over
  its intake material with a tamper-evident id-integrity check,
  `ProposalOrigin`, `SourceChangeKind`); the frozen 8-state lifecycle machine
  (`SelfEvolutionState`, exhaustive transition table,
  `validate_self_evolution_transition`, `SelfEvolutionGate`); the explicit
  pause/deferral records (`PendingResolution` (PENDING-only),
  `PendingProposalAuthorization`, `PendingProposalEvidence`); bounded
  recursion (`resolve_meta_chain`); the W4 binding (`SelfEvolutionStep`,
  table-validated at construction + `step_to_w4_evidence` reusing the W4
  package-internal `_build_evidence`); `SelfEvolutionTransitionResult`; the
  governed evaluation surface (`transition_self_evolution`,
  `defer_self_evolution`) which chain-checks every W7/W8/W9 reference against
  caller-supplied registries and re-runs the REAL W8 `PromotionGate` at both
  promotion-carrying transitions. Zero network, zero child processes, zero
  file mutation, zero version-control invocation, zero clock.
- `src/sos/__init__.py` (MODIFIED, +26 lines): W13 exports only (23 names);
  zero other changes; no export name collisions (verified:
  `sos.__all__` has 177 unique names).
- `tests/test_w13_selfevolution.py` (NEW, ~2400 lines): 78 deterministic
  offline test items in 42 test functions covering the Work Order's required
  regression coverage one-to-one (design §15). The happy path composes the
  REAL W3 recovery + REAL W7 `assure_candidate` (over a W6 candidate
  projection carrying the proposal's explicit id) + REAL W8
  lifecycle/evaluation/`PromotionGate` + REAL W9 `evaluate_autonomy`; boundary
  tests use directly-constructed W7/W8/W9 records (the W12 `assurance_record`
  precedent).
- `docs/implementation/W13-SELF-EVOLUTION-DESIGN.md` (MODIFIED): reconciled to
  the implemented contract — status header updated, §§13–15 added (implemented
  surface, design resolutions, honest deviations from the §12 recommended
  defaults, C1–C12 mapping, required-regression-coverage mapping); §§1–12
  preserved as prepared (extend, never weaken).
- `spec/development-state/W13-checkpoint.md`: this file, filled.

Zero modifications to W1–W12 sources, frozen specs, roadmap, or Work Order
machinery (verified: `git diff --name-only 0da1ca0..HEAD` lists exactly the
four non-checkpoint files above plus this file).

## Acceptance criteria → implementation → test mapping (filled)

Full mapping with test names in
`docs/implementation/W13-SELF-EVOLUTION-DESIGN.md` §14 (C1–C12) and §15 (the
Work Order's required regression coverage, one-to-one). Summary:

| Criterion | Implementation | Tests |
|---|---|---|
| C1 composed-authority integrity | import-identity reuse of W1/W4/W5/W6/W7/W8/W9 symbols; chain-check helpers re-resolve every cross-authority reference against the exact proposal-id/target-revision/decision chain; W8's own `Experiment.validate(known_assurance=...)` delegated; the REAL `PromotionGate` engine re-run at both promotion-carrying transitions | `test_w13_references_frozen_authorities_without_redefining`, `test_full_governed_happy_path_produces_deterministic_promoted_record`, `test_missing_or_unresolved_w9_reference_is_rejected` |
| C2 proposal-as-data integrity | inert diff-shaped `SourceChange` payload (path/base-revision/kind/payload-text); exact `target_revision` citation; untrusted `ProposalOrigin`; W1 `Traceability`; content-addressed id; W1 `JsonModelStore` round-trip; no apply path exists | `test_full_governed_happy_path_produces_deterministic_promoted_record`, `test_records_round_trip_through_w1_json_store`, `test_selfevolution_module_scan_is_clean` |
| C3 W7→W8→W9 ordering invariant | frozen transition table + state-dependent field presence (an advanced record without its gate binding is unconstructible) + per-transition gate bindings (W7 PASS / W8 promoted decision + bounded rollback / W9 ACT) | `test_lifecycle_state_machine_rejects_free_form_transitions` (exhaustive), `test_stage_skip_attempts_are_rejected_at_the_transition_boundary` (×9), `test_under_experiment_requires_w7_pass_bound_to_exact_chain`, `test_promotion_requires_the_w8_promotion_gate_decision` |
| C4 no self-authorization | `PROMOTED` reachable only through a supplied resolved W9 ACT decision from `known_decisions` (chain-checked, promotion-ref bound, evidence-set matched against the W8 evaluation); no method mints authority; PENDING-only pending records | `test_missing_or_unresolved_w9_reference_is_rejected`, `test_pending_authorization_can_never_auto_approve`, `test_evaluation_surface_exposes_no_proposal_generation_path` |
| C5 ASK pause mechanics | `PAUSED_ASKING` + `PendingProposalAuthorization.from_decision` (ASK-only); resume only via a NEW resolved ACT decision; `defer_self_evolution` for GATHER_EVIDENCE/EXPERIMENT with an explicit `PendingProposalEvidence` (no advancement, no refusal) | `test_w9_ask_pauses_with_explicit_pending_authorization_record`, `test_ask_pause_leaves_only_via_a_new_resolved_act_decision`, `test_w9_gather_evidence_defers_with_explicit_pending_record`, `test_w9_experiment_decision_defers_and_deferral_is_gated`, `test_deferral_while_paused_keeps_the_pause_state` |
| C6 Constitution/authority protection | `FROZEN_AUTHORITY_PATHS` + `FROZEN_AUTHORITY_PATH_PREFIXES` (work-orders directory) and `AUTHORITY_MODULE_PATHS` enforced at BOTH `SourceChange` and proposal construction (defense in depth); gate requirements are frozen code | `test_frozen_authority_target_paths_are_rejected_at_intake` (×12), `test_delete_on_authority_implementation_modules_is_rejected_at_intake` (×9), `test_non_authority_delete_and_authority_modify_remain_lawful_proposals` |
| C7 governed promotion/rollback | bounded W8 `RollbackPath` bound to the declared `rollback_ref` with SUCCESS provenance-bound recovery evidence required at BOTH the UNDER_AUTHORITY and PROMOTED transitions; rollback paths are W8-governed (experiment lifecycle ROLLED_BACK) or W9-governed (resolved ROLLBACK decision); stop-condition semantics enforced by the real PromotionGate re-run | `test_promotion_requires_a_bounded_rollback_path_bound_to_the_declared_reference`, `test_w9_rollback_from_authority_rolls_back_with_recovery_evidence`, `test_promoted_record_rolls_back_through_governed_recovery`, `test_w8_experiment_rollback_from_under_experiment_requires_governed_recovery` |
| C8 truth preservation | injective W7-status→W1-truth map (PASS→SUCCESS, FAIL→FAILED, UNKNOWN→UNKNOWN, BLOCKED→UNAVAILABLE); verbatim `TruthfulValue` step outcomes into W4 evidence; hypothesis predictions/payloads are DATA and never ingested; pause/deferral evidence is truthful UNKNOWN | `test_rejection_on_resolved_non_pass_w7_preserves_distinctions` (×3), `test_truth_distinctions_are_preserved_through_the_lifecycle`, `test_predictions_and_payloads_are_never_ingested_as_evidence` |
| C9 origin never authorizes | origin is identity material only; no gate function reads it (structural source proof) and all three origins produce identical governed outcomes (behavioral proof) | `test_origin_never_authorizes_identical_gates_for_every_origin`, `test_no_gate_reads_the_proposal_origin` |
| C10 bounded recursion | fixed `MAX_META_DEPTH = 3` named constant; construction + `resolve_meta_chain` reject out-of-range depths and inconsistent/missing ancestor chains (resolved from `known_proposals`); the evaluation surface has no proposal-generation path; one call advances exactly one proposal | `test_recursion_depth_overflow_is_rejected`, `test_ancestor_chain_must_resolve_completely_from_known_proposals`, `test_evaluation_surface_exposes_no_proposal_generation_path` |
| C11 determinism and bounds | clock-free core (caller-supplied timestamps); deterministic ordering; sha256 content-addressed ids; byte-identical re-runs from independent fixture repositories; tree-wide + module source scans | `test_identical_runs_produce_byte_identical_records_and_ids`, `test_no_self_modification_execution_tokens_anywhere_in_src`, `test_selfevolution_module_scan_is_clean` |
| C12 persistence and bounded authority surface | all W13 record types round-trip through W1 `JsonModelStore`; W13 exports only through `src/sos/__init__.py` (identity-asserted); no W14 symbols; no live-execution/self-modification symbols | `test_records_round_trip_through_w1_json_store`, `test_w13_exports_only_through_the_package_surface`, `test_no_w14_or_successor_symbols` |

## Verification (filled by the Worker at checkpoint time)

```text
python -m pytest
python -m compileall -q src tests
```

Exact-head results (implementation head `8750cf9e`; re-run at the branch tip,
which adds this checkpoint file only — identical counts):

```text
$ python3 -m pytest
438 passed in 1.37s
$ python3 -m compileall -q src tests
(exit code 0; no output — clean)
```

Exact pass count: **438** (0 failed, 0 errors, 0 skipped) = 360 baseline
(verified at the recorded dispatch base `0da1ca0` before any work) + 78 new
W13 test items (42 test functions, several parametrized). Duration is
environment-dependent; counts are exact. Fully offline: no network, no
provider, no wall clock.

## Honest deviations (filled)

1. **Two commits** (implementation `8750cf9e` + this documentation commit)
   instead of one, following the W10/W11/W12 convention so the checkpoint can
   record an exact implementation head SHA.
2. **W12-owned pending types not reused.** The prepared design §3 described
   "pending-authorization / pending-evidence markers" without naming types;
   W12's `PendingAuthorization`/`AuthorizationResolution` could not be reused
   because W13 must not depend on W12 implementation internals (Work Order
   sequencing note). W13 therefore owns `PendingProposalAuthorization` /
   `PendingProposalEvidence` / `PendingResolution` (PENDING-only), mirroring
   the W12 semantics. Recorded as design resolution §13.3.
3. **`AUTHORITY_MODULE_PATHS` extended** beyond the prepared §12 default (the
   W1/W4/W5/W6/W7/W8/W9 authority modules) with `src/sos/selfevolution.py`
   and `src/sos/__init__.py` — protecting the lifecycle machine's own module
   and the export boundary from DELETE-class proposals ("no code path may
   remove or weaken the lifecycle machine's own gate requirements"). A
   protective extension; MODIFY-class changes on authority modules and
   DELETE-class changes on non-authority modules remain lawful (still fully
   gated) proposals. Recorded as design resolution §13.2.10.
4. **Engine composition split** (design resolution §13.2.2): the lifecycle
   consumes W7 `AssuranceResult` / W9 `AutonomyDecision` records from the
   caller-supplied registries (C4's exact mandate) and chain-checks them,
   while the REAL W8 `PromotionGate` engine is additionally re-run inside the
   core at both promotion-carrying transitions; the real W7 `assure_candidate`
   and W9 `evaluate_autonomy` engines are composed by the evaluation fixtures
   (the Work Order's "injected W7/W8/W9 records" model) and are exercised
   end-to-end in the test suite.
5. **`assurance_status` field added** to the proposal record (beyond the
   prepared §3 field list) so the bound W7 status is visible on the record
   itself (C8 distinctness); an extension, nothing removed.

No other deviations from the Work Order envelope, the frozen architecture, or
the prepared design's recommended defaults were found: the five-file surface
was respected, all twelve acceptance criteria are mechanically enforced and
tested, and no frozen or W1–W12 file was touched.

## Known limitations (filled)

1. Contract/proposal evidence only (the Work Order's "Evaluation" section):
   the lifecycle is exercised on fixture proposals with injected W7/W8/W9
   records and W4 evidence over deterministically recovered fixture
   repositories; no live system is involved.
2. `PROMOTED` changes no source: adoption into SOS sources remains ordinary
   repository governance (Worker PR + Architect gate) performed outside this
   machinery; `adoption_revision` is a citation recorded as data when the
   caller supplies it (None is truthful) and is never fabricated or verified
   by this module.
3. Registries are caller-supplied in-memory mappings; the transition
   functions are pure with respect to them (the returned evidence is carried
   in the result for the caller to ingest — no hidden state, no registry
   mutation by the machinery).
4. A PAUSED_ASKING record has no in-slice resume side effects beyond the
   governed `PAUSED_ASKING → UNDER_AUTHORITY` transition (which requires a
   NEW resolved ACT decision); there is no timeout and no automatic
   resolution of a pending record.
5. The W7/W9 records are chain-checked and (for promotion) cross-checked
   against the real W8 gate, but the W7/W9 engines themselves are not re-run
   by the core (C4 mandates the caller-supplied-decision pattern); a record
   produced by the real engines satisfies every binding by construction, as
   the test suite demonstrates.

## Risk / rollback (filled)

**Risk:** boundary leakage — a self-evolution path that self-authorizes,
bypasses a gate, weakens rollback, or mutates sources. The C1–C12 mechanical
construction-validation invariants are the guard and the 78 promoted tests are
the executable proof (source scans additionally prove the module contains no
file-write/subprocess/network/version-control/clock token and no
proposal-generation surface). Secondary risk — mistaking this slice for
self-modification capability — is structurally excluded: the payload is inert
data, `PROMOTED` is a decision record, and adoption stays with ordinary
repository governance. **Rollback:** ordinary Git revert of the merged W13
change. No deployment, network side effect, or data migration is permitted in
this slice.

## Completion state (filled)

`WAITING_FOR_ARCHITECT`. No merge, no PR creation, no successor Work Order,
no W14 dispatch, no canonical-state modification. W13 completion requires the
Architect gate, actual Git merge, and canonical reconciliation recording the
W13 merge and the next frontier. Corrections stay on the same branch.
