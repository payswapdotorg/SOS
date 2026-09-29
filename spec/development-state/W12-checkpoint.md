# W12 Implementation Checkpoint (first bounded slice)

**Work Order:** `spec/work-orders/W12-optimization-loop.md` (frozen, authoritative)
**State:** `WAITING_FOR_ARCHITECT` (review iteration 1)
**Branch:** `work/w12-optimization-loop` (from live `main`)
**Base SHA (worker-branch cut point, live `main` at W12 dispatch):**
`e3a97b895ca7f6cc7206a50bde45b2b55c554195` — the dispatch/reconciliation
commit "Reconcile W11 completion and dispatch W12 optimization-loop slice",
one commit after the W11 merge `aae251813d31f5b85e005d4bff94462a84c440df`
recorded in the Work Order header (deviation note 2 below).
**Exact implementation head (contract code, exports, tests):**
`cba274710ba3c76a883edbf4a91f836b57279e83`
**Exact branch tip:** the commit that carries this checkpoint plus
`docs/implementation/W12-OPTIMIZATION-LOOP-DESIGN.md` (documentation-only
delta from the implementation head above; a commit cannot embed its own SHA —
the authoritative review head is recorded in the worker report
`/home/z/replay2/scripts/worker-reports/99-A-report.md`). The verification
outputs below were re-run at the tip.

## Dependency proof

W3 merged `6541441bb706ef1f27b2c38b9eb930433641b14b`, W4 merged
`26060db57c24ba8b36315c1005466046810c5163`, W5 merged
`2bfd0f89da129c6b3347d88b0d8da1b79dd04127`, W6 merged
`b5171f70ca5ce85ca0be07cfdb3abf034c03c32f`, W7 merged
`25f663cf444f92b3190074a9119619cbc53e9ece`, W8 merged
`65b84058aa204b3749e45b7e21ae433a4b138d83`, W9 merged
`203cfb7590bd25244cabf3cc7299dd192b00948d`, W11 merged
`aae251813d31f5b85e005d4bff94462a84c440df` (all per
`spec/development-state/implementation-state.json` at the base commit
`e3a97b8`, status `W12_DISPATCHED`, frontier `[W12]`). The Work Order's
stated dependency set (W3–W9, W11 optional seam) is therefore complete in
the branch ancestry; the base `e3a97b8` is itself a descendant of the W11
merge. No unmerged sibling branch was treated as a dependency.

## Scope implemented (exactly the five allowed files)

- `src/sos/optimization.py` (NEW, 1868 lines): the governed orchestrator —
  `OptimizationContractError(ModelValidationError)`; `IterationOutcome` +
  frozen transition table + `validate_iteration_transition`;
  `AuthorizationResolution`/`PendingAuthorization` (the explicit ASK pause,
  never auto-approved); `PromotionClass`/`LoopPromotion`; `LoopIteration`;
  `LoopStopReason`/`LoopStop`; `OptimizationLoop` (typed,
  construction-validated, content-addressed, bounded);
  `SimulatedObservation` + `ExperimentSimulatorPort` (injected deterministic
  evaluator); `governed_experiment` (W7-before-W8 construction gate);
  `apply_promotion` (PromotionGate + W9-ACT required, bounded rollback for
  DEPLOY class); `dispatch_deployment` (W11 seam); the W4 verbatim evidence
  helper; `OptimizationRun` (full explainability chain, chain-validated);
  `run_optimization_loop` (the deterministic bounded model-only pipeline).
- `src/sos/__init__.py` (MODIFIED, +20 lines): W12 exports only (18 names);
  zero other changes.
- `tests/test_w12_optimization_loop.py` (NEW, 1263 lines): 33 deterministic
  offline tests (30 functions, one parametrized over the four non-SUCCESS
  truth states) covering the full Work-Order required regression list
  one-to-one; stub simulator and stub deploy provider are test-local
  injected port objects.
- `docs/implementation/W12-OPTIMIZATION-LOOP-DESIGN.md` (NEW): design
  reconciled to the implementation, WO-traceable (C1–C10 + regression-list
  mapping).
- `spec/development-state/W12-checkpoint.md` (NEW): this file.

Zero modifications to W1–W11 sources, frozen specs, roadmap, or Work Order
machinery (verified: `git diff --name-only e3a97b8..HEAD` lists exactly the
three code/test files of the implementation commit plus the two docs files
of this commit).

## Acceptance criteria → implementation → test mapping

