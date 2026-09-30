# W12 Optimization Loop Design (first bounded slice)

**Work Order:** `spec/work-orders/W12-optimization-loop.md` (frozen, authoritative)
**Module:** `src/sos/optimization.py` (NEW, 1868 lines)
**Exports:** 18 names, W12 block only, in `src/sos/__init__.py`
**Tests:** `tests/test_w12_optimization_loop.py` (NEW, 1263 lines, 33 items)
**Base:** live `main` after the W11 merge (`aae2518…`), cut at the W12 dispatch
commit `e3a97b895ca7f6cc7206a50bde45b2b55c554195`
**Implementation head:** `cba274710ba3c76a883edbf4a91f836b57279e83`

This document is reconciled to **what was actually implemented** — not to an
aspirational design. Where the Work Order's wording required an interpretation,
the resolution is recorded in §12. Everything below is mechanically enforced by
construction-validation and proven by the 33-test suite.

---

## 1. What this module is (and is not)

W12 is the **governed brownfield optimization-loop orchestrator** — the first
bounded slice of the roadmap's W12. It *composes* the already-merged
authorities into one deterministic, bounded, model-only cycle over a
RECOVERED EXTERNAL system:

```
recovered system state (W3)
  -> candidate proposal (W6, W5-informed)
  -> assurance gate (W7)
  -> governed experiment (W8)
  -> W9 autonomy gate (ACT / ASK / REJECT)
  -> promotion or governed rollback (W8)
  -> evidence recording at every consequential step (W4, verbatim)
```

SOS remains every authority; the loop only orchestrates. It creates **no new
authority class** (architecture §12): every record it owns (`OptimizationLoop`,
`OptimizationRun`, `LoopIteration`, `LoopPromotion`, `LoopStop`,
`PendingAuthorization`, `SimulatedObservation`, and their enums) is a
*composition* record; the error type `OptimizationContractError` subclasses the
W1 `ModelValidationError` family. The loop operates on models and injected
port objects only — no live system, no network, no subprocess, no clock.

## 2. Composed-authority map (referenced, never redefined)

| Authority | Types/functions actually imported and used | Role in the loop |
|---|---|---|
| W1 `model.py` | `ModelValidationError`, `Traceability`, `TruthState`, `TruthfulValue`, `DecisionAction`, `JsonModelStore` (via tests) | error family anchor; truth contract delegated to (`SimulatedObservation` validates through `TruthfulValue`); traceability required with value+context; loop-record persistence |
| W3 `recovery.py` | `RecoveryResult` | the recovered external system: `system_state.architecture` (the graph), `system_state.id`, `revision`; loop input is type-checked to be a real `RecoveryResult` |
| W4 `evidence.py` | `Evidence`, `EvidenceGraph`, `EvidenceKind`, `EvidenceProvenance`, `_build_evidence` | the ONLY evidence path: every consequential step appends through the W4 module's own content-addressed assembly (`_build_evidence`) and `EvidenceGraph.ingest` (dedup + sorted); only existing evidence kinds |
| W5 `causal.py` | `CausalHypothesis`, `CausalKnowledgeGraph` | W5-informed candidate selection: hypotheses flow into W7 assurance (`known_hypotheses`) and are cited per-candidate (`reasoning_hypothesis_ids` → `candidate_hypothesis_ids`) |
| W6 `candidates.py` | `CandidateProposal`, `MutationKind` | candidate provenance: `mutation.kind`, `base_graph_ref`, `base_graph_revision`, `provenance_revision`, reasoning evidence/hypothesis ids; candidates are type-checked and chain-bound to the recovered system |
| W7 `assurance.py` | `AssuranceResult`, `AssuranceStatus`, `assure_candidate` | the assurance gate: the REAL W7 engine runs per candidate with the recovered graph, known evidence, known hypotheses, hard constraints, rollback evidence ids |
| W8 `experimentation.py` | `Experiment`, `ExperimentEvaluation`, `ExperimentMode`, `ExperimentState`, `PromotionDecision`, `PromotionGate`, `RollbackPath`, `StopCondition`, `evaluate_experiment`, `transition_experiment` | the governed experiment lifecycle, the promotion gate, the bounded rollback path, the typed stop conditions |
| W9 `autonomy.py` | `AutonomyDecision`, `AutonomyDecisionState`, `AutonomyRequest`, `evaluate_autonomy` | the autonomy gate at every consequential step: launch, ACT-promotion, and ROLLBACK are each separate REAL W9 decisions |
| W11 `execution.py` | `ExecutionActionScope`, `ExecutionProviderPort`, `ExecutionReceipt`, `ExecutionRequest`, `ExecutionSubstrate`, `RollbackReference`, `receipt_to_w4_evidence` | the optional execution seam: governed DEPLOY dispatch through the real substrate (§9) |

