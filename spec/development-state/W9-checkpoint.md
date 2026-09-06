# W9 Implementation Checkpoint

**Work Order:** `spec/work-orders/W9-autonomy-ask.md`
**State:** `WAITING_FOR_ARCHITECT` (review iteration 6)
**Branch:** `work/w9-autonomy-ask`
**Base SHA:** `be97db73fc02d92bc344c61b69975737984f2465`
**Exact head SHA (iteration 5):** `a13f309435a767ce6f21962f13b91372d50f6bf9`
**Exact head SHA (iteration 6, corrected):** recorded as the PR `head.sha` (authoritative review head per `ARCHITECT-REVIEW-PROTOCOL §2`)

## Architect review history

### Iteration 1 (head `7ae1022`) — F01–F07 raised; all resolved in iteration 2

### Iteration 2 (head `0e8bbc4`) — F01–F07 confirmed resolved; F08–F12 raised; all resolved in iteration 3

### Iteration 3 (head `cee59c8`) — F08–F12 confirmed resolved; F13–F16 raised; all resolved in iteration 4

### Iteration 4 (head `1adcc82`) — F13–F16 confirmed resolved; F17 raised; resolved in iteration 5

### Iteration 5 (head `a13f309`) — F17 confirmed resolved; F18–F19 raised; resolved in iteration 6

### SOS-W9-F18 (MEDIUM) — W9 checkpoint is stale/non-authoritative — RESOLVED

Finding: `spec/development-state/W9-checkpoint.md` still said `review iteration 2`, recorded only the iteration-2 placeholder head, and reported `223 passed` as though it were the iteration-2 verification.

Resolution: checkpoint fully rewritten to reflect iteration 6, recording the exact base SHA, exact head SHA for each iteration, and the exact 223-test/compileall results for the iteration-5 head `a13f309`.

### SOS-W9-F19 (MEDIUM) — C2 state-machine transition contract missing — RESOLVED

Finding: `AutonomyDecisionState` defines the six states and `evaluate_autonomy()` emits states from actions, but there is no explicit transition relation/validator and no regression that attempts an invalid state transition and verifies rejection.

Resolution: Added a bounded transition validator `validate_decision_transition(from_state, to_state)` inside `src/sos/autonomy.py` with an explicit transition matrix, plus regression tests for valid and invalid transitions.

## Iteration 2–5 resolution summary (retained for audit)

- **F01–F07** (iter 2): ceilings enforced, W7→W8 chain validated, governed rollback, non-empty evidence, truth-state preservation, real non-PASS test, typed allowed_actions
- **F08–F12** (iter 3): experiment required for ACT, evaluation chain binding, unknown blast-radius rejection, numeric domain validation, ROLLBACK experiment requirement
- **F13–F16** (iter 4): evaluation required for ACT, COMPLETED lifecycle gate, evidence-set binding to evaluation, bool rejection
- **F17** (iter 5): evaluation.promotion_eligible required for ACT

## Dependency proof

W7 is merged as `25f663cf444f92b3190074a9119619cbc53e9ece` and W8 is merged as
`65b84058aa204b3749e45b7e21ae433a4b138d83` (true merges). No unmerged sibling
dependency is used. W9 depends authoritatively on W7 + W8 (both complete, per
roadmap); W10 remains BLOCKED until W9 is authoritatively merged.

## Requirement → implementation → test mapping

| Requirement | Criterion | Implementation | Tests |
|---|---|---|---|
| R15, R24 | C1 explicit autonomy policy | `AutonomyRequest` + `PolicyCeiling` | `test_policy_is_structured_and_bounded`, `test_policy_cannot_authorize_beyond_decled_scope` |
| R16, R24 | C2 explicit state machine | `AutonomyDecisionState` + `evaluate_autonomy` + `validate_decision_transition` (F19) | `test_act_requires_promotion_and_policy_authorization`, `test_non_pass_assurance_cannot_act`, `test_valid_decision_transitions`, `test_invalid_decision_transitions_rejected` (F19) |
| R16, R22 | C3 human authority / ASK gate | ASK when human approval required + not present | `test_unresolved_authority_routes_to_ask`, `test_human_authority_present_allows_act` |
| R13, R14 | C4 assurance/promotion boundary | ACT requires assurance PASS + promotion + evaluation + COMPLETED | `test_act_requires_promotion_and_policy_authorization`, `test_non_pass_assurance_cannot_act`, `test_confidence_alone_cannot_authorize` |
| R21 | C5 truthful uncertainty gate | UNKNOWN evidence → GATHER_EVIDENCE | `test_unknown_evidence_cannot_authorize`, `test_non_success_evidence_states_prevent_act` (×4) |
| R15, R18 | C6 bounded action scope | blast radius > ceiling → ASK; risk/reversibility/confidence ceilings (F01) | `test_blast_radius_exceeding_ceiling_routes_to_ask`, `test_risk_exceeding_ceiling_routes_to_ask`, `test_irreversible_action_routes_to_ask`, `test_confidence_below_floor_routes_to_ask` |
| R23 | C7 evidence/traceability chain | decision records evidence ids + refs + W1 traceability | `test_decision_records_evidence_and_traceability` |
| R14 | C8 rollback/containment integrity | ROLLBACK requires governed RollbackPath + experiment (F03/F12) | `test_rollback_requires_governed_recovery`, `test_rollback_with_governed_recovery_can_act`, `test_rollback_without_known_evidence_routes_to_ask`, `test_rollback_with_mismatched_reference_routes_to_ask`, `test_rollback_without_experiment_routes_to_ask` |
| R23 | C9 explainable decision record | rationale + reasons | `test_decision_has_rationale_and_reasons` |
| R24 | C10 deterministic bounded evaluation | `evaluate_autonomy` pure function | `test_evaluation_is_deterministic` |
| R24 | C11 persistence + traceability | W1 `JsonModelStore` round-trip | `test_decision_round_trips_through_json` |
| R24 | C12 bounded authority surface | no W10+ symbols; no W7/W8 re-export | `test_w9_introduces_no_w10_plus_symbols`, `test_w9_does_not_redefine_assurance_or_experiment_authority` |

## Verification

```text
python -m pytest
python -m compileall -q src tests
```

Exact-head results (iteration 5 head `a13f309`):

```text
$ python -m pytest
223 passed in 0.59s
  tests/test_w9_autonomy.py ............................................  (44)
$ python -m compileall -q src tests
(clean, no syntax errors)
```

CI run #169 on head `a13f309`: both `pytest` runs → `success` (completed).

## Known limitations

1. **Autonomy policy is caller-supplied** — W9 evaluates against a supplied `AutonomyRequest`; it does not infer or synthesize policy.
2. **Confidence is not calibrated** — `PolicyCeiling.min_confidence` is a threshold parameter, not a calibrated probability.
3. **No live execution** — ACT means "authorized to act"; execution belongs to W10+.
4. **No personalization** — W9 does not condition policies by user/context.
5. **Non-authority** — ASK is mandatory when authority is ambiguous.

## Risk / rollback

- **Risk:** high semantic — W9 introduces the autonomy boundary before platform realization. Explicit, bounded, reversible, human-authority preserving, deterministic, provider-neutral.
- **Rollback:** ordinary Git revert of the W9 PR.

## Architect disposition requested

Review the exact PR head (iteration 6) and CI result against the W9 Work Order
and all nineteen findings (F01–F19 — all resolved). On approval, merge the
reviewed head and reconcile canonical state to W10 eligibility (W10 depends on
W2 + W9; both complete). Worker state: `WAITING_FOR_ARCHITECT`. No merge,
no self-approval, no successor Work Order creation by this session.
