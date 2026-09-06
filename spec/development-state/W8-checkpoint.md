# W8 Implementation Checkpoint

**Work Order:** `spec/work-orders/W8-experiment-promotion-rollback.md`
**State:** `WAITING_FOR_ARCHITECT` (review iteration 2)
**Branch:** `work/w8-experiment-promotion-rollback`
**Base SHA:** `7fefc148456167a4d7f8cd89675f5d32fe4e10bb`
**Reviewed head (iteration 1):** `69b68f9ad41ae5a242cc28ef5f4606df45fb1d80`
**Latest implementation SHA (iteration 2):** recorded as the PR `head.sha` (authoritative review head per `ARCHITECT-REVIEW-PROTOCOL §2`)

## Architect review (iteration 1) — four HIGH findings

Reviewed exact head `69b68f9ad41ae5a242cc28ef5f4606df45fb1d80`. Base matched
live main; five-file W8 surface; 164 tests + compileall; lifecycle direction
sound. Four HIGH findings blocked merge; all are resolved in iteration 2 on the
same PR.

### SOS-W8-F01 — HIGH — exact revision/provenance binding incomplete — RESOLVED

Finding: `Experiment.validate(known_assurance=…)` checked candidate_id,
assurance_result_id, and base_graph_id but not `base_graph_revision` or
`provenance_revision` against the W7 result. A caller could construct an
experiment with mismatched revision/provenance and pass validation.

Resolution: `Experiment.validate` now enforces exact equality of
`base_graph_revision` and `provenance_revision` against the originating
`AssuranceResult` (in addition to candidate_id, assurance_result_id,
base_graph_id). Regression tests: `test_experiment_rejects_mismatched_base_graph_revision`,
`test_experiment_rejects_mismatched_provenance_revision`.

### SOS-W8-F02 — HIGH — rollback eligibility satisfied by arbitrary string — RESOLVED

Finding: `rollback_ref` was only a string; `evaluate_experiment()` set
`recovery_satisfied = bool(rollback_ref.strip())` — any non-empty string
satisfied C7 without validating a `RollbackPath`.

Resolution: `evaluate_experiment` now accepts a caller-supplied `rollback_path:
RollbackPath | None`; recovery is satisfied only when the `RollbackPath` validates
against `known_evidence` AND all its evidence records are SUCCESS, or when a
documented `containment_policy_ref` is present. An arbitrary `rollback_ref` string
no longer satisfies recovery. Regression tests: `test_bogus_rollback_ref_cannot_satisfy_recovery`,
`test_validated_rollback_path_satisfies_recovery`, `test_non_success_rollback_evidence_blocks_promotion`.

### SOS-W8-F03 — HIGH — promotion can accept unrelated evaluation — RESOLVED

Finding: `PromotionGate.evaluate()` never validated `evaluation.experiment_id ==
experiment.id`; a promotion decision could consume an unrelated evaluation.

Resolution: `PromotionGate.evaluate` now raises `ModelValidationError` if
`evaluation.experiment_id != experiment.id`. Regression test:
`test_promotion_gate_rejects_evaluation_not_bound_to_experiment`.

### SOS-W8-F04 — HIGH — evaluation scope not explicit enough — RESOLVED

Finding: `evaluate_experiment()` iterated every entry in `known_evidence`, not a
declared set; eligibility depended on unrelated records; unknown evidence ids were
not rejected because there was no declared reference set.

Resolution: `evaluate_experiment` now accepts an explicit `evidence_refs:
tuple[str, …]` parameter; only those records participate in promotion gating.
Each is validated against `known_evidence`; unknown refs are treated as UNKNOWN
and block promotion. Unrelated evidence in `known_evidence` is ignored. Regression
tests: `test_unrelated_evidence_does_not_affect_promotion`,
`test_unknown_referenced_evidence_id_blocks_promotion`.

## Dependency proof

W7 is merged on `main` as `25f663cf444f92b3190074a9119619cbc53e9ece` (true merge:
parents `7973660` + `6eac75d`). W6 merged as `b5171f7…`, W5 `2bfd0f8…`, W3
`6541441…`, W4 `26060db…`, W2 `587201d3…`. No unmerged sibling dependency is used.
W8 depends authoritatively only on W7 (per roadmap); W9 remains BLOCKED until W8
is authoritatively merged.

