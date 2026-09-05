# W5 Work Order — Causal Knowledge + Architecture Memory

**Status:** DISPATCHED
**Task:** W5 — Causal knowledge + memory
**Dependencies:** W4 merged as `26060db57c24ba8b36315c1005466046810c5163`; W2 and W3 are also authoritatively merged (`587201d3e12a10ba9fac6da751d663a40c33dfb9`, `6541441bb706ef1f27b2c38b9eb930433641b14b`).

## Mission / requirement traceability

Implement the bounded W5 slice from the frozen roadmap: represent **causal knowledge and architecture memory** over the W2 System State / Architecture Graph using W4 evidence, while keeping causal claims explicitly uncertain, provenance-backed, versioned, and non-authorizing.

Primary requirements: R9 (evidence-backed reasoning), R20/R21 (learning and truthful uncertainty), R23 (traceability/explainability), R24 (repository-governed implementation). Frozen architecture invariants govern all causal interpretation: LLM output alone cannot establish truth, authorization, safety, completion, or causal efficacy; evidence must retain exact revision/deployment/temporal context; unknown/failed/unavailable must remain distinct.

## Scope

Build only the causal-knowledge and architecture-memory boundary:

1. A **causal relation / hypothesis record** that links named subjects or architecture entities with explicit direction, relation type, status, uncertainty/confidence, temporal context, and supporting evidence references.
2. Explicit distinction between **observational evidence** and **intervention evidence**. W4 evidence remains the evidence authority; W5 may classify/link evidence but must not fabricate interventions or promote observations into proven causal effects.
3. A deterministic, versioned **causal knowledge graph / memory store** with stable identity, provenance, deterministic ordering, deduplication, and JSON round-trip through the existing W1 persistence boundary.
4. A bounded **architecture-memory projection** that stores learned hypotheses/relationships about recovered architecture without mutating the W2/W3 canonical graph or silently replacing architecture truth.
5. Truthful handling of `UNKNOWN`, `FAILED`, and `UNAVAILABLE` supporting evidence; absence of evidence must not become causal support.
6. Evidence-backed traceability from every causal claim to its supporting W4 evidence ids and exact source/revision context where available.
7. Deterministic merge/update behavior for repeated causal evidence and explicit contradiction handling (e.g. competing hypotheses coexist rather than one being silently deleted).

## Explicit exclusions

Do **not** implement:

- candidate generation, search, graph mutation, or optimization (W6);
- assurance verdicts, impact/risk gates, safety approval, or promotion authorization (W7);
- experiments, canary/shadow execution, production promotion, or rollback orchestration (W8);
- autonomy, ASK, user authorization policy, or autonomous action (W9);
- contextual personalization/platform semantics (W10);
- greenfield/brownfield realization loops (W11/W12);
- SOS self-evolution or meta-adaptation (W13);
- any rewrite of Constitution, Mission, Value Model, System State, Evidence authority, frozen architecture, architecture lock, requirements, roadmap, or Work Order governance;
- live telemetry collection or a replacement evidence store;
- causal certainty derived solely from an LLM narrative, text generation, or confidence score.

## Architecture authorities

Required authorities, in descending order:

- `spec/architecture-lock.md` (frozen v1.0)
- `spec/requirements.md`
- `spec/implementation-roadmap.md`
- W1 model/truth/traceability contracts
- W2 System State / Architecture Graph
- W3 recovery provenance/uncertainty semantics
- W4 Evidence / Observability boundary

An Architecture Change Request is required before implementation if satisfying this Work Order would require changing any frozen semantic or authority boundary.

## Allowed implementation surfaces

Worker may modify only:

- `src/sos/causal.py` — W5 implementation;
- `src/sos/__init__.py` — W5 exports only;
- `tests/test_w5_causal.py` — W5 invariant/behavioral tests;
- `docs/implementation/W5-CAUSAL-KNOWLEDGE-MEMORY-DESIGN.md` — implementation design/evidence;
- `spec/development-state/W5-checkpoint.md` — durable execution checkpoint.

No other repository path is authorized. In particular, do not modify frozen authority artifacts or W1/W2/W3/W4 implementation files.

## Acceptance criteria

**C1 — deterministic causal identity:** identical causal claims with identical provenance/supporting evidence produce identical ids; differing meaningful provenance or relation semantics produce distinct ids.

**C2 — evidence-backed support:** every non-empty causal claim references one or more existing W4 evidence ids; unsupported claims are rejected or represented as an explicit hypothesis state with no implied truth.

**C3 — observation vs intervention distinction:** observation-only support cannot be encoded as intervention evidence; intervention evidence requires explicit intervention metadata and provenance actually supplied by the source.

**C4 — truthful uncertainty:** UNKNOWN/FAILED/UNAVAILABLE evidence cannot be silently converted to positive causal support; contradictory or insufficient evidence remains visibly uncertain.

**C5 — no authority mutation:** W5 memory can reference W2/W3 entities but cannot mutate the canonical System State / Architecture Graph or redefine Evidence semantics.

**C6 — deterministic memory behavior:** repeated identical ingestion is idempotent; ordering and serialization are deterministic; competing causal hypotheses remain separately addressable.

**C7 — provenance and traceability:** causal claims preserve supporting evidence ids plus exact source/revision/temporal context available from W4; W1 Mission/Value/Context traceability remains attached.

**C8 — architecture memory is a projection:** memory records hypotheses/learned relationships as versioned knowledge, never as a silent replacement for recovered or canonical architecture facts.

**C9 — repository persistence:** W5 objects round-trip through the existing W1 `JsonModelStore`; no new persistence/serialization authority is introduced.

**C10 — bounded surface:** no symbols, modules, or behavior for W6+ candidate generation, assurance, experiments, promotion, rollback, autonomy, ASK, or personalization are introduced.

## Deterministic verification

Worker must run from the exact PR head:

```text
python -m pytest
python -m compileall -q src tests
```

Tests must cover all acceptance criteria, especially causal-identity changes, unsupported claims, observation/intervention separation, uncertainty preservation, contradiction coexistence, no graph mutation, deterministic ordering, provenance/traceability, JSON round-trip, and W6+ boundary enforcement.

## Real-system / evaluation evidence

No live external system or collector is required for W5. Required evidence is deterministic repository tests plus a small in-memory causal fixture built only from W4 evidence records. Do not claim real-world causal efficacy from synthetic fixtures.

## Risk / rollback

**Risk:** moderate semantic risk because W5 becomes the source used by later candidate/search and assurance stages. Keep the model explicitly hypothesis/evidence-backed and non-authorizing. Rollback is an ordinary Git revert of the W5 PR; no running service or migration is introduced.

## Completion protocol

Worker must:

1. verify current `main` equals the recorded authoritative base;
2. verify W4 merge `26060db57c24ba8b36315c1005466046810c5163`;
3. implement only this Work Order;
4. run exact-head verification;
5. persist design/checkpoint evidence;
6. open/update one W5 PR;
7. stop in durable `WAITING_FOR_ARCHITECT` state;
8. make no merge and issue no successor Work Order.

Architect completion requires exact-head review, approval, actual Git merge, and post-merge reconciliation before W6 becomes eligible.
