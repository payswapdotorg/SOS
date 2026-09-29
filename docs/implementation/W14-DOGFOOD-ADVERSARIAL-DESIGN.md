# W14 Dogfood / Adversarial Verification Design (integrated verification program)

**Status:** PLANNED — Work Order PREPARED, DISPATCH BLOCKED (W12 PR #19 and
W13 are unmerged at preparation; this design is the authoritative shape of
the W14 verification program and binds the future Worker once dispatched)
**Work Order:** `spec/work-orders/W14-dogfood-adversarial-verification.md`
(prepared; frozen once dispatched)
**Dependencies at preparation:** W10 merged `a1778653c35064eeb9d71563f17b30fb174d9429`;
W11 merged `aae251813d31f5b85e005d4bff94462a84c440df`; W12 NOT merged (PR #19
open); W13 NOT merged (spec in preparation). Dispatch requires all four
authoritative merges (frozen sequencing rule).
**Preparation-time repo facts (verified by read):** live `main`
`e3a97b895ca7f6cc7206a50bde45b2b55c554195` (NOT the dispatch base);
`src/sos/` on main carries the W1–W11 modules (`model`, `graph`, `recovery`,
`evidence`, `causal`, `candidates`, `assurance`, `experimentation`,
`autonomy`, `personalization`, `platform`, `execution`) — the W12 module
(`src/sos/optimization.py` per the W12 Work Order) and the W13 module (per
the W13 Work Order, in preparation) join `main` through their own gates
before W14 dispatch. This design references W12/W13 ONLY through their
frozen Work Order semantics and roadmap definitions, never through unmerged
implementation internals.
**Harness (planned):** `tests/test_w14_adversarial_matrix.py`,
`tests/test_w14_dogfood_scenarios.py`, `tests/test_w14_determinism.py`,
`tests/w14_fixtures.py`; persisted matrix
`spec/development-state/W14-adversarial-evidence-matrix.json`; checkpoint
`spec/development-state/W14-checkpoint.md`

## 1. Overview

W14 is the roadmap's integrated verification wave: "end-to-end evidence over
representative systems and failure modes". It is a test program, not a
product. It composes every merged authority (W1–W13) through its public
contract on deterministic fixture systems and proves two things at the exact
head:

1. **Integration:** the frozen chain
   `Constitution → Mission → Value Model → Context → System State →
   Evidence → Hypothesis → Candidate State → Assurance → Experiment →
   Promotion/Rollback → Learning` (architecture §2) runs end-to-end and
   produces complete, resolvable, exact-revision evidence.
2. **Adversarial robustness:** sixteen mandated failure injections produce
   their typed governed outcomes — never silent success, never collapsed
   truth states, never a bypassed gate.

The program adds no authority class and no product code (architecture §12;
W14 Work Order exclusions). Its artifacts are tests, fixtures, a persisted
adversarial-evidence matrix, this design, and the checkpoint.

Requirement traceability: W14's Work Order lists the complete baseline
R1–R24. The mapping is: R1–R5 exercised by the scenario W1 stage (mission
authority, collaborative formalization records, explicit revision, value
constraints, context); R6/R7/R8 by the two entry paths and graph operations;
R9/R21 by the evidence-cycle and distinction design (§4, §6); R10 by the
causal stage; R11/R12 by the candidate stage; R13/R14 by assurance/rollback
stages and bypass cases; R15/R16/R22 by the W9 gate and ASK-bypass cases;
R17/R18 by the W10 narrowing stage and platform-widening cases; R19 by the
learning/memory record at cycle closure; R20 by the self-evolution boundary
cases; R23 by explainability assertions over the full record chain; R24 by
the repository-resident program itself (this design + tests + matrix are the
review artifacts).

## 2. Integrated verification architecture

### 2.1 Fixture systems (the "representative systems")

All fixtures are constructed in `tests/w14_fixtures.py` as pure data — no
files, no network, no clocks:

- **Brownfield fixture** — a fixture source manifest in the W3 recovery
  input shape (multi-component service/data-store graph with deliberate
  uncertainty, exact fixture revision ids) recovered through the merged W3
  surface into a W2 `SystemState`/`ArchitectureGraph` with preserved
  uncertainty. This is the "existing software system" entry (R6 brownfield).
- **Greenfield-seam fixture** — a W1 mission/value/context record set with
  no recovered system, whose first governed executions go through the W11
  `ExecutionSubstrate` with the two deterministic stub providers (the
  merged, test-local provider pattern). This is the mission-only entry
  (R6 greenfield, at the substrate seam).
