# W9 Autonomy + ASK + Human Authority Design

**Status:** IMPLEMENTED — REVIEW REQUIRED
**Work Order:** `spec/work-orders/W9-autonomy-ask.md`
**Dependencies:** W7 merged `25f663c`; W8 merged `65b8405`

W9 makes autonomy explicit, policy-governed, reversible, explainable, and
subordinate to human authority (architecture §§4.8–4.9, 5, 12–13).

## Governing principle

Autonomy is policy-governed: actions may only be considered within the policy's
declared `allowed_actions` and bounded by `PolicyCeiling` scope/risk/blast-radius/
reversibility constraints. W7 PASS is **non-authorizing** — it cannot be treated
as an authorization token. ACT requires W7 PASS + W8 promotion + W9 policy
authorization. `ASK` is mandatory when authority is ambiguous or scope is unsafe.

## Autonomy policy

`AutonomyRequest` (frozen, construction-validated) carries `allowed_actions`
(declared `DecisionAction` tuple), `PolicyCeiling` (max_risk, max_blast_radius,
require_reversible, min_confidence, require_human_approval_for_act), and W1
traceability. Cannot authorize beyond its declared scope/ceilings (C1, C6).

## Decision state machine

`AutonomyDecisionState` = `GATHER_EVIDENCE | EXPERIMENT | ACT | ASK | REJECT |
ROLLBACK`. `evaluate_autonomy` produces a deterministic `AutonomyDecision` with:

- `ACT`: all gates passed (policy allows + assurance PASS + promotion promoted +
  evidence SUCCESS + ceilings satisfied + human authority present if required);
- `ASK`: authority ambiguous, scope unsafe, or policy boundary unresolved;
- `REJECT`: explicit policy rejection (action not allowed);
- `ROLLBACK`: rollback with governed recovery evidence;
- `GATHER_EVIDENCE`: evidence insufficient (UNKNOWN/missing);
- `EXPERIMENT`: deferred to W8 lifecycle.

## Key invariants

- **C3 (ASK gate):** when `require_human_approval_for_act=True` and no human
  authority is present → ASK;
- **C4 (assurance/promotion boundary):** W7 PASS alone does not authorize ACT;
  W8 promotion is also required; non-PASS assurance → REJECT;
- **C5 (truthful uncertainty):** UNKNOWN/FAILED evidence → GATHER_EVIDENCE;
  confidence alone cannot authorize;
- **C6 (bounded scope):** blast radius exceeding ceiling → ASK;
- **C8 (rollback integrity):** ROLLBACK requires governed `RollbackPath` with
  SUCCESS evidence; without it → ASK;
- **C9 (explainability):** every decision has rationale + reasons + evidence ids
  + assurance/experiment/promotion/policy references + W1 traceability;
- **C12 (bounded surface):** no W10+ symbols; no W7/W8 authority re-export.

## Serialization

W9 records round-trip through the existing W1 `JsonModelStore` (no new persistence
authority) (C11).
