# W5 Causal Knowledge / Architecture Memory Design

W5 separates causal hypotheses from evidence and from memory.

A `CausalHypothesis` records cause, mechanism, effect, context, expected direction/magnitude, confidence and supporting evidence references. It does not manufacture causal proof.

High-impact eligibility requires at least one referenced `EvidenceRecord` marked `INTERVENTION`. Observational records remain valid evidence for hypothesis formation but cannot alone satisfy the high-impact causal gate.

`ArchitectureMemory` stores durable experience: context signature, candidate pattern, predictions, observations, outcome, learned rule, provenance and confidence. Memory is prior experience, not proof.

Both collections are append-only and exported deterministically. Candidate generation and assurance remain downstream responsibilities.
