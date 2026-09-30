# W14 Implementation Checkpoint (integrated verification program)

**Work Order:** `spec/work-orders/W14-dogfood-adversarial-verification.md`
(frozen, authoritative)
**State:** `WAITING_FOR_ARCHITECT` (review iteration 1)
**Branch:** `work/w14-dogfood-adversarial` (from live `main` AFTER the W13
merge)
**Base SHA (dispatch commit, live `main` AFTER the W13 merge):**
`c79daac5d664f104d44bb3a9f1015a92391a17f4` — "Reconcile W13 completion
(merge e24889d, independent Architect gate APPROVED, PR #20 review
5368791106, 438 passed + CI green at 62855f95) and open the W14 frontier",
the exact post-W13-merge `main` recorded at dispatch.
**Exact implementation head (contract code, tests, matrix, design):**
`02c12d45b72d2bcf77c177d9f3d98a18d7c18db8`
**Exact branch tip:** the commit carrying this checkpoint (a
documentation-only delta from the implementation head above; a commit cannot
embed its own SHA — the authoritative review head is recorded in the worker
report). The verification outputs below were produced at the implementation
head `02c12d4` and re-run at the tip (identical counts; the tip adds this
file and the matrix `repoHead` reconciliation only).

## Dependency proof (verified by the Worker from live Git history at the base)

Frozen-ledger declared dependencies (verified with `git log`/`git rev-parse`
at the base commit `c79daac`):

- W10 merged `a1778653c35064eeb9d71563f17b30fb174d9429` (PR #17, in the
  branch ancestry)
- W11 merged `aae251813d31f5b85e005d4bff94462a84c440df` (PR #18, in the
  branch ancestry)
- W12 merged `933e1e9ce32f25a1261329aa87038b6c4e5fd084` (PR #19, in the
  branch ancestry)
- W13 merged `e24889df4dd3a846d759dd583c27609b3b9220d2` (PR #20, in the
  branch ancestry; the base `c79daac` is the post-W13-reconciliation commit
  that opened the W14 frontier)

No unmerged branch content was used as a dependency (frozen sequencing rule);
no `src/sos/` file was modified (C8).

Baseline verified by the Worker before any work: exactly **438 passed**,
`compileall` clean, at the base `c79daac` on Python 3.12.14.

## Scope implemented (exactly the seven allowed files — filled)

- `tests/w14_fixtures.py` (NEW, ~2100 lines): the shared deterministic
  fixture builders — no test functions, not collected by pytest's default
  discovery (asserted by a determinism-suite test). Builds: the shared W1
  authorities (mission v1 with the full collaborative formalization
  vocabulary; the evidence-proposed, owner-authorized mission revision;
  value model with one HARD constraint; context; W9 policy with explicit
  ceilings); W4 evidence builders (intervention, rollback, suite, OTel-span,
  UNAVAILABLE runtime gap, arbitrary-truth-state observations); W5 causal
  builders (observation-only `proposed`/UNKNOWN; intervention-confirmed;
  success/failure learning records); W6 builders (objective profiles,
  candidates, Pareto sets with a genuine trade-off, the W2
  `SubgraphReplacement` boundary record); the brownfield fixture repository
  (multi-component, deliberate UNKNOWN/UNAVAILABLE uncertainty) recovered
  through the REAL W3 `recover_repository`; the greenfield-seam fixture
  (directly constructed W2 `SystemState`/`ArchitectureGraph` with fixed ids —
  the non-deterministic `SystemState.create`/W1 `decide` factories are
  deliberately unused); the stub W11 providers (counting, unavailable,
  no-deploy-capability) and the W12 stub simulator (injected port objects);
  the W10 narrowing stage; the W13 stage (the lawful chain through the real
  W7/W8/W9 engines + the frozen-authority refusal record); the two
  integrated scenario runners; and the determinism record-bundle
  serialization.
- `tests/test_w14_dogfood_scenarios.py` (NEW, 9 tests): the two integrated
  Mission-diagram scenarios (brownfield → governed promotion; greenfield
  seam → governed rollback) with closed evidence cycles, plus the focused
  roadmap-gate tests (mission revision; value-model filtering; Pareto
  output; causal distinction; subgraph boundary invariants; full
  exact-revision traceability).
