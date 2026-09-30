# W14 Dogfood / Adversarial Verification Design (integrated verification program)

**Status:** IMPLEMENTED — `WAITING_FOR_ARCHITECT` (review iteration 1). §§1–8
below are the prepared design, preserved verbatim (extend, never weaken);
§§9–14 are the Worker's implementation reconciliation appended at delivery
time against the exact implemented contract at the implementation head
recorded in `spec/development-state/W14-checkpoint.md`.
**Work Order:** `spec/work-orders/W14-dogfood-adversarial-verification.md`
(frozen at dispatch; the authoritative mission)
**Dependencies at preparation:** W10 merged `a1778653c35064eeb9d71563f17b30fb174d9429`;
W11 merged `aae251813d31f5b85e005d4bff94462a84c440df`; W12 NOT merged (PR #19
open); W13 NOT merged (spec in preparation). Dispatch requires all four
authoritative merges (frozen sequencing rule).
**Dispatch-time dependencies (verified by the Worker from Git history at the
dispatch base):** W10 merged `a1778653c35064eeb9d71563f17b30fb174d9429`;
W11 merged `aae251813d31f5b85e005d4bff94462a84c440df`; W12 merged `933e1e9`
(PR #19); W13 merged `e24889d` (PR #20); the dispatch base is the
post-W13-reconciliation `main` commit `c79daac5d664f104d44bb3a9f1015a92391a17f4`.
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
**Harness (as implemented):** `tests/test_w14_adversarial_matrix.py`,
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

## 9. Implemented harness scope (Worker reconciliation)

All seven allowed files were produced; no other file was touched (verified
by `git diff --name-only <base>..<head>`). The harness follows §7 exactly,
with the following realized surface:

- `tests/w14_fixtures.py` (~2100 lines): pure deterministic builders — the
  shared W1 authorities (`mission_v1`, the evidence-proposed + owner-
  authorized `mission_revision_from_evidence`, `value_model` with one HARD
  constraint whose text embeds the recovered frozen node id, `context_record`,
  `autonomy_policy`); the W4/W5 record builders (intervention/rollback/suite
  evidence, OTel span, UNAVAILABLE runtime gaps, observation-only vs
  intervention-confirmed hypotheses, success/failure learning records); the
  W6 builders (`objectives_profile`, `make_candidate`, Pareto sets with a
  genuine latency/cost trade-off, the W2 `SubgraphReplacement` boundary
  record); the brownfield fixture repository (multi-component sources +
  manifest deps + an unparsed `setup.py` manifest for deliberate UNKNOWN
  extraction + deployment/config/docs artifacts) recovered through the real
  W3 `recover_repository`; the greenfield-seam fixture (directly constructed
  W2 `SystemState`/`ArchitectureGraph` with fixed ids, UNKNOWN graph
  uncertainty, UNAVAILABLE deployment/environment references); the stub W11
  providers (`CountingExecutionProvider` with per-scope deterministic
  receipts and call counting, `UnavailableProvider`,
  `NoDeployCapabilityProvider`) and the W12 `StubSimulator`; the W10 stage
  runner; the W13 stage runner (the lawful chain + the frozen-authority
  refusal); the two scenario runners; and the determinism bundle
  serialization (`record_id`/`serialize_record`/`scenario_bundle`).
  NO test functions; not collected (the module name does not match pytest's
  `test_*.py` discovery and a determinism-suite test asserts both facts).
- `tests/test_w14_dogfood_scenarios.py` (9 tests): the two integrated
  scenarios end-to-end plus the focused roadmap-gate assertions (mission
  revision, value-model filtering, Pareto output, causal distinction,
  subgraph boundary invariants, full exact-revision traceability).
- `tests/test_w14_adversarial_matrix.py` (19 tests): the sixteen mandated
  cases (`test_adv_01` … `test_adv_16`), the dangling-reference and
  zero-engagement support assertions, and the persisted-matrix
  reconciliation test.
- `tests/test_w14_determinism.py` (14 test items in 9 functions): double-run
  equality for both scenarios, the ADV-14 meta-check, fresh-store +
  `JsonModelStore` round-trip determinism, scenario re-entry, the
  parametrized distinction sweep, the pairwise-distinctness sweep, the
  hermeticity source scan, and the fixtures-not-collected check.

## 10. The two integrated scenarios as implemented

**Scenario 1 — brownfield entry, governed promotion**
(`test_scenario_01_brownfield_full_chain_ends_in_governed_promotion`):
W1 mission v1 (full formalization) → W3 recovery of the fixture repository
(preserved UNKNOWN/UNAVAILABLE uncertainty) → W4 evidence cycle
(intervention, rollback, suite, OTel span, UNAVAILABLE runtime gap; verbatim
provenance at the exact fixture revision) → the evidence-proposed,
owner-authorized mission revision v2 → W5 causal knowledge (observation-only
hypothesis stays `proposed`/UNKNOWN; intervention-backed hypothesis
`confirmed`) + `ArchitectureMemory` v1 → W6 explicit multi-objective
candidates with a genuine trade-off → Pareto frontier (2 non-dominated of 3)
→ the W2 `SubgraphReplacement` boundary record → the W12
`run_optimization_loop` WITH stub execution providers, composing W7
assurance (the value-model HARD constraint FAILs the frozen-core candidate
with strictly better objectives), W9 gates, the W8 experiment/evaluation/
promotion gate, and the W11 governed DEPLOY (SUCCEEDED receipt, one provider
engagement) → a DEPLOY-class `LoopPromotion` with bounded rollback → W10
narrowing over the authorizing ACT decision (context selection + platform
constraint + personalization; ACT preserved; monotonic) → the W13 boundary
check (constitution-targeting proposal refused and recorded as verbatim
FAILED W4 evidence; a lawful proposal PROMOTED as data) → closure (a NEW
confirmed learning hypothesis from the run's own experiment evidence;
`ArchitectureMemory` v2; every cross-reference resolves).

**Scenario 2 — greenfield-seam entry, governed rollback**
(`test_scenario_02_greenfield_seam_full_chain_ends_in_governed_rollback`):
W1 authorities → W2 greenfield `SystemState` (direct construction, fixed
ids, truthful UNAVAILABLE deployment/environment) → W4 evidence cycle → W5
causal knowledge (a prior prototype CANARY as the intervention-grade prior)
→ W6 bounded search through the REAL `SearchEngine` (the greenfield graph
carries an INTERFACE node, so boundaries resolve) + the explicit Pareto set
→ W7 assurance PASS → the W8 governed experiment to COMPLETED → W9
GATHER_EVIDENCE → the W11 OBSERVE dispatch (the first governed execution —
the seam) → W9 ACT → W10 narrowing (ACT preserved) → the W11 DEPLOY
dispatch, which FAILS after start (partial failure; timestamps + rollback
reference + verbatim FAILED deployment evidence) → the W9 ROLLBACK decision
→ the W11 ROLLBACK dispatch (typed ROLLED_BACK receipt with SUCCESS recovery
evidence) → the W8 experiment lifecycle transitions to ROLLED_BACK → W12
convergence: the realized system's seed repository is recovered through W3
and enters the same brownfield loop, whose experiment fails and ends in a
governed ROLLED_BACK iteration → the W13 boundary check → closure (the
failure-informed learning hypothesis with UNKNOWN uncertainty; memory v2).

## 11. Adversarial realization notes (design §3 reconciled)

- **ADV-01/02/03 (missing/FAILED/UNKNOWN evidence)**: each case asserts the
  typed outcome at THREE boundaries — the W7 construction rejection or
  distinct gate status, the W12 loop's `ASSURANCE_NOT_PASSED` iteration with
  the status preserved verbatim as W4 evidence, and the W9 refusal (ACT →
  GATHER_EVIDENCE with the state recorded in the reasons). The W9 legs
  compose the full greenfield chain with a directly-constructed "optimistic
  evaluation" citing the faulty evidence (the W12 `assurance_record`
  precedent for boundary tests), because the merged W9 ACT gate checks the
  experiment/evaluation/promotion chain (SOS-W9-F08/F13/F14/F15) BEFORE the
  evidence-set checks (F04/F05).
