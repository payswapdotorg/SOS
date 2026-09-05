# W6 Candidate Generation + Bounded Search Design

**Status:** IMPLEMENTED — REVIEW REQUIRED
**Work Order:** `spec/work-orders/W6-candidate-generation-search.md`
**Dependencies:** W3 merged as `6541441…`; W5 merged as `2bfd0f8…`; W2 merged as `587201d3…`; W4 merged as `26060db…`

W6 generates and evaluates candidate architecture changes over the recovered W2/W3
System State / Architecture Graph using W5 causal knowledge, while preserving
explicit uncertainty, conflicting objectives, bounded search, and **non-authorizing**
behavior (architecture §§3.6, 4.5, 6, 9, 13.7).

## Governing principle

A candidate is a **proposal**, not an applied mutation. Candidate generation/reasoning
is untrusted relative to assurance (architecture §13.7: candidate architecture
cannot become production solely because it was generated). Candidate scores/predictions
cannot upgrade truth or authorization; LLM narrative alone cannot establish
correctness (§13.4). Evaluation is multi-objective — no single scalar quality
becomes authoritative (§6, §13).

## Bounded mutation representation

`SubgraphMutation` (frozen, construction-validated) is a W6-own declarative
mutation referencing the base graph by id: `kind`, `base_graph_ref`,
`target_node_ids`, `replacement_node_ids`, `boundary_interface_ids`,
`invariants`. It validates against a recovered `ArchitectureGraph` **without
mutating it** — boundary interfaces are nodes whose contracts the replacement
must preserve (typically interface-type nodes adjacent to the target subgraph);
they must be known graph nodes but need NOT be part of the target subgraph.

## Candidate proposal

`CandidateProposal` (frozen, construction-validated, content-addressed id)
references the base graph + revision, carries a `SubgraphMutation`, multi-objective
predicted effects, rationale, a W1 `TruthfulValue` uncertainty (never SUCCESS —
candidates are predictions, not proven facts), reasoning evidence/hypothesis ids
(W4/W5 references — no second authority), risks, and full W1 traceability.

## Multi-objective evaluation + Pareto

`CandidateObjective` (name, direction, predicted_value, uncertainty — never SUCCESS).
`CandidateEvaluation` (tuple of objectives, no scalar quality field). `dominates()`
implements Pareto dominance accounting for direction (MAXIMIZE/MINIMIZE). `ParetoFrontier.
from_candidates()` computes the deterministic non-dominated set, sorted by id.

## Finite deterministic search

`SearchBounds` (max_candidates, max_depth, max_iterations — all positive integers).
`CandidateSpace` (finite: base graph + revision + traceability + reasoning refs +
finite `available_replacements` tuple of (target, replacement) pairs). `SearchEngine.
search(space)` explores only the finite space within the bounds and returns a
`ParetoFrontier`. Pure function: identical inputs → identical frontier; no network,
no wall-clock, no unbounded recursion.

## Truthfulness (C5)

A candidate's `uncertainty` is **never SUCCESS** (candidates are predictions, not
proven facts). Predicted objective values carry non-SUCCESS uncertainty (typically
UNKNOWN). This prevents candidate scores or LLM text from upgrading truth or
authorization.

## Traceability (C6)

Every candidate records `base_graph_ref` + `base_graph_revision` + `provenance_revision`,
the W4 `reasoning_evidence_ids` and W5 `reasoning_hypothesis_ids` used in generation,
and full W1 Mission/Value/Context traceability. `validate(known_graph=,
known_evidence_ids=, known_hypothesis_ids=)` resolves references against actual
W2/W4/W5 records.

## Serialization

W6 objects round-trip through the existing W1 `JsonModelStore` (no new persistence
authority) (C9).

## Bounded surface (C10)

`src/sos/candidates.py` exports only W6 symbols. No W7+ (assurance, experimentation/
promotion/rollback, autonomy/ASK, personalization, realization, self-evolution)
symbols.

## Verification scope

Tests cover: deterministic identity (identical/differing mutation), bounded mutation
validation without canonical mutation, unknown target/boundary rejection, finite
deterministic search termination within bounds, unbounded/zero bounds rejection,
Pareto dominance, Pareto frontier excludes dominated candidates, no scalar quality
field, candidate scores cannot upgrade truth (never SUCCESS), SUCCESS-without-
intervention rejected, graph/evidence/causal traceability, missing-context rejection,
deterministic dedup/order, explicit rejection (missing graph ref, empty objectives,
empty mutation targets), JSON round-trip, W7+ boundary enforcement, and validation
against known graph + evidence + causal records.