Full mapping with test names in
`docs/implementation/W12-OPTIMIZATION-LOOP-DESIGN.md` §11 (C1–C10) and §12
(the WO's required regression coverage list, one-to-one). Summary:

| Criterion | Implementation anchor | Primary tests |
|---|---|---|
| C1 composed-authority integrity | import-identity reuse; `OptimizationRun.validate` chain check; candidate↔recovered-system binding | `test_w12_references_frozen_authorities_without_redefining`, `test_loop_record_enforces_terminal_outcomes_and_chain_consistency`, `test_loop_rejects_candidates_targeting_foreign_systems` |
| C2 W9 gate mechanics | three real W9 gates; inert `PendingAuthorization` (PENDING-only resolution) | `test_w9_ask_pauses_loop_with_explicit_pending_authorization_record`, `test_pending_authorization_can_never_auto_approve`, `test_w9_reject_refuses_the_iteration_and_the_loop_continues` |
| C3 W7→W8 ordering | `governed_experiment` PASS + exact chain, W8-revalidated | `test_governed_experiment_requires_w7_pass_bound_to_exact_chain`, `test_loop_records_assurance_not_passed_without_any_experiment` |
| C4 governed promotion/rollback | `apply_promotion` + `LoopPromotion` DEPLOY rules; ROLLBACK-state decision; typed stops | `test_promotion_requires_the_promotion_gate_decision`, `test_deploy_class_promotion_requires_a_bounded_rollback_path`, `test_stop_condition_fires_and_terminates_the_loop` |
| C5 verbatim W4 evidence | `_build_evidence` + `EvidenceGraph.ingest`, existing kinds only | `test_w4_evidence_appended_at_every_consequential_step` |
| C6 determinism and bounds | fixed bound; id-sorted dedup; clock-free; sha256 ids | `test_full_loop_happy_path_produces_governed_deterministic_record`, `test_identical_inputs_from_distinct_repositories_produce_identical_ids`, `test_max_iteration_bound_bounds_the_loop` |
| C7 distinction preservation | injective status→truth map; verbatim simulator states | `test_distinctions_preserved_through_the_loop` (×4), `test_simulated_observation_preserves_truthful_distinctions` |
| C8 model-only safety | no live/network/subprocess/clock; stub-provider seam | `test_no_successor_stage_or_live_execution_symbols`, `test_w11_seam_model_only_mode_without_providers` |
| C9 persistence round-trip | W1 `JsonModelStore`; no new persistence authority | `test_loop_record_round_trips_through_w1_json_store` |
| C10 bounded authority surface | W12 exports only; W1-anchored error; no successor symbols | `test_no_successor_stage_or_live_execution_symbols`, `test_w12_references_frozen_authorities_without_redefining` |

## Verification

```text
python3 -m pytest
python3 -m compileall -q src tests
```

Exact-head results (implementation head `cba2747`; re-run at the branch tip,
which adds documentation only — identical counts):

```text
$ python3 -m pytest
360 passed in 1.01s
$ python3 -m compileall -q src tests
(exit code 0; no output — clean)
```

Exact pass count: **360** (0 failed, 0 errors, 0 skipped) = 327 baseline
(verified at base `e3a97b8` before any work) + 33 new W12 tests. Duration is
environment-dependent; counts are exact. Fully offline: no network, no
provider, no wall clock.

## Honest deviations

1. **Session timeout / continuation.** The original Worker A3 session
   committed the implementation (`cba2747`) but timed out before writing
   the docs and delivering. This continuation session (same Task 99-A,
   Worker A3 continuation) verified the inherited state first
   (head `cba2747` exactly, 360 passed, compileall clean, no working-tree
   changes beyond untracked `__pycache__`), then wrote ONLY the two
   documentation files and delivered. The implementation and tests were
   not modified: `git diff cba2747..HEAD` is exactly the two docs files.
2. **Base SHA vs Work Order header.** The WO records the base as the W11
   merge commit `aae2518` ("exact base recorded at dispatch"); live `main`
   had advanced by exactly one commit — the W11-completion reconciliation
   and W12-dispatch commit `e3a97b8` — when the worker branch was cut. The
   branch base is therefore `e3a97b8` (a descendant of `aae2518`); all WO
   dependencies are in the ancestry. No WO semantics changed by the
   intervening commit (it is state documentation only).
3. **"W3 `RecoveryResult` id" (required outcome 1).** W3's
   `RecoveryResult` has no id field of its own; the loop binds the
   recovered system by the W3 identity pair `system_state.id` +
   `revision` (recorded as `recovered_state_ref` / `recovered_revision`,
   plus base-graph id/revision and provenance revision), all
   chain-checked. Recorded as design resolution §13.1.
4. **Two commits** (implementation `cba2747` + this documentation commit)
   instead of one, following the W10/W11 convention so the checkpoint can
   record an exact implementation head SHA.

No other deviations from the envelope, Work Order, or architecture were
found: the required regression coverage list is covered one-to-one
(design §12), the five-file surface was respected, and no frozen or
W1–W11 file was touched.

## Known limitations

1. Composition/contract evidence only: the loop runs on fixture
   recovered-system models with injected stub evaluators (WO "Evaluation"
   section); real brownfield system ingestion stays out of this slice.
2. A paused loop has no in-slice resume path — resumption after human
   authorization is a fresh run under a fresh W9 policy decision (the
   pending record is deliberately inert; no resolution code path exists).
3. The W11 seam builds its per-dispatch registries from the loop's current
   chain records; cross-run registry persistence remains W11's known
   limitation.
4. Candidate ranking is deterministic-by-id (content-addressed order), not
   multi-objective value ranking — a governed later slice.

## Risk / rollback

**Risk:** loop-level authority leakage — a step that bypasses W7/W8/W9 or
records inferred evidence. The C1–C10 construction-validation invariants
are the guard; the 33 tests are the executable proof. **Rollback:** ordinary
Git revert of the merged W12 change. No deployment or data migration is
permitted in this slice.

## Completion state

`WAITING_FOR_ARCHITECT`. No merge, no push, no successor Work Order, no W13
dispatch, no canonical-state modification. W12 completion requires the
Architect gate, actual Git merge, and canonical reconciliation recording the
W12 merge and the next frontier. Corrections stay on this branch.
