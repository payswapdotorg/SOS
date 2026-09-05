# W6 Work Order — Candidate Generation + Bounded Search

**Status:** DISPATCHED
**Task:** W6 — Candidate generation + bounded search
**Dependencies:** W3 merged as `6541441bb706ef1f27b2c38b9eb930433641b14b`; W5 merged as `2bfd0f89da129c6b3347d88b0d8da1b79dd04127` (authoritative merge commit).

## Mission / requirement traceability

Implement the bounded W6 slice from the frozen roadmap: generate and evaluate candidate architecture changes over the recovered W2/W3 System State / Architecture Graph using W5 causal knowledge, while preserving explicit uncertainty, conflicting objectives, bounded search, and non-authorizing behavior.

Primary requirements: R11/R12 (candidate generation and bounded search), R15 (multi-objective/Pareto reasoning), R21 (truthful uncertainty), R23 (traceability/explainability), R24 (repository-governed implementation). Frozen architecture invariants remain controlling: candidate generation/reasoning is untrusted relative to assurance; LLM output alone cannot establish truth, authorization, safety, completion, or causal efficacy; candidate changes must identify affected subgraphs and preserve boundary invariants.

## Scope

Build only the candidate-generation/search boundary:

1. A typed **candidate proposal** referencing an existing System State / Architecture Graph and an explicit bounded mutation description; candidates are proposals, not applied graph mutations.
2. A deterministic **subgraph mutation representation** sufficient to express bounded candidate edits without mutating canonical W2/W3 state.
3. A **candidate generator** that can produce bounded candidate proposals from existing graph structure and W5 knowledge, with deterministic identity, provenance, traceability, and explicit uncertainty.
4. A bounded **search/evaluation engine** that explores a caller-specified finite candidate space under explicit depth/count/resource limits; search must terminate deterministically within those limits.
5. Explicit **multi-objective ranking/Pareto frontier** semantics. Do not introduce a single scalar quality authority that collapses conflicting objectives or safety constraints.
6. Candidate evaluation inputs may include W5 hypotheses and W4 evidence references, but W6 must not create a second evidence or causal authority and must not treat generated scores as proof.
7. Deterministic duplicate elimination, stable ordering, contradiction coexistence, and full traceability of candidate origin/reasoning inputs.
8. Candidate rejection must be explicit and explainable when bounds, structural invariants, or required inputs are not satisfied.

## Explicit exclusions

Do **not** implement:

- assurance verdicts, impact/risk gates, safety approval, or promotion authorization (W7);
- experiments, canary/shadow execution, production promotion, or rollback orchestration (W8);
- autonomy, ASK, user authorization policy, or autonomous action (W9);
- contextual personalization/platform semantics (W10);
- greenfield/brownfield realization loops (W11/W12);
- SOS self-evolution/meta-adaptation (W13);
- mutation of the canonical W2/W3 graph or production system;
- replacement evidence or causal stores;
- silent optimization of away hard constraints/privacy/safety/fairness/legal requirements;
- any rewrite of Constitution, Mission, Value Model, System State, Evidence, Causal Knowledge, frozen architecture, architecture lock, requirements, roadmap, or Work Order governance;
- use of an LLM narrative or candidate score as evidence of correctness, authorization, safety, or causal efficacy.

## Architecture authorities

Required authorities, in descending order:

- `spec/architecture-lock.md` (frozen v1.0)
- `spec/requirements.md`
- `spec/implementation-roadmap.md`
- W2 System State / Architecture Graph contracts
- W3 recovery provenance/uncertainty semantics
- W4 Evidence / Observability boundary
- W5 Causal Knowledge / Architecture Memory boundary

An Architecture Change Request is required before implementation if satisfying this Work Order would require changing any frozen semantic or authority boundary.

## Allowed implementation surfaces

Worker may modify only:

- `src/sos/candidates.py` — W6 implementation;
- `src/sos/__init__.py` — W6 exports only;
- `tests/test_w6_candidates.py` — W6 invariant/behavioral tests;
- `docs/implementation/W6-CANDIDATE-GENERATION-SEARCH-DESIGN.md` — implementation design/evidence;
- `spec/development-state/W6-checkpoint.md` — durable execution checkpoint.

No other repository path is authorized. In particular, do not modify frozen authority artifacts or W1/W2/W3/W4/W5 implementation files.

## Acceptance criteria

**C1 — candidate identity and provenance:** identical candidate proposals with identical graph references, mutations, bounds, and reasoning inputs produce deterministic ids; meaningful semantic/provenance changes produce distinct ids.

**C2 — bounded mutation representation:** every candidate explicitly names its target graph/subgraph and bounded edit operations; canonical W2/W3 state remains immutable.

**C3 — finite deterministic search:** search accepts explicit finite bounds (for example maximum candidates/depth) and terminates deterministically without hidden unbounded recursion or network/runtime side effects.

**C4 — multi-objective/Pareto semantics:** candidate evaluation preserves multiple objective dimensions and constraints; Pareto dominance/frontier is deterministic; no single scalar quality becomes authoritative.

**C5 — uncertainty/truthfulness:** W5 hypotheses and W4 evidence remain inputs with their original truth/uncertainty semantics; candidate scores or LLM-produced text cannot upgrade truth or authorization.

**C6 — evidence/causal traceability:** every candidate records the W2/W3 graph revision/reference plus W4/W5 input references used in generation/evaluation, with W1 Mission/Value/Context traceability.

**C7 — deterministic dedup/order:** repeated identical candidates/search inputs are idempotent and produce stable ordering; competing candidates remain separately addressable.

**C8 — explicit rejection:** invalid bounds, missing required graph references, invalid mutations, or violated boundary invariants fail explicitly and explainably.

**C9 — repository persistence:** W6 objects round-trip through the existing W1 `JsonModelStore`; no new persistence authority is introduced.

**C10 — bounded surface:** no W7+ assurance, experiment/promotion/rollback, autonomy/ASK, personalization, realization, or self-evolution semantics are introduced.

## Deterministic verification

Worker must run from the exact PR head:

```text
python -m pytest
python -m compileall -q src tests
```

Tests must cover deterministic candidate identity, mutation validation/no canonical mutation, bounded termination, Pareto dominance/frontier, uncertainty preservation, graph/evidence/causal traceability, deterministic dedup/order, explicit invalid-input rejection, JSON round-trip, and the W7+ boundary.

## Real-system / evaluation evidence

No external live system is required for W6. Required evidence is deterministic repository tests plus a small in-memory candidate fixture built from W2/W3 graph references, W4 evidence ids, and W5 hypotheses. Do not claim candidate score or synthetic search results prove real-world improvement or safety.

## Risk / rollback

**Risk:** moderate-to-high semantic risk because W6 feeds assurance. Keep candidate generation explicitly untrusted, bounded, multi-objective, traceable, and non-authorizing. No production mutation is permitted. Rollback is an ordinary Git revert of the W6 PR; no running service or migration is introduced.

## Completion protocol

Worker must:

1. verify current `main` equals the authoritative dispatch base;
2. verify W3 and W5 authoritative merge facts;
3. implement only this Work Order;
4. run exact-head verification;
5. persist design/checkpoint evidence;
6. open/update one W6 PR;
7. stop in durable `WAITING_FOR_ARCHITECT` state;
8. make no merge and issue no successor Work Order.

Architect completion requires exact-head review, approval, actual Git merge, and post-merge reconciliation before W7 becomes eligible.