- `tests/test_w14_adversarial_matrix.py` (NEW, 19 tests): the sixteen
  operator-mandated adversarial cases (`test_adv_01` … `test_adv_16`), each
  asserting its typed governed outcome; the dangling-reference rejection and
  zero-provider-engagement support tests; and the persisted-matrix
  reconciliation test.
- `tests/test_w14_determinism.py` (NEW, 14 test items in 9 functions):
  double-run byte-equality for both scenarios; the ADV-14 meta-check;
  fresh-store + `JsonModelStore` round-trip determinism; scenario re-entry;
  the parametrized distinction sweep over FAILED/UNKNOWN/UNAVAILABLE/
  UNSUPPORTED; the pairwise-distinctness sweep; the hermeticity source scan;
  the fixtures-not-collected check.
- `spec/development-state/W14-adversarial-evidence-matrix.json` (NEW): the
  16-row machine-readable matrix (schema
  `sos-w14-adversarial-evidence-matrix/1.0`), `repoHead` = the exact
  implementation head `02c12d45b72d2bcf77c177d9f3d98a18d7c18db8`; every row
  names its attacked authority, injected fault, expected governed outcome,
  expected evidence record, distinction guarantee, owning test id, and PASS
  verdict.
- `spec/development-state/W14-checkpoint.md`: this file, filled.
- `docs/implementation/W14-DOGFOOD-ADVERSARIAL-DESIGN.md` (MODIFIED):
  reconciled to the implemented contract — status header updated; §§9–14
  appended (implemented harness scope, the two scenarios as implemented,
  adversarial realization notes, the requirement + roadmap-gate mapping, the
  design resolutions and honest deviations, the C1–C10 mapping); §§1–8
  preserved verbatim (extend, never weaken).

Zero modifications to `src/sos/`, frozen specs, roadmap, Work Order
machinery, or any W1–W13 test/checkpoint/design file (verified:
`git diff --name-only c79daac..HEAD` lists exactly the seven files above).

## Acceptance criteria → implementation → test mapping (filled)

| Criterion | Implementation | Tests |
|---|---|---|
| C1 complete integrated coverage | both scenarios compose W1–W13 through public merged contracts; the fourteen roadmap "Final integrated gate" items map to named passing tests (design §12) | `test_scenario_01_brownfield_full_chain_ends_in_governed_promotion`, `test_scenario_02_greenfield_seam_full_chain_ends_in_governed_rollback` + the focused roadmap-gate tests |
| C2 adversarial catalog completeness | the sixteen `test_adv_NN_*` tests; every matrix row names authority/fault/outcome; no case is satisfied by an unrelated test | all sixteen + `test_w14_adversarial_matrix_file_is_valid_and_reconciled` |
| C3 governed outcomes hold | every case asserts the typed outcome (rejection / ASK pause with pending record / no-run receipt / monotonic narrowing / boundary refusal / governed rollback); zero provider engagement on pre-gate rejections | the sixteen cases + `test_w14_zero_provider_engagement_on_pre_gate_rejection` |
| C4 distinction preservation | FAILED/UNKNOWN/UNAVAILABLE/UNSUPPORTED stay pairwise distinct through the composed chain in every case and in the dedicated sweeps; none collapses to a favorable value in any produced evidence graph | `test_distinction_sweep_non_success_states_survive_the_composed_chain` (×4), `test_distinction_sweep_pairwise_distinct_end_to_end`, per-case assertions in ADV-02/03/04/05 |
| C5 exact-revision traceability | every dogfood record resolves via content-addressed ids; every cross-authority reference chain-checks (`OptimizationRun.validate`); the matrix cites the exact run head | `test_w14_full_exact_revision_traceability_no_dangling_references`, the scenarios' chain assertions, the matrix `repoHead` |
| C6 determinism | identical fixture inputs → byte-identical records (equal id sets + byte-equal canonical serializations) across repeated runs, fresh stores, and re-entry; clock-free and random-free | `test_double_run_brownfield_scenario_is_byte_identical`, `test_double_run_greenfield_scenario_is_byte_identical`, `test_fresh_store_and_json_round_trip_determinism`, `test_scenario_reentry_over_the_same_fixture_root_is_identical`, `test_adv_14_non_deterministic_outputs_meta_check`, `test_w14_program_is_clock_free_random_free_and_offline` |
| C7 recovery correctness | stale-state and partial-failure cases end in explicitly typed recovered/rolled-back states with verbatim failure evidence and governed rollback; no partial record renders as success | `test_adv_15_stale_state_recovery`, `test_adv_16_partial_failure_recovery` |
| C8 verification-only surface | no `src/sos/` change, no new `sos` exports, no new authority symbols, no product code; the diff touches only the seven allowed files | `git diff --name-only c79daac..HEAD` (exactly the seven files) |
| C9 hermetic execution | zero network, zero subprocess, zero wall-clock/randomness; the whole suite passes offline; a source scan of the four W14 files forbids the non-hermetic tokens | `test_w14_program_is_clock_free_random_free_and_offline` |
| C10 machine-readable persisted matrix | the JSON parses against its schema, contains every required case id exactly once, carries all-PASS verdicts reconciled with the exact test run, and is cited by this checkpoint | `test_w14_adversarial_matrix_file_is_valid_and_reconciled` |

