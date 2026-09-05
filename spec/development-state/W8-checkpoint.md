# W8 Implementation Checkpoint

**Work Order:** `W8 — Experiment + Promotion / Rollback Plane`
**State:** `WAITING_FOR_ARCHITECT`
**Branch:** `work/w8-experiment-plane`
**Base SHA:** `ed35b4da1ea793c8b150519e9570f1355a34a994`
**Latest implementation SHA:** `3d6a847add226dc4524263be9ee59684af494e46`

## Dependency proof

W7 is authoritatively merged on `main` as `7a139d3a8efa5d587e4cb384d96abf54571d64b9`.

## Scope implemented

- explicit ExperimentDesign with population/context/allocation/success metrics/guardrails;
- sequential lifecycle from PROPOSED through PROMOTED with SIMULATED/REPLAYED branch;
- W7 assurance-gated ASSURED transition;
- explicit authority-bearing PromotionDecision and explicit assurance reference;
- live-stage GuardrailTrigger and RollbackRecord;
- deterministic lifecycle validation and serialization;
- invariant tests.

## Explicit exclusions

No autonomous policy design, personalization, deployment side effects, runtime monitoring, candidate generation, or frozen authority changes.

## Requirement mapping

| Requirement | Implementation / verification |
|---|---|
| R13 | Experiment lifecycle requires assurance before live stages and explicit guarded progression. |
| R14 | Rollback records identify guardrail evidence and recovery target; actual rollback execution is outside this semantic plane. |
| R23 | Experiment/candidate/base-state/assurance/authority references and guardrail evidence are explicit. |
| R24 | Work Order, design, checkpoint, implementation and tests are repository-resident. |

## Verification

Repository CI runs `python -m pytest`; local public GitHub DNS is unavailable in this execution environment, so no local pass count is asserted.

## Known limitations

- W8 models lifecycle transitions and execution-adapter contracts but does not perform deployment, allocation, monitoring or rollback side effects.
- Promotion authority is represented as explicit references; user authority evaluation remains W9.

## Architect disposition requested

Review exact PR head `3d6a847add226dc4524263be9ee59684af494e46`, verify CI, and merge only the reviewed head. After merge, W9 becomes eligible.