Identity of every referenced authority symbol is test-asserted
(`test_w12_references_frozen_authorities_without_redefining`), and every
W12-owned record's `__module__` is asserted to be `sos.optimization`. W7
statuses map to distinct W1 truth states with **none collapsed**
(`_ASSURANCE_TRUTH`: PASS→SUCCESS, FAIL→FAILED, UNKNOWN→UNKNOWN,
BLOCKED→UNAVAILABLE — C7).

## 3. The governed iteration state machine (required outcome 2)

`IterationOutcome` is a `str`-Enum whose members are exactly the loop's
lawful phases and outcomes — there are no free-form narrative transitions:

- **Non-terminal phases:** `PROPOSED`, `ASSURED`, `EXPERIMENTED`,
  `EVALUATED`, `DECIDED`.
- **Terminal outcomes:** `PROMOTED`, `ROLLED_BACK`,
  `PAUSED_PENDING_AUTHORIZATION`, `REFUSED`, `STOPPED_BY_CONDITION`,
  `GATHER_EVIDENCE`, `ASSURANCE_NOT_PASSED`.

The frozen transition table `_VALID_ITERATION_TRANSITIONS` is the whole
machine:

| From | Allowed to |
|---|---|
| `PROPOSED` | `ASSURED`, `ASSURANCE_NOT_PASSED` |
| `ASSURED` | `EXPERIMENTED`, `REFUSED`, `PAUSED_PENDING_AUTHORIZATION` |
| `EXPERIMENTED` | `EVALUATED` |
| `EVALUATED` | `DECIDED`, `STOPPED_BY_CONDITION` |
| `DECIDED` | `PROMOTED`, `ROLLED_BACK`, `PAUSED_PENDING_AUTHORIZATION`, `REFUSED`, `GATHER_EVIDENCE` |
| *(any terminal)* | *(nothing — terminal outcomes are terminal)* |

`validate_iteration_transition(from, to)` raises `OptimizationContractError`
for any transition not in the table (including non-enum inputs). Inside the
orchestrator, the local `advance()` helper validates every phase change, so
the recorded trajectory is always a legal path. A finished `OptimizationLoop`
records **only terminal outcomes** (`ITERATION_TERMINAL_OUTCOMES`) — the
phases exist to validate the trajectory, not to be persisted.

`LoopStop` carries a typed `LoopStopReason`
(`COMPLETED` / `MAX_ITERATIONS` / `STOP_CONDITION` /
`PAUSED_FOR_AUTHORIZATION`) plus, where lawful, the fired W8 `StopCondition`
record and/or the `PendingAuthorization` record; both are field-presence
validated against the reason, and `OptimizationLoop.validate` cross-checks
the stop against the iteration list (a paused stop requires a paused last
iteration; a max-iterations stop requires the bound to have been reached; a
stop-condition stop requires a stopped last iteration; `iterations_executed`
must equal the record length).

## 4. Chain-integrity invariants (C1)

Three layers make authority leakage mechanically impossible:

1. **Construction validation** (each record, `__post_init__` → `validate`):
   every W12 record is frozen and re-validates itself on construction.
   `LoopIteration` field presence is validated **against the outcome** — an
   experiment reference is impossible without the assurance reference that
   preceded it (the W7-before-W8 ordering is visible in the record itself);
   `PROMOTED` requires a `LoopPromotion` AND an `ACT` decision state;
   `ROLLED_BACK` requires `ROLLBACK`; `PAUSED_PENDING_AUTHORIZATION`
   requires the pending record AND `ASK`; `REFUSED` requires `REJECT`;
   `GATHER_EVIDENCE` requires `GATHER_EVIDENCE`; `STOPPED_BY_CONDITION`
   requires the stop-condition name; a promotion record is only lawful on a
   `PROMOTED` iteration; a pending record only on a paused one.
