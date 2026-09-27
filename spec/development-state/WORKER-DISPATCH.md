# SOS Worker Dispatch

**Status:** ACTIVE
**Dispatch authority:** Architect/TL coordination artifact
**Repository source of truth:** Git + canonical development state

## Current repository facts

- Main was advanced by the setup commits `22d00cc9`, `586a0766`, `6e0789e8`, `9dcd96aa`, and `bb369f4d`; workers MUST re-read live `main` before using a base SHA.
- W9 merge: `203cfb7590bd25244cabf3cc7299dd192b00948d`
- Active W10 PR: #17
- W10 branch: `work/w10-personalization-platform`
- Latest known W10 head at dispatch setup: `b5ccc5f3e9b9af247b78df00bde1b1554a73f8f9`
- **Stale-base condition:** PR #17 still targets the pre-setup W10 base `d2b813eb32085fdc5e12180da5f2f141b13036e7`; Worker A MUST refresh/rebase/update the branch against live `main` before the next Architect review. No merge is authorized on the stale base.

## Worker A — W10 closure

**Branch/PR:** existing `work/w10-personalization-platform` / PR #17

### Mission

Resolve the Architect review boundary on the same PR and return a corrected exact head to `WAITING_FOR_ARCHITECT`.

### Mandatory next checks

- Compare alternative predicates to actual context values.
- Do not treat SUCCESS truth state as a context match by itself.
- Ensure FAILED context never becomes implicit ACT.
- Preserve W9 ASK/REJECT and all authority ceilings.
- Model platform constraints as explicit narrowing constraints.
- Reconcile W10 checkpoint/design/PR metadata with the exact head.

### Required verification

`python -m pytest`
`python -m compileall -q src tests`

No merge by the worker.

## Worker B — W11 preparation

**Artifact:** `spec/work-orders/PREP-W11-execution-substrate.md`

### Mission

Define the provider-neutral execution contract and deterministic contract tests so implementation can start cleanly when the W11 gate opens.

### Forbidden

No live execution; no provider-specific semantics in SOS core; no W11 completion claim.

## Worker C — OpenMuse + Code-OSS preparation

**Artifact:** `spec/work-orders/PREP-provider-cockpit.md`

### Mission

Turn the OpenMuse and Code-OSS findings into concrete replaceable adapter/client seams and a smallest-first W11 implementation plan.

### Forbidden

No forks imported into SOS; no authority migration; no live execution; no roadmap completion claim.

## TL responsibilities

The Tech Lead must:

1. Keep Worker A focused on the existing W10 PR.
2. Prevent B/C from turning preparation into unauthorized W11 implementation.
3. Review B/C artifacts for duplication and contract drift.
4. Keep provider execution below SOS authorization and assurance.
5. Merge only after Architect review gates pass.
6. After W10 merge, convert the best preparation artifact into the next bounded implementation Work Order rather than creating an informal dependency.
7. Reconcile canonical state from actual Git facts after every merge.

## Concurrency model

`A: W10 implementation`
+
`B: W11 execution design`
+
`C: OpenMuse/Code-OSS integration design`

No sibling branch is an authoritative dependency until merged.

## Handoff state

A fresh TL should read this file, `TL-3-WORKER-COORDINATION.md`, the two preparation Work Orders, the active W10 PR, and the frozen architecture/roadmap before dispatching or changing work.
