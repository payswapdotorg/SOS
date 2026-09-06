# W9 Implementation Checkpoint

**Work Order:** `spec/work-orders/W9-autonomy-ask.md`
**State:** `WAITING_FOR_ARCHITECT`
**Branch:** `work/w9-autonomy-ask`
**Base SHA:** `be97db73fc02d92bc344c61b69975737984f2465`
**Latest implementation SHA:** recorded as the PR `head.sha` (authoritative review head per `ARCHITECT-REVIEW-PROTOCOL §2`)

## Dependency proof

W7 is merged as `25f663cf444f92b3190074a9119619cbc53e9ece` and W8 is merged as
`65b84058aa204b3749e45b7e21ae433a4b138d83` (true merges). No unmerged sibling
dependency is used. W9 depends authoritatively on W7 + W8 (both complete, per
roadmap); W10 remains BLOCKED until W9 is authoritatively merged.

## Scope implemented

- `AutonomyDecisionState` (GATHER_EVIDENCE/EXPERIMENT/ACT/ASK/REJECT/ROLLBACK) —
  explicit decision states (C2);
- `PolicyCeiling` (max_risk, max_blast_radius, require_reversible, min_confidence,
  require_human_approval_for_act) — bounded policy ceilings (C1, C6);
- `AutonomyRequest` (frozen, construction-validated) — structured, bounded,
  traceable autonomy policy with declared `allowed_actions`; cannot authorize
  beyond declared scope/ceilings (C1);
- `AutonomyDecision` (frozen, construction-validated, content-addressed SHA-256 id)
  — deterministic, explainable decision with rationale, reasons, evidence ids,
  assurance/experiment/promotion/policy references, and W1 traceability (C9);
- `evaluate_autonomy(...)` — deterministic evaluation engine:
  - C1: action must be in `policy.allowed_actions`; else REJECT;
  - C3: ASK when `require_human_approval_for_act=True` and no human authority present;
  - C4: ACT requires W7 PASS assurance + W8 promoted PromotionDecision; non-PASS → REJECT;
  - C5: UNKNOWN/FAILED evidence → GATHER_EVIDENCE; confidence alone cannot authorize;
  - C6: blast radius exceeding ceiling → ASK;
  - C8: ROLLBACK requires governed RollbackPath with SUCCESS evidence; else ASK;
  - EXPERIMENT action deferred to W8 lifecycle;
  - GATHER_EVIDENCE action authorized directly by policy;
- JSON round-trip via the existing W1 `JsonModelStore` (no new persistence
  authority) (C11);
- W9 invariant tests and repository-resident evidence.

## Explicit exclusions

No platform adapters/personalization (W10); no greenfield/brownfield realization
(W11/W12); no self-evolution (W13); no second evidence/cause/architecture authority;
no scalarized quality as sole authority; no LLM-derived proof or confidence-only
authorization; no mission/value/constitution revision authority; no autonomous
bypass of human authority or ASK; no production deployment integrations.

## Requirement → implementation → test mapping

| Requirement | Criterion | Implementation | Tests |
|---|---|---|---|
| R15, R24 | C1 explicit autonomy policy | `AutonomyRequest` + `PolicyCeiling` | `test_policy_is_structured_and_bounded`, `test_policy_cannot_authorize_beyond_decled_scope` |
| R16, R24 | C2 explicit state machine | `AutonomyDecisionState` + `evaluate_autonomy` | `test_act_requires_promotion_and_policy_authorization`, `test_non_pass_assurance_cannot_act` |
| R16, R22 | C3 human authority / ASK gate | ASK when human approval required + not present | `test_unresolved_authority_routes_to_ask`, `test_human_authority_present_allows_act` |
| R13, R14 | C4 assurance/promotion boundary | ACT requires assurance PASS + promotion | `test_act_requires_promotion_and_policy_authorization`, `test_non_pass_assurance_cannot_act`, `test_confidence_alone_cannot_authorize` |
| R21 | C5 truthful uncertainty gate | UNKNOWN evidence → GATHER_EVIDENCE | `test_unknown_evidence_cannot_authorize` |
| R15, R18 | C6 bounded action scope | blast radius > ceiling → ASK | `test_blast_radius_exceeding_ceiling_routes_to_ask` |
| R23 | C7 evidence/traceability chain | decision records evidence ids + refs + W1 traceability | `test_decision_records_evidence_and_traceability` |
| R14 | C8 rollback/containment integrity | ROLLBACK requires governed RollbackPath | `test_rollback_requires_governed_recovery`, `test_rollback_with_governed_recovery_can_act` |
| R23 | C9 explainable decision record | rationale + reasons | `test_decision_has_rationale_and_reasons` |
| R24 | C10 deterministic bounded evaluation | `evaluate_autonomy` pure function | `test_evaluation_is_deterministic` |
| R24 | C11 persistence + traceability | W1 `JsonModelStore` round-trip | `test_decision_round_trips_through_json` |
| R24 | C12 bounded authority surface | no W10+ symbols; no W7/W8 re-export | `test_w9_introduces_no_w10_plus_symbols`, `test_w9_does_not_redefine_assurance_or_experiment_authority` |

## Verification

```text
python -m pytest
python -m compileall -q src tests
```

Exact-head results:

```text
$ python -m pytest
196 passed in 0.50s
  tests/test_w9_autonomy.py .................  (17)
$ python -m compileall -q src tests
(clean, no syntax errors)
```

## Known limitations

1. **Autonomy policy is caller-supplied** — W9 evaluates against a supplied
   `AutonomyRequest`; it does not infer or synthesize policy. Policy authoring
   is a human/governance task.
2. **Confidence is not calibrated** — `PolicyCeiling.min_confidence` is a
   threshold parameter, but W9 does not compute calibrated confidence. Calibrated
   confidence is reserved for later work.
3. **No live execution** — W9 produces decisions, not executions. ACT means
   "authorized to act" — the actual action execution belongs to W10+ platform
   adapters.
4. **No personalization** — W9 does not condition policies by user/context.
5. **Non-authority** — W9 does not bypass human authority; ASK is mandatory when
   authority is ambiguous.

## Risk / rollback

- **Risk:** high semantic — W9 introduces the autonomy boundary before platform
  realization. The implementation is explicit, bounded, reversible, human-
  authority preserving, deterministic, and provider-neutral.
- **Rollback:** ordinary Git revert of the W9 PR. No running service, no data
  migration.

## Architect disposition requested

Review the exact PR head and CI result against the W9 Work Order. On approval,
merge the reviewed head and reconcile canonical state to W10 eligibility (W10
depends on W2 + W9; both complete). Worker state: `WAITING_FOR_ARCHITECT`. No
merge, no self-approval, no successor Work Order creation by this session.