2. **Loop-record validation** (`OptimizationLoop.validate`): indices exactly
   `1..n` in execution order; iteration count never exceeds the declared
   `max_iterations` (the record itself is bounded); only terminal outcomes;
   stop/iteration consistency; traceability required.
3. **Run-boundary chain check** (`OptimizationRun.validate`): every
   cross-authority reference in every iteration resolves AND binds — the
   assurance is bound to the iteration's candidate; the experiment to the
   iteration's candidate AND assurance; the evaluation to the iteration's
   experiment AND candidate; the governing decision state equals the state
   of the last-cited W9 decision; a promotion's authorizing decision is an
   `ACT` decision bound to the promoted experiment AND assurance; the
   promotion's experiment/evaluation/receipt all resolve; a pending
   authorization references an `ASK` decision; every promotion-gate decision
   references a known experiment/evaluation; every iteration evidence id is
   present in the run's evidence graph. An unresolved W9 reference, a
   mismatched chain, or a dangling evidence id makes the run unconstructible.

## 5. W9 ASK-pause semantics (C2) — never a silent default, never auto-approved

The loop consults the REAL W9 engine (`evaluate_autonomy`) at **three gates
per iteration**: experiment launch (action `EXPERIMENT`), promotion
(action `ACT`, with the W8 gate decision and evaluation), and governed
rollback (action `ROLLBACK`, with the rollback path). Outcomes:

- **ACT** — proceeds (promotion only through `apply_promotion`, §6).
- **REJECT** — the *iteration* terminates as `REFUSED`; the loop continues
  with the next candidate (refusal is not loop termination).
- **ASK** — the loop **PAUSES**: a `PendingAuthorization` is built from the
  real ASK decision (`from_decision` refuses anything that is not a real W9
  `AutonomyDecision` in the ASK state), the iteration terminates as
  `PAUSED_PENDING_AUTHORIZATION`, the stop record is
  `PAUSED_FOR_AUTHORIZATION` carrying the pending record, and a truthful
  `UNKNOWN` OBSERVATION-kind evidence entry records the pause itself
  ("loop paused pending human authorization"). The loop then halts — no
  further candidate is processed.
- **ROLLBACK** (at the rollback gate) — the governed rollback path (§6).
- **GATHER_EVIDENCE** (at the ACT gate) — the iteration terminates as
  `GATHER_EVIDENCE`; the loop continues.

The pause can never resolve itself: `AuthorizationResolution` has exactly
one member, `PENDING`; the frozen `PendingAuthorization` exposes no method
that grants, mints, or upgrades authorization; constructing one in a
resolved state is a contract error. Approval would require a fresh W9
decision under human authority — no such code path exists in this slice.

## 6. W7-before-W8 ordering and PromotionGate/RollbackPath governance (C3, C4)

