# W5 Causal Knowledge + Architecture Memory Design

**Status:** IMPLEMENTED — REVIEW REQUIRED
**Work Order:** `spec/work-orders/W5-causal-knowledge-memory.md`
**Dependencies:** W4 merged as `26060db57c24ba8b36315c1005466046810c5163`; W2 merged as `587201d3…`; W3 merged as `6541441…`

W5 represents **causal knowledge and architecture memory** over the W2 System
State / Architecture Graph using W4 evidence, while keeping causal claims
explicitly uncertain, provenance-backed, versioned, and **non-authorizing**
(architecture §§3.8–3.9, §13.4–3.5).

## Governing principle

A causal claim is a hypothesis, not a fact. Observation is not intervention;
correlation is not causation; an LLM narrative alone cannot establish causal
efficacy. W5 represents each causal claim at exactly the confidence its
supporting evidence warrants, reusing W1 `TruthState` / `TruthfulValue` and W4
`Evidence` records as the sole evidence authority.

## Causal hypothesis

`CausalHypothesis` (frozen dataclass, construction-validated) links a cause
subject to an effect subject with:

- `relation_type` — the frozen `CausalRelationType` vocabulary (influences,
  constrains, realizes, observes, owns);
- `direction` — positive / negative / neutral;
- `status` — the lifecycle `proposed → supported → confirmed | rejected`;
- `uncertainty` — a W1 `TruthfulValue`; the hypothesis is never silently certain;
- `supporting_evidence` — a tuple of `EvidenceSupport` references to W4 evidence
  ids + how each supports (observational or intervention);
- `provenance_revision` — the exact repository revision the claim pertains to;
- `traceability` — full W1 Mission/Value/Context traceability.

### Status authority gating

Promotion to `confirmed` (a causal certainty state) requires at least one
intervention-grade supporting evidence record (architecture §13.4: intervention
evidence outranks observational correlation for causal claims). Observation-only
support cannot reach `confirmed`; it may reach `supported` with non-SUCCESS
uncertainty.

## Evidence support + observation vs intervention

`EvidenceSupport` references a W4 evidence id and declares `support_kind`:

- `OBSERVATIONAL` — observation-only support; cannot establish intervention
  efficacy; must not carry `InterventionMetadata`.
- `INTERVENTION` — intervention-grade support; **requires** explicit
  `InterventionMetadata` (intervention_id, intervention_kind, applied_at,
  revision, environment) — provenance actually supplied by the source.

An observation-only evidence id cannot be encoded as intervention support; the
constructor rejects it.

## Truthful uncertainty (C4)

When the caller supplies the observed result states (`known_evidence_results`):
evidence whose observed result is `UNKNOWN` / `FAILED` / `UNAVAILABLE` cannot
back a `SUCCESS` (positive) causal claim. Absence of evidence never becomes
causal support. Contradictory hypotheses (e.g. positive vs negative direction
on the same subjects) coexist with distinct identities — neither is silently
deleted.

## Deterministic identity

`_hypothesis_id` is a content-addressed SHA-256 over `(cause_subject,
effect_subject, relation_type, direction, rationale, provenance_revision,
sorted(supporting_evidence ids + support_kind))`. Identical claims with
identical supporting evidence ⇒ identical id (C1); differing relation type,
direction, subjects, or supporting evidence ids ⇒ distinct ids.

## Causal knowledge graph

`CausalKnowledgeGraph` is a deterministically-ordered, deduplicating collection:

- `ingest(hypothesis)` returns a new graph; identical hypotheses deduplicate by
  id (idempotent, C6); hypotheses remain sorted by id;
- `by_subject(subject)` indexes hypotheses touching a subject;
- `validate(known_evidence_ids=, known_evidence_results=)` rejects unknown
  evidence references and enforces truthful uncertainty.

## Architecture memory — versioned projection, never a replacement

`ArchitectureMemory` is a versioned projection of learned hypotheses about a
recovered graph:

- `graph_ref` references the W2/W3 Architecture Graph by id — memory never
  mutates the canonical graph (C5);
- hypotheses are explicitly uncertain knowledge (priors), never silent
  replacements for recovered architecture facts (C8);
- `validate(known_graph_id=, …)` rejects a `graph_ref` that does not match the
  known recovered graph.

## Serialization

W5 objects round-trip through the existing W1 `JsonModelStore` (deterministic
`json.dumps(..., indent=2, sort_keys=True)`). No new persistence/serialization
authority is introduced (C9).

## Bounded surface (C10)

`src/sos/causal.py` exports only W5 symbols: `CausalHypothesis`,
`CausalKnowledgeGraph`, `CausalRelationType`, `EvidenceSupport`,
`InterventionMetadata`, `SupportKind`, `ArchitectureMemory`. No W6+ symbols
(candidate/search, assurance, experimentation/promotion/rollback, autonomy/ASK,
personalization) are introduced.

## Verification scope

Tests cover: deterministic identity (identical / differing semantics / differing
evidence); evidence-backed support (unknown evidence rejected, unsupported claim
as explicit hypothesis, unsupported + SUCCESS rejected); observation vs
intervention (observation cannot be intervention, intervention requires
metadata); truthful uncertainty (non-SUCCESS evidence cannot support SUCCESS
claim; contradictions coexist); no authority mutation (canonical graph
untouched); deterministic memory (idempotent ingest, sorted ordering);
provenance/traceability (evidence ids + revision + W1 traceability, missing
context rejected); architecture-memory-as-projection (versioned, graph_ref
mismatch rejected); JSON round-trip; W6+ boundary enforcement; status lifecycle
(observation-only cannot reach `confirmed`, intervention-backed can).
