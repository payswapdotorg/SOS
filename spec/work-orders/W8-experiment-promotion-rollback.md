# W8 — Experiment + Promotion / Rollback Plane

**Status:** READY FOR ARCHITECT DISPATCH
**Dependencies:** W7 merged on `main`
**Governing architecture:** `spec/architecture.md` §§4, 9, 12–13; `spec/sos-meta-model.md`
**Requirements:** R13–R14, R23–R24

## Goal

Represent and govern the safe lifecycle from an assured candidate through bounded shadow/canary/controlled experimentation to promotion or rollback, without allowing untrusted candidates to bypass assurance or authority controls.

## Scope

- explicit experiment lifecycle and stage transitions;
- experiment design, population/allocation, success metrics and guardrails;
- rollback triggers and bounded recovery declaration;
- promotion decision representation requiring assurance pass and configured authority;
- immutable experiment result/evidence references;
- deterministic transition validation and serialization;
- tests for illegal transitions, failed assurance, guardrail rollback, promotion authority and traceability.

## Explicit exclusions

- autonomous policy design (W9);
- contextual personalization/platform adapters (W10);
- production integration beyond the lifecycle representation and execution-adapter interface;
- changing frozen assurance/authority semantics.

## Acceptance criteria

1. Experiment lifecycle supports the frozen stages from PROPOSED through ASSURED/TESTED/SIMULATED/REPLAYED/SHADOW/CANARY/EXPERIMENTAL/PROMOTED with ROLLBACK from live stages.
2. Promotion requires an assurance result that passed configured gates.
3. Promotion requires explicit authority evidence and cannot be inferred from candidate confidence.
4. Guardrails can trigger rollback from live stages.
5. Rollback records the triggering evidence and recovery target.
6. Experiment design records population/context, allocation, metrics and guardrails.
7. Stage transitions are deterministic and reject illegal skips.
8. Experiment and promotion records preserve exact candidate/base-state revisions and traceability.
9. No W8 path can bypass assurance, mission authority, or constitutional constraints.
10. Tests cover lifecycle and rollback invariants.

## Verification

Focused deterministic unit tests, static checks and exact-head repository evidence.
