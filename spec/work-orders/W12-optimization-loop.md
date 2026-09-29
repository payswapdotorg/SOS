# W12 — Brownfield Optimization Loop (first bounded slice: the governed orchestrator)

**Status:** DISPATCHED — WORKER AUTHORIZED
**Dependencies (all authoritative):** W3 `6541441bb706ef1f27b2c38b9eb930433641b14b`; W4 `26060db57c24ba8b36315c1005466046810c5163`; W5 `2bfd0f89da129c6b3347d88b0d8da1b79dd04127`; W6 `b5171f70ca5ce85ca0be07cfdb3abf034c03c32f`; W7 `25f663cf444f92b3190074a9119619cbc53e9ece`; W8 `65b84058aa204b3749e45b7e21ae433a4b138d83`; W9 `203cfb7590bd25244cabf3cc7299dd192b00948d`; W11 substrate `aae251813d31f5b85e005d4bff94462a84c440df`
**Roadmap:** `spec/implementation-roadmap.md` — W12 (Brownfield optimization loop — production evolution from existing software; this Work Order is its first bounded implementation slice)
**Primary requirements:** R1, R6, R7, R8, R9, R10, R11, R12, R13, R14, R15, R18, R22, R23, R24
**Base for Worker branch:** live `main` AFTER the W11 merge (exact base recorded at dispatch: `aae251813d31f5b85e005d4bff94462a84c440df`)

## Mission

Implement the governed brownfield optimization loop as an orchestrator that
COMPOSES the already-merged authorities — W3 recovered system, W5 causal
knowledge, W6 candidate generation, W7 assurance, W8 experimentation/
promotion/rollback, W9 autonomy/ASK, W4 evidence recording, and (optionally,
via its port) the W11 execution substrate — into one deterministic, bounded,
fully-traceable cycle:

```
recovered system state
  → candidate proposal (W6, W5-informed)
  → assurance gate (W7)
  → governed experiment (W8)
  → W9 autonomy decision gate (ACT / ASK / REJECT)
  → promotion or governed rollback (W8)
  → evidence recording at every step (W4, verbatim)
```

The loop is a **simulation-level composition** in this slice: it operates on
models and injected port objects (deterministic stub evaluators), never on
live production systems. SOS remains every authority; the loop only
orchestrates.

The implementation MUST reuse, without redefining: W1 model/validation/
persistence, W3 recovery types, W4 EvidenceGraph ingestion, W5 causal types,
W6 candidate types and ranking, W7 AssuranceResult, W8 Experiment lifecycle/
PromotionGate/RollbackPath/StopCondition, W9 AutonomyRequest/AutonomyDecision
state machine, W11 ExecutionSubstrate port. No new authority class may be
created (architecture §12).

## Required outcomes

1. **Loop record model:** a typed, construction-validated, content-addressed
   `OptimizationLoop` record carrying: the recovered-system reference (W3
   `RecoveryResult` id), iteration entries, stop outcome, traceability; JSON
   round-trip via W1 `JsonModelStore`.
2. **Governed iteration lifecycle:** each iteration is a typed record
   (candidate refs, assurance refs, experiment refs, W9 decision refs,
   evidence refs, outcome) with a deterministic state machine — no free-form
   narrative transitions.
3. **W9 authority at every consequential step:** promotion, rollback, and
   experiment launch are gated on resolved W9 decisions; an ASK decision
   PAUSES the loop with an explicit pending-authorization record (never a
   silent default, never an auto-approve); REJECT terminates the iteration
   as refused.
4. **W7-before-W8 ordering:** an experiment cannot be constructed for a
   candidate whose W7 assurance result is not a pass bound to the exact same
   candidate/revision chain (mechanically enforced, ordering invariant).
5. **W8 promotion/rollback governance:** promotion requires the W8
   `PromotionGate` result; every DEPLOY-class promotion carries a bounded
   `RollbackPath`; stop conditions are W8 `StopCondition`-typed.
6. **W5/W6 candidate provenance:** candidates cite their `SubgraphMutation`
   and (where present) the W5 causal hypotheses that informed selection;
   ordering over candidates is deterministic (stable tie-breaks).
7. **W4 evidence recording:** every consequential step appends verbatim
   evidence entries through the existing W4 evidence vocabulary/ingestion
   path (observed, not inferred; no new evidence kinds).
8. **W11 substrate integration (optional seam):** the loop MAY dispatch
   governed execution steps through the W11 `ExecutionSubstrate` port when
   supplied; without it the loop runs in model-only mode. No live execution.
9. **Bounded, deterministic loop:** fixed max-iteration bound, deterministic
   candidate order, clock-free core (timestamps are caller-supplied data),
   identical inputs → identical loop records, zero network.
