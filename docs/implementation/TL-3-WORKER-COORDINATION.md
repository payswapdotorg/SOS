# SOS TL + 3-Worker Coordination Contract

**Status:** ACTIVE PREPARATION
**Purpose:** Give the LLM Tech Lead a durable three-worker operating model while preserving the frozen SOS governance and sequencing rules.

## Operating principle

The Tech Lead coordinates three concurrent lanes:

1. **Worker A — W10 Closure:** owns the existing W10 PR and all Architect-requested corrections on the same branch/PR.
2. **Worker B — W11 Preparation:** prepares the provider-neutral execution substrate contract, tests/specification, and integration plan without claiming W11 completion or introducing live execution.
3. **Worker C — Provider/Cockpit Preparation:** researches and designs the OpenMuse execution-provider seam and Code-OSS cockpit seam without making either product a semantic authority.

Workers B and C may work concurrently because their preparation artifacts do not depend on unmerged worker code.

## Hard coordination rules

- Only Worker A may modify PR #17 until an Architect explicitly expands the scope.
- Workers B and C must not modify W1-W10 implementation semantics.
- No worker may treat another worker's unmerged branch as a dependency.
- Preparation artifacts are not roadmap completion and do not change the canonical frontier.
- Any implementation that changes a frozen semantic authority requires an Architecture Change Request.
- LLM/model output remains proposal material.
- Git, CI, tests, and persisted evidence remain authoritative.
- Each worker stops at a durable review-ready state rather than merging its own work.

## Integration strategy

The intended convergence is:

`W10 merged`
→ `W11 execution contract`
→ `OpenMuse/provider implementation`
→ `Code-OSS/web cockpit`
→ `W11 realization gate`
→ `W12 brownfield loop`

The TL must keep the execution contract provider-neutral so OpenMuse can be replaced without changing SOS mission, evidence, assurance, or autonomy semantics.

## Worker reporting

Each worker checkpoint must include:

- Work item identifier;
- exact base SHA or source revision;
- exact head SHA when code is involved;
- files/artifacts changed;
- requirement/architecture traceability;
- tests/evaluation performed;
- unresolved findings;
- known limitations;
- next action;
- explicit statement that no unmerged sibling is treated as a dependency.

## Stop conditions

Stop and escalate when:

- authority artifacts disagree;
- a change would redefine a frozen semantic;
- a preparation artifact starts encoding provider-specific semantics into SOS core;
- an execution design can bypass W7/W8/W9 gates;
- platform metadata is being used as authorization;
- evidence is being inferred rather than observed;
- exact base/head cannot be verified.
