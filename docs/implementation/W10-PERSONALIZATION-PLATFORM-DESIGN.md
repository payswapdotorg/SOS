# W10 Personalization + Platform Adapters Design

**Status:** IMPLEMENTED — REVIEW REQUIRED (Architect review iteration 4; findings A1–A7 corrected)
**Work Order:** `spec/work-orders/W10-personalization-platform.md`
**Dependencies:** W2 merged `587201d3`; W9 merged `203cfb7`
**Base:** `main` @ `29c69ff14e140376393770cefe114ceb13005206`

W10 implements contextual personalization and platform-neutral adapter
contracts. Context may narrow policy but never widen it. Adapters are
contract/policy interfaces only — no deployment or side effects.

## Personalization

`ContextualSelector` carries typed context dimensions (W1 `ContextValue`) with
truthful truth states. `ContextualPolicy` narrows a W9 `AutonomyRequest`:
`narrowed_allowed_actions` must be a subset; `narrowed_ceilings` must be
stricter or equal. `PersonalizationDecision` records context refs, policy refs,
rationale, reasons, and W1 traceability.

### Alternative selection — `select_policy` (corrected, A1)

`select_policy(*, alternatives, selector, w9_decision_state, traceability)`
treats each alternative's declared selector as a **predicate over the
supplied context**. For every dimension an alternative declares (dimension
identity + key):

- the supplied selector must **contain** a corresponding value (`ABSENT`
  otherwise);
- the supplied value must be **resolvable** (`TruthState.SUCCESS`);
- the alternative's declared constraint must be **equal** to that actual
  supplied value.

An alternative whose declared dimension is absent, unresolved, or
value-mismatched in the supplied selector is **not** context-compatible. A
`SUCCESS` flag on the alternative's own declaration alone never implies
compatibility. Among compatible alternatives the selection is deterministic —
`(priority, id)` order. When no alternative is compatible, the
highest-priority alternative is carried as the proposal and the state is
narrowed (below). Per-dimension outcomes are recorded as `matched` /
`mismatched` / `unresolved` (with the supplied truth state, or `ABSENT`).

### Truth-state narrowing (A2) and monotonicity (A3)

Every non-SUCCESS truth state supplied in the top-level selector — `FAILED`
and `EMPTY` included, alongside `UNKNOWN`/`UNSUPPORTED`/`UNAVAILABLE` —
narrows the decision. No non-SUCCESS supplied state is collapsed into
success, so a FAILED context can never silently preserve `ACT`
(`evaluate_personalization` applies the same rule to every supplied
dimension).

All state adjustment is monotonic in the W9 decision-state lattice via
`narrow_decision_state`: restriction ranks
`ACT < {EXPERIMENT, GATHER_EVIDENCE} < ASK < {REJECT, ROLLBACK}`, derived
from the frozen W9 transition contract (`src/sos/autonomy.py`, SOS-W9-F19).
The candidate state is applied only when strictly more restrictive:

- inherited `REJECT` stays `REJECT`; inherited `ROLLBACK` stays `ROLLBACK`
  (an ASK candidate is a widening and is refused);
- `ACT` may narrow to `ASK`;
- nothing ever moves to a less restrictive state than inherited, on any
  state-adjusting path (no-compatible-alternative path, unresolved-context
  guard, and `evaluate_personalization`'s per-dimension guard).

### Selection explainability (A4)

`PolicySelection` records — strictly additively to the existing fields, with
safe defaults (`()` / `""`) so previously persisted records and old call sites
remain loadable:

- `alternative_evaluations`: per alternative (`AlternativeEvaluation`) — its
  id, whether it was context-compatible, and one
  `AlternativeDimensionEvaluation` per declared dimension with the outcome
  (`matched` / `mismatched` / `unresolved`), the declared and supplied truth
  states, and the declared/supplied values;
- `inherited_state`: the inherited W9 decision state;
- `narrowing_chain`: the monotonic steps (`StateNarrowingStep`: from → to,
  with reason) that produced the final `state` from `inherited_state`.

The whole record is deterministic and JSON-round-trippable through the W1
`JsonModelStore` (C10).

## Platform adapters

`PlatformSurface` (frozen vocabulary: web/mobile/desktop/tv/cross-platform/
wearable/api/edge/cloud/other). `AdapterCapability` (name, supported).
`PlatformAdapter` (frozen, construction-validated, traceable).
`AdapterPlan` (side-effect-free validation result: compatible/missing
capabilities). `validate_adapter` is a pure function — no network, no
deployment, no side effects; it performs capability-set validation only.

### Platform policy constraints (corrected, A5)

`PlatformPolicyConstraint` is a typed, construction-validated narrowing
constraint record over an **already-authorized** W9 policy — the platform
analogue of `ContextualPolicy`:

- `narrowed_allowed_actions` must be a non-empty subset of the authorized
  policy's `allowed_actions` (real W1 `DecisionAction` members — plain
  strings are rejected);
- `narrowed_ceilings` must be stricter than or equal: `max_risk` no higher,
  `max_blast_radius` no wider, `require_reversible` not relaxed,
  `min_confidence` floor no lower, human approval for ACT never waived.

Construction raises `ModelValidationError` deterministically on widening or
invalid constraint data (C12). `constrain_policy(adapter, ...)` is the pure
builder that validates the adapter and returns the constraint bound to it
(`adapter_id`, traceability). Platform constraints may restrict an authorized
policy but never widen it (C7); adapter capability/metadata remains
non-authoritative.

## Key invariants

- **C3:** context cannot expand `allowed_actions`, relax ceilings, waive human
  approval, or turn ASK/REJECT into ACT;
- **C4:** every non-SUCCESS supplied truth state (FAILED and EMPTY included)
  routes to ASK per the monotonic narrowing rule — never a silent ACT;
- **C6:** adapter validation and constraint construction are side-effect free
  and deterministic;
- **C7:** platform constraints narrow an already-authorized policy
  (subset actions, stricter-or-equal ceilings), never widen;
- **C8:** selection records per-alternative evaluation evidence (dimension
  outcomes with truth states), the inherited W9 state, and the narrowing
  chain (inherited → final, with reasons);
- **C9:** identical authoritative inputs produce identical selection and
  validation results (no network/provider dependence);
- **C10:** records round-trip through the W1 `JsonModelStore`, with
  backward-compatible defaults for pre-iteration-4 records;
- **C12:** new adapters implement the contract without changing global
  authorities; invalid adapter/constraint data is rejected deterministically.