- **ADV-04/05**: no-run receipts are produced through the real
  `ExecutionSubstrate` over full-chain ACT decisions; pairwise distinctness
  is asserted across UNAVAILABLE/FAILED/UNSUPPORTED receipts and their W4
  conversions.
- **ADV-06**: the forged W7/W8 legs use decisions that CLAIM forged
  references (directly constructed, the W11-test precedent) so the substrate
  registry lookups — not the earlier echo checks — are what refuses them;
  the W12 leg forges a decision id on a real loop record via a field-
  preserving copy and asserts `OptimizationRun.validate` rejects it.
- **ADV-07**: the W12 leg grafts the assured candidate id onto a stale
  revision (explicit `candidate_id`), because `governed_experiment` checks
  candidate identity before revisions.
- **ADV-08**: the W9 leg binds the evaluation to the mismatched experiment
  so the earlier chain checks pass and the experiment/assurance candidate
  mismatch is what REJECTs.
- **ADV-11**: three levels — the substrate refuses an ASK decision (zero
  engagement); the loop under a human-approval policy pauses with the
  explicit `PendingAuthorization` (PENDING-only); the W13 pause cannot be
  resumed with the SAME ASK decision.
- **ADV-13**: the refusal is recorded as a verbatim FAILED W4 observation;
  the lawful MODIFY on an authority module still passes (the gate is
  selective, not blanket — only DELETE is refused on authority modules).
