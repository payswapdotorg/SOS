# W7 — Assurance + Impact Analysis

**Status:** DISPATCHED — WORKER AUTHORIZED
**Dependencies:** W6 authoritative merge `b5171f70ca5ce85ca0be07cfdb3abf034c03c32f`
**Roadmap:** `spec/implementation-roadmap.md` — W7
**Primary requirements:** R12, R13, R15, R21, R23, R24

## Mission
Implement the first assurance boundary above W6 candidate generation. W7 must evaluate candidate proposals for evidence-backed feasibility, impact, risk, safety/constraint compliance, and uncertainty without becoming an execution, promotion, autonomy, or authority plane.

## Governing authorities

The implementation MUST obey, without redefining them:

- `spec/architecture-lock.md` (frozen v1.0), especially Assurance and Optimization invariants;
- `spec/requirements.md` R12/R13/R15/R21/R23/R24;
- `spec/implementation-roadmap.md` W7 outcome;
- `docs/implementation/SOS-IMPLEMENTATION-PROCESS.md` and `AGENTS.md` for implementation governance;
- W1 truth/traceability models, W2 System State/Architecture Graph, W3 recovery uncertainty, W4 evidence, W5 causal knowledge/memory, and W6 candidate proposals as read-only upstream authorities.

Candidate generation/reasoning remains untrusted. LLM text, candidate scores, confidence, or narrative MUST NOT by themselves establish truth, safety, authorization, completion, or causal efficacy. Production promotion remains a later W8 concern.

## Required outcome

Create a deterministic, evidence-aware assurance model that can accept a W6 `CandidateProposal` and produce a structured non-authorizing assurance result covering at minimum:

1. **Evidence gates:** explicit checks over available evidence and known provenance/revision context; missing/unknown/failed/unavailable evidence remain distinct and block unjustified PASS outcomes.
2. **Impact analysis:** identify affected graph scope, boundary/interface exposure, dependency reach, blast radius, and relevant constraint/mission/value traceability.
3. **Risk assessment:** represent material risks, severity, likelihood/uncertainty, mitigations, and residual risk without collapsing uncertainty into certainty.
4. **Safety/constraint gates:** hard constraints must be explicit and cannot be silently optimized away; failure of a hard constraint must not be masked by favorable objectives.
5. **Causal qualification:** W5 causal hypotheses may inform reasoning, but observational evidence cannot be upgraded into intervention proof.
6. **Reversibility/containment:** assurance must surface whether rollback/recovery is available or whether a documented containment policy applies; W8 owns actual experiment/promotion/rollback lifecycle.
7. **Multi-objective preservation:** assurance must preserve W6 objective dimensions and not introduce a single authoritative quality score.
8. **Truthful result states:** PASS/FAIL/UNKNOWN/BLOCKED or equivalent structured states must be explicit and justified by evidence; no unsupported SUCCESS claim.
9. **Traceability:** result references the candidate, base graph/revision, evidence/reasoning inputs, assurance rules/gates, and W1 traceability.
10. **Non-authorizing boundary:** the W7 result cannot itself authorize application, production promotion, autonomy, or user actions.

## Allowed implementation surface

Worker MUST limit implementation to these five files unless an Architect-approved correction expands scope:

- `src/sos/assurance.py`
- `src/sos/__init__.py` (W7 exports only)
- `tests/test_w7_assurance.py`
- `docs/implementation/W7-ASSURANCE-IMPACT-ANALYSIS-DESIGN.md`
- `spec/development-state/W7-checkpoint.md`

Do not modify frozen authority artifacts, roadmap semantics, Work Order machinery, or W1–W6 source files.

## Explicit exclusions

W7 MUST NOT implement:

- experiment execution, shadow/canary/controlled experiments, promotion, rollout, rollback execution, or deployment mutation (W8);
- autonomy policies, ASK/user authorization, or decision execution (W9);
- personalization/platform adapters (W10);
- greenfield/brownfield realization (W11/W12);
- self-evolution/meta-adaptation (W13);
- production writes, live mutation, network orchestration, or deployment control;
- a second evidence/cause/architecture authority;
- scalarized architecture quality as the sole gate;
- LLM-derived proof, confidence-only safety, or unsupported causal certainty.

## Acceptance criteria

### C1 — Candidate binding + provenance
Every assurance result binds to the exact candidate id, base graph id/revision, provenance revision, and W1 traceability. Mismatches are explicitly rejected.

### C2 — Evidence-backed gate evaluation
Each gate records its evidence references and a truthful status. Unknown, failed, and unavailable states are not converted to PASS.

### C3 — Impact + blast radius
The result identifies affected candidate nodes/edges, boundary interfaces, dependency reach, and a deterministic bounded blast-radius representation. No hidden unbounded graph traversal.

### C4 — Hard-constraint enforcement
Known hard-constraint violations deterministically fail/block assurance and cannot be offset by objective improvements.

### C5 — Risk representation
Risks preserve severity/likelihood/uncertainty and mitigation/residual-risk data without implying false certainty.

### C6 — Causal qualification
Observational W4 evidence and proposed W5 hypotheses are distinguishable from intervention-grade evidence; causal efficacy is never established from narrative or confidence alone.

### C7 — Reversibility / containment
Assurance records whether governed rollback/recovery evidence exists or whether a documented containment exception applies; it does not execute rollback.

### C8 — Multi-objective integrity
Assurance consumes W6 objectives without introducing a single scalar authoritative score. Conflicting objectives remain visible.

### C9 — Deterministic, bounded evaluation
Same inputs produce the same assurance result; evaluation is finite and bounded by explicit limits.

### C10 — Explicit rejection / truthful failures
Missing candidate, graph, evidence, provenance, or required assurance context is rejected explicitly. Failed evaluation remains distinguishable from unavailable/unknown.

### C11 — Traceability + persistence
Results round-trip through the existing W1 JSON persistence mechanism without creating a new persistence authority.

### C12 — Bounded surface / non-authorization
Only W7 symbols are introduced/exported; no W8+ execution or authority semantics appear.

## Deterministic verification

Worker MUST run and report exact-head results for:

```text
python -m pytest
python -m compileall -q src tests
```

Tests MUST include regression coverage for every acceptance criterion, including negative tests proving observational evidence cannot become intervention proof, hard constraints cannot be optimized away, unknown evidence cannot become PASS, and W7 cannot authorize execution/promotion.

## Risk / rollback

Risk is semantic and potentially high because W7 feeds later promotion and autonomy work. The implementation is read-only/non-authorizing and has no deployment side effects. Rollback is ordinary Git revert of the merged W7 PR.

## Completion protocol

When implementation is complete, the Worker MUST:

1. checkpoint exact base/head SHAs and evidence;
2. run the deterministic verification commands;
3. leave the Worker state at `WAITING_FOR_ARCHITECT`;
4. stop without merging and without creating W8;
5. await Architect review. Corrections stay on the same PR.