**W7-before-W8.** `governed_experiment` is the loop's *only* experiment
construction path. It refuses: a non-`AssuranceResult`, a
non-`CandidateProposal`, any status other than `PASS`, and any chain
mismatch (candidate id, base graph id, base graph revision, provenance
revision must all equal the assurance's). It then constructs the W8
`Experiment` (state `PLANNED`) and re-validates through the W8 authority
itself (`experiment.validate(known_assurance=assurance)` — SOS-W8-F01), so
the binding is enforced by both W12 and W8. Experiments require a rollback
reference and non-empty W8-typed stop conditions. In the orchestrator, a
non-PASS assurance never reaches this function: the iteration terminates as
`ASSURANCE_NOT_PASSED` with no experiment, and the failing status is
preserved verbatim in TEST-kind evidence.

**Promotion.** `apply_promotion` requires: a real W8 `PromotionDecision`
with `promoted=True` (a refused gate decision or a non-gate object is a
contract error — there is no implicit promotion path), a real `ACT`-state
W9 decision bound to the exact experiment and assurance, and full chain
agreement (gate↔experiment, gate↔evaluation, evaluation↔experiment,
experiment↔assurance). The resulting `LoopPromotion.promotion_ref` is
mechanically `"<experiment_id>:<evaluation_id>"` — the gate decision's
binding — and is validated as such.

**Rollback.** For `PromotionClass.DEPLOY` the promotion is unconstructible
without a bounded W8 `RollbackPath` that (a) carries recovery evidence ids,
(b) whose `reference` equals the experiment's `rollback_ref`. `MODEL_ONLY`
promotions must not claim an execution receipt. `LoopPromotion` (not just
the function) enforces this — the record itself is the invariant. The
governed rollback path is itself W9-gated: only a `ROLLBACK`-state decision
applies it (the experiment transitions to `ROLLED_BACK`, a ROLLBACK-kind
evidence entry records the applied path); ASK pauses, REJECT refuses.
Stop conditions are W8 `StopCondition`-typed end to end: the simulator may
only fire *declared* conditions, and a fired hard stop terminates both the
iteration (`STOPPED_BY_CONDITION`) and the loop (`LoopStop` carrying the
typed `StopCondition` record).

## 7. W4 verbatim evidence policy (C5)

Every consequential step appends evidence through the existing W4
vocabulary and ingestion path — the W4 module's own `_build_evidence`
(content-addressed assembly, so the evidence-id algorithm exists exactly
once) and `EvidenceGraph.ingest` (the only ingestion path: deduplicating,
order-sorted). Kinds used, all pre-existing (the 13 frozen kinds; no new
kind is defined):

| Step | Kind | Result state |
|---|---|---|
| candidate selection | `OBSERVATION` | SUCCESS (the selected candidate id — the loop's own observed choice) |
| W7 assurance gate | `TEST` | distinct per status: SUCCESS / FAILED / UNKNOWN / UNAVAILABLE |
| simulated experiment outcome | `EXPERIMENT` | the simulator's `TruthState` **verbatim** |
| W11 deployment | `DEPLOYMENT` (via W11 `receipt_to_w4_evidence`) | the receipt's outcome state verbatim |
| governed rollback applied | `ROLLBACK` | SUCCESS (the applied reference) |
| model-only promotion | `OBSERVATION` | SUCCESS (the promotion ref) |
| pending-authorization pause | `OBSERVATION` | UNKNOWN (the pause itself, never silent) |

Nothing inferred is recorded as observed: the loop records its own steps'
outputs (real record ids, real truth states); system facts are never
invented. Provenance is exact (`source`, `observed_subject`, caller-supplied
`timestamp`/`environment`, `implementation_revision` bound to the recovered
revision). FAILED/UNKNOWN/UNAVAILABLE/UNSUPPORTED stay distinct end to end —
the W7 mapping is injective and the simulator's state flows through the
EXPERIMENT-kind evidence, the W8 evaluation, and the recorded outcome
unchanged (C7; parametrized test over the four non-SUCCESS states).

## 8. Determinism, content addressing, and bounds (C6, C8)

- **Bounded:** `max_iterations` is a caller-supplied positive integer; the
  orchestrator never exceeds it, and a loop record carrying more iterations
  than the declared bound is *unconstructible*. Candidate count, iteration
  indices (`1..n`), and stop `iterations_executed` all agree.
- **Deterministic ordering:** candidates are deduplicated by content
  address and sorted by id (stable tie-break: equal ids are identical
  candidates, which cannot both remain).
- **Clock-free:** the core consults no clock — all timestamps
  (`timestamp`, observation windows, receipt times in the W11 seam) are
  caller-supplied data.
- **Content addressing:** `OptimizationLoop`, `LoopIteration`,
  `LoopPromotion`, and `PendingAuthorization` derive their ids as
  sha256-over-own-material (first 16 hex) — `loop-…`, `iteration-…`,
  `loop-promotion-…`, `pending-…`. Identical inputs produce identical loop
  records (byte-identical ids), including across distinct repository roots
  (W3 recovery ids are content-addressed over relative paths).
- **Model-only safety (C8):** no running system, network, subprocess, or
  wall clock anywhere in `src/sos/optimization.py`; the source is scanned
  by test for forbidden tokens (`subprocess`, `socket`, `urllib`,
  `time.time`, `datetime.now`, `uuid4`, `http(s)://`, W13/W14 symbols);
  the W11 seam, when exercised, runs against a test-local stub provider.

## 9. The W11 seam behavior (required outcome 8; optional)

The seam is all-or-nothing at the call boundary: `execution_providers` and
`execution_provider_id` must be supplied together, or neither (model-only
mode). In model-only mode nothing is dispatched, `run.receipts` is empty,
promotions are `MODEL_ONLY` (which must not claim a receipt), and no
DEPLOYMENT-kind evidence exists.

With the seam, dispatch happens **only** after the W8 gate granted promotion
AND the W9 ACT decision resolved — `dispatch_deployment` requires the
`ACT` decision, a `PASS` assurance bound to the exact experiment, and a
rollback path whose reference equals the experiment's `rollback_ref`. It
constructs a real W11 `ExecutionRequest` (DEPLOY scope, `w9_decision_id`,
`w7_assurance_id`, `w8_experiment_id`, `w8_promotion_ref` =
`decision.promotion_id`, `RollbackReference` from the W8 `RollbackPath`)
and submits it through a **real `ExecutionSubstrate`** whose registries are
the loop's current chain records (the authorizing decision, the assurance,
the experiment) and whose providers are the caller-supplied port objects.
All remaining gates are the substrate's own (W9 resolution, scope state,
provider-not-authorizer, W7 PASS + exact chain, W8 chain, rollback
binding) — the loop adds none and bypasses none.