## Required regression coverage mapping (the Work Order's MUST list — filled)

| Required item | Owning test(s) |
|---|---|
| all sixteen adversarial cases, each asserting its governed outcome | `test_adv_01` … `test_adv_16` |
| the two integrated dogfood scenarios end-to-end with closed evidence cycles | `test_scenario_01_…promotion`, `test_scenario_02_…rollback` |
| mission revision is explicit and evidence-proposed (never silent) | `test_w14_mission_revision_is_explicit_evidence_proposed_and_owner_authorized` + the scenario W1 stage |
| value-model hard constraints filter candidates | `test_w14_value_model_hard_constraints_filter_candidates` + the scenario's `ASSURANCE_NOT_PASSED` iteration |
| Pareto/non-dominated candidate output | `test_w14_pareto_non_dominated_candidate_output` + the scenarios' frontier stages |
| causal hypothesis vs evidence distinction | `test_w14_causal_hypothesis_evidence_distinction` + the scenarios' W5 stages |
| subgraph replacement boundary invariants | `test_w14_subgraph_replacement_boundary_invariants` + the scenarios' W6 stages |
| determinism double-runs (identical ids) | the double-run tests + `test_adv_14_…` |
| fresh-store determinism | `test_fresh_store_and_json_round_trip_determinism` |
| distinction sweep over the non-success truth states | the two sweep tests |
| dangling-reference rejection | `test_w14_dangling_reference_rejection` + ADV-01/06 |
| zero provider engagement on pre-gate rejection | `test_w14_zero_provider_engagement_on_pre_gate_rejection` + per-case counters |
| the full pre-existing W1–W13 suite green and unmodified | 478 passed = 438 baseline (unmodified) + 40 W14 items; zero existing test files touched |

## Roadmap "Final integrated gate" mapping (the Work Order's binding table — filled)

