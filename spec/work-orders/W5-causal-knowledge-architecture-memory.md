# W5 — Causal Knowledge + Architecture Memory

**Status:** READY FOR ARCHITECT DISPATCH
**Dependencies:** W4 merged on `main`
**Governing architecture:** `spec/architecture.md` §§3.8–3.9, 5–6, 12–13; `spec/sos-meta-model.md`
**Requirements:** R10, R19, R23–R24

## Goal

Represent explicit causal hypotheses and durable architecture memory while preserving the distinction between observation/correlation and intervention evidence.

## Scope

- typed CausalHypothesis entity;
- explicit expected mechanism/direction/magnitude and uncertainty;
- evidence references with observational/intervention distinction;
- high-impact causal-eligibility guard requiring intervention evidence;
- ArchitectureMemory entity for context, candidate patterns, predictions, observations, outcomes, learned rules and provenance;
- append-only memory storage and deterministic serialization;
- tests and repository-resident evidence.

## Explicit exclusions

- candidate generation/search/ranking (W6);
- assurance and experiment execution (W7–W8);
- autonomous promotion;
- silently converting correlation into causal proof;
- changing frozen architecture/evidence semantics.

## Acceptance criteria

1. Causal hypotheses are explicit records with context, mechanism, expected effect, confidence, status and evidence references.
2. Evidence references preserve whether supporting evidence is observational or intervention-based.
3. A high-impact causal claim cannot be marked eligible without intervention evidence.
4. Architecture memory stores durable intervention context, predictions, observations, outcomes, learned rules and provenance.
5. Memory is treated as prior experience, not authoritative proof.
6. Storage is append-only and deterministic for a fixed input set.
7. Tests cover causal evidence distinction, high-impact gating, memory durability and serialization.
8. W5 contains no candidate search, assurance or production experimentation.

## Verification

Focused deterministic unit tests, static checks and exact-head repository evidence.
