# W3 Implementation Checkpoint

**Work Order:** `W3 — Existing-System Architecture Recovery`
**State:** `WAITING_FOR_ARCHITECT`
**Branch:** `work/w3-architecture-recovery`
**Base SHA:** `801754ab4dcbf5627f68ca65ad7d28973f1aa9de`
**Latest implementation SHA:** `63de2a3d82f20efb35dfe7508f0d1e4a7cf39b1f`

## Dependency proof

W2 is authoritatively merged on `main` as `587201d3e12a10ba9fac6da751d663a40c33dfb9`.

## Scope implemented

- deterministic repository filesystem inventory;
- conservative static source/manifest/deployment classification;
- Python import dependency extraction when repository-local targets resolve;
- graph node/edge provenance tied to repository paths and supplied revision;
- explicit unavailable findings for runtime deployment/environment facts;
- W2 ArchitectureGraph/SystemState output and W1 traceability;
- deterministic recovery result ordering and invariant tests.

## Explicit exclusions

No runtime observation, telemetry ingestion, causal inference, architecture memory, candidate generation/search, graph mutation, assurance, experimentation, promotion/rollback, or authority changes.

## Requirement mapping

| Requirement | Implementation / verification |
|---|---|
| R6 | `recover_repository()` accepts an existing repository root and recovers static structure into W2 state. |
| R7 | Recovered `SystemState` contains implementation/configuration/deployment/policy/environment references and recovered architecture. |
| R8 | Recovery populates W2 typed graph semantics without rewriting architecture authority. |
| R21 | Runtime deployment/environment remain `UNAVAILABLE`; missing live facts are not synthesized. |
| R23 | Recovered nodes and edges retain source-path/revision provenance and explicit uncertainty. |
| R24 | Work Order, design, checkpoint, implementation and tests are repository-resident. |

## Verification

The repository's W2 `.github/workflows/test.yml` workflow runs `python -m pytest` on push and pull request. Public GitHub DNS is unavailable in this execution environment, so no local pass count is asserted. The W3 test suite is deterministic and covers inventory ordering, repository-local import extraction, provenance, unavailable runtime facts and invalid roots.

## Known limitations

- Python dependency extraction intentionally resolves only repository-root module paths; projects using extra source roots are conservatively incomplete rather than falsely connected.
- JSON persistence remains the W1 dictionary wire format.
- Static recovery cannot establish live runtime state; W4 remains responsible for runtime/evidence ingestion.

## Architect disposition requested

Review the exact PR head against W3 scope and frozen architecture. On approval, merge the reviewed head and reconcile W3 completion. W4 remains independently eligible because it depends only on W2.
