# PREP-W11 — Provider-Neutral Execution Substrate Preparation

**Status:** DISPATCHED PREPARATION SPIKE — NOT A ROADMAP COMPLETION
**Owner:** Worker B
**Related roadmap Work Order:** W11 — Greenfield System Realization
**Purpose:** Prepare the execution boundary so W11 can begin immediately after its frozen sequencing gate opens.

## Traceability

- Architecture: §§4, 8, 9, 10, 12, 13 of `spec/architecture.md`
- Requirements: R6, R7, R8, R9, R13, R14, R15, R18, R22, R23, R24
- Dependencies already authoritative: W1, W2, W9
- No unmerged W10 code may be treated as a dependency.

## Scope

Define a provider-neutral execution contract that can represent:

- execution intent and bounded action scope;
- selected provider and provider capabilities;
- immutable source/system revision references;
- workspace/environment context;
- pre-execution W9 authorization reference;
- upstream W7/W8 assurance/evaluation/promotion references where applicable;
- execution lifecycle;
- side-effect receipt;
- stdout/stderr/log references;
- changed revision references;
- failure/unknown/unavailable/unsupported outcomes;
- rollback/recovery references;
- evidence provenance.

The preparation MAY add design/specification tests and diagrams. It MUST NOT add production external side effects.

## Required design shape

The design should establish one semantic boundary similar to:

`ExecutionRequest → ExecutionProvider → ExecutionReceipt → Evidence`

The provider executes; SOS remains the authority.

## Acceptance criteria

1. No provider can authorize itself.
2. An execution request cannot bypass W9 authority.
3. Provider capability is distinguishable from policy authorization.
4. Execution receipt preserves exact revision/environment/time provenance.
5. Failed/unknown/unavailable/unsupported execution outcomes remain distinct.
6. Rollback/recovery is represented as governed behavior, not free-form narrative.
7. OpenMuse, GitHub Actions, SSH/VM, and future providers can implement the same contract without changing SOS core semantics.
8. The design identifies where W7 assurance and W8 promotion evidence bind to execution.
9. Deterministic local contract tests are possible without a real provider.

## Explicit exclusions

- No live deployment.
- No browser automation.
- No OpenMuse integration code yet.
- No Code-OSS extension work.
- No changes to frozen roadmap/architecture/constitution.
- No W11 completion claim.

## Deliverables

- execution contract design;
- provider capability matrix;
- lifecycle/state model;
- failure/receipt schema;
- deterministic contract tests or test plan;
- integration handoff for W11.
