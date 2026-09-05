# W6 Candidate Generation / Search Design

W6 is the search boundary between a known System State and downstream assurance.

`generate_candidates()` accepts explicit `SubgraphReplacement` declarations and metric sets, validates them against the W2 graph, and emits immutable `CandidateState` proposals. The base graph/system state is never mutated.

Each candidate exposes benefit, cost, risk, uncertainty, reversibility, blast radius and memory-prior metadata. Ranking is Pareto-based: no candidate is rejected merely because another candidate is better on one conflicting dimension. Deterministic ordering supplies stable presentation without inventing a scalar architecture authority.

`ArchitectureMemory` can raise or lower candidate priority only through `memory_prior`; it never proves correctness or authorizes execution.

A `SearchBudget` hard-bounds the number of generated candidates. W6 has no assurance, experiment, promotion, rollback or autonomous execution semantics.