- **ADV-15**: the loop rejects the stale-revision candidate; stale SUCCESS
  evidence becomes typed UNKNOWN and non-promotion-eligible (SOS-W8-F05);
  the recovery at two revisions yields distinct graph ids with the
  uncertainty preserved at both.
- **ADV-16**: the brownfield loop with a failing provider ends in a
  ROLLED_BACK iteration (no promotion record; verbatim FAILED deployment
  evidence; SUCCESS rollback evidence; the experiment lifecycle ROLLED_BACK;
  exactly one provider engagement), and the greenfield scenario's failed
  deploy recovers through the governed W11 ROLLBACK dispatch.

## 12. Requirement and roadmap-gate mapping (filled)

The prepared §1 mapping is realized by the following owning tests (all in
the W14 modules; scenario stages are asserted inside the two end-to-end
scenario tests):

| Requirement(s) | Realization |
| --- | --- |
| R1–R5 | `test_scenario_01_…promotion` (W1 stage), `test_w14_mission_revision_is_explicit_evidence_proposed_and_owner_authorized`, `test_w14_value_model_hard_constraints_filter_candidates` |
| R6 | the two scenarios (brownfield W3 entry; greenfield W11-substrate seam) |
| R7/R8 | `test_scenario_01_…promotion` (W2/W3 stage), `test_w14_subgraph_replacement_boundary_invariants` |
| R9/R21 | `test_adv_01_missing_evidence`, `test_adv_02_failed_evidence`, `test_adv_03_unknown_evidence`, the distinction sweeps, the scenarios' W4 stages |
| R10 | `test_w14_causal_hypothesis_evidence_distinction`, the scenarios' W5 stages |
| R11/R12 | `test_w14_pareto_non_dominated_candidate_output`, the scenarios' W6 stages |
| R13/R14 | `test_adv_12_rollback_bypass_attempts`, `test_adv_16_partial_failure_recovery`, the scenarios' W7/W8/W11 stages |
| R15/R16/R22 | `test_adv_10_provider_self_authorization`, `test_adv_11_ask_bypass_attempts`, the scenarios' W9 stages |
| R17/R18 | `test_adv_09_platform_widening_attempts`, the scenarios' W10 stages |
| R19 | the scenarios' closure stages (learning records + memory v2) |
| R20 | `test_adv_13_self_evolution_boundary_violations`, the scenarios' W13 stages |
| R23 | `test_w14_full_exact_revision_traceability_no_dangling_references`, the scenarios' chain assertions |
| R24 | the repository-resident program itself (this design + the tests + the matrix + the checkpoint) |