## Scope implemented

- `ExperimentMode` (SHADOW/CANARY/CONTROLLED) + `ExperimentState` (PLANNED/READY/
  RUNNING/STOPPED/COMPLETED/FAILED/ROLLED_BACK);
- `StopCondition` (name, threshold, metric) — explicit hard-stop conditions that
  cannot be optimized away (C5);
- `RollbackPath` (reference, evidence_ids, detail, recovered) — governed rollback/
  recovery reference backed by evidence; `with_recovered()` for explicit recovery
  state transitions;
- `Experiment` (frozen, construction-validated, content-addressed SHA-256 id) —
  binds exact candidate id + assurance result id + base graph id/revision +
  provenance revision + W1 traceability; bounded mode/scope/window/success-criteria/
  stop-conditions/rollback-ref/containment-policy-ref (C1/C3);
- `transition_experiment(exp, new_state, known_assurance=…)` — validated lifecycle
  state machine (C8): invalid transitions rejected; entry assurance gate (C2) —
  only PASS assurance can enter READY/RUNNING; rollback cannot bypass intermediate
  semantics;
- `ExperimentEvaluation` (frozen, content-addressed id) — truthful evidence
  evaluation preserving W4 evidence ids + truth states (C4); `promotion_eligible`
  requires evaluation_success + all evidence SUCCESS + no hard stop + rollback/
  containment satisfied; `stopped` for hard-stop conditions (C5); objectives
  preserved from W7 assurance (C9, no scalar);
- `evaluate_experiment(exp, known_evidence=…, evaluation_success=…, stop_trigger=…,
  known_assurance=…)` — deterministic, bounded evaluation function;
- `PromotionGate.evaluate(exp, ev, known_assurance=…)` → `PromotionDecision` —
  explicit promotion gate: promoted only when assurance PASS + evaluation
  promotion-eligible; no implicit promotion from completion (C6);
- JSON round-trip via the existing W1 `JsonModelStore` (no new persistence
  authority) (C11);
- W8 invariant tests and repository-resident evidence.

## Explicit exclusions

No autonomy/ASK/user-authorization/decision execution (W9); no personalization/
platform adapters (W10); no greenfield/brownfield realization (W11/W12); no
self-evolution/meta-adaptation (W13); no second evidence/cause/architecture
authority; no scalarized architecture quality as the sole promotion authority;
no LLM-derived proof or confidence-only promotion; no production deployment
integrations or provider-specific execution semantics.

## Requirement → implementation → test mapping

| Requirement | Criterion | Implementation | Tests |
|---|---|---|---|
| R23, R24 | C1 exact candidate/assurance binding | `Experiment` binds candidate+assurance+graph+revision+traceability; mismatch rejected | `test_experiment_binds_to_exact_candidate_assurance_and_graph`, `test_experiment_rejects_candidate_assurance_mismatch` |
| R13, R21 | C2 entry assurance gate | `transition_experiment` rejects non-PASS → READY/RUNNING | `test_non_pass_assurance_cannot_enter_executable_experiment` (×3), `test_pass_assurance_can_enter_executable_experiment` |
| R24 | C3 bounded experiment model | mode/scope/window/stop-conditions validated | `test_experiment_mode_scope_window_are_explicit_and_validated`, `test_experiment_rejects_empty_scope`, `test_experiment_rejects_empty_stop_conditions` |
| R9, R21 | C4 truthful evidence evaluation | evidence truth states preserved; UNKNOWN can't produce PASS | `test_evaluation_preserves_evidence_ids_and_truth_states`, `test_unknown_evidence_cannot_produce_promotion_pass` |
| R13, R21 | C5 hard stop / safety conditions | stop_trigger fires; not offset by objectives | `test_hard_stop_condition_stops_experiment_and_cannot_be_offset_by_objectives` |
| R14 | C6 promotion gate | explicit `PromotionGate.evaluate`; no implicit promotion | `test_promotion_requires_successful_evaluation`, `test_no_implicit_promotion_from_completion` |
| R14 | C7 rollback / containment | `RollbackPath` evidence-backed; missing blocks promotion; containment exception allows | `test_rollback_requires_valid_governed_recovery_evidence`, `test_missing_rollback_blocks_promotion_eligibility`, `test_documented_containment_exception_allows_promotion_eligibility` |
| R24 | C8 lifecycle state machine | validated transitions; invalid rejected; rollback can't bypass | `test_invalid_state_transitions_rejected`, `test_valid_lifecycle_progression`, `test_rollback_cannot_bypass_intermediate_semantics` |
| R12, R15 | C9 multi-objective preservation | objectives threaded from W7 assurance; no scalar | `test_experiment_preserves_objectives_without_scalar_authority` |
| R24 | C10 deterministic bounded evaluation | `evaluate_experiment` pure function | `test_evaluation_is_deterministic` |
| R24 | C11 persistence + traceability | W1 `JsonModelStore` round-trip | `test_experiment_round_trips_through_json` |
| R24 | C12 bounded authority surface | no W9+ symbols; no W7 authority re-export | `test_w8_introduces_no_w9_plus_symbols`, `test_w8_does_not_redefine_assurance_authority` |

