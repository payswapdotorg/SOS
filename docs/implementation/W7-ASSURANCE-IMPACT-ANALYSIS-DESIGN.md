# W7 Assurance + Impact Analysis Design

**Status:** IMPLEMENTED — REVIEW REQUIRED
**Work Order:** `spec/work-orders/W7-assurance-impact-analysis.md`
**Dependencies:** W6 merged as `b5171f7…`; W5 `2bfd0f8…`; W3 `6541441…`; W4 `26060db…`; W2 `587201d3…`

W7 is the first assurance boundary above W6 candidate generation. It evaluates
candidate proposals for evidence-backed feasibility, impact, risk, safety/constraint
compliance, and uncertainty **without becoming an execution, promotion, autonomy, or
authority plane** (architecture §§4.6, 9, 13).

## Governing principle

Assurance is **non-authorizing**. A result carries no "authorized"/"approved" flag;
it cannot authorize application, production promotion, autonomy, or user actions.
Candidate generation/reasoning is untrusted — LLM text, scores, confidence, or
narrative cannot establish truth, safety, authorization, completion, or causal
efficacy (§13.4). Evidence gates are truthful: UNKNOWN/FAILED/UNAVAILABLE evidence
cannot become PASS; hard-constraint violations deterministically FAIL and cannot be
offset by objective improvements.

## Assurance result

`AssuranceResult` (frozen, construction-validated, content-addressed id) binds to
the exact candidate id, base graph id/revision, provenance revision, and W1
traceability. It carries: a truthful `AssuranceStatus` (PASS/FAIL/UNKNOWN/BLOCKED),
a tuple of `AssuranceGate`s, an `ImpactAnalysis`, a `RiskAssessment`, a
`ReversibilityAssessment`, and the preserved W6 objectives (no scalar score).

## Evidence gates (C2)

`AssuranceGate` (name, status, evidence_ids, detail). Each gate records its
evidence references and a truthful status. `_evidence_to_gate_status` maps a W4
evidence record's observed `TruthState` to a gate status: SUCCESS→PASS, FAILED→FAIL,
UNKNOWN/UNSUPPORTED→UNKNOWN, UNAVAILABLE→BLOCKED. `_aggregate_gate_status` ensures
no PASS emerges from non-PASS evidence.

## Impact + blast radius (C3)

`ImpactAnalysis` identifies affected nodes (the candidate's declared target
subgraph), affected edges (single-hop edges touching targets), boundary interfaces
(declared by the candidate), and dependency reach (direct adjacency, single-hop —
bounded, no unbounded traversal). `BlastRadius` is a conservative level by affected
count.

## Hard-constraint enforcement (C4)

The hard-constraint gate checks each declared hard constraint against the
candidate's target nodes. A violation deterministically FAILs the gate; the
overall result FAILs regardless of objective favorability. Hard constraints
cannot be offset by objective improvements.

## Risk representation (C5)

`RiskItem` (name, severity, uncertainty, mitigation, residual). Risk uncertainty
is **never SUCCESS** — risk is inherently uncertain. Each item has a mitigation or
residual note. `RiskAssessment` is a non-empty collection.

## Causal qualification (C6)

The causal-qualification gate checks whether any W5 hypothesis referenced by the
candidate has intervention-grade support (W5 `SupportKind.INTERVENTION` backed by
a W4 evidence record whose `EvidenceKind` is in `{EXPERIMENT, CANARY, SHADOW,
REPLAY, SIMULATION}`). Observational evidence alone cannot PASS the causal gate —
causal efficacy is never established from narrative or confidence.

## Reversibility / containment (C7)

`ReversibilityAssessment` records whether rollback evidence exists (from the
candidate's declared risks) or whether a documented containment policy applies.
W7 records reversibility; it does NOT execute rollback (W8 owns the lifecycle).

## Multi-objective integrity (C8)

The result preserves the W6 `CandidateProposal.objectives` tuple unchanged — no
scalar authoritative score is introduced. Conflicting objectives remain visible.

## Deterministic, bounded evaluation (C9)

`assure_candidate` is a pure function: identical inputs produce identical results.
Evaluation is finite and bounded — impact is single-hop, gates are a fixed set.

## Truthful failures (C10)

Missing candidate/graph/evidence/hypotheses are explicitly rejected
(`ModelValidationError`). The overall status is FAIL if any gate FAILs; BLOCKED
if any gate BLOCKs; UNKNOWN if any gate is UNKNOWN; PASS only if all gates PASS.

## Traceability + persistence (C11)

Results round-trip through the existing W1 `JsonModelStore` (no new persistence
authority).

## Bounded surface / non-authorization (C12)

`src/sos/assurance.py` exports only W7 symbols. No W8+ (experiment, promotion,
rollback, autonomy, ASK, personalization, realization, self-evolution) symbols.
The result carries no authorization flag.

## Verification scope

Tests cover: candidate binding + provenance, graph-id mismatch rejection, evidence-
backed gate evaluation, UNKNOWN/UNAVAILABLE evidence cannot become PASS, impact
identifies affected nodes + boundary + blast radius, bounded impact (no unbounded
traversal), hard-constraint violation FAILs and cannot be offset by objectives,
risk preserves severity/uncertainty/mitigation, observational evidence cannot become
intervention proof, intervention-grade evidence passes the causal gate,
reversibility recorded not executed, multi-objective integrity (no scalar),
deterministic evaluation, missing candidate/graph/evidence rejection, JSON round-
trip, W8+ boundary enforcement, and non-authorization (no authorized/approved flag).