Receipt handling: the receipt converts verbatim into DEPLOYMENT-kind
evidence (`receipt_to_w4_evidence`) and is ingested; only a `SUCCESS`
receipt can produce a DEPLOY-class promotion (with its receipt id); a
FAILED receipt promotes **nothing** — the failure evidence is preserved
verbatim and the iteration falls through to the W9-governed rollback path;
an UNAVAILABLE provider yields a truthful no-run UNAVAILABLE receipt (the
provider is never called) and likewise routes to governed rollback.

## 10. The orchestrator's normative pipeline

`run_optimization_loop` (keyword-only, all registries caller-supplied):

1. Validate caller data: real `RecoveryResult`; real `AutonomyRequest`
   policy; `max_iterations` positive; non-empty all-`StopCondition` stops;
   `risk`/`confidence` in [0, 1]; simulator is an `ExperimentSimulatorPort`;
   seam all-or-nothing; traceability and policy validated.
2. Bind candidates to the recovered system (`base_graph_ref` = recovered
   graph id; `base_graph_revision` and `provenance_revision` = the
   recovered revision) — foreign candidates are rejected (C1).
3. Order candidates deterministically (§8); build the evidence/hypotheses
   registries (caller-supplied graph, or a fresh one); resolve
   `rollback_evidence_ids` against the graph.
4. For each candidate (index 1..n, bounded): selection evidence → real W7
   `assure_candidate` → TEST evidence → non-PASS terminates the iteration
   as `ASSURANCE_NOT_PASSED` (continue) → build the W8 `RollbackPath` →
   `governed_experiment` (C3) → W9 launch decision → REJECT refuses /
   ASK pauses (§5) → W8 lifecycle `PLANNED→READY→RUNNING→terminal`
   (COMPLETED/STOPPED/FAILED via real `transition_experiment`, with the
   injected simulator's `SimulatedObservation`; undeclared fired stops are
   contract errors) → EXPERIMENT evidence (verbatim truth state) → real
   `evaluate_experiment` → a stopped evaluation terminates iteration AND
   loop as `STOPPED_BY_CONDITION` → real `PromotionGate.evaluate` → if
   granted: W9 ACT-gate → ACT (+seam: §9; −seam: model-only promotion) /
   ASK pause / REJECT refuse / GATHER_EVIDENCE → else (or failed
   deployment): W9 ROLLBACK-gate → ROLLBACK applies the governed rollback
   (experiment → `ROLLED_BACK`, ROLLBACK evidence) / ASK pause / REJECT
   refuse.
