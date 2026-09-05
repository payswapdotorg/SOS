# W3 — Existing-System Architecture Recovery

**Status:** DISPATCHED BY ARCHITECT
**Dependencies:** W2 merged on `main` as `587201d3e12a10ba9fac6da751d663a40c33dfb9`
**Governing architecture:** `spec/architecture.md` §§3.5–3.7, 10, 12–13; `spec/architecture-lock.md`
**Requirements:** R6–R8, R21, R23–R24

## Goal

Recover an existing software repository into the authoritative W2 System State / Architecture Graph boundary without pretending static repository evidence proves runtime reality.

## Scope

- deterministic repository inventory;
- conservative static classification of source, manifests, configuration and deployment-related artifacts;
- repository-local dependency extraction where the relationship is directly supported;
- W2 ArchitectureGraph/SystemState population with explicit uncertainty;
- source-path and exact repository-revision provenance on recovered facts;
- explicit unavailable/unknown findings for runtime, deployment and environment facts not directly observable;
- deterministic ordering and repository-resident evidence.

## Explicit exclusions

- runtime telemetry or live environment access;
- causal inference or architecture memory;
- candidate generation/search or graph mutation;
- assurance, experimentation, promotion or rollback;
- autonomous authority or action execution;
- redefining W2 graph/System State semantics or frozen architecture.

## Owning architecture authorities

`spec/architecture.md`, `spec/architecture-lock.md`, W2 System State / Architecture Graph, and the frozen truth-state/evidence boundaries.

## Allowed implementation surfaces

- `src/sos/` recovery-related implementation;
- `tests/` W3 tests;
- `docs/implementation/W3-ARCHITECTURE-RECOVERY-DESIGN.md`;
- `spec/development-state/W3-checkpoint.md`.

## Forbidden authority surfaces

Do not modify the Constitution, frozen architecture, architecture lock, requirements, roadmap, W1/W2 semantics, or create a competing evidence/authority model.

## Acceptance criteria

1. An explicit repository root is recovered deterministically.
2. Directly supported static facts become typed W2 graph/state facts with provenance.
3. Repository-local dependency relationships are added only when deterministically resolvable.
4. Runtime/deployment/environment gaps remain explicit `UNKNOWN`/`UNAVAILABLE` evidence and are never converted into successful facts.
5. Recovered output carries Mission/Value/Context traceability through W2 contracts.
6. Identical repository bytes plus the same supplied revision produce deterministic semantic output.
7. Invalid roots and broken references are rejected by tests.
8. No runtime, candidate, assurance, experiment, promotion, rollback, or execution side effects are introduced.

## Deterministic verification

`python -m pytest`

Add focused negative/invariant tests covering ordering, provenance, unresolved runtime facts and invalid repository roots.

## Real-system/evaluation evidence

No live deployment evidence is required for this static recovery slice. Any unavailable runtime/deployment facts must be recorded as such.

## Risk / rollback

Low execution risk: W3 is a read/recovery semantic boundary and must not mutate recovered production state. Rollback is ordinary Git revert of the W3 PR.

## Required persisted evidence

Before review, persist exact base SHA, exact head SHA, PR identity, verification results, requirement-to-test mapping, known limitations and risk/rollback status in the W3 checkpoint.

## Completion / reconciliation

Worker stops at `WAITING_FOR_ARCHITECT`. Completion occurs only after Architect approval, actual Git merge, and canonical reconciliation. W4 remains independently eligible because it depends only on W2.
