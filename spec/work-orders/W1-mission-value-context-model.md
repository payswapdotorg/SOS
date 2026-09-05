# W1 — Mission / Value / Context Model

**Status:** READY FOR ARCHITECT DISPATCH
**Dependencies:** W0 foundation artifacts are merged on `main`.
**Governing architecture:** `spec/architecture.md` §§3.1–3.4, 5–8
**Requirements:** R1–R5, R15–R18, R22–R23

## Goal

Implement the authoritative domain model and persistence/API boundary for Constitution-referenced mission metadata needed by SOS: Mission, Value Model, Context, autonomy policy and explicit Ask decisions. Do not implement runtime architecture search, candidate generation or production experimentation in this slice.

## Scope

- versioned Mission model with collaborative formalization state;
- versioned Value Model with business-model-derived objectives/constraints;
- Context model supporting user/cohort/platform/environment dimensions;
- explicit autonomy policy and `ASK` decision representation;
- validation of hard/soft/risk/preference constraint classes;
- truthful unknown/unavailable state representation;
- tests for revision, authority and cross-model traceability;
- repository-resident evidence for exact revision and verification.

## Explicit exclusions

- architecture graph implementation (W2);
- runtime architecture recovery (W3);
- telemetry/evidence graph (W4);
- candidate search (W6);
- production experiment/promotion (W8);
- changing the frozen Constitution or architecture semantics;
- silently inferring or mutating mission intent from telemetry.

## Acceptance criteria

1. Mission has stable identity, version, owner/authority, goals, outcomes, assumptions, ambiguities and change history.
2. Mission revisions are explicit proposals/approved revisions; no telemetry path may silently revise intent.
3. Value Model represents business-model inputs and derives typed objective/constraint/incentive/opportunity records without outranking Mission or Constitution.
4. Context is extensible and can distinguish user/cohort/device/platform/environment dimensions.
5. Autonomy policy can express per-action/environment thresholds and required human approval.
6. Decision states include `ACT`, `EXPERIMENT`, `GATHER_EVIDENCE`, and `ASK`.
7. `ASK` payloads carry the exact decision, alternatives, evidence quality, uncertainty and trade-offs needed from the user.
8. Failed/unavailable/unknown state is distinct from empty/successful state.
9. Every model carries traceability to owning mission/value/authority records.
10. Tests and static validation prove the model invariants.

## Verification

- focused unit/integration tests for all invariants;
- type/static checks;
- serialization/deserialization round trips;
- negative tests for invalid authority transitions and failed-read conflation;
- exact-head verification recorded in the PR.

## Required PR evidence

Record exact base SHA, exact head SHA, PR identity, commands/results, known limitations, and a requirement-to-implementation-to-test mapping. The worker stops at `WAITING_FOR_ARCHITECT` after the checkpoint.
