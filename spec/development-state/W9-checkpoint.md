# W9 Implementation Checkpoint

**Work Order:** `W9 — Autonomy + ASK + Authority Controls`
**State:** `WAITING_FOR_ARCHITECT`
**Branch:** `work/w9-autonomy-authority`
**Base SHA:** `a33937d38af8dc42055c7b08c0642778977d4343`
**Latest implementation SHA:** `94d646a723575a16d884f8ebd4b67a5be518391a`

## Dependency proof

W7 merged as `7a139d3a8efa5d587e4cb384d96abf54571d64b9`; W8 merged as `79da7d0b8d6757470a42d52c51d8f891acbef672`.

## Scope implemented

- explicit immutable AuthorityGrant records;
- DecisionRequest with confidence/calibration/evidence-quality/impact/risk/reversibility/blast-radius inputs;
- bounded evaluator routing insufficient authority to ASK;
- explicit GATHER_EVIDENCE path when the grant allows it;
- complete ASK payload;
- append-only AuthorityLedger and deterministic export;
- W1 AutonomyPolicy preserved as a lower-level policy primitive; no second semantic authority.

## Explicit exclusions

No action execution, deployment, personalization, greenfield/brownfield realization, self-evolution, mission/constitution mutation, or autonomous policy rewriting.

## Requirement mapping

| Requirement | Implementation / verification |
|---|---|
| R15 | Explicit grants and evaluator consider confidence, calibration, risk, impact, reversibility, blast radius and evidence quality. |
| R16 | `ASK` is mandatory when authority is absent/insufficient; payload carries decision, alternatives, evidence quality, uncertainty and trade-offs. |
| R22 | AuthorityGrant records explicit owner-granted action/environment scope. |
| R23 | Decisions preserve request/grant refs, calibration and evidence quality. |
| R24 | Work Order, design, checkpoint, implementation and tests are repository-resident. |

## Verification

Repository CI runs `python -m pytest`; local public GitHub DNS is unavailable, so no local pass count is asserted.

## Known limitations

- Grant validity dates are represented as immutable metadata; an external clock/policy service is not part of W9.
- Decision evaluation produces records but deliberately executes nothing.

## Architect disposition requested

Review exact PR head and merge only the reviewed head. After merge, W10 and W11 become independently eligible by roadmap dependency structure.
