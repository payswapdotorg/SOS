# W14 — Full Dogfood / Adversarial Verification (integrated verification program)

**Status:** PREPARED — DISPATCH BLOCKED (W12 and W13 are not merged; dispatch is authorized only after all four frozen dependencies carry authoritative merge SHAs)
**Dependencies (frozen roadmap: W10–W13):** W10 merged `a1778653c35064eeb9d71563f17b30fb174d9429` (verified authoritative); W11 merged `aae251813d31f5b85e005d4bff94462a84c440df` (verified authoritative); W12 NOT merged at preparation (PR #19 open, Architect gate pending — no merge SHA exists yet); W13 NOT merged at preparation (Work Order spec being prepared in parallel; implementation and authoritative merge both pending). The dispatching Architect MUST re-verify all four dependency merges from actual Git history immediately before dispatch and record the W12/W13 merge SHAs in the dispatch envelope; a branch, PR, or agent statement is never dependency evidence (`spec/implementation-roadmap.md` — frozen sequencing rule).
**Roadmap:** `spec/implementation-roadmap.md` — W14 (Full dogfood/adversarial verification — "end-to-end evidence over representative systems and failure modes"; this Work Order also discharges the roadmap's frozen "Final integrated gate" MUST-verify list)
**Primary requirements:** R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R13, R14, R15, R16, R17, R18, R19, R20, R21, R22, R23, R24 (the complete frozen baseline — W14 is the integrated verification wave; the per-requirement → scenario/case mapping is recorded in `docs/implementation/W14-DOGFOOD-ADVERSARIAL-DESIGN.md`)
**Base for Worker branch:** live `main` AFTER the W13 merge (exact base SHA recorded at dispatch; it must be re-read from live `main` at dispatch — the preparation-time live main `e3a97b895ca7f6cc7206a50bde45b2b55c554195` is NOT the dispatch base)

## Mission

Verify the COMPLETE SOS architecture as one integrated system. W14 is a
**verification/test-program Work Order**, not a new product subsystem: it
composes and exercises the already-merged authorities — W1 mission/value/
context, W2 system state/architecture graph, W3 recovery, W4 evidence, W5
causal knowledge, W6 candidate generation, W7 assurance, W8 experiment/
promotion/rollback, W9 autonomy/ASK, W10 personalization/platforms, W11
execution substrate, W12 brownfield optimization loop, W13 self-evolution —
through two program elements:

1. **Integrated dogfood scenarios:** deterministic end-to-end cycles on
   fixture systems running the full frozen chain

   ```
   mission/value/context (W1)
     → system state + recovery (W2/W3, brownfield fixture)
       → evidence cycle (W4, verbatim)
         → causal hypotheses (W5)
           → candidate generation + multi-objective ranking (W6)
             → assurance gate (W7)
               → governed experiment (W8)
                 → W9 autonomy decision gate (ACT / ASK / REJECT)
                   → contextual/platform narrowing (W10)
                     → governed execution via stub providers (W11)
                       → brownfield optimization loop composition (W12)
                         → self-evolution boundary check (W13)
                           → promotion or governed rollback (W8)
                             → evidence-cycle closure + learning record (W4/W5)
   ```

2. **Adversarial verification:** a failure-injection program that attacks the
   same chain and proves the governed outcome holds in every case — no
   silent success, no collapsed truth states, no bypassed gate.

Bounded-slice discipline (binding): W14 adds **no authority classes, no new
product subsystems, and no changes to `src/sos/`**. It only composes merged
authorities through their public contracts and records what actually happens.
A defect exposed by an adversarial case is a finding to be escalated, never a
patch silently applied in this Work Order (see Risk/rollback).

### Adversarial case catalog (operator directive — binding, verbatim)

The W14 test program MUST include all of the following adversarial cases;
each is mapped to the authority it attacks and the governed outcome that must
hold (full mapping and expected observable behavior: design doc §3):

- missing evidence;
- FAILED evidence;
- UNKNOWN evidence;
- UNAVAILABLE provider;
- UNSUPPORTED capability;
- forged authority references;
- mismatched revisions;
- mismatched candidates;
- platform widening attempts;
- provider self-authorization;
- ASK bypass attempts;
- rollback bypass attempts;
- self-evolution boundary violations;
- non-deterministic outputs;
- stale-state recovery;
- partial-failure recovery.

FAILED, UNKNOWN, UNAVAILABLE and UNSUPPORTED MUST remain pairwise distinct
throughout the entire program (R21; architecture §13 invariant 6); no
adversarial case may resolve by collapsing one of these states into another
or into SUCCESS/EMPTY.

### Roadmap "Final integrated gate" mapping (binding)

Every item of the roadmap's frozen "Final integrated gate" list MUST map to a
named verification requirement in the W14 program (the list as read from
`spec/implementation-roadmap.md` enumerates fourteen items):

| Roadmap MUST-verify item | Verification requirement |
| --- | --- |
| mission formalization and revision | dogfood scenario asserts W1 mission versioning + explicit, owner-authorized revision proposal from evidence (never silent) |
| value-model constraints | scenario asserts value-model-derived hard constraints filter/penalize candidates (W1/W6/W7) |
| context and personalization boundaries | adversarial widening cases + scenario context narrowing (W10) subordinate to global mission/hard constraints |
| system/architecture graph reconstruction | brownfield scenario reconstructs the fixture system through W3 with preserved uncertainty (W2/W3) |
| evidence truthfulness | missing/FAILED/UNKNOWN evidence cases + verbatim W4 recording (R21) |
| causal hypothesis/evidence distinction | scenario keeps W5 hypotheses distinct from W4 evidence; correlation never re-typed as intervention |
| candidate subgraph replacement | scenario applies `A' = A - S + S'` boundary-preserving replacement (W6/W2) |
| multi-objective trade-offs | scenario produces a Pareto/non-dominated candidate set, not a scalar winner (W6) |
| assurance and rollback | adversarial rollback-bypass cases + governed promotion/rollback in scenarios (W7/W8) |
| ASK/autonomy policy | adversarial ASK-bypass cases + ACT/ASK/REJECT gating in scenarios (W9) |
| platform adapters | scenario routes through platform adapters; platform narrowing stays explicit (W10) |
| greenfield and brownfield paths | two scenarios: brownfield fixture (W3 entry) and greenfield-seam fixture (W11 substrate entry) converging on the same loop |
| SOS self-evolution with meta-adaptation boundary | self-evolution boundary-violation cases against the merged W13 surface (architecture §11/§12; architecture-lock self-evolution invariants) |
| full exact-revision traceability | every dogfood run cites exact revisions and content-addressed record ids; all cross-references resolve |

## Required outcomes

1. **Adversarial failure matrix:** a machine-readable, schema-validated
   matrix of rows `case × authority-attacked` carrying: injected fault,
   expected governed outcome (typed), expected evidence record, the
   distinction guarantee (which of FAILED/UNKNOWN/UNAVAILABLE/UNSUPPORTED
   must remain distinct), owning test id, and run verdict. Persisted as
   `spec/development-state/W14-adversarial-evidence-matrix.json` and
   reconciled with the live test results at the exact head.
2. **Exact-revision evidence:** every dogfood run cites the exact fixture
   revisions and content-addressed record ids it produced/consumed; every
   cross-authority reference in every produced evidence graph resolves (no
   dangling ids); the persisted matrix header cites the exact repo head the
   program ran against.
3. **Integrated dogfood scenarios:** at least two end-to-end scenarios (one
   brownfield entry through W3 recovery; one greenfield-seam entry through
   the W11 substrate stub) completing the full chain of the Mission diagram
   above, each ending in a governed promotion or governed rollback with
   closed evidence cycles.
4. **Determinism checks:** identical fixture inputs produce byte-identical
   records (equal content-addressed ids) across repeated runs, fresh stores,
   and scenario re-entry; the non-determinism adversarial case is the
   meta-check that fails the suite if this ever breaks.
5. **Governed-outcome assertions:** every adversarial case asserts the
   precise typed outcome (construction rejection in the W1
   `ModelValidationError` family, ASK pause with pending-authorization
   record, no-run truthful receipt, monotonic narrowing, containment, or
   governed rollback) — never a bare "did not crash", never an untyped
   state, never silent success.
6. **Stale-state and partial-failure recovery:** the final two adversarial
   cases must end in explicitly typed recovered/rolled-back states with the
   failure recorded verbatim in W4 evidence; no partial record is ever
   rendered as success.
7. **Distinction preservation sweep:** the program includes a sweep asserting
   the pairwise distinctness of the non-success truth states end-to-end
   through the composed chain (not only per-module).
8. **Regression inviolability:** all pre-existing W1–W13 test modules remain
   unmodified and green at the exact head (extend-never-weaken; no existing
   assertion is weakened, skipped, or deleted).
9. **Hermetic execution:** the entire program runs with zero network, zero
   subprocess spawning, and zero wall-clock/randomness dependence; fixture
   timestamps are caller-supplied data.
10. **Persisted checkpoint evidence:** `spec/development-state/W14-checkpoint.md`
    records the exact base/head SHAs, the full verification results, the
    matrix reconciliation, and the requirement/roadmap-gate mapping table.

## Allowed implementation surface

Worker MUST limit implementation to these seven files unless an
Architect-approved correction expands scope:

- `tests/test_w14_adversarial_matrix.py`
- `tests/test_w14_dogfood_scenarios.py`
- `tests/test_w14_determinism.py`
- `tests/w14_fixtures.py` (shared deterministic fixture builders: constructs
  the fixture mission/value/context/system records and chains them across
  merged authorities; contains NO test functions; not collected by pytest's
  default `test_*.py` discovery; importable as a top-level module under the
  repo's pytest `pythonpath = ["src"]` + prepend-mode layout)
- `spec/development-state/W14-adversarial-evidence-matrix.json`
- `spec/development-state/W14-checkpoint.md`
- `docs/implementation/W14-DOGFOOD-ADVERSARIAL-DESIGN.md`

Do not modify frozen authority artifacts, roadmap semantics, Work Order
machinery, any `src/sos/` file, any existing test file, or any W1–W13
checkpoint/design document.

## Explicit exclusions

W14 (this slice) MUST NOT implement:

- any change to `src/sos/` — a failing adversarial case against a frozen
  contract is escalated as a finding (stable ID, owning module, expected vs
  actual), never patched inside this Work Order's PR;
- a new mission/value/context/evidence/causal/candidate/assurance/experiment/
  autonomy/execution/error/persistence/self-evolution authority, or any new
  authority class (architecture §12 — the four authority classes are frozen);
- new product subsystems, new ports, or new runtime mechanisms — W14 composes
  existing merged contracts only;
- live production access, network I/O, subprocess spawning, or deployment;
- W15 final-gate work (repository-level reconciliation stays a separate,
  later Work Order);
- LLM/model output as authorization, truth, or evidence;
- weakening, skipping, or deleting any pre-existing W1–W13 test;
- nondeterministic or wall-clock-dependent tests, ordering, or fixtures;
- mutation of the Constitution, frozen specs, or the roadmap.

## Acceptance criteria

### C1 — Complete integrated coverage
Every merged W1–W13 authority is exercised in at least one integrated
dogfood scenario through its public merged contract, and every roadmap
"Final integrated gate" item maps to a named, passing verification
requirement recorded in the checkpoint.

### C2 — Adversarial catalog completeness
All sixteen operator-mandated adversarial cases exist as deterministic tests;
each matrix row names its attacked authority, injected fault, and expected
governed outcome; no case is satisfied by an unrelated test.

### C3 — Governed outcomes hold
For every adversarial case the observed outcome equals the typed governed
outcome (rejection, ASK pause with pending record, no-run truthful receipt,
monotonic narrowing, boundary refusal/containment, or governed rollback);
zero provider/loop engagement occurs on pre-gate rejections.

### C4 — Distinction preservation
FAILED/UNKNOWN/UNAVAILABLE/UNSUPPORTED remain pairwise distinct through the
composed chain in every case and in the dedicated sweep; none collapses to a
favorable value anywhere in the produced evidence graphs.

### C5 — Exact-revision traceability
Every dogfood evidence record resolves to its producing record via
content-addressed ids; every cross-authority reference chain-checks (same
candidate/revision/decision chain); the persisted matrix cites the exact run
head.

### C6 — Determinism
Identical fixture inputs → byte-identical records (identical
content-addressed ids) across repeated runs and fresh stores; the suite is
clock-free and random-free.

### C7 — Recovery correctness
Stale-state and partial-failure cases end in explicitly typed
recovered/rolled-back states with verbatim failure evidence and governed
rollback where required; no partial record renders as success.

### C8 — Verification-only surface
No `src/sos/` changes, no new `sos` exports, no new authority symbols, no
new product code; the diff touches only the seven allowed files.

### C9 — Hermetic execution
Zero network, zero subprocess, zero external system dependence; the full
suite passes offline.

### C10 — Machine-readable persisted matrix
`W14-adversarial-evidence-matrix.json` parses against its schema, contains
every required case id, carries all-PASS verdicts reconciled with the exact
test run, and is cited by the W14 checkpoint.

## Required regression coverage

Tests MUST include, at minimum: all sixteen adversarial cases (missing
evidence; FAILED evidence; UNKNOWN evidence; UNAVAILABLE provider;
UNSUPPORTED capability; forged authority references; mismatched revisions;
mismatched candidates; platform widening attempts; provider
self-authorization; ASK bypass attempts; rollback bypass attempts;
self-evolution boundary violations; non-deterministic outputs; stale-state
recovery; partial-failure recovery) each asserting its governed outcome;
the two integrated dogfood scenarios end-to-end with closed evidence cycles;
mission revision is explicit and evidence-proposed (never silent);
value-model hard constraints filter candidates; Pareto/non-dominated
candidate output; causal hypothesis vs evidence distinction; subgraph
replacement boundary invariants; determinism double-runs (identical ids);
fresh-store determinism; distinction sweep over the non-success truth
states; dangling-reference rejection; zero provider engagement on pre-gate
rejection; and the full pre-existing W1–W13 suite green and unmodified.

## Deterministic verification

Worker MUST run and report exact-head results for:

```text
python -m pytest
python -m compileall -q src tests
```

No network/provider dependency may be required for the deterministic
acceptance suite.

## Evaluation / real-system evidence

This slice produces integrated contract evidence over deterministic fixture
systems: the "representative systems" of the roadmap row are two fixture
systems (a brownfield fixture recovered through W3 with uncertainty, and a
greenfield-seam fixture driven through W11 stub providers), exercised with
injected stub evaluators and providers. Evidence is the produced W4 evidence
graphs, loop/decision records, the adversarial matrix, and the exact-head
test results. Live production dogfooding, real telemetry, and real provider
engagement stay out of this slice (excluded above); W14's claim is
architectural integration correctness, not production performance.

## Risk / rollback

**Risk:** (1) adversarial cases expose genuine product defects in merged
waves. This is the purpose of W14. Protocol: the Worker records a finding
(stable ID `SOS-W14-F??`, owning module, expected vs actual, minimal
reproduction in the test module marked with the finding reference) and stops
— the Worker does NOT modify `src/sos/` in this Work Order; the Architect
either authorizes a bounded correction under the owning wave's criteria
(re-reviewed there, then W14 re-runs the matrix) or returns the defect for a
follow-up slice. W14's PR merges only with the complete matrix green.
(2) False confidence: a case passes because the injection missed the chain —
mitigated by requiring each case to bind to a named authority and assert a
positive governed outcome, not merely absence of failure.

**Rollback:** ordinary Git revert of the merged W14 change. W14 introduces
no runtime state, no schema changes, and no data migration, so revert is
complete recovery. (A revert of W14 removes verification coverage only —
the W15 gate then fails its adversarial-evidence check by design.)

## Completion / reconciliation protocol

When implementation is complete, the Worker MUST:

1. checkpoint exact base/head SHAs, verification evidence, and the
   matrix/checkpoint reconciliation in
   `spec/development-state/W14-checkpoint.md`;
2. report the exact pytest and compileall results at the exact head;
3. remain at `WAITING_FOR_ARCHITECT`;
4. stop without merging, without dispatching any successor Work Order (W15
   stays blocked; there is no W16 in the frozen roadmap), and without
   modifying canonical state;
5. await Architect review. Corrections stay on the same PR.

W14 completion requires the Architect gate, actual Git merge, and canonical
reconciliation recording the W14 merge and the W15 frontier.