5. Assemble the `LoopStop` (COMPLETED when nothing fired), the
   `OptimizationLoop`, and the `OptimizationRun`; `run.validate()` chain
   checks everything (§4); return the run.

The injected port object (`ExperimentSimulatorPort`, `simulator_id` +
`simulate(experiment) -> SimulatedObservation`) is the Work Order's
"deterministic stub evaluator": model-only, authority-free — its output is
only ever a `TruthState` that flows through the W4/W8/W9 gates unchanged,
and `SimulatedObservation` delegates its value/detail contract to W1
`TruthfulValue` (EMPTY is not a lawful outcome — it is an observation-
capture state; SUCCESS requires a value; non-SUCCESS requires detail).

## 11. Acceptance-criteria traceability (C1–C10 → implementation + tests)

| Criterion | Implementation | Tests |
|---|---|---|
| **C1** composed-authority integrity | §2 import map; `run_optimization_loop` candidate↔recovered-system binding; `OptimizationRun.validate` full chain check (§4) | `test_w12_references_frozen_authorities_without_redefining`, `test_loop_record_enforces_terminal_outcomes_and_chain_consistency`, `test_unresolved_w9_reference_is_rejected_at_the_run_boundary`, `test_loop_rejects_candidates_targeting_foreign_systems` |
| **C2** W9 gate mechanics | three real W9 gates (§5); `PendingAuthorization` from real ASK only; single-member `AuthorizationResolution`; no auto-approve path | `test_w9_ask_pauses_loop_with_explicit_pending_authorization_record`, `test_pending_authorization_can_never_auto_approve`, `test_w9_reject_refuses_the_iteration_and_the_loop_continues`, `test_pending_authorization_requires_a_real_ask_decision`, `test_unresolved_w9_reference_is_rejected_at_the_run_boundary` |
| **C3** W7→W8 ordering | `governed_experiment` PASS + exact-chain requirement, re-validated by W8; `LoopIteration` experiment-requires-assurance | `test_governed_experiment_requires_w7_pass_bound_to_exact_chain` (FAIL/UNKNOWN/foreign-candidate/non-record), `test_loop_records_assurance_not_passed_without_any_experiment` |
| **C4** governed promotion/rollback | `apply_promotion` (granted gate + ACT + full chain); `LoopPromotion` DEPLOY rollback/receipt rules; ROLLBACK-state decision applies rollback; typed stops | `test_promotion_requires_the_promotion_gate_decision`, `test_promotion_requires_a_resolved_w9_act_decision`, `test_deploy_class_promotion_requires_a_bounded_rollback_path`, `test_stop_condition_fires_and_terminates_the_loop`, `test_model_only_failed_experiment_routes_to_governed_rollback`, `test_failed_deployment_routes_to_governed_rollback` |
| **C5** verbatim W4 evidence | §7 policy; only existing kinds; `_build_evidence` + `ingest` | `test_w4_evidence_appended_at_every_consequential_step`, `test_loop_records_assurance_not_passed_without_any_experiment`, `test_w11_seam_dispatches_governed_deployment` (DEPLOYMENT evidence), `test_model_only_failed_experiment_routes_to_governed_rollback` (ROLLBACK evidence) |
| **C6** determinism and bounds | §8: fixed bound, id-sorted dedup, clock-free, sha256 ids | `test_full_loop_happy_path_produces_governed_deterministic_record` (rerun equality), `test_identical_inputs_from_distinct_repositories_produce_identical_ids`, `test_deterministic_candidate_ordering_and_dedup`, `test_max_iteration_bound_bounds_the_loop` (incl. record-beyond-bound unconstructible) |
| **C7** distinction preservation | injective `_ASSURANCE_TRUTH`; verbatim simulator truth into EXPERIMENT evidence; outcomes never favorable | `test_distinctions_preserved_through_the_loop` (×4: FAILED/UNKNOWN/UNAVAILABLE/UNSUPPORTED), `test_simulated_observation_preserves_truthful_distinctions`, `test_unavailable_provider_yields_truthful_unavailable_receipt` |
| **C8** model-only safety | no live/network/subprocess/clock; seam against stub providers; seam all-or-nothing | `test_no_successor_stage_or_live_execution_symbols` (exported-symbol + source-token scans), `test_w11_seam_model_only_mode_without_providers`, `test_w11_seam_dispatches_governed_deployment` |
| **C9** persistence round-trip | plain W1-serializable records; `JsonModelStore` round-trip; no new persistence authority | `test_loop_record_round_trips_through_w1_json_store` |
| **C10** bounded authority surface | W12 exports only through `sos.__init__`; no successor symbols; `OptimizationContractError` in W1 family | `test_no_successor_stage_or_live_execution_symbols`, `test_w12_references_frozen_authorities_without_redefining`, `test_iteration_state_machine_rejects_free_form_transitions` |

