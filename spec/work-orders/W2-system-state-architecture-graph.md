# W2 — System State + Architecture Graph

**Status:** READY FOR ARCHITECT DISPATCH
**Dependencies:** W1 merged on `main`
**Governing architecture:** `spec/architecture.md` §§3.5–3.6, 4, 6, 10, 12–13; `spec/sos-meta-model.md`
**Requirements:** R7–R8, R23–R24

## Goal

Implement the authoritative, versioned System State and Architecture Graph representation required for later recovery, evidence, candidate search and assurance. The representation must preserve architecture as a versioned hypothesis/projection of System State and must make local subgraph changes explicit and boundary-aware.

## Scope

- versioned System State entity and immutable revision identity;
- typed Architecture Graph nodes and edges from the frozen meta-model;
- boundary contracts and graph uncertainty representation;
- implementation/configuration/deployment/policy/environment references as state links;
- active experiment references without implementing experimentation;
- local candidate/subgraph replacement declaration sufficient for downstream Work Orders;
- graph/state validation and serialization round trips;
- traceability to Mission/Value/Context from W1;
- deterministic invariant tests and repository-resident evidence.

## Explicit exclusions

- architecture recovery from an existing repository/runtime (W3);
- telemetry/evidence ingestion graph (W4);
- causal knowledge or architecture memory (W5);
- candidate generation/search/ranking (W6);
- assurance/promotion/experimentation execution (W7–W8);
- redefining frozen architecture or meta-model semantics;
- making an architecture graph a semantic authority above System State.

## Acceptance criteria

1. System State has stable identity, version, and explicit references for architecture, implementation, configuration, deployment, policy, environment and active experiments.
2. Architecture Graph is typed, versioned and attached to a System State.
3. Supported node types include capability, service, component, data store, interface, deployment, trust boundary, policy, model, adapter and external dependency.
4. Supported edge types include call, data-flow, dependency, trust, deployment, runtime-interaction, realizes, observes, influences, owns and constrains.
5. Every local candidate/subgraph declaration identifies the target subgraph, replacement subgraph and boundary/interface invariants.
6. Graph uncertainty is explicit and cannot masquerade as authoritative certainty.
7. System State and graph artifacts carry Mission/Value/Context traceability from W1.
8. Serialization/deserialization is deterministic and preserves semantic distinctions.
9. Tests reject invalid node/edge types, broken references, missing boundary invariants and non-versioned state transitions.
10. W2 implementation remains free of runtime recovery and telemetry behavior.

## Verification

- focused unit/integration tests for graph/state invariants;
- type/static checks;
- serialization/deserialization round trips;
- negative tests for broken references and boundary mismatch declarations;
- exact-head verification and repository-resident evidence.

## Required PR evidence

Record exact base SHA, exact head SHA, PR identity, commands/results, requirement-to-implementation-to-test mapping, known limitations, and risk/rollback considerations. Review-ready state must be persisted before Architect review.
