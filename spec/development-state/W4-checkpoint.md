# W4 Implementation Checkpoint

**Work Order:** `W4 — Evidence + Observability Fabric`
**State:** `WAITING_FOR_ARCHITECT`
**Branch:** `work/w4-evidence-observability`
**Base SHA:** `b476216ab8e627cd03c0ad7a0c1aa424714dcbbe`
**Latest implementation SHA:** `8b2e2e27a7a1550efba2e0056039dae13324b964`

## Dependency proof

W2 is authoritatively merged as `587201d3e12a10ba9fac6da751d663a40c33dfb9`. W3 is also merged as `713264759bc804e0cfec0f36e06801e3338e98f4`, but W4 does not depend on W3.

## Scope implemented

- typed EvidenceKind vocabulary;
- explicit observational/intervention EvidenceMode;
- EvidenceRecord with source/subject/time/environment/result/provenance/confidence/availability/traceability;
- append-only EvidenceStore with deterministic export;
- collector-neutral TelemetryEventEnvelope preserving source/resource/time/attributes;
- W3 recovery-to-static-analysis evidence adapter;
- deterministic invariant tests.

## Explicit exclusions

No causal inference, architecture memory, candidate search, assurance, promotion, experimentation execution, or authority changes.

## Requirement mapping

| Requirement | Implementation / verification |
|---|---|
| R9 | Evidence records link source, subject, revision, timestamp and environment with durable serialization. |
| R10 | `EvidenceMode` distinguishes observational from intervention evidence; W4 does not infer causality. |
| R21 | TruthfulValue states and evidence availability are preserved distinctly. |
| R23 | Provenance and traceability are mandatory. |
| R24 | Work Order, design, checkpoint, implementation and tests are repository-resident. |

## Verification

`.github/workflows/test.yml` executes `python -m pytest`. The current environment cannot resolve public GitHub DNS, so local execution is unavailable and no unverified pass count is claimed.

## Known limitations

- Typed-object reconstruction from JSON remains deferred.
- Live OpenTelemetry ingestion/collector integration is represented only by a stable event envelope; actual runtime adapters require environment access and remain bounded by this W4 interface.
- Causal interpretation remains explicitly deferred to W5.

## Architect disposition requested

Review exact PR head, verify CI, and merge only the reviewed head. After merge, W5 becomes eligible.
