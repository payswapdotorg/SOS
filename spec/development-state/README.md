# SOS Development State — Authority Declaration

`spec/development-state/` contains repository-resident implementation governance state so a fresh Architect/worker can recover without conversation history.

## Authority classes

| Artifact | Role |
|---|---|
| `implementation-state.json` | Canonical machine task state for this frozen roadmap |
| `current-state.md` | Human-readable projection; informational only |
| Work Orders under `spec/work-orders/` | Task scope, dependencies, acceptance and evidence requirements |
| `spec/implementation-roadmap.md` | Human-readable sequencing/progress authority |
| Git history / live `main` | Completion authority |

## Required invariants

1. Task dependencies are acyclic and reference known Work Orders.
2. A task cannot be complete without an actual Architect-authorized Git merge.
3. An unmerged branch is never a dependency.
4. Exact base/head SHAs are preserved at handoff and review boundaries.
5. Machine state never overrides frozen architecture or Work Orders.
6. Derived navigation fields never authorize work.
7. Roadmap and machine state must be reconciled after governed progress changes.
8. Evidence records failed/unavailable/unknown states honestly.
9. Self-evolution cannot bypass the SOS Constitution or assurance boundary.

## Recovery

`live main → roadmap → implementation-state → selected Work Order → dependency merge evidence → same PR/head → review findings → exact-head verification → evidence → frontier`