## Verification

CI workflow: `.github/workflows/test.yml` (runs on push and PR).

Deterministic verification commands (run from repo root):

```text
python -m pytest
python -m compileall -q src tests
```

Exact-head results (recorded in the PR description at push time):

```text
$ python -m pytest
172 passed in 0.45s
  tests/test_w1_models.py  ........   (8)
  tests/test_w2_graph.py   ........   (8)
  tests/test_w3_recovery.py .................... (20)
  tests/test_w4_evidence.py .........................  (25)
  tests/test_w5_causal.py  ..........................  (26)
  tests/test_w6_candidates.py ........................  (24)
  tests/test_w7_assurance.py ............................  (28)
  tests/test_w8_experimentation.py .................................  (33)
$ python -m compileall -q src tests
(clean, no syntax errors)
```

Iteration 1 (head `69b68f9`) was 164 tests (25 W8); iteration 2 adds 8 F01-F04
regression tests -> 172 total (33 W8). CI on iteration 1 ran `pytest` -> `success`;
iteration 2 CI re-runs on the corrected head.

## Known limitations

1. **Experiment evaluation success is caller-supplied** — `evaluation_success`
   is a boolean parameter, not computed from evidence. Real experiment outcome
   evaluation (comparing observed metrics against success criteria) is later
   work; W8 represents the lifecycle/evaluation boundary.
2. **Stop conditions are triggered by caller-supplied `stop_trigger` names** —
   the evaluation does not parse metric values against thresholds automatically;
   the caller names which stop condition fired. Automated threshold comparison is
   later work.
3. **No live deployment integration** — W8 models lifecycle semantics; it does
   not execute deployments, canaries, or shadow rollouts. Provider-specific
   execution belongs to later platform/context work (W10).
4. **Rollback recovery is a state transition, not an execution** — `RollbackPath.
   with_recovered(True)` marks the recovery state; W8 does not execute rollback
   (it models the lifecycle).
5. **Non-authority** — W8 does not implement W9 autonomy/ASK. Promotion is an
   explicit decision, not an autonomous action.
6. **No production writes / network / provider dependency** — deterministic tests
   require no external system.

## Risk / rollback

- **Risk:** semantic, potentially high — W8 becomes the lifecycle boundary before
  autonomy. The implementation is deterministic, explicit, traceable, and
  provider-neutral. No production mutation.
- **Rollback:** ordinary Git revert of the W8 PR. No running service, no data
  migration.

## Architect disposition requested

Review the exact PR head (iteration 2) and CI result against the W8 Work Order
and the four iteration-1 findings (SOS-W8-F01 through SOS-W8-F04 — all
resolved). On approval, merge the reviewed head and reconcile canonical state
to W9 eligibility (W9 depends on W7 + W8; W7 is complete). Worker state:
`WAITING_FOR_ARCHITECT`. No merge, no self-approval, no successor Work Order
creation by this session.
