"""W8 — experimentation + promotion / rollback invariant tests.

Failing-first per SOS-IMPLEMENTATION-PROCESS §5: defines the behavioural
contract of ``src/sos/experimentation.py`` before it exists. Covers the W8 Work
Order acceptance criteria C1–C12 and the required regression coverage.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sos import (
    ArchitectureGraph,
    AssuranceResult,
    AssuranceStatus,
    BoundaryContract,
    CandidateObjective,
    CandidateProposal,
    EdgeType,
    Evidence,
    EvidenceKind,
    EvidenceProvenance,
    GraphEdge,
    GraphNode,
    GraphUncertainty,
    InterventionMetadata,
    JsonModelStore,
    ModelValidationError,
    MutationKind,
    NodeType,
    ObjectiveDirection,
    StaticEvidenceAdapter,
    SubgraphMutation,
    SupportKind,
    EvidenceSupport,
    CausalHypothesis,
    CausalRelationType,
    Traceability,
    TruthState,
    TruthfulValue,
    assure_candidate,
)
from sos.experimentation import (
    Experiment,
    ExperimentEvaluation,
    ExperimentMode,
    ExperimentState,
    PromotionDecision,
    PromotionGate,
    RollbackPath,
    StopCondition,
    evaluate_experiment,
    transition_experiment,
)


REVISION = "deadbeefcafebabe1234567890abcdef12345678"


def tr() -> Traceability:
    return Traceability(
        constitution_ref="constitution:1", mission_ref="mission:1",
        value_model_ref="value:1", context_ref="context:1",
    )


def prov(*, source: str = "static-recovery", subject: str = "node-a", env: str = "production", revision: str = REVISION) -> EvidenceProvenance:
    return EvidenceProvenance(
        source=source, observed_subject=subject,
        timestamp="2026-09-09T12:00:00Z", environment=env, implementation_revision=revision,
    )


def evidence(subject: str = "node-a", state: TruthState = TruthState.SUCCESS, value=None, detail=None) -> Evidence:
    if state == TruthState.SUCCESS and value is None:
        value = "observed"
    result = TruthfulValue(state, value, detail)
    return StaticEvidenceAdapter.from_static_observation(
        subject_ref=subject, observation=f"obs-{subject}", result=result,
        traceability=tr(), provenance=prov(subject=subject),
    )


def intervention_evidence(subject: str = "node-a") -> Evidence:
    from sos.evidence import _build_evidence
    return _build_evidence(
        kind=EvidenceKind.EXPERIMENT, source_ref="experiment-42",
        subject_ref=subject,
        result=TruthfulValue(TruthState.SUCCESS, "intervention-applied", None),
        provenance=prov(subject=subject),
        traceability=tr(), timestamp="2026-09-09T12:00:00Z",
        environment="production", confidence=0.9, availability=TruthState.SUCCESS,
    )


def rollback_evidence(subject: str = "node-a") -> Evidence:
    return StaticEvidenceAdapter.from_static_observation(
        subject_ref=subject, observation="rollback path verified",
        result=TruthfulValue(TruthState.SUCCESS, "rollback-capable", None),
        traceability=tr(), provenance=prov(subject=subject),
    )


def _node(node_id: str, name: str = "svc", ntype: NodeType = NodeType.SERVICE) -> GraphNode:
    return GraphNode(
        id=node_id, type=ntype, name=name,
        attributes={"kind": "source", "source_path": name, "revision": REVISION},
        uncertainty=GraphUncertainty(TruthState.SUCCESS, confidence=1.0),
    )


def graph(graph_id: str = "arch-1") -> ArchitectureGraph:
    nodes = (
        _node("node-a", "service-a"),
        GraphNode(id="node-i", type=NodeType.INTERFACE, name="api",
                  attributes={"kind": "source", "source_path": "api", "revision": REVISION},
                  uncertainty=GraphUncertainty(TruthState.SUCCESS, confidence=1.0)),
        _node("node-b", "service-b"),
        _node("node-a-prime", "service-a-prime"),
    )
    edges = (
        GraphEdge(id="e1", type=EdgeType.CALL, source_id="node-a", target_id="node-i",
                  attributes={}, uncertainty=GraphUncertainty(TruthState.SUCCESS, confidence=1.0)),
        GraphEdge(id="e2", type=EdgeType.CALL, source_id="node-i", target_id="node-b",
                  attributes={}, uncertainty=GraphUncertainty(TruthState.SUCCESS, confidence=1.0)),
    )
    contracts = (BoundaryContract(id="bc1", interface_node_id="node-i", contract="HTTP API",
                                  invariants=("stable-schema",), uncertainty=GraphUncertainty(TruthState.SUCCESS, confidence=1.0)),)
    return ArchitectureGraph(
        id=graph_id, version=1, nodes=nodes, edges=edges, boundary_contracts=contracts,
        uncertainty=GraphUncertainty(TruthState.SUCCESS, confidence=1.0), traceability=tr(),
    )


def hypothesis() -> CausalHypothesis:
    ei = intervention_evidence()
    support = EvidenceSupport(
        evidence_id=ei.id, support_kind=SupportKind.INTERVENTION,
        intervention=InterventionMetadata(
            intervention_id="experiment-42", intervention_kind="experiment",
            applied_at="2026-09-09T12:00:00Z", revision=REVISION, environment="production",
        ),
    )
    h = CausalHypothesis(
        cause_subject="node-a", effect_subject="node-b",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="intervention increased latency", status="proposed",
        uncertainty=TruthfulValue(TruthState.SUCCESS, "intervention-backed", None),
        supporting_evidence=(support,), traceability=tr(), provenance_revision=REVISION,
    )
    return h.with_status("confirmed", known_evidence_ids={ei.id}, known_evidence_records={ei.id: ei})


def objectives() -> tuple[CandidateObjective, ...]:
    return (
        CandidateObjective(name="latency", direction=ObjectiveDirection.MINIMIZE, predicted_value=150.0,
                            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted")),
        CandidateObjective(name="cost", direction=ObjectiveDirection.MINIMIZE, predicted_value=1000.0,
                            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted")),
    )


def candidate() -> CandidateProposal:
    ei = intervention_evidence()
    h = hypothesis()
    m = SubgraphMutation(
        kind=MutationKind.SUBGRAPH_REPLACE, base_graph_ref="arch-1",
        target_node_ids=("node-a",), replacement_node_ids=("node-a-prime",),
        boundary_interface_ids=("node-i",), invariants=("preserve-api", "stable-schema"),
    )
    return CandidateProposal(
        id="", base_graph_ref="arch-1", base_graph_revision=REVISION,
        mutation=m, objectives=objectives(), rationale="reduce latency",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not proven"),
        reasoning_evidence_ids=(ei.id,), reasoning_hypothesis_ids=(h.id,),
        risks=("rollback-risk",), traceability=tr(), provenance_revision=REVISION,
    )


def pass_assurance() -> AssuranceResult:
    """A W7 assurance result with status PASS (intervention evidence + rollback evidence + containment)."""
    arch = graph()
    ei = intervention_evidence()
    rb = rollback_evidence()
    h = hypothesis()  # references ei via with_status(..., known_evidence_records={ei.id: ei})
    # Build the candidate referencing the SAME ei and h so known_evidence resolves.
    m = SubgraphMutation(
        kind=MutationKind.SUBGRAPH_REPLACE, base_graph_ref="arch-1",
        target_node_ids=("node-a",), replacement_node_ids=("node-a-prime",),
        boundary_interface_ids=("node-i",), invariants=("preserve-api", "stable-schema"),
    )
    c = CandidateProposal(
        id="", base_graph_ref="arch-1", base_graph_revision=REVISION,
        mutation=m, objectives=objectives(), rationale="reduce latency",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not proven"),
        reasoning_evidence_ids=(ei.id,), reasoning_hypothesis_ids=(h.id,),
        risks=("rollback-risk",), traceability=tr(), provenance_revision=REVISION,
    )
    known = {ei.id: ei, rb.id: rb}
    return assure_candidate(
        candidate=c, base_graph=arch, known_evidence=known, known_hypotheses={h.id: h},
        rollback_evidence_ids=(rb.id,),
    )


def non_pass_assurance(status: AssuranceStatus) -> AssuranceResult:
    """Build a W7 assurance result that is NOT PASS (e.g. FAIL/UNKNOWN/BLOCKED)."""
    arch = graph()
    e = evidence(state=TruthState.UNKNOWN, detail="no data")
    h = CausalHypothesis(
        cause_subject="node-a", effect_subject="node-b",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="r", status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "observation only"),
        supporting_evidence=(), traceability=tr(), provenance_revision=REVISION,
    )
    c = candidate()
    # Override candidate to reference the unknown evidence + unsupported hypothesis.
    c2 = CandidateProposal(
        id="", base_graph_ref=c.base_graph_ref, base_graph_revision=c.base_graph_revision,
        mutation=c.mutation, objectives=c.objectives, rationale=c.rationale,
        uncertainty=c.uncertainty, reasoning_evidence_ids=(e.id,), reasoning_hypothesis_ids=(h.id,),
        risks=c.risks, traceability=c.traceability, provenance_revision=c.provenance_revision,
    )
    return assure_candidate(candidate=c2, base_graph=arch, known_evidence={e.id: e}, known_hypotheses={h.id: h})


def stop_conditions() -> tuple[StopCondition, ...]:
    return (
        StopCondition(name="error-rate-exceeded", threshold=0.05, metric="error-rate"),
        StopCondition(name="latency-regression", threshold=250.0, metric="p99-latency"),
    )


# --- C1: exact candidate/assurance binding ---


def test_experiment_binds_to_exact_candidate_assurance_and_graph():
    ar = pass_assurance()
    exp = Experiment(
        id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision, mode=ExperimentMode.CANARY,
        scope=("node-a",), observation_window=("2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"),
        success_criteria=("latency<200",), stop_conditions=stop_conditions(),
        rollback_ref="rollback-path-1", traceability=tr(),
    )
    assert exp.candidate_id == ar.candidate_id
    assert exp.assurance_result_id == ar.id
    assert exp.base_graph_id == ar.base_graph_id
    assert exp.base_graph_revision == REVISION
    assert exp.traceability.context_ref == "context:1"


def test_experiment_rejects_candidate_assurance_mismatch():
    ar = pass_assurance()
    exp = Experiment(
        id="", candidate_id="wrong-candidate", assurance_result_id=ar.id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision, mode=ExperimentMode.CANARY,
        scope=("node-a",), observation_window=("2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"),
        success_criteria=("latency<200",), stop_conditions=stop_conditions(),
        rollback_ref="rollback-path-1", traceability=tr(),
    )
    # Binding validation against the known assurance must reject the mismatch.
    with pytest.raises(ModelValidationError):
        exp.validate(known_assurance=ar)


# --- C2: entry assurance gate ---


@pytest.mark.parametrize("status", [AssuranceStatus.FAIL, AssuranceStatus.UNKNOWN, AssuranceStatus.BLOCKED])
def test_non_pass_assurance_cannot_enter_executable_experiment(status):
    ar = non_pass_assurance(status)
    exp = Experiment(
        id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision, mode=ExperimentMode.CANARY,
        scope=("node-a",), observation_window=("2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"),
        success_criteria=("latency<200",), stop_conditions=stop_conditions(),
        rollback_ref="rollback-path-1", traceability=tr(),
    )
    # A non-PASS experiment cannot transition to READY (executable).
    with pytest.raises(ModelValidationError):
        transition_experiment(exp, ExperimentState.READY, known_assurance=ar)


def test_pass_assurance_can_enter_executable_experiment():
    ar = pass_assurance()
    exp = Experiment(
        id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision, mode=ExperimentMode.CANARY,
        scope=("node-a",), observation_window=("2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"),
        success_criteria=("latency<200",), stop_conditions=stop_conditions(),
        rollback_ref="rollback-path-1", traceability=tr(),
    )
    ready = transition_experiment(exp, ExperimentState.READY, known_assurance=ar)
    assert ready.state == ExperimentState.READY


# --- C3: bounded experiment model ---


def test_experiment_mode_scope_window_are_explicit_and_validated():
    ar = pass_assurance()
    exp = Experiment(
        id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision, mode=ExperimentMode.SHADOW,
        scope=("node-a", "node-b"), observation_window=("2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"),
        success_criteria=("latency<200",), stop_conditions=stop_conditions(),
        rollback_ref="rb-1", traceability=tr(),
    )
    assert exp.mode == ExperimentMode.SHADOW
    assert len(exp.scope) == 2


def test_experiment_rejects_empty_scope():
    ar = pass_assurance()
    with pytest.raises(ModelValidationError):
        Experiment(
            id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
            base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
            provenance_revision=ar.provenance_revision, mode=ExperimentMode.CANARY,
            scope=(), observation_window=("2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"),
            success_criteria=("latency<200",), stop_conditions=stop_conditions(),
            rollback_ref="rb-1", traceability=tr(),
        )


def test_experiment_rejects_empty_stop_conditions():
    ar = pass_assurance()
    with pytest.raises(ModelValidationError):
        Experiment(
            id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
            base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
            provenance_revision=ar.provenance_revision, mode=ExperimentMode.CANARY,
            scope=("node-a",), observation_window=("2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"),
            success_criteria=("latency<200",), stop_conditions=(),
            rollback_ref="rb-1", traceability=tr(),
        )


# --- C4: truthful evidence evaluation ---


def test_evaluation_preserves_evidence_ids_and_truth_states():
    ar = pass_assurance()
    exp = Experiment(
        id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision, mode=ExperimentMode.CANARY,
        scope=("node-a",), observation_window=("2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"),
        success_criteria=("latency<200",), stop_conditions=stop_conditions(),
        rollback_ref="rb-1", traceability=tr(),
    )
    e_ok = evidence(subject="node-a", value="120ms")
    e_unknown = evidence(subject="node-a", state=TruthState.UNKNOWN, detail="no data")
    known = {e_ok.id: e_ok, e_unknown.id: e_unknown}
    ev = evaluate_experiment(exp, known_evidence=known)
    assert e_ok.id in ev.evidence_ids
    assert e_unknown.id in ev.evidence_ids
    assert ev.evidence_results[e_unknown.id] == TruthState.UNKNOWN


def test_unknown_evidence_cannot_produce_promotion_pass():
    ar = pass_assurance()
    exp = Experiment(
        id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision, mode=ExperimentMode.CANARY,
        scope=("node-a",), observation_window=("2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"),
        success_criteria=("latency<200",), stop_conditions=stop_conditions(),
        rollback_ref="rb-1", traceability=tr(),
    )
    e_unknown = evidence(subject="node-a", state=TruthState.UNKNOWN, detail="no data")
    ev = evaluate_experiment(exp, known_evidence={e_unknown.id: e_unknown})
    # UNKNOWN evidence cannot produce a promotion PASS.
    assert ev.promotion_eligible is False


# --- C5: hard stop / safety conditions ---


def test_hard_stop_condition_stops_experiment_and_cannot_be_offset_by_objectives():
    ar = pass_assurance()
    exp = Experiment(
        id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision, mode=ExperimentMode.CANARY,
        scope=("node-a",), observation_window=("2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"),
        success_criteria=("latency<200",), stop_conditions=stop_conditions(),
        rollback_ref="rb-1", traceability=tr(),
    )
    # A stop condition is triggered (error-rate 0.10 > threshold 0.05).
    e_stop = evidence(subject="node-a", value="error-rate=0.10")
    known = {e_stop.id: e_stop}
    ev = evaluate_experiment(exp, known_evidence=known, stop_trigger=("error-rate-exceeded",))
    # Hard stop fires; experiment is stopped/failed; promotion not eligible.
    assert ev.stopped is True
    assert ev.promotion_eligible is False


# --- C6: promotion gate ---


def test_promotion_requires_successful_evaluation():
    ar = pass_assurance()
    exp = Experiment(
        id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision, mode=ExperimentMode.CANARY,
        scope=("node-a",), observation_window=("2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"),
        success_criteria=("latency<200",), stop_conditions=stop_conditions(),
        rollback_ref="rb-1", traceability=tr(),
    )
    e_ok = evidence(subject="node-a", value="120ms")
    ev = evaluate_experiment(exp, known_evidence={e_ok.id: e_ok})
    # Without a successful evaluation flag, promotion is not granted.
    gate = PromotionGate()
    decision = gate.evaluate(exp, ev, known_assurance=ar)
    assert decision.promoted is False


def test_no_implicit_promotion_from_completion():
    ar = pass_assurance()
    exp = Experiment(
        id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision, mode=ExperimentMode.CANARY,
        scope=("node-a",), observation_window=("2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"),
        success_criteria=("latency<200",), stop_conditions=stop_conditions(),
        rollback_ref="rb-1", traceability=tr(),
    )
    e_ok = evidence(subject="node-a", value="120ms")
    ev = evaluate_experiment(exp, known_evidence={e_ok.id: e_ok}, evaluation_success=True)
    # Even with a successful evaluation, promotion requires an explicit gate decision.
    assert ev.promotion_eligible is True  # eligible, but not yet promoted
    gate = PromotionGate()
    decision = gate.evaluate(exp, ev, known_assurance=ar)
    # The gate decides; promotion is an explicit decision, not implicit.
    assert isinstance(decision, PromotionDecision)


# --- C7: rollback / containment ---


def test_rollback_requires_valid_governed_recovery_evidence():
    ar = pass_assurance()
    exp = Experiment(
        id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision, mode=ExperimentMode.CANARY,
        scope=("node-a",), observation_window=("2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"),
        success_criteria=("latency<200",), stop_conditions=stop_conditions(),
        rollback_ref="rb-1", traceability=tr(),
    )
    rb = rollback_evidence()
    path = RollbackPath(reference="rb-1", evidence_ids=(rb.id,), detail="verified rollback path")
    path.validate(known_evidence={rb.id: rb})
    assert path.recovered is False  # not yet recovered — just eligible


def test_missing_rollback_blocks_promotion_eligibility():
    ar = pass_assurance()
    exp = Experiment(
        id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision, mode=ExperimentMode.CANARY,
        scope=("node-a",), observation_window=("2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"),
        success_criteria=("latency<200",), stop_conditions=stop_conditions(),
        rollback_ref="",  # no rollback reference
        traceability=tr(),
    )
    e_ok = evidence(subject="node-a", value="120ms")
    ev = evaluate_experiment(exp, known_evidence={e_ok.id: e_ok}, evaluation_success=True)
    # Without a rollback reference, promotion is not eligible (no governed recovery).
    assert ev.promotion_eligible is False


def test_documented_containment_exception_allows_promotion_eligibility():
    ar = pass_assurance()
    exp = Experiment(
        id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision, mode=ExperimentMode.SHADOW,
        scope=("node-a",), observation_window=("2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"),
        success_criteria=("latency<200",), stop_conditions=stop_conditions(),
        rollback_ref="",  # no rollback
        containment_policy_ref="governed-containment-exception-2026-001",
        traceability=tr(),
    )
    e_ok = evidence(subject="node-a", value="120ms")
    ev = evaluate_experiment(exp, known_evidence={e_ok.id: e_ok}, evaluation_success=True)
    # A documented containment exception is a governed alternative to rollback.
    assert ev.promotion_eligible is True


# --- C8: lifecycle state machine ---


def test_invalid_state_transitions_rejected():
    ar = pass_assurance()
    exp = Experiment(
        id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision, mode=ExperimentMode.CANARY,
        scope=("node-a",), observation_window=("2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"),
        success_criteria=("latency<200",), stop_conditions=stop_conditions(),
        rollback_ref="rb-1", traceability=tr(),
    )
    # PLANNED -> COMPLETED is not a valid direct transition (must go through READY/RUNNING).
    with pytest.raises(ModelValidationError):
        transition_experiment(exp, ExperimentState.COMPLETED, known_assurance=ar)


def test_valid_lifecycle_progression():
    ar = pass_assurance()
    exp = Experiment(
        id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision, mode=ExperimentMode.CANARY,
        scope=("node-a",), observation_window=("2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"),
        success_criteria=("latency<200",), stop_conditions=stop_conditions(),
        rollback_ref="rb-1", traceability=tr(),
    )
    ready = transition_experiment(exp, ExperimentState.READY, known_assurance=ar)
    running = transition_experiment(ready, ExperimentState.RUNNING, known_assurance=ar)
    completed = transition_experiment(running, ExperimentState.COMPLETED, known_assurance=ar)
    assert completed.state == ExperimentState.COMPLETED
    # Rollback can occur from RUNNING or COMPLETED.
    rolled = transition_experiment(completed, ExperimentState.ROLLED_BACK, known_assurance=ar)
    assert rolled.state == ExperimentState.ROLLED_BACK


def test_rollback_cannot_bypass_intermediate_semantics():
    ar = pass_assurance()
    exp = Experiment(
        id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision, mode=ExperimentMode.CANARY,
        scope=("node-a",), observation_window=("2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"),
        success_criteria=("latency<200",), stop_conditions=stop_conditions(),
        rollback_ref="rb-1", traceability=tr(),
    )
    # PLANNED -> ROLLED_BACK is not valid (must run first or be stopped/failed).
    with pytest.raises(ModelValidationError):
        transition_experiment(exp, ExperimentState.ROLLED_BACK, known_assurance=ar)


# --- C9: multi-objective preservation ---


def test_experiment_preserves_objectives_without_scalar_authority():
    ar = pass_assurance()
    exp = Experiment(
        id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision, mode=ExperimentMode.CANARY,
        scope=("node-a",), observation_window=("2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"),
        success_criteria=("latency<200",), stop_conditions=stop_conditions(),
        rollback_ref="rb-1", traceability=tr(),
    )
    e_ok = evidence(subject="node-a", value="120ms")
    ev = evaluate_experiment(exp, known_evidence={e_ok.id: e_ok}, known_assurance=ar)
    assert len(ev.objectives) == len(ar.objectives)
    assert not hasattr(ev, "quality_score")
    assert not hasattr(ev, "score")


# --- C10: deterministic bounded evaluation ---


def test_evaluation_is_deterministic():
    ar = pass_assurance()
    exp = Experiment(
        id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision, mode=ExperimentMode.CANARY,
        scope=("node-a",), observation_window=("2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"),
        success_criteria=("latency<200",), stop_conditions=stop_conditions(),
        rollback_ref="rb-1", traceability=tr(),
    )
    e_ok = evidence(subject="node-a", value="120ms")
    ev1 = evaluate_experiment(exp, known_evidence={e_ok.id: e_ok})
    ev2 = evaluate_experiment(exp, known_evidence={e_ok.id: e_ok})
    assert ev1.promotion_eligible == ev2.promotion_eligible
    assert ev1.id == ev2.id


# --- C11: persistence + traceability ---


def test_experiment_round_trips_through_json(tmp_path):
    ar = pass_assurance()
    exp = Experiment(
        id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision, mode=ExperimentMode.CANARY,
        scope=("node-a",), observation_window=("2026-09-09T00:00:00Z", "2026-09-10T00:00:00Z"),
        success_criteria=("latency<200",), stop_conditions=stop_conditions(),
        rollback_ref="rb-1", traceability=tr(),
    )
    p = tmp_path / "experiment.json"
    JsonModelStore(p).save(exp)
    data = JsonModelStore(p).load()
    assert data["candidate_id"] == ar.candidate_id
    assert data["base_graph_id"] == "arch-1"
    assert data["mode"] == "canary"
    assert data["traceability"]["context_ref"] == "context:1"


# --- C12: bounded authority surface ---


def test_w8_introduces_no_w9_plus_symbols():
    import sos.experimentation as emod
    forbidden = {
        "AutonomyPolicy", "AskPayload", "Act", "Decision", "DecisionAction",
        "PlatformAdapter", "Personalization", "Greenfield", "Brownfield",
        "SelfEvolution", "MetaAdaptation",
    }
    exported = {n for n in dir(emod) if not n.startswith("_")}
    assert not (forbidden & exported), f"forbidden W9+ symbols present: {forbidden & exported}"


def test_w8_does_not_redefine_assurance_authority():
    import sos.experimentation as emod
    # W8 must not re-export W7 assurance authority symbols (it consumes them read-only).
    forbidden = {"AssuranceResult", "AssuranceStatus", "AssuranceGate", "assure_candidate"}
    exported = {n for n in dir(emod) if not n.startswith("_")}
    assert not (forbidden & exported), f"W8 must not re-export W7 assurance authority: {forbidden & exported}"
