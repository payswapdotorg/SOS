# W6 — Candidate Generation + Bounded Search

**Status:** READY FOR ARCHITECT DISPATCH
**Dependencies:** W3 and W5 merged on `main`
**Governing architecture:** `spec/architecture.md` §§6, 12–13; `spec/sos-meta-model.md`
**Requirements:** R8, R11–R12, R19, R23–R24

## Goal

Generate bounded alternative System State candidates from the W2 architecture graph and rank them as a Pareto/non-dominated set using mission-aligned benefit, cost, risk, uncertainty, reversibility and blast-radius metadata. Search is advisory; it does not authorize deployment.

## Scope

- immutable candidate evaluation representation;
- bounded search budget with deterministic candidate cap;
- candidate generation from explicit `SubgraphReplacement` mutations;
- use ArchitectureMemory as a prior/input signal, never as proof;
- multi-objective Pareto/non-dominated ranking;
- explicit authority/risk/reversibility/blast-radius metadata;
- traceability and deterministic serialization;
- tests for boundary preservation, budget enforcement, dominance and memory-prior semantics.

## Explicit exclusions

- assurance gates (W7);
- experimentation, canarying, promotion or rollback execution (W8);
- changing System State or ArchitectureGraph in place;
- autonomous action authorization;
- treating memory confidence or model confidence as proof;
- changing frozen architecture or authority semantics.

## Acceptance criteria

1. Multiple CandidateState alternatives can be represented without mutating the base System State.
2. Every candidate declares its changed subgraph, replacement, boundary interfaces/invariants, predicted effects and risks.
3. Search is bounded by an explicit deterministic budget.
4. Candidate generation is deterministic for fixed inputs.
5. Ranking supports conflicting objectives and produces the non-dominated/Pareto subset.
6. Candidate scoring exposes benefit, cost, risk, uncertainty, reversibility and blast radius rather than a single opaque architecture score.
7. ArchitectureMemory can influence candidate priority as a prior, but memory cannot prove candidate correctness.
8. Candidate authority metadata is descriptive only; no promotion or execution occurs in W6.
9. Tests cover invalid boundaries, budget limits, Pareto dominance and deterministic ordering.
10. W6 introduces no assurance, experiment or production execution semantics.

## Verification

Focused deterministic tests, static checks and exact-head review evidence.
