# SOS Agent Operating Contract

**Status: FROZEN GOVERNANCE ARTIFACT**

The SOS repository is the sole durable source of truth for product architecture, requirements, implementation scope, progress, verification evidence, and recovery. Conversation history, agent memory, pasted summaries, PR prose, and unstored plans are non-authoritative.

## Mandatory bootstrap

1. Read `README.md`.
2. Read `spec/architecture.md`.
3. Read `spec/architecture-lock.md`.
4. Read `spec/requirements.md`.
5. Read `spec/implementation-roadmap.md`.
6. Read `docs/implementation/SOS-IMPLEMENTATION-PROCESS.md`.
7. Read `docs/research/research-basis.md` when architectural interpretation or research-backed rationale is needed.
8. Inspect live GitHub `main`, open PRs, commits, CI, and persisted evidence before implementation or review.

## Authority rules

- Frozen architecture meaning belongs to `spec/architecture.md` and `spec/architecture-lock.md`.
- Product requirements belong to `spec/requirements.md` and governed mission/value artifacts introduced by implementation.
- Implementation sequencing/progress belongs to `spec/implementation-roadmap.md` plus its explicitly declared machine-state counterparts.
- Work authorization belongs to a selected Work Order.
- Actual implementation facts belong to Git branches, commits, PRs, CI, and persisted evidence.
- Actual completion is the Architect-authorized Git merge followed by canonical reconciliation.
- Derived status/frontier fields never authorize work.

## Repository-only rule

If an important fact exists only in conversation, persist it in the appropriate repository artifact before relying on it. If repository artifacts disagree, stop and reconcile them. Never guess.

## Architecture freeze

Ordinary implementation work may not redefine the mission model, architecture authority, system-state semantics, assurance boundary, autonomy/authority model, evidence semantics, or promotion protocol. Use the governed architecture-change process when required.

## Implementation discipline

Implement one bounded Work Order slice per branch/PR unless a roadmap gate explicitly defines an integration slice.

Before coding:

1. re-read live `main`;
2. determine the eligible Work Order from repository state;
3. verify merged dependencies by actual Git evidence;
4. read the Work Order and relevant contracts;
5. inspect implementation and tests;
6. write a failing behavioral test first for new behavioral invariants where practical.

Then implement the smallest conforming change, run deterministic verification, run required real-system/evaluation evidence, record exact revisions, submit for Architect review, and stop at `WAITING_FOR_ARCHITECT` when review-ready.

## No silent autonomy

The worker may propose, implement, test, checkpoint, and respond to review findings within its authorized scope. It may not redefine the mission, lower an autonomy threshold, disable safety constraints, merge its own work, self-approve, invent evidence, or create successor work.

## Completion

Code existing, tests passing, CI green, a PR being open, or an agent saying “done” does not establish completion. Completion requires the governing review/approval gate, actual Git merge evidence, and post-merge reconciliation.

## Recovery

Resume from:

`live main → roadmap → machine state → Work Order → dependency merge evidence → same PR/head → review findings → exact-head verification → persisted evidence → frontier recomputation`

Never require a future agent to reconstruct state from chat.