- **Shared fixture authorities** — W1 mission/value/context records
  (versioned, with one evidence-proposed revision step), W5 causal
  hypotheses (clearly typed as hypotheses, not evidence), W6 candidate
  proposals (subgraph replacement + multi-objective objectives), stub W7/W8
  evaluators (deterministic, injected), a W9 policy with explicit ceilings.

Both entries converge on the same composed evolution cycle — the architecture
§10 symmetry claim is thereby executed, not asserted.

### 2.2 The composed cycle

Each scenario runs the Mission-diagram chain of the Work Order through the
**merged public contracts only** (imported from `sos` exactly as the
existing W1–W11 test modules import them; W12/W13 through their merged
surfaces per their Work Orders). At each stage the scenario asserts the
stage's frozen invariants (selected per stage: e.g., W7-before-W8 ordering,
W9 ACT-required promotion, W10 narrowing monotonicity, W11 receipt
provenance echo, W12 loop-record explainability, W13 boundary respect) and
appends verbatim W4 evidence. Cycle closure requires: a governed promotion
OR a governed rollback, a learning/memory record (W5/W19), and a fully
resolvable evidence graph (every id content-addressed and present).

### 2.3 Failure injection points

The same cycle is re-run with one injected fault per adversarial case, at
the arrow the case attacks (e.g., missing evidence at the
assurance→experiment boundary; forged references at the
decision→execution boundary). Each injection is a pure data mutation of the
fixture chain (an unresolvable id, a mismatched revision, a widened
constraint record, an ASK-state decision where ACT is required, a stale
system revision, a provider that fails after start). Injections never mock
or monkey-patch `src/sos/` internals — they manipulate inputs, so the
merged validation paths are exactly what runs.

## 3. Adversarial case catalog (sixteen cases, binding)

| # | Case (verbatim) | Authority attacked | Injected fault | Governed outcome that MUST hold |
| --- | --- | --- | --- | --- |
| 1 | missing evidence | W4/W7/W9/W12 | consequential step cites absent/unresolvable evidence ids | construction rejection (W1 `ModelValidationError` family) or explicit ASK/gather outcome per policy; never silent proceed; no record implying the step ran |
| 2 | FAILED evidence | W1/W4/W10 | evidence/observation with `TruthState.FAILED` feeding a gate | FAILED propagates as FAILED end-to-end; gates treat it as blocking; W10-style narrowing on every non-SUCCESS state; no collapse to SUCCESS/EMPTY |
| 3 | UNKNOWN evidence | W1/W4/W9 | `TruthState.UNKNOWN` evidence feeding an autonomy/loop decision | UNKNOWN cannot authorize ACT; routes per policy to ASK/GATHER_EVIDENCE; recorded verbatim with its distinction intact |
| 4 | UNAVAILABLE provider | W11/W4 | unknown provider id, or provider raising its unavailability signal | no-run UNAVAILABLE receipt; distinct from FAILED and UNSUPPORTED; W4 conversion keeps availability distinct from result; never rendered as success |
| 5 | UNSUPPORTED capability | W11 | fully-authorized request beyond the provider's capability set | no-run UNSUPPORTED receipt (a truthful outcome, not a rejection of the request's validity); distinct from UNAVAILABLE |
| 6 | forged authority references | W9/W11/W12 | decision/assurance/experiment ids that do not resolve, or resolve to a different chain | pre-dispatch rejection; zero provider engagement; the forged reference never satisfies any gate |
| 7 | mismatched revisions | W7/W11/W12 | assurance/experiment/reference pinned to a different revision than the candidate chain | chain-check rejection at construction or submit; provenance echo mismatch rejected; no cross-revision grafting |
| 8 | mismatched candidates | W6/W7/W8/W12 | experiment/assurance bound to a different candidate id than the one proposed | cross-candidate reference rejected; the chain-check never equates distinct candidates |
| 9 | platform widening attempts | W10 | platform/personalization constraint that widens `allowed_actions` or relaxes ceilings | deterministic rejection (W1 validation family); monotonic narrowing invariant holds; the widened policy is never applied |
| 10 | provider self-authorization | W9/W11 | execution request whose authorizer is the provider itself, or request lacking the W9 decision reference | unconstructible or rejected before any provider call; the provider is never the authorizer (R22) |
| 11 | ASK bypass attempts | W9/W11/W12 | promotion/execution attempted under an ASK or unresolved decision | loop pauses with explicit pending-authorization record; substrate refuses; no auto-approve, no default-to-ACT |
| 12 | rollback bypass attempts | W8/W11 | DEPLOY-class promotion without bounded rollback path; ROLLED_BACK without governed rollback reference | unconstructible at type level or rejected; bounded `RollbackPath`/`RollbackReference` mandatory (architecture §13 invariant 10) |
| 13 | self-evolution boundary violations | W13 + architecture §11/§12 | self-evolution attempt that touches frozen authority surfaces or would disable the mechanism judging it | refused/contained per the merged W13 boundary contract and the architecture-lock self-evolution invariants; the violation is recorded as evidence, never applied |
| 14 | non-deterministic outputs | all | meta-case: identical scenario run twice; any divergence | the determinism assertion itself fails the suite; identical inputs MUST yield identical content-addressed ids (see §6) |
| 15 | stale-state recovery | W2/W3/W12 | chain continues from a recovered system whose revision is stale relative to the cited evidence/assurance | explicit re-reconciliation or typed stale-state outcome; stale assurance/decisions are not silently reused (chain mismatch → rejection); uncertainty preserved |
| 16 | partial-failure recovery | W4/W8/W11/W12 | mid-lifecycle failure (experiment fails mid-way; provider fails after start; evidence partially ingested) | typed failure state; governed rollback where required; failure recorded verbatim; no partial record rendered as success; recovery resumes only from the typed state |

