# W8 Experimentation + Promotion / Rollback Design

**Status:** IMPLEMENTED — REVIEW REQUIRED
**Work Order:** `spec/work-orders/W8-experiment-promotion-rollback.md`
**Dependencies:** W7 merged as `25f663c…`; W6 `b5171f7…`; W5 `2bfd0f8…`; W3 `6541441…`; W4 `26060db…`; W2 `587201d3…`

W8 consumes non-authorizing W7 assurance results and defines deterministic
experiment, evaluation, promotion-gating, containment, and rollback state
semantics without becoming a platform-specific deployment adapter or an autonomy
authority (architecture §§4.7–4.9, 9, 13).

## Governing principle

Only a W7 assurance result with status PASS can enter an executable experiment
state. Promotion is an explicit gated decision, not implicit from experiment
completion. Rollback/containment is required for promotion eligibility. W8 owns
experimentation/promotion/rollback lifecycle only — no W9 autonomy/ASK, no W10
platform/personalization, no W7 authority re-export.

## Experiment model

`Experiment` (frozen, construction-validated, content-addressed id) binds to the
exact candidate id, assurance result id, base graph id/revision, provenance
revision, and W1 traceability. Bounded: explicit `ExperimentMode` (SHADOW/
CANARY/CONTROLLED), scope, observation window, success criteria, stop conditions,
rollback reference, and optional containment policy reference.

## Entry assurance gate (C2)

`transition_experiment(exp, READY, known_assurance=ar)` rejects transitions to
executable states (READY/RUNNING) when the assurance status is not PASS.
FAIL/UNKNOWN/BLOCKED remain distinguishable and cannot become execution-ready.

## Lifecycle state machine (C8)

Validated transitions: PLANNED→READY→RUNNING→{COMPLETED|STOPPED|FAILED}→
ROLLED_BACK. Invalid direct transitions are rejected (e.g. PLANNED→COMPLETED).
Rollback cannot bypass intermediate semantics (PLANNED→ROLLED_BACK rejected).

## Truthful evidence evaluation (C4)

`evaluate_experiment(exp, known_evidence=…)` preserves W4 evidence ids + truth
states. UNKNOWN/FAILED/UNAVAILABLE evidence cannot produce promotion eligibility.
`evaluation_success` is caller-supplied (not inferred from narrative).

## Hard stop conditions (C5)

A fired `stop_trigger` stops the experiment and cannot be offset by favorable
objectives — `stopped=True` and `promotion_eligible=False` regardless of evidence.

## Promotion gate (C6)

`PromotionGate.evaluate(exp, ev, known_assurance=ar)` returns an explicit
`PromotionDecision`: promoted only when assurance is PASS + evaluation is
promotion-eligible. No implicit promotion from completion, no confidence-only
shortcut.

## Rollback / containment (C7)

`RollbackPath` (reference, evidence_ids, detail, recovered) validates against
known evidence. Promotion eligibility requires rollback evidence or a documented
containment exception (`containment_policy_ref`). Missing both blocks promotion.

## Multi-objective preservation (C9)

W6 objectives are threaded from the W7 assurance result through the evaluation
(`known_assurance.objectives`). No scalar quality score.

## Persistence (C11)

W8 records round-trip through the existing W1 `JsonModelStore` (no new
persistence authority).

## Bounded authority surface (C12)

`src/sos/experimentation.py` exports only W8 symbols. No W9+ (autonomy, ASK,
platform, personalization, realization, self-evolution) symbols. Does not
re-export W7 assurance authority.