10. **Explainability:** the final loop record preserves the full chain —
    context refs, candidate alternatives, assurance results, experiment
    evaluations, W9 decisions, uncertainty/distinctions (FAILED/UNKNOWN/
    UNAVAILABLE/UNSUPPORTED never collapse).

## Allowed implementation surface

Worker MUST limit implementation to these five files unless an
Architect-approved correction expands scope:

- `src/sos/optimization.py`
- `src/sos/__init__.py` (W12 exports only)
- `tests/test_w12_optimization_loop.py`
- `docs/implementation/W12-OPTIMIZATION-LOOP-DESIGN.md`
- `spec/development-state/W12-checkpoint.md`

Do not modify frozen authority artifacts, roadmap semantics, Work Order
machinery, or W1–W11 source files.

## Explicit exclusions

W12 (this slice) MUST NOT implement:

- live production access, network I/O, subprocess spawning, or deployment;
- W13 SOS self-evolution / meta-adaptation (the loop targets RECOVERED
  EXTERNAL systems, not SOS's own sources);
- W14 integrated dogfood/adversarial verification;
- a new mission/value/context/evidence/causal/candidate/assurance/experiment/
  autonomy/execution/error/persistence authority;
- LLM/model output as authorization, truth, or evidence;
- unbounded iteration, wall-clock dependence, or nondeterministic ordering;
- mutation of the Constitution, frozen specs, or the roadmap.

## Acceptance criteria

### C1 — Composed-authority integrity
The loop orchestrates only through the real W3/W4/W5/W6/W7/W8/W9(/W11)
types; every cross-authority reference is chain-checked (same candidate/
revision/decision chain); no authority is duplicated or bypassed.

### C2 — W9 gate mechanics
ASK pauses with an explicit pending record; REJECT refuses the iteration;
ACT proceeds only with a resolved decision; no auto-promotion without ACT.

### C3 — W7→W8 ordering invariant
Experiments are unconstructible without a passing assurance bound to the
exact chain (construction-validated).

### C4 — Governed promotion/rollback
Promotion requires PromotionGate; DEPLOY-class promotions carry bounded
RollbackPath; stop conditions are typed; rollback is itself governed.

### C5 — Verbatim W4 evidence
Every consequential step appends evidence entries through the existing W4
vocabulary; nothing inferred is recorded as observed.

### C6 — Determinism and bounds
Fixed iteration bound; deterministic ordering; clock-free core; identical
inputs → byte-identical loop records (content-addressed ids).

### C7 — Distinction preservation
FAILED/UNKNOWN/UNAVAILABLE/UNSUPPORTED outcomes remain distinct end-to-end;
none collapses to a favorable value.

### C8 — Model-only safety
No live system, network, subprocess, or file mutation outside the five
allowed files; the W11 seam, when used, runs against stub providers.

### C9 — Persistence round-trip
Loop records round-trip through W1 `JsonModelStore`; no new persistence
authority.

### C10 — Bounded authority surface
No W13/W14 symbols, no self-evolution paths, no duplicate authorities;
W12 exports only through `src/sos/__init__.py`.

## Required regression coverage

Tests MUST include, at minimum: full-loop happy path (deterministic record);
W9 ASK pause with pending record; W9 REJECT refusal; missing/unresolved W9
reference rejection; W7-missing or W7-fail experiment rejection; promotion
without PromotionGate rejection; DEPLOY without RollbackPath rejection;
stop-condition termination; max-iteration bound; determinism (identical
runs → identical content-addressed ids); W4 evidence appended at every step;
candidate provenance citation; distinction preservation through the loop;
W11-substrate seam in model-only mode; JSON round-trip; and absence of
W13/W14/live-execution symbols.

## Deterministic verification

Worker MUST run and report exact-head results for:

```text
python -m pytest
python -m compileall -q src tests
```

No network/provider dependency may be required for the deterministic
acceptance suite.

## Evaluation / real-system evidence

This slice is composition/contract evidence: the loop is exercised on
fixture recovered-system models with injected stub evaluators. Real
brownfield system ingestion stays out of this slice.

## Risk / rollback

**Risk:** loop-level authority leakage (a step that bypasses W7/W8/W9 or
records inferred evidence). The mechanical construction-validation invariants
(C1–C7) are the guard; the tests are the executable proof.

**Rollback:** ordinary Git revert of the merged W12 change. No deployment or
data migration is permitted in this slice.

## Completion / reconciliation protocol

When implementation is complete, the Worker MUST:

1. checkpoint exact base/head SHAs and verification evidence;
2. report the exact pytest and compileall results;
3. remain at `WAITING_FOR_ARCHITECT`;
4. stop without merging, without dispatching W13, and without modifying
   canonical state;
5. await Architect review. Corrections stay on the same PR.

W12 completion requires the Architect gate, actual Git merge, and canonical
reconciliation recording the W12 merge and next frontier.