## 12. Work-Order required regression coverage → test mapping

The WO's required list, one-to-one (33 items: 30 functions, one
parametrized ×4):

| WO required coverage | Tests |
|---|---|
| full-loop happy path (deterministic record) | `test_full_loop_happy_path_produces_governed_deterministic_record` |
| W9 ASK pause with pending record | `test_w9_ask_pauses_loop_with_explicit_pending_authorization_record`, `test_pending_authorization_can_never_auto_approve` |
| W9 REJECT refusal | `test_w9_reject_refuses_the_iteration_and_the_loop_continues` |
| missing/unresolved W9 reference rejection | `test_unresolved_w9_reference_is_rejected_at_the_run_boundary`, `test_pending_authorization_requires_a_real_ask_decision` |
| W7-missing / W7-fail experiment rejection | `test_governed_experiment_requires_w7_pass_bound_to_exact_chain`, `test_loop_records_assurance_not_passed_without_any_experiment` |
| promotion without PromotionGate rejection | `test_promotion_requires_the_promotion_gate_decision` |
| DEPLOY without RollbackPath rejection | `test_deploy_class_promotion_requires_a_bounded_rollback_path` |
| stop-condition termination | `test_stop_condition_fires_and_terminates_the_loop` |
| max-iteration bound | `test_max_iteration_bound_bounds_the_loop` |
| determinism (identical runs → identical ids) | `test_full_loop_happy_path_produces_governed_deterministic_record`, `test_identical_inputs_from_distinct_repositories_produce_identical_ids`, `test_deterministic_candidate_ordering_and_dedup` |
| W4 evidence appended at every step | `test_w4_evidence_appended_at_every_consequential_step` |
| candidate provenance citation | `test_candidate_provenance_is_cited_in_iteration_records` |
| distinction preservation through the loop | `test_distinctions_preserved_through_the_loop` (×4), `test_simulated_observation_preserves_truthful_distinctions` |
| W11-substrate seam in model-only mode | `test_w11_seam_model_only_mode_without_providers`, `test_w11_seam_dispatches_governed_deployment`, `test_failed_deployment_routes_to_governed_rollback`, `test_unavailable_provider_yields_truthful_unavailable_receipt` |
| JSON round-trip | `test_loop_record_round_trips_through_w1_json_store` |
| absence of W13/W14/live-execution symbols | `test_no_successor_stage_or_live_execution_symbols`, `test_w12_references_frozen_authorities_without_redefining` |

Plus state-machine/record-shape regressions beyond the list:
`test_iteration_state_machine_rejects_free_form_transitions`,
`test_loop_record_enforces_terminal_outcomes_and_chain_consistency`,
`test_loop_rejects_candidates_targeting_foreign_systems`,
`test_model_only_failed_experiment_routes_to_governed_rollback`.

The suite composes the REAL authorities end-to-end: the recovered system is
produced by the real W3 `recover_repository` over a fixture repository;
candidates/hypotheses/evidence are real W6/W5/W4 records; assurance,
experiments, evaluations, gates, and decisions come from the real
W7/W8/W9 engines; deployments go through the real W11 `ExecutionSubstrate`
against a test-local stub provider. The deterministic stub evaluator
(`StubSimulator`) and the stub deploy provider stay local to the test
module — injected port objects, per the port boundary.

## 13. Design resolutions (Work-Order wording → implemented reading)