| Roadmap MUST-verify item | Named passing verification requirement |
|---|---|
| mission formalization and revision | `test_scenario_01_…promotion` (W1 stage: v2 approved, owner-authorized, evidence-proposed) + `test_w14_mission_revision_is_explicit_evidence_proposed_and_owner_authorized` |
| value-model constraints | `test_w14_value_model_hard_constraints_filter_candidates` (better objectives still FAIL) + the scenario's filtered iteration |
| context and personalization boundaries | `test_adv_09_platform_widening_attempts` + the scenarios' W10 stages (ACT preserved under narrowing) |
| system/architecture graph reconstruction | `test_scenario_01_…promotion` W2/W3 stage (UNKNOWN/UNAVAILABLE uncertainty preserved) |
| evidence truthfulness | ADV-01/02/03 + the scenarios' verbatim W4 stages |
| causal hypothesis/evidence distinction | `test_w14_causal_hypothesis_evidence_distinction` + the W5 stages |
| candidate subgraph replacement | `test_w14_subgraph_replacement_boundary_invariants` (both the W2 and W6 contracts) |
| multi-objective trade-offs | `test_w14_pareto_non_dominated_candidate_output` (2 non-dominated of 3, no scalar) |
| assurance and rollback | `test_adv_12_rollback_bypass_attempts`, `test_adv_16_partial_failure_recovery` + both scenario terminals (promotion / rollback) |
| ASK/autonomy policy | `test_adv_11_ask_bypass_attempts` + the scenarios' ACT/ASK/REJECT gating |
| platform adapters | the scenarios' W10 stages (adapter plan + typed platform constraint, narrowing explicit) |
| greenfield and brownfield paths | `test_scenario_01_…promotion` (W3 entry) + `test_scenario_02_…rollback` (W11-substrate seam entry) converging on the same loop |
| SOS self-evolution with meta-adaptation boundary | `test_adv_13_self_evolution_boundary_violations` (frozen paths, DELETE attacks, recursion bound, refusal-as-evidence) + the scenarios' W13 stages |
| full exact-revision traceability | `test_w14_full_exact_revision_traceability_no_dangling_references` + the matrix `repoHead` = the exact implementation head |

## Verification (filled by the Worker at checkpoint time)

```text
python -m pytest
python -m compileall -q src tests
```

Exact-head results (implementation head `02c12d4`; re-run at the branch tip,
which adds this checkpoint file and the matrix `repoHead` reconciliation
only — identical counts):

```text
$ python3 -m pytest
478 passed in 1.79s
$ python3 -m compileall -q src tests
(exit code 0; no output — clean)
```

Exact pass count: **478** (0 failed, 0 errors, 0 skipped) = 438 baseline
(verified at the recorded dispatch base `c79daac` before any work) + 40 new
W14 test items (9 dogfood-scenario tests, 19 adversarial-module tests, 12
determinism test items across 9 functions — the parametrized sweep counts
as 4 items). Duration is environment-dependent; counts are exact. Fully
offline: no network, no provider, no wall clock, no randomness.

## Matrix reconciliation (filled)

`spec/development-state/W14-adversarial-evidence-matrix.json` at the tip:
schema `sos-w14-adversarial-evidence-matrix/1.0`; `repoHead`
`02c12d45b72d2bcf77c177d9f3d98a18d7c18db8` (the exact implementation head
the 478-pass run was produced at; re-run at the tip with identical counts);
16 rows, one per mandated case, case names exactly the frozen sixteen
(each once); every `verdict` is `PASS`, reconciled with the exact test run
(the owning `test_adv_NN_*` tests are part of the 478; any failure would
fail the suite and falsify the matrix claim); every `testId` resolves to a
real function in `tests/test_w14_adversarial_matrix.py` (mechanically
checked by `test_w14_adversarial_matrix_file_is_valid_and_reconciled`).
The matrix is validated by that test at every run; this checkpoint cites it
per C10.

## Honest deviations and findings (filled)

1. **Two commits** (implementation `02c12d4` + this documentation commit)
   instead of one, following the W10–W13 convention so the checkpoint and
   the matrix can cite an exact implementation-head SHA. The matrix's
   `repoHead` carried a provisional base-branch citation in the
   implementation commit and is reconciled to the exact implementation head
   in this commit (documented in the design §13.6).
2. **Observation for the Architect (non-blocking; NO `src/sos` change was
   made — the W14 protocol forbids it):** the merged W1
   `Mission.approve_revision` reconstructs the approved record via
   `asdict`, deep-converting the nested `Traceability` into a plain dict, so
   the RETURNED record fails `Mission.validate()` (`AttributeError: 'dict'
   object has no attribute 'validate'`). The existing W1 suite never
   validates the return value, so this is latent; the semantic content
   (statement, version, parent chain, history, decided_by) is intact. The
   W14 fixture (`mission_revision_from_evidence`) re-issues the approved
   record through the public W1 constructor with the original
   `Traceability` object, changing no field values, and every
   mission-revision invariant (explicit, versioned, evidence-proposed,
   owner-authorized, never silent) is asserted and holds. Escalated for the
   Architect to route to W1 if deemed a contract defect.
