"""W9 — autonomy + ASK + human authority invariant tests.

Failing-first per SOS-IMPLEMENTATION-PROCESS §5: defines the behavioural
contract of ``src/sos/autonomy.py`` before it exists. Covers the W9 Work Order
acceptance criteria C1–C12 and the required regression coverage.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sos import (
    AssuranceResult,
    AssuranceStatus,
    CandidateObjective,
    CandidateProposal,
    DecisionAction,
    Evidence,
    EvidenceKind,
    EvidenceProvenance,
    Experiment,
    ExperimentMode,
    ExperimentState,
    GraphEdge,
    GraphNode,
    GraphUncertainty,
    JsonModelStore,
    ModelValidationError,
    MutationKind,
    NodeType,
    ObjectiveDirection,
    PromotionDecision,
    PromotionGate,
    RollbackPath,
    StaticEvidenceAdapter,
    SubgraphMutation,
    SupportKind,
    CausalHypothesis,
    CausalRelationType,
    EvidenceSupport,
    InterventionMetadata,
    EdgeType,
    BoundaryContract,
    Traceability,
    TruthState,
    TruthfulValue,
    assure_candidate,
    evaluate_experiment,
    transition_experiment,
)
from sos.autonomy import (
    AutonomyDecision,
    AutonomyDecisionState,
    AutonomyRequest,
    PolicyCeiling,
    evaluate_autonomy,
)


REVISION = "deadbeefcafebabe1234567890abcdef12345678"


def tr() -> Traceability:
    return Traceability(
        constitution_ref="constitution:1", mission_ref="mission:1",
        value_model_ref="value:1", context_ref="context:1",
    )


def prov(*, subject: str = "node-a", env: str = "production", revision: str = REVISION) -> EvidenceProvenance:
    return EvidenceProvenance(
        source="static-recovery", observed_subject=subject,
        timestamp="2026-09-10T12:00:00Z", environment=env, implementation_revision=revision,
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
        traceability=tr(), timestamp="2026-09-10T12:00:00Z",
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


def graph(graph_id: str = "arch-1"):
    from sos import ArchitectureGraph
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


def hypothesis():
    ei = intervention_evidence()
    support = EvidenceSupport(
        evidence_id=ei.id, support_kind=SupportKind.INTERVENTION,
        intervention=InterventionMetadata(
            intervention_id="experiment-42", intervention_kind="experiment",
            applied_at="2026-09-10T12:00:00Z", revision=REVISION, environment="production",
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


def objectives():
    return (
        CandidateObjective(name="latency", direction=ObjectiveDirection.MINIMIZE, predicted_value=150.0,
                            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted")),
        CandidateObjective(name="cost", direction=ObjectiveDirection.MINIMIZE, predicted_value=1000.0,
                            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted")),
    )


def candidate():
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


def pass_assurance():
    arch = graph()
    ei = intervention_evidence()
    rb = rollback_evidence()
    h = hypothesis()
    c = candidate()
    known = {ei.id: ei, rb.id: rb}
    return assure_candidate(
        candidate=c, base_graph=arch, known_evidence=known, known_hypotheses={h.id: h},
        rollback_evidence_ids=(rb.id,),
    )


def completed_experiment_with_promotion(ar: AssuranceResult):
    """Build a COMPLETED experiment with a promotion-eligible evaluation + a promoted PromotionDecision."""
    exp = Experiment(
        id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision, mode=ExperimentMode.CANARY,
        scope=("node-a",), observation_window=("2026-09-10T00:00:00Z", "2026-09-11T00:00:00Z"),
        success_criteria=("latency<200",), stop_conditions=(
            __import__("sos").StopCondition(name="error-rate", threshold=0.05, metric="error-rate"),
        ),
        rollback_ref="rb-1", traceability=tr(), state=ExperimentState.COMPLETED,
    )
    e_ok = evidence(subject="node-a", value="120ms")
    rb = rollback_evidence()
    known = {e_ok.id: e_ok, rb.id: rb}
    rbp = RollbackPath(reference="rb-1", evidence_ids=(rb.id,), detail="verified rollback path")
    ev = evaluate_experiment(
        exp, known_evidence=known, evidence_refs=(e_ok.id,),
        evaluation_success=True, rollback_path=rbp, known_assurance=ar,
    )
    gate = PromotionGate()
    decision = gate.evaluate(exp, ev, known_assurance=ar)
    return exp, ev, decision


def policy():
    """A W9 autonomy policy with bounded scope/ceilings."""
    return AutonomyRequest(
        id="policy-1", version=1,
        allowed_actions=(DecisionAction.ACT, DecisionAction.EXPERIMENT, DecisionAction.GATHER_EVIDENCE),
        ceilings=PolicyCeiling(
            max_risk=0.3, max_blast_radius="service", require_reversible=True,
            min_confidence=0.8, require_human_approval_for_act=False,
        ),
        traceability=tr(),
    )


# --- C1: explicit autonomy policy ---


def test_policy_is_structured_and_bounded():
    p = policy()
    assert p.allowed_actions  # non-empty
    assert p.ceilings.max_risk > 0
    assert p.ceilings.require_reversible is True
    assert p.traceability.context_ref == "context:1"


def test_policy_cannot_authorize_beyond_decled_scope():
    p = policy()  # allows ACT and EXPERIMENT but not ROLLBACK
    assert DecisionAction.ROLLBACK not in p.allowed_actions
    # Evaluating a ROLLBACK action against this policy should not authorize it.
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ROLLBACK,
        assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(), traceability=tr(),
    )
    assert result.state == AutonomyDecisionState.REJECT  # action not in allowed_actions -> REJECT


# --- C2: explicit action/request state machine ---


def test_act_requires_promotion_and_policy_authorization():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    e_ok = evidence(subject="node-a", value="120ms")
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT,
        assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(e_ok.id,), traceability=tr(),
        known_evidence={e_ok.id: e_ok}, confidence=0.9, risk=0.1,
        evaluation=ev,
    )
    assert result.state == AutonomyDecisionState.ACT


def test_non_pass_assurance_cannot_act():
    """C4: W7 PASS is non-authorizing; non-PASS cannot ACT."""
    # Build a FAIL assurance by using unknown evidence
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    # Override: simulate a FAIL assurance by creating a mismatched one
    # We can't easily build a FAIL AssuranceResult via the fixture; instead test
    # that ACT without a promoted promotion decision fails.
    # A non-promoted promotion decision:
    non_promoted = PromotionDecision(
        promoted=False, rationale="not promoted",
        experiment_id=exp.id, evaluation_id=ev.id,
    )
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT,
        assurance=ar, experiment=exp, promotion=non_promoted,
        evidence_ids=(), traceability=tr(),
    )
    assert result.state != AutonomyDecisionState.ACT


# --- C3: human authority / ASK gate ---


def test_unresolved_authority_routes_to_ask():
    """C3: when human approval is required and not present, route to ASK."""
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    # A policy that requires human approval for ACT.
    p_with_approval = AutonomyRequest(
        id="policy-2", version=1,
        allowed_actions=(DecisionAction.ACT,),
        ceilings=PolicyCeiling(
            max_risk=0.3, max_blast_radius="service", require_reversible=True,
            min_confidence=0.8, require_human_approval_for_act=True,  # requires human
        ),
        traceability=tr(),
    )
    result = evaluate_autonomy(
        policy=p_with_approval, action=DecisionAction.ACT,
        assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(), traceability=tr(),
        human_authority_present=False,  # no human authority present
    )
    assert result.state == AutonomyDecisionState.ASK


def test_human_authority_present_allows_act():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p_with_approval = AutonomyRequest(
        id="policy-2", version=1,
        allowed_actions=(DecisionAction.ACT,),
        ceilings=PolicyCeiling(
            max_risk=0.3, max_blast_radius="service", require_reversible=True,
            min_confidence=0.8, require_human_approval_for_act=True,
        ),
        traceability=tr(),
    )
    e_ok = evidence(subject="node-a", value="120ms")
    result = evaluate_autonomy(
        policy=p_with_approval, action=DecisionAction.ACT,
        assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(e_ok.id,), traceability=tr(),
        human_authority_present=True,
        known_evidence={e_ok.id: e_ok}, confidence=0.9, risk=0.1,
        evaluation=ev,
    )
    assert result.state == AutonomyDecisionState.ACT


# --- C5: truthful uncertainty gate ---


def test_unknown_evidence_cannot_authorize():
    """C5: UNKNOWN truth state cannot become authorization."""
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT,
        assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=("unknown-ev",),  # evidence id that doesn't resolve to SUCCESS
        traceability=tr(),
        known_evidence={},  # empty -> all UNKNOWN
    )
    assert result.state != AutonomyDecisionState.ACT


# --- C6: bounded action scope ---


def test_blast_radius_exceeding_ceiling_routes_to_ask():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()  # max_blast_radius = "service"
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT,
        assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(), traceability=tr(),
        blast_radius="organization",  # exceeds "service"
    )
    assert result.state == AutonomyDecisionState.ASK


# --- C7: evidence and traceability chain ---


def test_decision_records_evidence_and_traceability():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    e_ok = evidence(subject="node-a", value="120ms")
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT,
        assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(e_ok.id,), traceability=tr(),
        known_evidence={e_ok.id: e_ok},
    )
    assert e_ok.id in result.evidence_ids
    assert result.assurance_id == ar.id
    assert result.experiment_id == exp.id
    assert result.traceability.context_ref == "context:1"


# --- C8: rollback/containment integrity ---


def test_rollback_requires_governed_recovery():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    # A policy that allows ROLLBACK
    p_rb = AutonomyRequest(
        id="policy-rb", version=1,
        allowed_actions=(DecisionAction.ROLLBACK,),
        ceilings=PolicyCeiling(
            max_risk=0.3, max_blast_radius="service", require_reversible=True,
            min_confidence=0.8, require_human_approval_for_act=False,
        ),
        traceability=tr(),
    )
    # Without a rollback path, ROLLBACK should route to ASK
    result = evaluate_autonomy(
        policy=p_rb, action=DecisionAction.ROLLBACK,
        assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(), traceability=tr(),
        rollback_path=None,
    )
    assert result.state == AutonomyDecisionState.ASK


def test_rollback_with_governed_recovery_can_act():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p_rb = AutonomyRequest(
        id="policy-rb", version=1,
        allowed_actions=(DecisionAction.ROLLBACK,),
        ceilings=PolicyCeiling(
            max_risk=0.3, max_blast_radius="service", require_reversible=True,
            min_confidence=0.8, require_human_approval_for_act=False,
        ),
        traceability=tr(),
    )
    rb = rollback_evidence()
    rbp = RollbackPath(reference="rb-1", evidence_ids=(rb.id,), detail="verified")
    result = evaluate_autonomy(
        policy=p_rb, action=DecisionAction.ROLLBACK,
        assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(rb.id,), traceability=tr(),
        known_evidence={rb.id: rb},
        rollback_path=rbp, confidence=0.9, risk=0.1,
    )
    assert result.state == AutonomyDecisionState.ROLLBACK


# --- C9: explainable decision record ---


def test_decision_has_rationale_and_reasons():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT,
        assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(), traceability=tr(),
    )
    assert result.rationale.strip()  # non-empty
    assert len(result.reasons) > 0


# --- C10: deterministic ---


def test_evaluation_is_deterministic():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    r1 = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT,
        assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(), traceability=tr(),
    )
    r2 = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT,
        assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(), traceability=tr(),
    )
    assert r1.state == r2.state
    assert r1.id == r2.id


# --- C11: persistence ---


def test_decision_round_trips_through_json(tmp_path):
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT,
        assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(), traceability=tr(),
    )
    path = tmp_path / "autonomy.json"
    JsonModelStore(path).save(result)
    data = JsonModelStore(path).load()
    assert data["state"] == result.state.value
    assert data["assurance_id"] == ar.id
    assert data["traceability"]["context_ref"] == "context:1"


# --- C12: bounded authority surface ---


def test_w9_introduces_no_w10_plus_symbols():
    import sos.autonomy as amod
    forbidden = {
        "PlatformAdapter", "Personalization", "Greenfield", "Brownfield",
        "SelfEvolution", "MetaAdaptation", "Deployer", "Deploy",
    }
    exported = {n for n in dir(amod) if not n.startswith("_")}
    assert not (forbidden & exported), f"forbidden W10+ symbols: {forbidden & exported}"


def test_w9_does_not_redefine_assurance_or_experiment_authority():
    import sos.autonomy as amod
    forbidden = {"AssuranceResult", "AssuranceStatus", "assure_candidate",
                 "Experiment", "ExperimentState", "evaluate_experiment", "PromotionGate"}
    exported = {n for n in dir(amod) if not n.startswith("_")}
    assert not (forbidden & exported), f"W9 must not re-export W7/W8 authority: {forbidden & exported}"


# --- confidence-only authorization rejected ---


def test_confidence_alone_cannot_authorize():
    """C5: confidence alone cannot authorize; evidence + assurance + promotion required."""
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    # High confidence but no promotion
    non_promoted = PromotionDecision(
        promoted=False, rationale="confidence-only is not authorization",
        experiment_id=exp.id, evaluation_id=ev.id,
    )
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT,
        assurance=ar, experiment=exp, promotion=non_promoted,
        evidence_ids=(), traceability=tr(),
    )
    assert result.state != AutonomyDecisionState.ACT


# --- SOS-W9-F01 regression: policy ceilings enforced ---


def test_risk_exceeding_ceiling_routes_to_ask():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    e_ok = evidence(subject="node-a", value="120ms")
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT, assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(e_ok.id,), traceability=tr(),
        known_evidence={e_ok.id: e_ok}, confidence=0.9, risk=0.5,
    )
    assert result.state == AutonomyDecisionState.ASK


def test_irreversible_action_routes_to_ask():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    e_ok = evidence(subject="node-a", value="120ms")
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT, assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(e_ok.id,), traceability=tr(),
        known_evidence={e_ok.id: e_ok}, confidence=0.9, risk=0.1, reversible=False,
    )
    assert result.state == AutonomyDecisionState.ASK


def test_confidence_below_floor_routes_to_ask():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    e_ok = evidence(subject="node-a", value="120ms")
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT, assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(e_ok.id,), traceability=tr(),
        known_evidence={e_ok.id: e_ok}, confidence=0.5, risk=0.1,
    )
    assert result.state == AutonomyDecisionState.ASK


def test_act_rejects_promotion_not_bound_to_experiment():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    e_ok = evidence(subject="node-a", value="120ms")
    wrong_promo = PromotionDecision(
        promoted=True, rationale="wrong", experiment_id="different-experiment-id", evaluation_id=ev.id,
    )
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT, assurance=ar, experiment=exp, promotion=wrong_promo,
        evidence_ids=(e_ok.id,), traceability=tr(),
        known_evidence={e_ok.id: e_ok}, confidence=0.9, risk=0.1,
        evaluation=ev,
    )
    assert result.state == AutonomyDecisionState.REJECT


def test_rollback_without_known_evidence_routes_to_ask():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p_rb = AutonomyRequest(
        id="policy-rb", version=1, allowed_actions=(DecisionAction.ROLLBACK,),
        ceilings=PolicyCeiling(max_risk=0.3, max_blast_radius="service", require_reversible=True,
            min_confidence=0.8, require_human_approval_for_act=False),
        traceability=tr(),
    )
    rb = rollback_evidence()
    rbp = RollbackPath(reference="rb-1", evidence_ids=(rb.id,), detail="verified")
    result = evaluate_autonomy(
        policy=p_rb, action=DecisionAction.ROLLBACK, assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(rb.id,), traceability=tr(), known_evidence=None, rollback_path=rbp, confidence=0.9, risk=0.1,
    )
    assert result.state == AutonomyDecisionState.ASK


def test_rollback_with_mismatched_reference_routes_to_ask():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p_rb = AutonomyRequest(
        id="policy-rb", version=1, allowed_actions=(DecisionAction.ROLLBACK,),
        ceilings=PolicyCeiling(max_risk=0.3, max_blast_radius="service", require_reversible=True,
            min_confidence=0.8, require_human_approval_for_act=False),
        traceability=tr(),
    )
    rb = rollback_evidence()
    rbp = RollbackPath(reference="wrong-ref", evidence_ids=(rb.id,), detail="wrong")
    result = evaluate_autonomy(
        policy=p_rb, action=DecisionAction.ROLLBACK, assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(rb.id,), traceability=tr(), known_evidence={rb.id: rb}, rollback_path=rbp, confidence=0.9, risk=0.1,
    )
    assert result.state == AutonomyDecisionState.ASK


def test_act_with_empty_evidence_routes_to_gather_evidence():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT, assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(), traceability=tr(), known_evidence={}, confidence=0.9, risk=0.1,
        evaluation=ev,
    )
    assert result.state == AutonomyDecisionState.GATHER_EVIDENCE


def test_act_without_known_evidence_store_routes_to_gather_evidence():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    e_ok = evidence(subject="node-a", value="120ms")
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT, assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(e_ok.id,), traceability=tr(), known_evidence=None, confidence=0.9, risk=0.1,
        evaluation=ev,
    )
    assert result.state == AutonomyDecisionState.GATHER_EVIDENCE


@pytest.mark.parametrize("state,detail", [
    (TruthState.UNKNOWN, "no data"),
    (TruthState.FAILED, "test raised"),
    (TruthState.UNAVAILABLE, "collector down"),
    (TruthState.UNSUPPORTED, "not supported"),
])
def test_non_success_evidence_states_prevent_act(state, detail):
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    # Use the evaluation's evidence_ids but replace the known evidence with a bad record
    e_ok_id = ev.evidence_ids[0] if ev.evidence_ids else "e1"
    e_bad = evidence(subject="node-a", state=state, detail=detail)
    # Use e_bad's id as the known_evidence key but under the evaluation's evidence_id
    known = {e_ok_id: e_bad}
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT, assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=ev.evidence_ids, traceability=tr(), known_evidence=known, confidence=0.9, risk=0.1,
        evaluation=ev,
    )
    assert result.state != AutonomyDecisionState.ACT
    assert any(state.value in r for r in result.reasons)


def test_fail_assurance_rejects_act():
    arch = graph()
    e_unknown = evidence(subject="node-a", state=TruthState.UNKNOWN, detail="no data")
    h = CausalHypothesis(
        cause_subject="node-a", effect_subject="node-b",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="r", status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "observation only"),
        supporting_evidence=(), traceability=tr(), provenance_revision=REVISION,
    )
    m = SubgraphMutation(
        kind=MutationKind.SUBGRAPH_REPLACE, base_graph_ref="arch-1",
        target_node_ids=("node-a",), replacement_node_ids=("node-a-prime",),
        boundary_interface_ids=("node-i",), invariants=("preserve-api",),
    )
    c = CandidateProposal(
        id="", base_graph_ref="arch-1", base_graph_revision=REVISION,
        mutation=m, objectives=objectives(), rationale="r",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted"),
        reasoning_evidence_ids=(e_unknown.id,), reasoning_hypothesis_ids=(h.id,),
        risks=(), traceability=tr(), provenance_revision=REVISION,
    )
    ar = assure_candidate(candidate=c, base_graph=arch, known_evidence={e_unknown.id: e_unknown}, known_hypotheses={h.id: h})
    assert ar.status != AssuranceStatus.PASS
    # Build a real experiment + evaluation bound to this (non-PASS) assurance.
    exp = Experiment(
        id="", candidate_id=ar.candidate_id, assurance_result_id=ar.id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision, mode=ExperimentMode.CANARY,
        scope=("node-a",), observation_window=("2026-09-10T00:00:00Z", "2026-09-11T00:00:00Z"),
        success_criteria=("latency<200",), stop_conditions=(
            __import__("sos").StopCondition(name="error-rate", threshold=0.05, metric="error-rate"),
        ),
        rollback_ref="rb-1", traceability=tr(), state=ExperimentState.COMPLETED,
    )
    e_ok = evidence(subject="node-a", value="120ms")
    from sos import ExperimentEvaluation as EvEval
    ev = EvEval(
        id="", experiment_id=exp.id,
        assurance_result_id=ar.id, candidate_id=ar.candidate_id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision,
        evidence_ids=(e_ok.id,), evidence_results={e_ok.id: TruthState.SUCCESS},
        objectives=(), promotion_eligible=False, stopped=False, detail="eval", traceability=tr(),
    )
    p = policy()
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT, assurance=ar, experiment=exp, promotion=None,
        evidence_ids=(e_ok.id,), traceability=tr(), known_evidence={e_ok.id: e_ok}, confidence=0.9, risk=0.1,
        evaluation=ev,
    )
    assert result.state == AutonomyDecisionState.REJECT


def test_policy_rejects_non_decision_action_in_allowed_actions():
    with pytest.raises(ModelValidationError, match="non-DecisionAction"):
        AutonomyRequest(
            id="bad-policy", version=1,
            allowed_actions=("ACT", "EXPERIMENT"),
            ceilings=PolicyCeiling(max_risk=0.3, max_blast_radius="service", require_reversible=True,
                min_confidence=0.8, require_human_approval_for_act=False),
            traceability=tr(),
        )

# --- SOS-W9-F08 regression: ACT requires experiment ---


def test_act_without_experiment_routes_to_ask():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    e_ok = evidence(subject="node-a", value="120ms")
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT, assurance=ar, experiment=None, promotion=promo,
        evidence_ids=(e_ok.id,), traceability=tr(),
        known_evidence={e_ok.id: e_ok}, confidence=0.9, risk=0.1,
    )
    assert result.state == AutonomyDecisionState.ASK


# --- SOS-W9-F09 regression: evaluation bound to exact experiment ---


def test_act_with_mismatched_evaluation_rejects():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    e_ok = evidence(subject="node-a", value="120ms")
    # A forged evaluation with a DIFFERENT experiment_id.
    from sos import ExperimentEvaluation as EvEval
    wrong_ev = EvEval(
        id="", experiment_id="different-experiment",
        assurance_result_id=ar.id, candidate_id=ar.candidate_id,
        base_graph_id=ar.base_graph_id, base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision,
        evidence_ids=(), evidence_results={}, objectives=(),
        promotion_eligible=True, stopped=False, detail="forged", traceability=tr(),
    )
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT, assurance=ar, experiment=exp, promotion=promo,
        evaluation=wrong_ev, evidence_ids=(e_ok.id,), traceability=tr(),
        known_evidence={e_ok.id: e_ok}, confidence=0.9, risk=0.1,
    )
    assert result.state == AutonomyDecisionState.REJECT


# --- SOS-W9-F10 regression: unknown blast radius ---


def test_unknown_blast_radius_routes_to_ask():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    e_ok = evidence(subject="node-a", value="120ms")
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT, assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(e_ok.id,), traceability=tr(),
        known_evidence={e_ok.id: e_ok}, confidence=0.9, risk=0.1,
        blast_radius="galactic",  # unknown level
    )
    assert result.state == AutonomyDecisionState.ASK


# --- SOS-W9-F11 regression: invalid numeric domains ---


def test_negative_risk_rejected():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    e_ok = evidence(subject="node-a", value="120ms")
    with pytest.raises(ModelValidationError, match="risk"):
        evaluate_autonomy(
            policy=p, action=DecisionAction.ACT, assurance=ar, experiment=exp, promotion=promo,
            evidence_ids=(e_ok.id,), traceability=tr(),
            known_evidence={e_ok.id: e_ok}, confidence=0.9, risk=-0.5,
        )


def test_confidence_above_one_rejected():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    e_ok = evidence(subject="node-a", value="120ms")
    with pytest.raises(ModelValidationError, match="confidence"):
        evaluate_autonomy(
            policy=p, action=DecisionAction.ACT, assurance=ar, experiment=exp, promotion=promo,
            evidence_ids=(e_ok.id,), traceability=tr(),
            known_evidence={e_ok.id: e_ok}, confidence=1.5, risk=0.1,
        )


# --- SOS-W9-F12 regression: ROLLBACK requires experiment ---


def test_rollback_without_experiment_routes_to_ask():
    ar = pass_assurance()
    p_rb = AutonomyRequest(
        id="policy-rb", version=1, allowed_actions=(DecisionAction.ROLLBACK,),
        ceilings=PolicyCeiling(max_risk=0.3, max_blast_radius="service", require_reversible=True,
            min_confidence=0.8, require_human_approval_for_act=False),
        traceability=tr(),
    )
    rb = rollback_evidence()
    rbp = RollbackPath(reference="rb-1", evidence_ids=(rb.id,), detail="verified")
    result = evaluate_autonomy(
        policy=p_rb, action=DecisionAction.ROLLBACK, assurance=ar, experiment=None, promotion=None,
        evidence_ids=(rb.id,), traceability=tr(),
        known_evidence={rb.id: rb}, rollback_path=rbp, confidence=0.9, risk=0.1,
    )
    assert result.state == AutonomyDecisionState.ASK

# --- SOS-W9-F13 regression: evaluation required for ACT ---


def test_act_without_evaluation_routes_to_ask():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    e_ok = evidence(subject="node-a", value="120ms")
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT, assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(e_ok.id,), traceability=tr(),
        known_evidence={e_ok.id: e_ok}, confidence=0.9, risk=0.1,
        evaluation=None,  # F13: no evaluation
    )
    assert result.state == AutonomyDecisionState.ASK


def test_act_rejects_promotion_evaluation_id_mismatch():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    e_ok = evidence(subject="node-a", value="120ms")
    # Forge a promotion with a different evaluation_id
    wrong_promo = PromotionDecision(
        promoted=True, rationale="wrong eval",
        experiment_id=exp.id, evaluation_id="different-eval-id",
    )
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT, assurance=ar, experiment=exp, promotion=wrong_promo,
        evidence_ids=(e_ok.id,), traceability=tr(),
        known_evidence={e_ok.id: e_ok}, confidence=0.9, risk=0.1,
        evaluation=ev,
    )
    assert result.state == AutonomyDecisionState.REJECT


# --- SOS-W9-F14 regression: ACT requires COMPLETED experiment ---


def test_act_rejects_non_completed_experiment():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    # Override to RUNNING state
    from sos import Experiment as ExpCls
    running_exp = ExpCls(
        id=exp.id, candidate_id=exp.candidate_id, assurance_result_id=exp.assurance_result_id,
        base_graph_id=exp.base_graph_id, base_graph_revision=exp.base_graph_revision,
        provenance_revision=exp.provenance_revision, mode=exp.mode, scope=exp.scope,
        observation_window=exp.observation_window, success_criteria=exp.success_criteria,
        stop_conditions=exp.stop_conditions, rollback_ref=exp.rollback_ref,
        traceability=exp.traceability, state=ExperimentState.RUNNING,
    )
    p = policy()
    e_ok = evidence(subject="node-a", value="120ms")
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT, assurance=ar, experiment=running_exp, promotion=promo,
        evidence_ids=(e_ok.id,), traceability=tr(),
        known_evidence={e_ok.id: e_ok}, confidence=0.9, risk=0.1,
        evaluation=ev,
    )
    assert result.state == AutonomyDecisionState.REJECT


# --- SOS-W9-F15 regression: evidence_ids must match evaluation ---


def test_act_rejects_mismatched_evidence_set():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    # Use a different evidence id than what's in the evaluation
    e_other = evidence(subject="node-b", value="90ms")
    result = evaluate_autonomy(
        policy=p, action=DecisionAction.ACT, assurance=ar, experiment=exp, promotion=promo,
        evidence_ids=(e_other.id,), traceability=tr(),
        known_evidence={e_other.id: e_other}, confidence=0.9, risk=0.1,
        evaluation=ev,
    )
    assert result.state == AutonomyDecisionState.REJECT


# --- SOS-W9-F16 regression: bool rejected for numeric domains ---


def test_bool_risk_rejected():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    e_ok = evidence(subject="node-a", value="120ms")
    with pytest.raises(ModelValidationError, match="risk"):
        evaluate_autonomy(
            policy=p, action=DecisionAction.ACT, assurance=ar, experiment=exp, promotion=promo,
            evidence_ids=(e_ok.id,), traceability=tr(),
            known_evidence={e_ok.id: e_ok}, confidence=0.9, risk=True,
            evaluation=ev,
        )


def test_bool_confidence_rejected():
    ar = pass_assurance()
    exp, ev, promo = completed_experiment_with_promotion(ar)
    p = policy()
    e_ok = evidence(subject="node-a", value="120ms")
    with pytest.raises(ModelValidationError, match="confidence"):
        evaluate_autonomy(
            policy=p, action=DecisionAction.ACT, assurance=ar, experiment=exp, promotion=promo,
            evidence_ids=(e_ok.id,), traceability=tr(),
            known_evidence={e_ok.id: e_ok}, confidence=False, risk=0.1,
            evaluation=ev,
        )
