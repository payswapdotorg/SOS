# W8 — Experimentation + Promotion / Rollback

**Status:** DISPATCHED — WORKER AUTHORIZED
**Dependencies:** W7 authoritative merge `25f663cf444f92b3190074a9119619cbc53e9ece`
**Roadmap:** `spec/implementation-roadmap.md` — W8
**Primary requirements:** R12, R14, R15, R21, R23, R24

## Mission
Implement the controlled experimentation and promotion/rollback lifecycle above the W7 assurance boundary. W8 consumes non-authorizing W7 assurance results and defines deterministic experiment, evaluation, promotion-gating, containment, and rollback state semantics without becoming a platform-specific deployment adapter or an autonomy authority.

## Governing authorities

The implementation MUST obey, without redefining them:

- `spec/architecture-lock.md` (frozen v1.0), especially Assurance, Optimization, System State, and Implementation Governance invariants;
- `spec/requirements.md` R12/R14/R15/R21/R23/R24;
- `spec/implementation-roadmap.md` W8;
- `docs/implementation/SOS-IMPLEMENTATION-PROCESS.md` and `AGENTS.md`;
- W1 truth/traceability models, W2 System State/Architecture Graph, W4 evidence, W5 causal knowledge, W6 candidate proposals, and W7 assurance results as read-only upstream authorities.

Candidate reasoning remains untrusted. W8 MUST NOT turn model output, confidence, or narrative into evidence, authorization, promotion, causal efficacy, or completion. Promotion requires configured evidence gates. Live candidates require rollback or equivalent governed recovery unless a documented higher-order containment policy explicitly applies.

## Required outcome

Create a deterministic W8 lifecycle model that can consume a W7 `AssuranceResult` and represent at minimum:

1. **Experiment definition:** explicit candidate binding, exact base graph/revision, bounded mode (`SHADOW`, `CANARY`, `CONTROLLED`), scope, duration/observation window, success criteria, stop conditions, and rollback/recovery reference.
2. **Entry gating:** only appropriately assured candidates may enter an experiment; FAIL/BLOCKED/UNKNOWN assurance must not be silently promoted into execution eligibility.
3. **Experiment lifecycle:** explicit states for planned/ready/running/stopped/completed/failed/rolled-back with deterministic, validated transitions.
4. **Evidence accumulation:** attach W4 evidence by exact id/provenance and preserve observed truth states; observational evidence may evaluate experiment outcomes but does not become causal proof merely by being observed.
5. **Stop/abort conditions:** explicit hard stop conditions that cannot be optimized away; failure or unavailable evidence is represented truthfully.
6. **Promotion gating:** promotion requires configured evidence gates and a successful bounded experiment evaluation; no scalar quality authority, no confidence-only promotion, and no promotion from W7 non-PASS assurance.
7. **Rollback/containment lifecycle:** explicit rollback eligibility/reference, recovery state transitions, and containment outcome; W8 may model/execute lifecycle semantics but MUST NOT invent or silently downgrade recovery guarantees.
8. **Multi-objective integrity:** preserve W6 objectives and W7 uncertainty/risk/impact information without replacing them with a single scalar architecture-quality score.
9. **Traceability:** every experiment, evaluation, promotion, and rollback state references candidate, assurance result, graph/revision, evidence, rules/configuration, and W1 traceability.
10. **Non-authority boundary:** W8 must not implement W9 autonomy/ASK/user authority or W10+ platform/personalization semantics.

## Allowed implementation surface

Worker MUST limit implementation to these five files unless an Architect-approved correction expands scope:

- `src/sos/experimentation.py`
- `src/sos/__init__.py` (W8 exports only)
- `tests/test_w8_experimentation.py`
- `docs/implementation/W8-EXPERIMENT-PROMOTION-ROLLBACK-DESIGN.md`
- `spec/development-state/W8-checkpoint.md`

Do not modify frozen authority artifacts, roadmap semantics, Work Order machinery, or W1–W7 source files.

