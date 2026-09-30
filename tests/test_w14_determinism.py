"""W14 — the determinism verification program.

Work Order: ``spec/work-orders/W14-dogfood-adversarial-verification.md``
(Required outcomes 4, 9; acceptance criteria C6, C9; the "Determinism
checks" and "Hermetic execution" requirements). Design §6.

Proves that identical fixture inputs produce byte-identical records
(identical content-addressed ids and identical canonical serializations):

- **double-run equality**: each integrated scenario runs twice with
  independently constructed but value-identical fixture inputs;
- **fresh-store equality**: the same scenario re-run against fresh W1/W4
  stores reproduces identical ids (idempotent re-ingestion, the W4 dedup
  pattern; W1 ``JsonModelStore`` round-trips);
- **scenario re-entry**: re-running over the SAME fixture root reproduces
  identical records;
- **ADV-14 meta-check**: the adversarial "non-deterministic outputs" case —
  the suite fails if the merged stack ever diverges under identical inputs;
- **distinction sweep**: every non-success truth state (FAILED, UNKNOWN,
  UNAVAILABLE, UNSUPPORTED) survives the composed chain to the final
  evidence graph as itself, pairwise distinct from all others (R21);
- **hermeticity**: the W14 program is clock-free, random-free, and offline
  (a source scan of the four W14 files).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import w14_fixtures as w14
from sos import (
    AssuranceStatus,
    AutonomyDecisionState,
    ContextDimension,
    DecisionAction,
    EvidenceGraph,
    ExecutionActionScope,
    ExecutionLifecycleState,
    ExecutionReceipt,
    ExperimentEvaluation,
    JsonModelStore,
    PromotionDecision,
    TruthState,
    TruthfulValue,
    assure_candidate,
    evaluate_autonomy,
    evaluate_personalization,
    receipt_to_w4_evidence,
)
from sos.personalization import ContextualSelector
from sos.model import _convert_for_json

# ---------------------------------------------------------------------------
# Double-run equality (C6)
# ---------------------------------------------------------------------------


def test_double_run_brownfield_scenario_is_byte_identical(tmp_path):
    """Two independently built brownfield fixtures produce the identical
    record set: equal id multisets and byte-equal canonical serializations."""
    first = w14.run_brownfield_scenario(tmp_path / "repo-one")
    second = w14.run_brownfield_scenario(tmp_path / "repo-two")

    bundle_a = w14.scenario_bundle(first)
    bundle_b = w14.scenario_bundle(second)
    assert set(bundle_a) == set(bundle_b)
    assert bundle_a == bundle_b

    # the evidence graphs agree record-for-record in deterministic order
    ids_a = [r.id for r in first.evidence_graph.records]
    ids_b = [r.id for r in second.evidence_graph.records]
    assert ids_a == ids_b
    assert ids_a == sorted(ids_a)  # the W4 graph keeps records id-sorted

    # the loop and iteration identities are identical
    assert first.run.loop.id == second.run.loop.id
    assert [it.id for it in first.run.loop.iterations] == [
        it.id for it in second.run.loop.iterations
    ]
    assert [d.id for d in first.run.decisions] == [d.id for d in second.run.decisions]
    assert [r.id for r in first.run.receipts] == [r.id for r in second.run.receipts]


def test_double_run_greenfield_scenario_is_byte_identical(tmp_path):
    """Two independently built greenfield-seam fixtures produce the identical
    record set (deterministic direct construction; no uuid factories)."""
    first = w14.run_greenfield_scenario(tmp_path / "green-one")
    second = w14.run_greenfield_scenario(tmp_path / "green-two")

    bundle_a = w14.scenario_bundle(first)
    bundle_b = w14.scenario_bundle(second)
    assert set(bundle_a) == set(bundle_b)
    assert bundle_a == bundle_b

    # the deterministic greenfield ids are the fixture constants
    assert first.harness.system_state.id == second.harness.system_state.id
    assert first.harness.system_state.id == "w14-gf-state-1"
    assert first.harness.system_state.revision_id == "w14-gf-rev-1"
    assert first.observe_receipt.id == second.observe_receipt.id
    assert first.deploy_receipt.id == second.deploy_receipt.id
    assert first.rollback_receipt.id == second.rollback_receipt.id


def test_adv_14_non_deterministic_outputs_meta_check(tmp_path):
    """The adversarial meta-case: identical inputs → identical outputs. The
    assertion itself fails the suite on any divergence (design §6)."""
    brown_a = w14.run_brownfield_scenario(tmp_path / "b-one")
    brown_b = w14.run_brownfield_scenario(tmp_path / "b-two")
    assert w14.scenario_bundle(brown_a) == w14.scenario_bundle(brown_b)

    green_a = w14.run_greenfield_scenario(tmp_path / "g-one")
    green_b = w14.run_greenfield_scenario(tmp_path / "g-two")
    assert w14.scenario_bundle(green_a) == w14.scenario_bundle(green_b)


# ---------------------------------------------------------------------------
# Fresh-store equality + W1 JsonModelStore round-trip (C6)
# ---------------------------------------------------------------------------


def test_fresh_store_and_json_round_trip_determinism(tmp_path):
    """Re-running against fresh stores reproduces identical ids: the W4
    graph deduplicates idempotently, and the W1 JsonModelStore round-trips
    the loop record byte-identically."""
    first = w14.run_brownfield_scenario(tmp_path / "repo")

    # fresh W4 store: re-ingesting the identical records reproduces the graph
    fresh = EvidenceGraph(
        id=first.evidence_graph.id, version=1, records=(), traceability=w14.tr()
    )
    for record in first.evidence_graph.records:
        fresh = fresh.ingest(record)
    assert [r.id for r in fresh.records] == [
        r.id for r in first.evidence_graph.records
    ]
    # re-ingesting a duplicate is a no-op (the dedup pattern)
    assert fresh.ingest(first.evidence_graph.records[0]) is fresh

    # W1 JsonModelStore round-trip: byte-identical canonical serialization
    store = JsonModelStore(tmp_path / "store" / "loop.json")
    store.save(first.run.loop)
    loaded = json.loads((tmp_path / "store" / "loop.json").read_text(encoding="utf-8"))
    assert loaded == _convert_for_json(first.run.loop)
    expected_bytes = (
        json.dumps(_convert_for_json(first.run.loop), indent=2, sort_keys=True) + "\n"
    )
    assert (tmp_path / "store" / "loop.json").read_text(encoding="utf-8") == expected_bytes


def test_scenario_reentry_over_the_same_fixture_root_is_identical(tmp_path):
    """Scenario re-entry: running the scenario again over the SAME fixture
    root (the repository already exists; the fixture builder is idempotent)
    reproduces byte-identical records."""
    root = tmp_path / "repo"
    first = w14.run_brownfield_scenario(root)
    second = w14.run_brownfield_scenario(root)
    assert w14.scenario_bundle(first) == w14.scenario_bundle(second)
    assert first.run.loop.id == second.run.loop.id


# ---------------------------------------------------------------------------
# The distinction sweep (C4 / R21 — outcome 7)
# ---------------------------------------------------------------------------

NON_SUCCESS_STATES = (
    TruthState.FAILED,
    TruthState.UNKNOWN,
    TruthState.UNAVAILABLE,
    TruthState.UNSUPPORTED,
)


@pytest.mark.parametrize("state", NON_SUCCESS_STATES)
def test_distinction_sweep_non_success_states_survive_the_composed_chain(tmp_path, state):
    """Every non-success truth state survives the composed chain AS ITSELF:
    recorded verbatim by W4, mapped to a distinct non-PASS W7 gate status,
    unable to authorize a W9 ACT, narrowing the W10 decision, and preserved
    verbatim by the W11 receipt → W4 conversion. No state collapses to
    SUCCESS/EMPTY or into another state anywhere."""
    harness = w14.brownfield_harness(tmp_path / "repo")

    # (a) W4: the observation is recorded verbatim with its exact state
    record = w14.stateful_evidence(
        harness.graph.id, w14.BROWN_REVISION, state,
        f"{state.value} observation detail",
    )
    assert record.result.state is state
    assert record.result.state not in (TruthState.SUCCESS, TruthState.EMPTY)

    # (b) W7: the evidence gate maps the state to a distinct non-PASS status
    # (the merged mapping: FAILED→FAIL, UNKNOWN/UNSUPPORTED→UNKNOWN,
    # UNAVAILABLE→BLOCKED — none favorable, FAILED strictly blocking)
    harness.evidence_graph = harness.evidence_graph.ingest(record)
    harness.known_evidence[record.id] = record
    candidate = w14.make_candidate(
        base_graph_id=harness.graph.id, revision=w14.BROWN_REVISION,
        target_node_id=harness.node_ids["svc_notifications.py"],
        replacement_node_id=harness.node_ids["svc_reports.py"],
        boundary_node_id=harness.node_ids["store_ledger.py"],
        reasoning_evidence_ids=(record.id,),
        reasoning_hypothesis_ids=(harness.confirmed_hyp.id,),
        objectives=w14.objectives_profile(100.0, 200.0, 2500.0),
        rationale="distinction sweep candidate",
    )
    assurance = assure_candidate(
        candidate=candidate, base_graph=harness.graph,
        known_evidence=dict(harness.known_evidence),
        known_hypotheses=dict(harness.known_hypotheses),
        rollback_evidence_ids=(harness.rollback_ev.id,),
    )
    assert assurance.status is not AssuranceStatus.PASS
    if state is TruthState.FAILED:
        assert assurance.status is AssuranceStatus.FAIL  # strictly blocking
    evidence_gate = next(
        g for g in assurance.gates if g.name == "evidence-availability"
    )
    assert evidence_gate.status is not AssuranceStatus.PASS

    # (c) W9: the state cannot authorize ACT — an optimistic evaluation
    # citing the state's evidence is refused at the W9 evidence gate and the
    # state value is recorded verbatim in the reasons
    green = w14.greenfield_harness()
    state_evidence = w14.stateful_evidence(
        green.graph.id, w14.GREEN_REVISION, state,
        f"greenfield observation is {state.value}",
        source_ref=f"obs-sweep-{state.value}",
    )
    known_green = dict(green.known_evidence)
    known_green[state_evidence.id] = state_evidence
    optimistic_evaluation = ExperimentEvaluation(
        id="", experiment_id=green.experiment.id,
        assurance_result_id=green.assurance.id,
        candidate_id=green.experiment.candidate_id,
        base_graph_id=green.assurance.base_graph_id,
        base_graph_revision=green.assurance.base_graph_revision,
        provenance_revision=green.assurance.provenance_revision,
        evidence_ids=(state_evidence.id,),
        evidence_results={state_evidence.id: state},
        objectives=(), promotion_eligible=True, stopped=False,
        detail=f"optimistic evaluation over {state.value} evidence",
        traceability=w14.tr(),
    )
    optimistic_promotion = PromotionDecision(
        promoted=True, rationale=f"forged gate decision over {state.value} evidence",
        experiment_id=green.experiment.id,
        evaluation_id=optimistic_evaluation.id,
    )
    decision = evaluate_autonomy(
        policy=green.policy, action=DecisionAction.ACT,
        assurance=green.assurance, experiment=green.experiment,
        promotion=optimistic_promotion, evaluation=optimistic_evaluation,
        evidence_ids=(state_evidence.id,), traceability=w14.tr(),
        known_evidence=known_green,
        blast_radius="limited", risk=0.1, confidence=0.9, reversible=True,
    )
    assert decision.state.value != "ACT"
    assert any(state.value in r for r in decision.reasons)  # recorded verbatim

    # (d) W10: a context value carrying the state narrows the decision
    selector = ContextualSelector(
        id=f"w14-sweep-{state.value}", version=1,
        dimensions=(w14.context_value_state(
            ContextDimension.DEVICE, "class", state,
            f"device class observation is {state.value}",
        ),),
        traceability=w14.tr(),
    )
    personalization = evaluate_personalization(
        policy=harness.policy, selector=selector,
        w9_decision_state=AutonomyDecisionState.ACT,
        w9_decision_id=decision.id,
        traceability=w14.tr(),
    )
    assert personalization.state == "ASK"  # narrowed, never preserved-as-ACT

    # (e) W11 → W4: a receipt with the outcome state converts verbatim
    receipt = sweep_receipt(state, base_graph_id=harness.graph.id)
    converted = receipt_to_w4_evidence(receipt, traceability=w14.tr())
    assert converted.result.state is state
    assert converted.result.state not in (TruthState.SUCCESS, TruthState.EMPTY)

    # (f) the state survives into the final evidence graph as itself
    graph = harness.evidence_graph.ingest(converted)
    stored = next(r for r in graph.records if r.id == converted.id)
    assert stored.result.state is state


def sweep_receipt(state: TruthState, *, base_graph_id: str) -> ExecutionReceipt:
    """A lawful W11 receipt whose outcome carries the given truth state
    (no-run terminals for UNAVAILABLE/UNSUPPORTED; ran terminals with exact
    time provenance for FAILED/UNKNOWN)."""
    lifecycle = {
        TruthState.FAILED: ExecutionLifecycleState.FAILED,
        TruthState.UNKNOWN: ExecutionLifecycleState.OUTCOME_UNKNOWN,
        TruthState.UNAVAILABLE: ExecutionLifecycleState.UNAVAILABLE,
        TruthState.UNSUPPORTED: ExecutionLifecycleState.UNSUPPORTED,
    }[state]
    return ExecutionReceipt(
        request_id="exec-request-sweep", provider_id=w14.PROVIDER_OBSERVE,
        action_scope=ExecutionActionScope.OBSERVE,
        lifecycle=lifecycle,
        outcome=TruthfulValue(
            state, None, f"sweep observation outcome {state.value}"
        ),
        w9_decision_id="autonomy-sweep",
        source_revision=w14.GREEN_REVISION,
        provenance_revision=w14.GREEN_REVISION,
        base_graph_id=base_graph_id,
        base_graph_revision=w14.GREEN_REVISION,
        environment="greenfield-stub",
        started_at=(
            w14.TS_DEPLOY_START
            if state in (TruthState.FAILED, TruthState.UNKNOWN) else None
        ),
        finished_at=(
            w14.TS_DEPLOY_END if state is TruthState.FAILED else None
        ),
    )


def test_distinction_sweep_pairwise_distinct_end_to_end(tmp_path):
    """The four non-success truth states are pairwise distinct through the
    whole composed chain: four evidence records, four receipts, four
    converted evidence records — twelve records, four distinct states, none
    SUCCESS/EMPTY, and every produced id distinct."""
    harness = w14.brownfield_harness(tmp_path / "repo")
    graph = harness.evidence_graph
    receipts = []
    converted = []
    for state in NON_SUCCESS_STATES:
        record = w14.stateful_evidence(
            harness.graph.id, w14.BROWN_REVISION, state,
            f"pairwise {state.value} detail",
            source_ref=f"obs-pairwise-{state.value}",
        )
        graph = graph.ingest(record)
        receipt = sweep_receipt(state, base_graph_id=harness.graph.id)
        receipts.append(receipt)
        evidence = receipt_to_w4_evidence(receipt, traceability=w14.tr())
        converted.append(evidence)
        graph = graph.ingest(evidence)

    observed_states = [r.result.state for r in converted] + [
        r.outcome.state for r in receipts
    ]
    assert len(observed_states) == 8
    assert set(observed_states) == set(NON_SUCCESS_STATES)
    for state in observed_states:
        assert state not in (TruthState.SUCCESS, TruthState.EMPTY)
    # every produced record is distinct (content addressing separates them)
    all_ids = [r.id for r in receipts] + [r.id for r in converted]
    assert len(set(all_ids)) == len(all_ids) == 8
    # the graph holds all of them simultaneously — no state overwrote another
    stored_states = {
        r.result.state for r in graph.records
        if r.result.state in NON_SUCCESS_STATES
    }
    assert stored_states == set(NON_SUCCESS_STATES)
    graph.validate()


# ---------------------------------------------------------------------------
# Hermeticity (C9): clock-free, random-free, offline
# ---------------------------------------------------------------------------

W14_FILES = (
    Path(__file__).resolve().parent / "w14_fixtures.py",
    Path(__file__).resolve().parent / "test_w14_dogfood_scenarios.py",
    Path(__file__).resolve().parent / "test_w14_adversarial_matrix.py",
    Path(__file__).resolve().parent / "test_w14_determinism.py",
)

#: Forbidden non-hermetic tokens (import/call shapes; the W14 program must
#: stay clock-free, random-free, offline, and subprocess-free). The tokens
#: are built by concatenation so that this scan file's own source never
#: literally contains the strings it forbids.
FORBIDDEN_TOKENS = (
    "import " + "random",
    "from " + "random",
    "uuid" + "4",
    "uuid." + "uuid",
    "datetime" + ".now",
    "datetime" + ".",
    "import " + "time",
    "time" + ".time",
    "time" + ".monotonic",
    "import " + "subprocess",
    "subprocess" + ".",
    "import " + "socket",
    "socket" + ".",
    "url" + "lib",
    "import " + "requests",
    "requests" + ".",
    "http" + ".client",
    "os" + ".system",
    "pop" + "en",
)


def test_w14_program_is_clock_free_random_free_and_offline():
    """A source scan of the four W14 program files: no clock, no randomness,
    no network, no subprocess (C9; design §6)."""
    for path in W14_FILES:
        source = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_TOKENS:
            assert token not in source, (
                f"{path.name} contains the forbidden non-hermetic token {token!r}"
            )


def test_w14_fixtures_module_is_not_collected_and_has_no_tests():
    """The shared fixture module carries no test functions and is not named
    for pytest discovery (the Work Order's allowed-surface contract)."""
    assert not w14.__name__.startswith("test_")
    test_functions = [
        name for name in dir(w14)
        if name.startswith("test_") and callable(getattr(w14, name))
    ]
    assert test_functions == []