3. **W6 search-engine split across the two fixtures** (design §13.1): the
   W3 static recovery classifies no INTERFACE nodes, so the merged
   `SearchEngine` generates no candidates over a recovered brownfield
   graph; the brownfield scenario composes explicit multi-objective
   candidates (the frozen W12 test precedent) plus the W2
   `SubgraphReplacement` boundary record, while the greenfield fixture
   exercises the real bounded-generation path. Both W6 surfaces are
   exercised across the program; C1 holds.
4. **W2 boundary semantics are stricter than W6** (design §13.2): the W2
   `SubgraphReplacement` requires boundary interfaces ⊆ the target subgraph;
   the fixture's W2 record therefore declares the target as the mutation's
   target plus its boundary node.
5. **W9 ACT-gate ordering** (design §13.4): the adversarial W9 legs
   (ADV-01/02/03, the distinction sweep) compose the full greenfield chain
   with directly-constructed "optimistic evaluations" citing the faulty
   evidence (the W12 `assurance_record` direct-construction precedent),
   because the merged W9 ACT gate validates the experiment/evaluation/
   promotion chain (SOS-W9-F08…F15) before the evidence-store checks
   (F04/F05).
6. **No defect findings among the sixteen cases:** every case produced its
   typed governed outcome through the merged authorities; the only
   observation is item 2 above (latent W1 type-fidelity quirk outside the
   sixteen cases' scope).

## Known limitations (filled)

1. Contract/fixture evidence only (the Work Order's "Evaluation" section):
   the "representative systems" are the two fixture systems (the brownfield
   repository recovered through W3; the greenfield-seam state driven through
   the W11 substrate with stub providers); no live system, real telemetry,
   or real provider is involved, and no performance claim is made.
2. The scenario runners are simulation-level compositions: the W12 loop
   runs with injected deterministic stub evaluators and the W11 seam runs
   against test-local stub providers (the merged port-object pattern);
   promotion/rollback are governed decision records, never live changes.
3. The W10 stage verifies narrowing over the W9 ACT decision
   post-authorization (the loop dispatches under the ACT decision it
   produced; the W10 stage asserts the ACT decision's action remains within
   the contextually/platform-narrowed policy — narrowing never widens).
4. The matrix's `repoHead` cites the implementation head; the branch tip
   (this checkpoint commit) is documentation-only over it, with identical
   verification counts re-run and recorded above.
5. The distinction sweep covers the four non-SUCCESS truth states through
   W4 recording, W7 gate mapping, W9 refusal, W10 narrowing, and the
   W11→W4 receipt conversion; EMPTY is out of scope by design (it is not a
   lawful execution outcome and the W1 authority keeps it distinct from
   SUCCESS).

## Risk / rollback (filled)

**Risk:** false confidence — a case passing because the injection missed
the chain. Mitigated by the Work Order's own requirement, implemented
everywhere: each case binds to a named authority, injects a specific fault,
and asserts a POSITIVE typed outcome (not merely absence of failure), with
counting providers proving zero engagement on pre-gate rejections and the
matrix mechanically reconciled to the owning tests. Secondary risk — a
latent merged defect surfacing later — is covered by the escalation protocol
(item 2 above is the single observation found, already recorded for the
Architect. **Rollback:** ordinary Git revert of the merged W14 change. W14
introduces no runtime state, no schema changes, and no data migration (it
touches no product code), so revert is complete recovery; a revert removes
verification coverage only — the W15 gate would then fail its
adversarial-evidence check by design.

## Completion state (filled)

`WAITING_FOR_ARCHITECT`. No merge, no PR creation, no successor Work Order
(W15 stays blocked), no dispatching, no canonical-state modification. W14
completion requires the Architect gate, actual Git merge, and canonical
reconciliation recording the W14 merge and the W15 frontier. Corrections
stay on the same branch.
