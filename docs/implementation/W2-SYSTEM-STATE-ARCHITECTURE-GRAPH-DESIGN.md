# W2 System State / Architecture Graph Design

**Status:** IMPLEMENTED — REVIEW REQUIRED
**Work Order:** `spec/work-orders/W2-system-state-architecture-graph.md`

W2 adds the versioned System State and typed Architecture Graph boundary without implementing recovery, telemetry, search, assurance or experiments.

`SystemState` owns references to implementation, configuration, deployment, policy and environment state and attaches exactly one versioned `ArchitectureGraph`. Every state carries W1 Mission/Value/Context traceability.

`ArchitectureGraph` contains typed nodes, typed edges, boundary contracts and explicit uncertainty. Unknown/failed/unavailable graph facts are represented as truth states rather than empty success.

`SubgraphReplacement` declares the target and replacement subgraphs plus boundary interfaces and invariants. It is a declaration/validation primitive only; W6+ remains responsible for candidate generation and downstream decisioning.

All W2 artifacts use the existing deterministic JSON persistence boundary from W1. No new serialization authority is introduced.

## Verification scope

Tests cover the frozen node/edge vocabulary, broken graph references, duplicate ids, uncertainty truthfulness, System State reference integrity, candidate boundary declarations, and JSON semantic preservation.