Case 13 binds to whatever boundary contract the merged W13 Work Order
freezes (its dispatch/merge precedes W14); at W14 authoring time the test
binds to that merged contract. The roadmap-level invariant is fixed
regardless of W13's internal shape: self-evolution may not rewrite the
Constitution, frozen architecture, evidence authority, assurance boundary,
or autonomy limits (architecture-lock "Self-evolution").

## 4. Failure-matrix structure

`spec/development-state/W14-adversarial-evidence-matrix.json` is the
machine-readable deliverable (checked mechanically by the W15 gate):

```json
{
  "schema": "sos-w14-adversarial-evidence-matrix/1.0",
  "workOrder": "spec/work-orders/W14-dogfood-adversarial-verification.md",
  "repoHead": "<exact 40-hex SHA the program ran against>",
  "generatedBy": "W14 checkpoint protocol (Worker-filled at run time)",
  "rows": [
    {
      "caseId": "ADV-01-missing-evidence",
      "case": "missing evidence",
      "authorityAttacked": ["W4", "W7", "W9", "W12"],
      "injectedFault": "<one-line description>",
      "expectedGovernedOutcome": "<typed outcome, per §3>",
      "expectedEvidenceRecord": "<kind/shape of the record that must exist>",
      "distinctionGuarantee": ["FAILED", "UNKNOWN", "UNAVAILABLE", "UNSUPPORTED"],
      "testId": "tests/test_w14_adversarial_matrix.py::test_adv_01_missing_evidence",
      "verdict": "PASS",
      "notes": ""
    }
  ]
}
```

Rules: one row per case × targeted-authority grouping (a case attacking
multiple authorities MAY split into several rows with distinct `caseId`
suffixes, but every one of the sixteen case names must appear at least
once); `verdict` is filled only from the exact-head test run and must be
`PASS` for every row at merge; the sixteen case names are the frozen
enum — no renaming, no dropping, no case counted twice under one name. The
`distinctionGuarantee` column preserves FAILED ≠ UNKNOWN ≠ UNAVAILABLE ≠
UNSUPPORTED per row: each row must state which non-success states its
governed outcome keeps distinct, and the dedicated sweep (§6) proves the
pairwise distinctness globally.

## 5. Exact-revision evidence design

Every dogfood run is a pure function of (fixture set, merged code revision).
The exact-revision discipline has two layers:

1. **In-program (test-asserted):** every record produced by the scenario
   (W4 evidence, W6 candidates, W7 assurance, W8 experiments, W9 decisions,
   W11 receipts, W12 loop records) carries its content-addressed id over its
   own material (the repo-wide `*-<sha256[:16]>` pattern) and its
   provenance/traceability fields cite the exact fixture revision ids
   (`implementation_revision` on W4 provenance; the W3 recovery revision).
   The program asserts: (a) every id referenced anywhere in the produced
   evidence graph resolves to a record present in the run's store (no
   dangling references — the adversarial "forged/mismatched" cases are the
   negative control); (b) every cross-authority reference agrees on the
   candidate/revision/decision chain; (c) re-running yields the identical
   id set (§6).
