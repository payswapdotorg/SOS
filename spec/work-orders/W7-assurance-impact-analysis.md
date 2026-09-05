# W7 — Assurance + Impact Analysis

**Status:** READY FOR ARCHITECT DISPATCH
**Dependencies:** W6 merged on `main`
**Governing architecture:** `spec/architecture.md` §§4, 9, 12–13; `spec/sos-meta-model.md`
**Requirements:** R13–R14, R23–R24

## Goal

Provide the trusted assurance boundary that evaluates candidate proposals against explicit verification evidence, impact/risk conditions, and configured safety gates before any downstream experiment or promotion.

## Scope

- typed assurance check/result vocabulary for static analysis, tests, replay, simulation, impact and risk;
- explicit PASS/FAIL/INCONCLUSIVE/NOT_RUN states;
- impact and risk assessment representation;
- configured assurance policy with required checks and maximum tolerated risk/impact;
- candidate evaluation that blocks on failed or required-but-unavailable evidence;
- deterministic assurance result serialization;
- tests for evidence truthfulness, gating, impact/risk thresholds and deterministic evaluation.

## Explicit exclusions

- live deployment, experimentation, canarying or promotion (W8);
- rollback execution (W8);
- candidate generation/search (W6);
- replacing System State or ArchitectureGraph;
- inventing evidence or treating LLM output as assurance evidence;
- changing frozen architecture or authority semantics.

## Acceptance criteria

1. Assurance checks identify type, source, subject, result state, evidence references and provenance.
2. Required checks can be configured per assurance policy.
3. Failed required checks block a candidate.
4. Required checks that are unavailable, unknown or not run do not count as success.
5. Impact and risk are explicit and evaluated against configured bounds.
6. Assurance result preserves every check outcome and explains the gate decision.
7. Assurance references the candidate and its base system state without mutating either.
8. Serialization is deterministic and preserves non-success states.
9. Tests cover positive and negative assurance paths and threshold behavior.
10. W7 has no promotion, experiment execution or rollback behavior.

## Verification

Focused deterministic unit tests, static checks, and exact-head repository evidence.