1. **"W3 `RecoveryResult` id"** (required outcome 1): W3's `RecoveryResult`
   is a plain frozen record with no id field of its own. The loop therefore
   binds the recovered system by `recovery.system_state.id`
   (`recovered_state_ref`) + `recovery.revision` (`recovered_revision`) —
   the W3 identity pair — and additionally records the base graph
   id/revision and provenance revision. All are chain-checked.
2. **"experiment launch ... gated on resolved W9 decisions"** (required
   outcome 3): implemented as a dedicated W9 decision with
   `DecisionAction.EXPERIMENT` at launch, distinct from the ACT decision at
   promotion and the ROLLBACK decision at rollback — three separate gates,
   each a real `evaluate_autonomy` call.
3. **Simulation-level composition (mission):** the "experiment execution"
   inside the loop is the injected `ExperimentSimulatorPort` (model-only
   deterministic evaluator), while the optional W11 seam governs the
   DEPLOY step only. This matches the WO's "deterministic stub evaluators"
   and its "optionally, via its port" reading of substrate use.
4. **`GATHER_EVIDENCE` as an iteration outcome:** the W9 state machine
   includes GATHER_EVIDENCE; at the ACT gate it terminates the iteration
   (recorded truthfully, loop continues) rather than looping internally —
   the WO's "bounded" requirement forbids unbounded re-entry, and a fresh
   evidence-gathering pass would be a new loop run under fresh policy.
5. **Stop-condition evidence kind:** the fired stop is recorded via the
   iteration's EXPERIMENT-kind evidence (the simulated observation that
   fired it) plus the typed `StopCondition` on both the iteration and the
   stop record; no new evidence kind was added for stops (C5 forbids new
   kinds).

## 14. Exclusions honored (WO "Explicit exclusions")

No live production access, network I/O, subprocess spawning, or deployment
(source-token-scanned by test); no W13 self-evolution (the loop targets
recovered EXTERNAL systems — `sos.optimization` contains no self-evolution
symbols; scanned); no W14 dogfood/adversarial verification; no new
mission/value/context/evidence/causal/candidate/assurance/experiment/
autonomy/execution/error/persistence authority (identity-asserted by
test); no LLM output as authorization/truth/evidence; no unbounded
iteration, wall-clock dependence, or nondeterministic ordering; no mutation
of the Constitution, frozen specs, or roadmap. Implementation surface is
exactly the five allowed files (implementation commit: the three code/test
files; this documentation commit adds the two docs files).

## 15. Deterministic verification (exact-head results)

At the implementation head `cba2747` (and re-run at the branch tip, which
adds documentation only — identical counts):

```text
$ python3 -m pytest
360 passed in 1.01s
$ python3 -m compileall -q src tests
(exit code 0; no output — clean)
```

360 = 327 baseline (verified at base `e3a97b8` before any work) + 33 new
W12 items. Fully offline: no network, no provider, no wall clock.

## 16. Known limitations (honest)

1. Contract/composition evidence only — the loop is exercised on fixture
   recovered-system models with injected stub evaluators (WO "Evaluation"
   section); real brownfield system ingestion stays out of this slice.
2. A paused loop has no in-slice resume path: resumption after human
   authorization is a fresh `run_optimization_loop` invocation under a
   fresh policy decision (the pending record is deliberately inert).
3. The per-dispatch W11 substrate registries are the loop's current chain
   records; cross-run registry persistence is W11's known limitation, not
   resolved here.
4. `SimulatedObservation.value` is free-form caller data (W1-validated);
   the loop does not interpret it beyond truth-state preservation.
5. Multi-objective ranking across candidates is not implemented — W6
   candidates arrive ranked by their content-addressed ids (deterministic
   order per required outcome 6); value-ranking over objectives would be a
   governed later slice.

## 17. Stop-condition review

- No step bypasses W7/W8/W9: experiment construction, promotion, rollback,
  and DEPLOY dispatch are each mechanically gated (§4–§6, §9).
- No inferred evidence: every appended W4 entry is an observed loop-step
  output with exact provenance (§7).
- No authority duplicated: identity-asserted imports only (§2).
- No successor-stage symbols, no self-modification, no live execution
  (§14, test-enforced).
- Worker stops at `WAITING_FOR_ARCHITECT`; corrections stay on this branch.
