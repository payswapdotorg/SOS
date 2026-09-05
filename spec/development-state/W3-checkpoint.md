# W3 Implementation Checkpoint

**Work Order:** `W3 — Existing-System Architecture Recovery`
**State:** `WAITING_FOR_ARCHITECT`
**Branch:** `work/w3-architecture-recovery`
**Base SHA:** `801754ab4dcbf5627f68ca65ad7d28973f1aa9de`

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
| R6 | `recover_repository()` accepts a supplied existing repository root and recovers static structure into W2 state. |
| R7 | Recovered `SystemState` contains implementation/configuration/deployment/policy/environment references and recovered architecture. |
| R8 | Recovery populates W2 typed graph semantics; it does not rewrite architecture authority. |
| R21 | Runtime deployment/environment remain `UNAVAILABLE`; inference does not collapse missing facts into success. |
| R23 | Recovered facts retain source-path and repository-revision provenance plus uncertainty. |
| R24 | Work Order, design, checkpoint and tests are repository-resident. |

## Verification

The repository already contains the W2 `.github/workflows/test.yml` pytest workflow. This execution environment cannot access GitHub Actions logs directly and cannot resolve public GitHub DNS, so no local test claim is being fabricated. The W3 tests are deterministic and are configured for the repository CI workflow.

## Known limitations

- Static dependency extraction currently targets Python imports whose module paths resolve directly from the repository root; projects with additional source roots may yield conservative omissions rather than false dependencies.
- JSON persistence remains the W1 canonical dictionary wire format rather than typed-object deserialization.
- Static recovery cannot establish live runtime state, which remains explicitly unavailable until W4.

## Architect disposition requested

Review the exact PR head against W3 scope and frozen architecture. On approval, merge the reviewed head and reconcile W3 completion. W4 remains independently eligible because both W3 and W4 depend only on W2.
