# W1 Mission / Value / Context Design

**Status:** IMPLEMENTED — REVIEW REQUIRED
**Work Order:** `spec/work-orders/W1-mission-value-context-model.md`
**Architecture:** SOS Architecture v1.0, §§3.2–3.4, 5–8
**Requirements:** R1–R5, R15–R18, R21–R22

## Decision

W1 is implemented as a small Python domain boundary under `src/sos/` with no runtime dependencies. The boundary is deliberately limited to Mission, Value Model, Context, Autonomy Policy, Decision/ASK, truthful read states, traceability, validation and deterministic JSON persistence.

## Mission

`Mission` carries stable identity, owner authority, version, statement, goals, desired outcomes, stakeholders, measures, assumptions, ambiguities, status, parent version and revision history.

Revision is explicit:

`ACTIVE → PROPOSED_REVISION → ACTIVE`

Approval requires the mission authority. There is no telemetry or inference path that mutates mission intent.

## Value Model

`ValueModel` owns business-model data and typed objectives, budgets, incentives, opportunities and constraints. Constraints are classified as `HARD`, `SOFT`, `RISK` or `PREFERENCE`; the `hard` boolean is validated against the class so an implementation cannot accidentally represent a soft constraint as hard.

Value artifacts carry traceability to Constitution and Mission and do not become a higher-order authority.

## Context

`Context` contains extensible dimensions for user, cohort, device, platform, environment, workload, geography, time and regulatory context. Each value is wrapped in `TruthfulValue`, preserving `SUCCESS`, `EMPTY`, `FAILED`, `UNKNOWN`, `UNSUPPORTED` and `UNAVAILABLE` as distinct states.

## Autonomy and ASK

`AutonomyPolicy` contains action/environment-specific rules for minimum confidence, maximum risk, reversibility, blast radius and human approval.

`decide(...)` evaluates the requested action against policy. An action without sufficient authority is not treated as authorized; the result becomes `ASK` and requires a complete `AskPayload` containing the exact decision, alternatives, evidence quality, uncertainty and trade-offs.

## Persistence boundary

`JsonModelStore` provides deterministic UTF-8 JSON serialization for W1 artifacts. It does not infer missing state or collapse non-success truth states into values.

## Explicit non-scope

This slice does not implement architecture graph/state recovery, telemetry/evidence graph, causal knowledge, candidate generation, assurance, experimentation, promotion or rollback. Those remain downstream Work Orders.

## Verification

Local deterministic suite executed from the implementation worktree:

```text
python -m pytest
8 passed in 0.11s
```

Coverage includes explicit mission approval, invalid authority transition rejection, typed constraints, truthful state distinctions, contextual dimensions, unauthorized-action-to-ASK conversion, authorized ACT, JSON round-trip and value-model traceability.
