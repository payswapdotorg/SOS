# W9 — Autonomy + ASK + Authority Controls

**Status:** READY FOR ARCHITECT DISPATCH
**Dependencies:** W7 and W8 merged on `main`
**Governing architecture:** `spec/architecture.md` §§4–5, 12–13; `spec/sos-meta-model.md`
**Requirements:** R15–R16, R22–R24

## Goal

Make user-granted authority and structured autonomous decision policy explicit, including calibrated confidence, impact/risk/reversibility/blast-radius/evidence-quality inputs and mandatory `ASK` escalation when authority is insufficient.

## Scope

- explicit immutable AuthorityGrant records by action/environment;
- decision request/evaluation using W1 policy primitives without creating a second authority;
- evidence-quality and calibration metadata;
- deterministic policy outcome among ACT, EXPERIMENT, GATHER_EVIDENCE, ASK;
- ASK payload with exact decision, alternatives, evidence, uncertainty and trade-offs;
- append-only authority/decision records and deterministic serialization;
- tests for scope boundaries, high-impact escalation and ASK completeness.

## Explicit exclusions

- personalized execution policies (W10);
- greenfield/brownfield realization (W11–W12);
- self-evolution (W13);
- changing mission/constitution authority;
- executing actions or deployments.

## Acceptance criteria

1. AuthorityGrant identifies owner, action class, environment, limits and validity.
2. A decision cannot exceed an explicit grant.
3. High-risk or high-impact requests outside the grant become ASK.
4. Low-confidence requests may become GATHER_EVIDENCE instead of acting where policy permits.
5. ASK carries exact decision, alternatives, evidence quality, uncertainty and trade-offs.
6. Decision records preserve calibration and evidence quality.
7. Authority and decision records are immutable/append-only and deterministic to serialize.
8. Existing W1 `AutonomyPolicy` remains a policy primitive rather than a competing authority.
9. Tests cover authorized ACT, authorized EXPERIMENT, insufficient authority ASK, and evidence gathering.
10. W9 introduces no execution side effects.