2. **Run-level (checkpoint-asserted):** the repo head the suite ran against
   is recorded in the matrix header (`repoHead`) and in the W14 checkpoint
   (base/head SHAs, exact pytest/compileall outputs), per the task-entry
   contract and evidence contract (SOS-IMPLEMENTATION-PROCESS §4/§10). Tests
   do not invoke Git — the Worker fills the run-level fields at checkpoint
   time from the exact reviewed head, exactly as prior waves did.

## 6. Determinism verification design

`tests/test_w14_determinism.py` proves: identical inputs → identical
evidence records.

- **Double-run equality:** each integrated scenario runs twice in the same
  process with independently constructed but value-identical fixture inputs;
  the two runs' complete record sets must have equal id multisets and
  byte-equal serialized records.
- **Fresh-store equality:** the same scenario re-run against a fresh W1
  `JsonModelStore`/W4 `EvidenceGraph` reproduces identical ids (idempotent
  re-ingestion, the W4 dedup pattern).
- **Distinction sweep:** for every non-success truth state
  (`FAILED`, `UNKNOWN`, `UNSUPPORTED`, `UNAVAILABLE` — the frozen W1
  `TruthState` members besides SUCCESS/EMPTY), a parameterized assertion
  that the state survives the composed chain to the final evidence graph
  as itself, distinct from all others.
- **Meta-case ADV-14:** the adversarial "non-deterministic outputs" case is
  exactly the double-run assertion — the suite fails if the merged stack is
  ever non-deterministic under identical inputs.
- The whole program is clock-free and random-free: fixture timestamps are
  caller-supplied strings (the existing `prov()`/`tr()` test convention);
  no `datetime.now`, no `random`, no uuid, no iteration over unordered
  structures without stable tie-breaks.

## 7. Harness scope

| File | Role |
| --- | --- |
| `tests/w14_fixtures.py` | pure fixture builders: fixture authorities (W1 mission/value/context with revision step), brownfield manifest + W3 recovery input, stub evaluators/providers (W11 pattern), policy records; NO test functions; deterministic; hermetic |
| `tests/test_w14_adversarial_matrix.py` | the sixteen cases of §3 as deterministic tests, each binding to its attacked authority and asserting its typed governed outcome; plus the dangling-reference and zero-engagement assertions |
| `tests/test_w14_dogfood_scenarios.py` | the two integrated scenarios (brownfield entry, greenfield-seam entry), full chain, closed evidence cycles, promotion and rollback variants, explainability/traceability assertions, the roadmap "Final integrated gate" item assertions (Work Order mapping table) |
| `tests/test_w14_determinism.py` | §6: double-run, fresh-store, distinction sweep, ADV-14 |
| `spec/development-state/W14-adversarial-evidence-matrix.json` | §4 machine-readable matrix (Worker-maintained, reconciled at checkpoint) |
| `spec/development-state/W14-checkpoint.md` | base/head SHAs, verification outputs, matrix reconciliation, requirement + roadmap-gate mapping table |
| `docs/implementation/W14-DOGFOOD-ADVERSARIAL-DESIGN.md` | this design |

Conventions follow the existing suite exactly (module docstring naming the
Work Order and criteria; helpers `tr()`/`prov()`/`evidence()`-style; imports
from `sos`; construction-rejection asserted via the W1 `ModelValidationError`
family). No existing test file is modified; the pre-existing suite must stay
green unmodified (extend-never-weaken).

Defect-escalation design (Work Order Risk/rollback): a case that fails
against a frozen contract becomes a finding `SOS-W14-F??` (owning module,
expected vs actual, reproduction referenced from the test module) — the
W14 Worker never patches `src/sos/`; the Architect routes the correction to
the owning wave's surface. W14 merges only with the full matrix PASS.

## 8. Non-goals

- No new authority classes, subsystems, ports, or product code (architecture
  §12; W14 is a verification program).
- No changes to `src/sos/`, no new `sos` exports, no modification of
  existing tests or W1–W13 artifacts.
- No live execution, network, subprocess, deployment, real telemetry, or
  real provider engagement; no performance/benchmark claims.
- No W15 work (repository-level reconciliation/final gate is the next Work
  Order); no roadmap/constitution/architecture edits; no unfreezing of any
  semantic decision (a collision found by the program escalates as a finding
  or Architecture Change Request, never an in-PR semantic patch).
- No dependence on unmerged PR #19 internals or the parallel W13
  preparation: W14 binds to W12/W13 only through their merged Work Order
  contracts and actual merges.
