# W8 Experiment / Promotion / Rollback Design

W8 governs the controlled lifecycle after W7 assurance.

The lifecycle is sequential and explicit:

`PROPOSED → ANALYZED → ASSURED → TESTED → SIMULATED/REPLAYED → SHADOW → CANARY → EXPERIMENTAL → PROMOTED`

Live stages may transition to `ROLLBACK` only through a recorded guardrail trigger and recovery target.

`ASSURED` requires a passing W7 `AssuranceResult`. `PROMOTED` requires an explicit `PromotionDecision` containing authority and assurance references. No candidate confidence, memory prior, or model output can authorize promotion.

The module models transitions and records, but performs no deployment, experiment allocation, monitoring, or rollback side effects. Those are execution-adapter responsibilities outside this bounded semantic plane.
