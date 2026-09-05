# W4 — Evidence / Observability

**Status:** DISPATCHED BY ARCHITECT
**Dependencies:** W2 merged on `main` as `587201d3e12a10ba9fac6da751d663a40c33dfb9`; W3 merged on `main` as `6541441bb706ef1f27b2c38b9eb930433641b14b`
**Governing architecture:** `spec/architecture.md` §§3.5–3.7, 4, 10, 12–13; `spec/architecture-lock.md`
**Requirements:** R7, R9, R21, R23–R24

## Goal

Establish the SOS evidence/observability boundary so observations can be attached to the recovered System State and Architecture Graph with exact provenance and truthful truth states, without pretending that telemetry itself establishes causality or authorization.

## Scope

- evidence records for observations, measurements, logs, traces, tests and source/revision observations;
- deterministic evidence identity and stable ordering;
- explicit linkage from evidence to System State / Architecture Graph entities and mission/context traceability;
- preservation of `SUCCESS`, `FAILED`, `UNKNOWN`, `UNAVAILABLE` and empty observations as distinct states;
- evidence provenance including source, observed subject, time/context where actually supplied, and exact implementation revision where applicable;
- static/test evidence ingestion that does not invent runtime facts;
- supported OpenTelemetry-shaped telemetry ingestion boundary where directly supplied, without requiring a live collector;
- repository-resident checkpoint evidence and deterministic tests.

## Explicit exclusions

- causal inference or causal confidence updates (W5);
- architecture memory/priors (W5);
- candidate generation/search or mutation (W6);
- assurance verdicts or safety gates (W7);
- experimentation, promotion, rollback (W8);
- autonomy/action execution or ASK decisions (W9);
- redefining W2 System State / Architecture Graph semantics;
- treating telemetry as a complete evidence model;
- fabricating runtime/deployment/environment observations from static artifacts.

## Owning architecture authorities

`spec/architecture.md`, `spec/architecture-lock.md`, W1/W2/W3 contracts, and the repository's frozen truth-state/evidence boundaries.

## Allowed implementation surfaces

- `src/sos/` evidence/observability-related implementation;
- `tests/` W4 tests;
- `docs/implementation/W4-EVIDENCE-OBSERVABILITY-DESIGN.md`;
- `spec/development-state/W4-checkpoint.md`.

## Forbidden authority surfaces

Do not modify the Constitution, frozen architecture, architecture lock, requirements, roadmap, W1/W2/W3 semantics, `implementation-state.json` except for Architect reconciliation, or create a competing authority/evidence model.

## Acceptance criteria

1. Evidence records have deterministic identity and preserve exact provenance.
2. Evidence can reference recovered System State / Architecture Graph subjects without changing their semantic authority.
3. Truthful states remain distinct: successful observation, failure, unknown, unavailable, and genuinely empty observation are not conflated.
4. Evidence does not claim runtime reality when only static/repository evidence exists.
5. Mission/Value/Context traceability is preserved through evidence records.
6. Repeated ingestion of identical evidence is deterministic and does not create random semantic identity.
7. Invalid subject references and malformed evidence are rejected by tests.
8. W4 introduces observation/evidence only: no causal, candidate, assurance, experiment, promotion, rollback, or execution semantics.

## Deterministic verification

`python -m pytest`

Add focused tests for provenance, subject references, truth-state separation, deterministic identity/order, duplicate ingestion, invalid evidence, and explicit unavailable runtime observations.

## Real-system/evaluation evidence

Live telemetry is not required for this bounded repository implementation slice. Any unavailable live/runtime observations must remain explicitly unavailable rather than synthesized.

## Risk / rollback

Low-to-moderate semantic risk: evidence contracts become inputs to later assurance/causal stages. Rollback is an ordinary Git revert; no production data migration or runtime service is introduced by W4.

## Required persisted evidence

Before review, persist exact base SHA, exact head SHA, PR identity, verification results, requirement-to-test mapping, known limitations, and risk/rollback status in the W4 checkpoint.

## Completion / reconciliation

Worker stops at `WAITING_FOR_ARCHITECT`. Completion occurs only after Architect approval, actual Git merge, and canonical reconciliation. W5 remains blocked until W4 is authoritatively merged.
