# W10 Personalization + Platform Adapters Design

**Status:** IMPLEMENTED — REVIEW REQUIRED
**Work Order:** `spec/work-orders/W10-personalization-platform.md`
**Dependencies:** W2 merged `587201d3`; W9 merged `203cfb7`

W10 implements contextual personalization and platform-neutral adapter
contracts. Context may narrow policy but never widen it. Adapters are
contract/policy interfaces only — no deployment or side effects.

## Personalization

`ContextualSelector` carries typed context dimensions (W1 `ContextValue`) with
truthful truth states. `ContextualPolicy` narrows a W9 `AutonomyRequest`:
`narrowed_allowed_actions` must be a subset; `narrowed_ceilings` must be stricter
or equal. `PersonalizationDecision` records context refs, policy refs, rationale,
reasons, and W1 traceability. `evaluate_personalization` routes
unknown/unavailable context to ASK.

## Platform adapters

`PlatformSurface` (frozen vocabulary: web/mobile/desktop/tv/cross-platform/
wearable/api/edge/cloud/other). `AdapterCapability` (name, supported).
`PlatformAdapter` (frozen, construction-validated, traceable).
`AdapterPlan` (side-effect-free validation result: compatible/missing capabilities).
`validate_adapter` is a pure function — no network, no deployment, no side effects.

## Key invariants

- **C3:** context cannot expand `allowed_actions`, relax ceilings, waive human
  approval, or turn ASK/REJECT into ACT;
- **C4:** unknown/unavailable context routes to ASK;
- **C6:** adapter validation is side-effect free and deterministic;
- **C7:** platform constraints narrow, never widen;
- **C12:** new adapters implement the contract without changing global authorities.