Roadmap "Final integrated gate" mapping (the Work Order's binding table):

| Roadmap item | Owning verification |
| --- | --- |
| mission formalization and revision | `test_scenario_01_…promotion` W1 stage + `test_w14_mission_revision…` |
| value-model constraints | `test_w14_value_model_hard_constraints_filter_candidates` + the scenario's `ASSURANCE_NOT_PASSED` iteration |
| context and personalization boundaries | `test_adv_09_platform_widening_attempts` + the scenarios' W10 stages |
| system/architecture graph reconstruction | `test_scenario_01_…promotion` W2/W3 stage (preserved uncertainty) |
| evidence truthfulness | ADV-01/02/03 + the scenarios' verbatim W4 stages |
| causal hypothesis/evidence distinction | `test_w14_causal_hypothesis_evidence_distinction` + W5 stages |
| candidate subgraph replacement | `test_w14_subgraph_replacement_boundary_invariants` + W6 stages |
| multi-objective trade-offs | `test_w14_pareto_non_dominated_candidate_output` + frontier stages |
| assurance and rollback | `test_adv_12_rollback_bypass_attempts`, `test_adv_16_partial_failure_recovery` + both scenario terminals |
| ASK/autonomy policy | `test_adv_11_ask_bypass_attempts` + the scenarios' W9 gating |
| platform adapters | the scenarios' W10 stages (adapter plan + typed constraint) + `test_adv_09` |
| greenfield and brownfield paths | `test_scenario_01_…promotion` + `test_scenario_02_…rollback` |
| SOS self-evolution with meta-adaptation boundary | `test_adv_13_self_evolution_boundary_violations` + the scenarios' W13 stages |
| full exact-revision traceability | `test_w14_full_exact_revision_traceability_no_dangling_references` + the matrix `repoHead` |

## 13. Design resolutions and honest deviations (filled)

1. **W6 search-engine split across the two fixtures.** The W3 static
   recovery conservatively classifies no INTERFACE nodes, so the merged
   `SearchEngine` (which resolves boundaries through interface nodes)
   generates no candidates over a recovered brownfield graph. The brownfield
   scenario therefore composes explicit multi-objective candidates (the
   frozen W12 test precedent) PLUS the W2 `SubgraphReplacement` boundary
   record, while the greenfield fixture (whose graph carries a gateway
   INTERFACE node) exercises the real bounded generation path. Both W6
   surfaces are exercised across the program; C1 holds.
2. **W2 boundary semantics are stricter than W6.** The W2
   `SubgraphReplacement` requires boundary interfaces ⊆ the target subgraph;
   the W6 `SubgraphMutation` only requires boundary ⊆ graph nodes. The
   brownfield fixture's W2 record therefore declares the target as the
   mutation's target plus its boundary node — the same replacement viewed
   under the stricter W2 contract.
3. **Observation (non-blocking, escalated for the Architect; NO `src/sos`
   change was made):** the merged W1 `Mission.approve_revision` reconstructs
   the approved record via `asdict`, which deep-converts the nested
   `Traceability` into a plain dict, so the RETURNED record fails
   `Mission.validate()`. The existing W1 suite never validates the return
   value (latent). The semantic content is intact; the W14 fixture re-issues
   the approved record through the public W1 constructor with the original
   `Traceability`, changing no field values (see
   `mission_revision_from_evidence`). Recorded for the Architect to route to
   W1 if deemed a contract defect; it does not weaken any W14 assertion
   (all mission-revision invariants — explicit, versioned, evidence-proposed,
   owner-authorized — are asserted and hold).
4. **W9 ACT-gate ordering.** The merged W9 ACT path validates the
   experiment/evaluation/promotion chain (SOS-W9-F08 through F15) before
   the evidence-store checks (F04/F05). The adversarial W9 legs (ADV-01/02/03
   and the distinction sweep) therefore compose the full greenfield chain
   with directly-constructed "optimistic evaluations" citing the faulty
   evidence — the W12 `assurance_record` precedent — so the evidence checks
   are exactly what refuses.
5. **`evaluate_personalization` requires `w9_decision_id`.** The W10 stage
   always passes the exact W9 decision id being narrowed (never a synthetic
   placeholder).
6. **Two-commit delivery** (implementation head + checkpoint commit),
   following the W10–W13 convention so the checkpoint and the matrix can
   cite the exact implementation-head SHA. The matrix's `repoHead` carries a
   provisional base-branch citation in the implementation commit and is
   reconciled to the exact implementation head in the checkpoint commit (the
   tip); the checkpoint documents that the tip adds documentation only and
   the verification counts are identical.
7. **`W14-adversarial-evidence-matrix.json` is mechanically checked** by
   `test_w14_adversarial_matrix_file_is_valid_and_reconciled` (schema,
   40-hex `repoHead`, the sixteen frozen case names exactly once each,
   real owning tests in the adversarial module, all-PASS verdicts,
   distinction guarantees within the frozen vocabulary).

## 14. Acceptance-criteria mapping (C1–C10, filled)

| Criterion | Realization |
| --- | --- |
| C1 complete integrated coverage | both scenarios compose W1–W13 through public merged contracts; every roadmap gate item maps to a named passing test (§12) |
| C2 adversarial catalog completeness | the sixteen `test_adv_NN_*` tests; every matrix row names authority/fault/outcome; no case satisfied by an unrelated test |
| C3 governed outcomes hold | every case asserts the typed outcome; `test_w14_zero_provider_engagement_on_pre_gate_rejection` proves zero engagement |
| C4 distinction preservation | the parametrized sweep + the pairwise sweep + per-case distinctness assertions (ADV-02/03/04/05) |
| C5 exact-revision traceability | `test_w14_full_exact_revision_traceability_no_dangling_references`; `OptimizationRun.validate` chain-checks; the matrix cites the run head |
| C6 determinism | the double-run/fresh-store/re-entry/ADV-14 tests; byte-equal canonical bundles |
| C7 recovery correctness | ADV-15/16 end in typed recovered/rolled-back states with verbatim failure evidence and governed rollback |
| C8 verification-only surface | only the seven allowed files changed; zero `src/sos` changes (git diff verified) |
| C9 hermetic execution | the source scan + the offline fixtures (fixed revisions/timestamps, injected port objects) |
| C10 machine-readable matrix | the persisted JSON validated by its reconciliation test and cited by the checkpoint |
