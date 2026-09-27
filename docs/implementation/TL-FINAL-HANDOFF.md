# SOS — Final LLM Tech Lead Handoff

**Date:** 2026-09-27
**Role:** LLM Tech Lead / Product Architect handoff
**Authority:** Repository + actual Git facts

## 1. Mission and architectural stance

SOS is a mission-governed operating system for continuously improving the realization of software systems.

The frozen semantic loop is:

`Constitution → Mission → Value Model → Context → System State → Evidence → Hypothesis → Candidate State → Assurance → Experiment → Promotion/Rollback → Learning`

LLMs are proposal/reasoning mechanisms. They are never a fifth authority class.

## 2. Authoritative implementation frontier

W0 through W9 are authoritatively merged.

- W9 merge: `203cfb7590bd25244cabf3cc7299dd192b00948d`
- Live main must be re-read before every new branch/base decision.
- W10 is the current roadmap frontier.
- W10 PR: #17
- W10 branch: `work/w10-personalization-platform`
- Latest setup artifact chain ended at `2e20902183492c9f00a92eba92129d97879b6eb9`.

The repository machine state remains W10-dispatched. Preparation spikes below are intentionally not recorded as roadmap completion.

## 3. Current W10 reality

The W10 implementation exists on PR #17 and has passed deterministic CI on recent exact heads, but it is not merged.

The PR originally targeted base `d2b813eb32085fdc5e12180da5f2f141b13036e7`. The Architect setup commits have advanced main, so the PR is now stale-base.

**Worker A must refresh/rebase/update the W10 branch against live main before another Architect review.**

The next review must verify:

1. Alternative selectors are true predicates against actual context values, not merely SUCCESS flags.
2. FAILED context truth states cannot silently preserve ACT.
3. W9 ASK/REJECT and all policy ceilings remain authoritative.
4. Platform constraints explicitly narrow an already-authorized policy.
5. All W10 checkpoint/design/PR evidence records the exact corrected head.
6. Exact-head CI is green.

## 4. Three-worker operating model

### Worker A — W10 closure

Owns the existing W10 PR only.

Goal:

`W10 correction → exact verification → WAITING_FOR_ARCHITECT`

No new PR and no merge by the worker.

Primary artifact:

`spec/work-orders/W10-personalization-platform.md`

Coordination:

`spec/development-state/WORKER-DISPATCH.md`

### Worker B — W11 execution-substrate preparation

Artifact-only preparation for the next realization gate.

Primary artifact:

`spec/work-orders/PREP-W11-execution-substrate.md`

Define a provider-neutral contract of the form:

`ExecutionRequest → ExecutionProvider → ExecutionReceipt → Evidence`

Required properties:

- W9 authority cannot be bypassed.
- Provider capability is separate from authorization.
- Exact source revision/environment/time provenance is preserved.
- Failure/unknown/unavailable/unsupported outcomes stay distinct.
- Rollback/recovery is governed.
- Multiple providers can implement the same contract.

No live execution yet.

### Worker C — OpenMuse + Code-OSS preparation

Primary artifact:

`spec/work-orders/PREP-provider-cockpit.md`

OpenMuse is being evaluated as a replaceable execution provider for browser, terminal, workspace, computer and durable-task execution.

Code-OSS is being evaluated as a replaceable engineering cockpit/client surface for mission, system state, evidence, candidates, assurance, experiments, ASK and worker sessions.

Neither is allowed to become an SOS authority.

## 5. Target architecture after preparation

```
                    ┌─────────────────────┐
                    │       SOS CORE      │
                    │ mission / evidence  │
                    │ assurance / policy  │
                    │ candidate evolution │
                    └──────────┬──────────┘
                               │
                       control/API seam
                               │
             ┌─────────────────┴─────────────────┐
             │                                   │
      execution providers                   client surfaces
             │                                   │
      ┌──────┼────────┐                 ┌────────┴───────┐
      │      │        │                 │                │
   OpenMuse GitHub   VM/CI          Code-OSS        Web/Mobile
```

The central architectural rule is:

**Providers execute authorized bounded requests; SOS decides whether they are authorized.**

**Clients display/request SOS state; clients do not define SOS semantics.**

## 6. Sequencing rule

Do not silently turn the preparation spikes into W11/W12/W13 completion.

The frozen program remains:

`W10 → W11 → W12 → W13 → W14 → W15`

Preparation is allowed in parallel because it does not claim or depend on unmerged implementation.

When W10 is merged, the TL should convert the strongest preparation artifact into the next bounded implementation Work Order and dispatch against a freshly verified main SHA.

## 7. Review discipline

Before every implementation/review action:

`live main → canonical state → Work Order → exact dependencies → implementation → exact verification → Architect review`

Never:

- use chat history as state;
- use an unmerged branch as a dependency;
- treat CI green as semantic approval;
- let a provider authorize itself;
- let context widen W9 authority;
- treat missing/failed data as success;
- merge a stale base.

## 8. Immediate TL priorities

1. Get Worker A to refresh PR #17 against live main and close the W10 findings.
2. Have Worker B produce the provider-neutral execution contract and contract tests.
3. Have Worker C produce the OpenMuse adapter + Code-OSS cockpit integration design.
4. Review B/C artifacts together for duplicated semantics and authority leakage.
5. After W10 merges, authorize the smallest W11 implementation slice using the prepared contract.

## 9. Success condition for this handoff

A fresh TL should be able to recover the complete operating state from:

- `ARCHITECT_START_HERE.md`
- `AGENTS.md`
- frozen architecture/requirements/roadmap
- `spec/development-state/implementation-state.json`
- `spec/development-state/WORKER-DISPATCH.md`
- `docs/implementation/TL-3-WORKER-COORDINATION.md`
- the active W10 PR
- `PREP-W11-execution-substrate.md`
- `PREP-provider-cockpit.md`

without requiring conversation history.
