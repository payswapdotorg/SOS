# SOS — Final LLM Tech Lead Handoff

**Date:** 2026-09-29 (TL takeover reconciliation)
**Role:** LLM Tech Lead / Product Architect handoff
**Authority:** Repository + actual Git facts

## 1. Mission and architectural stance

SOS is a mission-governed operating system for continuously improving the realization of software systems.

The frozen semantic loop is:

`Constitution → Mission → Value Model → Context → System State → Evidence → Hypothesis → Candidate State → Assurance → Experiment → Promotion/Rollback → Learning`

LLMs are proposal/reasoning mechanisms. They are never a fifth authority class.

Non-negotiable invariants (full set lives in the frozen constitution/architecture; operator-restated): Constitution authoritative; mission/value/context explicit; System State canonical; evidence never stronger than observed; FAILED ≠ UNKNOWN ≠ UNAVAILABLE ≠ UNSUPPORTED; W7 assures, W8 experiments/promotes/rolls back, W9 authorizes; ASK never becomes ACT implicitly; platform context narrows but never widens; providers execute, SOS authorizes; clients display, SOS defines semantics; LLM output is proposal material, not authority; self-evolution is itself governed; all consequential changes bounded and reversible; no unmerged sibling is an authoritative dependency; exact source revisions traceable; fresh agents recover entirely from the repository.

## 2. Authoritative implementation frontier

W0 through W11 are authoritatively merged:

- W10 merge: `a1778653c35064eeb9d71563f17b30fb174d9429` (PR #17)
- W11 merge: `aae251813d31f5b85e005d4bff94462a84c440df` (PR #18)
- W12 dispatch/reconciliation point: `e3a97b895ca7f6cc7206a50bde45b2b55c554195`

Governance caveat (recorded, binding): W10 and W11 were accepted via **operator-delegated TL self-approval** rather than independent Architect review. Git state is authoritative; governance confidence is weaker than intended. Do NOT rewrite history or reopen W10/W11 unless later integration evidence exposes an actual semantic defect. For W12/W13/W14/W15, strict independent Architect gates are restored — the TL verifies but never self-approves.

Live `main` must be re-read before every new branch/base decision.

## 3. Current W12 reality

- W12 PR: `#19`, branch `work/w12-optimization-loop`, base `e3a97b895ca7f6cc7206a50bde45b2b55c554195`, exact head `fd6d20f875ff3d52ceec6c3100548be57be34e61` (implementation `cba274710ba3c76a883edbf4a91f836b57279e83` + docs/checkpoint commit).
- State: `WAITING_FOR_ARCHITECT` (checkpoint review iteration 1). Open, mergeable, CI green on the exact head, **zero submitted reviews** — the Architect gate has NOT been given. No merge is authorized.
- TL independent verification (2026-09-29): `python -m pytest` → **360 passed**; `python -m compileall -q src tests` → clean; C1–C10 review complete, no semantic defects; two non-blocking notes recorded in `spec/development-state/current-state.md` (lifecycle-vs-truth axis on FAILED mapping; deterministic id-ordering vs future value-ranking).
- The W12 implementation composes the real W3/W4/W5/W6/W7/W8/W9(/W11) authorities; it introduces no new authority class (architecture §12).

The Architect review of PR #19 must address (at minimum): genuine gating by pre-existing authorities at every consequential step; MODEL_ONLY promotion stays internal model state; rollback evidence distinguishes modeled lifecycle transition from actual external recovery; truth-state distinctions preserved end-to-end; exact non-forgeable cross-authority references; deterministic ordering acceptable for the current W6 candidate model; the optional W11 seam incapable of becoming an authority. Do not expand W12 because additional functionality is imaginable.

## 4. Three-worker operating model

Current cycle (state and missions): see `spec/development-state/WORKER-DISPATCH.md` (authoritative). Summary:

- **Worker A — W12 closure:** fresh review at the exact head, verify C1–C10, run the gates, fix any semantic defect on the SAME PR #19, stop at `WAITING_FOR_ARCHITECT` with an exact-head checkpoint. No merge, no second implementation.
- **Worker B — W13 preparation:** DELIVERED (package committed by this reconciliation). Standing mission: review the prepared package for contract drift; no W13 implementation before the W12 merge.
- **Worker C — W14 + W15 preparation:** DELIVERED (packages committed by this reconciliation). No implementation.

No-sibling-dependency rule: B/C artifacts are based on current `main`, frozen architecture, roadmap, and authoritative merged work — never on Worker A's unmerged branch.

Post-merge rotations (operator directive, binding):

- After W12 merges: A → W13 implementation; B → W13 verification/adversarial review support; C → W14 implementation preparation. TL reconciles machine state + operational docs, records the W12 merge SHA, moves frontier to W13.
- After W13 merges: A → W14 integration implementation; B → W14 adversarial verification; C → W15 final-gate preparation.
- After W14 merges (W15 final gate): A → integration/reproduction verification; B → adversarial evidence audit; C → documentation/reconciliation audit; TL → final integration; Architect → final gate. No new architecture during W15.

## 5. Target architecture

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
   provider   GitHub   VM/CI          client cockpit   Web/Mobile
   (W11 port)
```

The central architectural rule is:

**Providers execute authorized bounded requests; SOS decides whether they are authorized.**

**Clients display/request SOS state; clients do not define SOS semantics.**

## 6. Sequencing rule

The frozen program remains:

`W12 → W13 → W14 → W15 → ROADMAP COMPLETE`

W13/W14/W15 specification packages exist (this reconciliation) but are DISPATCH-BLOCKED until their frozen dependencies carry authoritative merge SHAs. Preparation never claims or depends on unmerged implementation. At dispatch time, re-verify dependency merges from actual Git history and record the exact base SHA.

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
- merge a stale base;
- merge without the independent Architect gate (W12+).

Completion standard (binding): implementation → exact-head verification → checkpoint → Architect review → approved → actual Git merge → canonical reconciliation → next frontier. Code + tests + PR + green CI are necessary, never sufficient.

## 8. Immediate TL priorities

1. Close W12 correctly: Worker A's independent review (or equivalent fresh verification) → Architect approval → merge → canonical reconciliation (record W12 merge SHA, frontier → W13).
2. Keep the prepared W13 package reconciled; at W12 merge, convert it into the dispatched bounded W13 Work Order with a freshly verified base SHA.
3. Dispatch per the rotation table (§4); enforce the no-sibling-dependency rule.
4. Re-run every gate personally at every exact head; never trust reported numbers.
5. After each merge, reconcile `implementation-state.json`, `current-state.md`, `WORKER-DISPATCH.md`, and this handoff.

## 9. Success condition for this handoff

A fresh TL should be able to recover the complete operating state from:

- `ARCHITECT_START_HERE.md`
- `AGENTS.md`
- frozen architecture/requirements/roadmap/constitution
- `spec/development-state/implementation-state.json`
- `spec/development-state/current-state.md`
- `spec/development-state/WORKER-DISPATCH.md`
- `spec/work-orders/W12-optimization-loop.md` + the W12 checkpoint/design at the exact PR #19 head
- the prepared W13/W14/W15 packages
- the active PR #19

without requiring conversation history. Recovery order: live main SHA → roadmap → implementation-state.json → PR #19 → W12 Work Order → checkpoint + design at exact head → frozen architecture/requirements/constitution → operational docs → close W12 → dispatch W13 → W14 → W15.
