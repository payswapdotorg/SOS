# W3 — Existing-System Architecture Recovery

**Status:** READY FOR ARCHITECT DISPATCH
**Dependencies:** W2 merged on `main`
**Governing architecture:** `spec/architecture.md` §§3.5–3.6, 10, 12–13; `spec/sos-meta-model.md`
**Requirements:** R6–R8, R21, R23–R24

## Goal

Recover a useful, explicitly uncertain Architecture Graph and System State from an existing software repository without pretending that inferred facts are authoritative runtime truth.

## Scope

- filesystem/repository source adapter;
- deterministic discovery of source files, manifests and deployment/configuration hints;
- extraction of conservative component/service/interface/data-store/deployment/dependency relationships where directly supported by source evidence;
- explicit unknown/unavailable recovery findings for facts the repository cannot establish;
- mapping recovered structure into W2 `ArchitectureGraph` and `SystemState` artifacts;
- evidence/provenance references back to exact repository paths and revisions;
- deterministic serialization and invariant tests;
- repository-resident recovery report/checkpoint.

## Explicit exclusions

- runtime telemetry or live environment observation (W4);
- causal inference or architecture memory (W5);
- candidate generation/search/ranking (W6);
- assurance, promotion, experimentation and rollback execution (W7–W8);
- silent repair or mutation of the recovered system;
- treating static source inference as proof of runtime behavior;
- redefining frozen architecture or meta-model semantics.

## Acceptance criteria

1. A repository adapter can produce a deterministic inventory from a supplied root.
2. Recovery identifies supported source/manifests without assuming runtime facts that are absent.
3. Recovered nodes/edges use only the frozen W2 vocabulary.
4. Every inferred graph fact has provenance and explicit uncertainty.
5. Missing runtime/deployment information remains `UNKNOWN` or `UNAVAILABLE`, not success.
6. Recovery output is attached to a versioned System State with exact source/revision references.
7. The adapter is deterministic for identical repository inputs.
8. Tests cover path inventory, conservative dependency extraction, provenance, uncertainty and malformed-input behavior.
9. W3 contains no telemetry ingestion, candidate search or experimentation behavior.

## Verification

- focused unit tests;
- deterministic snapshot-style recovery tests;
- static/type checks;
- exact-head verification;
- repository-resident recovery report.

## Required PR evidence

Record exact base/head SHAs, Work Order identity, recovered paths, recovery rules, deterministic verification results, known blind spots, uncertainty classes and requirement mapping. Review-ready state must be persisted before Architect review.