## Explicit exclusions

W8 MUST NOT implement:

- autonomy policy, ASK, user authorization, or autonomous decision execution (W9);
- personalization or platform adapters (W10);
- greenfield or brownfield realization loops (W11/W12);
- SOS self-evolution/meta-adaptation (W13);
- second evidence/cause/architecture authority;
- scalarized architecture quality as the sole promotion authority;
- LLM-derived proof or confidence-only safety/promotion;
- silent mission/value/constraint changes;
- production deployment integrations or provider-specific execution semantics that belong to later platform/context work.

## Acceptance criteria

### C1 — Exact candidate/assurance binding
Every W8 experiment binds to the exact candidate id, base graph id/revision, provenance revision, and originating W7 assurance result id. Mismatches are rejected explicitly.

### C2 — Entry assurance gate
Only a W7 assurance result with status `PASS` can enter an executable experiment state. `FAIL`, `UNKNOWN`, and `BLOCKED` remain distinguishable and cannot become execution-ready.

### C3 — Bounded experiment model
Experiment mode, target scope, observation window, success criteria, and stop conditions are explicit and deterministically validated; no hidden unbounded execution or traversal.

### C4 — Truthful evidence evaluation
Experiment outcome evaluation preserves W4 evidence ids, provenance/revision, and truth states. Missing/unknown/failed/unavailable evidence remains distinct and cannot be converted to PASS.

### C5 — Hard stop / safety conditions
Explicit hard stop conditions deterministically stop or fail the experiment and cannot be offset by favorable objective observations.

### C6 — Promotion gate
Promotion is a distinct lifecycle state transition gated by successful experiment evaluation and required evidence. There is no implicit promotion from experiment completion and no confidence-only shortcut.

### C7 — Rollback / containment
Rollback/recovery is explicit, traceable, and required for live/promotion-eligible candidates unless a documented governed containment exception is referenced. Rollback state cannot be claimed complete without the required evidence/reference.

### C8 — Lifecycle state machine
Invalid state transitions are rejected. State history is deterministic and traceable; rollback paths cannot bypass required intermediate semantics.

### C9 — Multi-objective preservation
W6 objective dimensions and W7 impact/risk/uncertainty remain available through experiment and promotion evaluation. No single scalar becomes authoritative.

### C10 — Deterministic bounded evaluation
Same lifecycle inputs produce the same evaluation/decision states. Every evaluation has explicit limits and no network/provider dependency is required for deterministic tests.

### C11 — Persistence + traceability
W8 records round-trip through the existing W1 `JsonModelStore` without introducing another persistence authority; traceability remains intact.

### C12 — Bounded authority surface
W8 owns experimentation/promotion/rollback lifecycle semantics only. It does not implement W9 autonomy/ASK or redefine W7 evidence/assurance authority.

## Required regression coverage

Tests MUST include, at minimum: rejection of non-PASS W7 assurance at experiment entry; exact candidate/graph/assurance binding; all lifecycle transition rules; unknown/unavailable/failed evidence cannot produce promotion PASS; hard stop cannot be offset by objectives; promotion requires explicit successful evaluation; rollback requires valid governed recovery evidence/reference; missing rollback/containment blocks promotion eligibility; round-trip persistence; deterministic evaluation; and absence of W9+ authority/platform symbols.

## Deterministic verification

Worker MUST run and report exact-head results for:

```text
python -m pytest
python -m compileall -q src tests
```

## Risk / rollback

Risk is semantic and potentially high because W8 becomes the lifecycle boundary before autonomy. The implementation must remain deterministic, explicit, traceable, and provider-neutral. Git revert of the merged W8 change is the repository rollback mechanism.

## Completion protocol

When implementation is complete, the Worker MUST:

1. checkpoint exact base/head SHAs and verification evidence;
2. run the deterministic verification commands;
3. leave Worker state at `WAITING_FOR_ARCHITECT`;
4. stop without merging and without creating W9;
5. await Architect review. Corrections stay on the same PR.
