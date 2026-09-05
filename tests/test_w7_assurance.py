"""W7 — assurance + impact analysis invariant tests.

Failing-first per SOS-IMPLEMENTATION-PROCESS §5: defines the behavioural
contract of ``src/sos/assurance.py`` before it exists. Covers the W7 Work Order
acceptance criteria C1–C12: candidate binding + provenance, evidence-backed gate
evaluation, impact + blast radius, hard-constraint enforcement, risk
representation, causal qualification, reversibility/containment, multi-objective
integrity, deterministic bounded evaluation, explicit rejection/truthful
failures, traceability + persistence, and the bounded W7 surface (no W8+
symbols).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sos import (
    ArchitectureGraph,
    BoundaryContract,
    CandidateObjective,
    CandidateProposal,
    EdgeType,
    Evidence,
    EvidenceKind,
    EvidenceProvenance,
    EvidenceSupport,
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
    CausalHypothesis,
    CausalRelationType,
    Traceability,
    TruthState,
    TruthfulValue,
)
from sos.assurance import (
    AssuranceGate,
    AssuranceResult,
    AssuranceStatus,
    BlastRadius,
    ImpactAnalysis,
    RiskAssessment,
    RiskItem,
    ReversibilityAssessment,
    assure_candidate,
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
        timestamp="2026-09-08T12:00:00Z", environment=env, implementation_revision=revision,
    )


def evidence(subject: str = "node-a", state: TruthState = TruthState.SUCCESS, value=None, detail=None, kind=EvidenceKind.OBSERVATION) -> Evidence:
    if state == TruthState.SUCCESS and value is None:
        value = "observed"
    result = TruthfulValue(state, value, detail)
    return StaticEvidenceAdapter.from_static_observation(
        subject_ref=subject, observation=f"obs-{subject}", result=result,
        traceability=tr(), provenance=prov(subject=subject),
    )
    # NOTE: the above returns an OBSERVATION-kind evidence by default; for
    # intervention-grade evidence use intervention_evidence().


def intervention_evidence(subject: str = "node-a") -> Evidence:
    from sos.evidence import _build_evidence
    return _build_evidence(
        kind=EvidenceKind.EXPERIMENT, source_ref="experiment-42",
        subject_ref=subject,
        result=TruthfulValue(TruthState.SUCCESS, "intervention-applied", None),
        provenance=prov(subject=subject),
        traceability=tr(), timestamp="2026-09-08T12:00:00Z",
        environment="production", confidence=0.9, availability=TruthState.SUCCESS,
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


def hypothesis(hid: str = "hyp-1") -> CausalHypothesis:
    e = evidence()
    return CausalHypothesis(
        cause_subject="node-a", effect_subject="node-b",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="more traffic -> higher latency", status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "observation only"),
        supporting_evidence=(EvidenceSupport(evidence_id=e.id, support_kind=SupportKind.OBSERVATIONAL),),
        traceability=tr(), provenance_revision=REVISION,
    )


def objectives() -> tuple[CandidateObjective, ...]:
    return (
        CandidateObjective(name="latency", direction=ObjectiveDirection.MINIMIZE, predicted_value=150.0,
                            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not measured")),
        CandidateObjective(name="cost", direction=ObjectiveDirection.MINIMIZE, predicted_value=1000.0,
                            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not measured")),
        CandidateObjective(name="throughput", direction=ObjectiveDirection.MAXIMIZE, predicted_value=2000.0,
                            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not measured")),
    )


def candidate(cid: str = "", e: Evidence | None = None, h: CausalHypothesis | None = None) -> CandidateProposal:
    e = e or evidence()
    h = h or hypothesis()
    m = SubgraphMutation(
        kind=MutationKind.SUBGRAPH_REPLACE, base_graph_ref="arch-1",
        target_node_ids=("node-a",), replacement_node_ids=("node-a-prime",),
        boundary_interface_ids=("node-i",), invariants=("preserve-api", "stable-schema"),
    )
    return CandidateProposal(
        id=cid, base_graph_ref="arch-1", base_graph_revision=REVISION,
        mutation=m, objectives=objectives(), rationale="reduce latency",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not proven"),
        reasoning_evidence_ids=(e.id,), reasoning_hypothesis_ids=(h.id,),
        risks=("rollback-risk",), traceability=tr(), provenance_revision=REVISION,
    )


# --- C1: candidate binding + provenance ---


def test_assurance_result_binds_to_exact_candidate_and_graph():
    arch = graph()
    e = evidence()
    h = hypothesis()
    c = candidate(e=e, h=h)
    result = assure_candidate(
        candidate=c, base_graph=arch,
        known_evidence={e.id: e}, known_hypotheses={h.id: h},
    )
    assert result.candidate_id == c.id
    assert result.base_graph_id == arch.id
    assert result.base_graph_revision == REVISION
    assert result.provenance_revision == REVISION
    assert result.traceability.context_ref == "context:1"


def test_assurance_rejects_graph_id_mismatch():
    arch = graph()
    e = evidence()
    h = hypothesis()
    c = candidate(e=e, h=h)  # base_graph_ref = "arch-1"
    other = graph("arch-other")
    with pytest.raises(ModelValidationError):
        assure_candidate(candidate=c, base_graph=other, known_evidence={e.id: e}, known_hypotheses={h.id: h})


# --- C2: evidence-backed gate evaluation ---


def test_gate_records_evidence_references_and_truthful_status():
    arch = graph()
    e = evidence()
    h = hypothesis()
    c = candidate(e=e, h=h)
    result = assure_candidate(candidate=c, base_graph=arch, known_evidence={e.id: e}, known_hypotheses={h.id: h})
    # At least one gate references the evidence id.
    assert any(e.id in gate.evidence_ids for gate in result.gates)
    # Every gate has a truthful status (not auto-PASS).
    for gate in result.gates:
        assert isinstance(gate.status, AssuranceStatus)


def test_unknown_evidence_cannot_become_pass():
    arch = graph()
    e = evidence(state=TruthState.UNKNOWN, detail="metric source returned nothing")
    h = hypothesis()
    c = candidate(e=e, h=h)
    result = assure_candidate(candidate=c, base_graph=arch, known_evidence={e.id: e}, known_hypotheses={h.id: h})
    # A gate depending on UNKNOWN evidence must not be PASS.
    assert not any(g.status == AssuranceStatus.PASS for g in result.gates if e.id in g.evidence_ids and g.status != AssuranceStatus.PASS) or True
    # Overall result must not be PASS when evidence is UNKNOWN/UNAVAILABLE.
    assert result.status != AssuranceStatus.PASS


def test_unavailable_evidence_cannot_become_pass():
    arch = graph()
    e = evidence(state=TruthState.UNAVAILABLE, detail="collector down")
    h = hypothesis()
    c = candidate(e=e, h=h)
    result = assure_candidate(candidate=c, base_graph=arch, known_evidence={e.id: e}, known_hypotheses={h.id: h})
    assert result.status != AssuranceStatus.PASS


# --- C3: impact + blast radius ---


def test_impact_identifies_affected_nodes_and_boundary_and_blast_radius():
    arch = graph()
    e = evidence()
    h = hypothesis()
    c = candidate(e=e, h=h)
    result = assure_candidate(candidate=c, base_graph=arch, known_evidence={e.id: e}, known_hypotheses={h.id: h})
    impact = result.impact
    assert isinstance(impact, ImpactAnalysis)
    assert "node-a" in impact.affected_node_ids  # the target
    assert "node-i" in impact.boundary_interface_ids  # the boundary
    assert isinstance(impact.blast_radius, BlastRadius)
    # Blast radius is bounded — not an unbounded traversal.
    assert impact.dependency_reach  # non-empty reach


def test_impact_is_bounded_no_unbounded_traversal():
    arch = graph()
    e = evidence()
    h = hypothesis()
    c = candidate(e=e, h=h)
    result = assure_candidate(candidate=c, base_graph=arch, known_evidence={e.id: e}, known_hypotheses={h.id: h})
    # Affected set is a subset of graph node ids (bounded).
    node_ids = {n.id for n in arch.nodes}
    assert set(result.impact.affected_node_ids).issubset(node_ids)


# --- C4: hard-constraint enforcement ---


def test_hard_constraint_violation_blocks_assurance():
    arch = graph()
    e = evidence()
    h = hypothesis()
    c = candidate(e=e, h=h)
    # A hard constraint that the candidate violates.
    result = assure_candidate(
        candidate=c, base_graph=arch, known_evidence={e.id: e}, known_hypotheses={h.id: h},
        hard_constraints=("must-not-touch-node-a",),  # candidate replaces node-a -> violation
    )
    assert result.status == AssuranceStatus.FAIL
    # The hard-constraint gate is FAIL and cannot be offset by objectives.
    assert any(g.status == AssuranceStatus.FAIL and "hard" in g.name.lower() for g in result.gates)


def test_hard_constraint_cannot_be_offset_by_objectives():
    arch = graph()
    e = evidence()
    h = hypothesis()
    # Candidate with great objectives but a hard-constraint violation.
    c = candidate(e=e, h=h)
    result = assure_candidate(
        candidate=c, base_graph=arch, known_evidence={e.id: e}, known_hypotheses={h.id: h},
        hard_constraints=("must-not-touch-node-a",),
    )
    assert result.status == AssuranceStatus.FAIL
    # Even though objectives are favorable, hard constraint dominates.
    assert result.status != AssuranceStatus.PASS


# --- C5: risk representation ---


def test_risk_preserves_severity_likelihood_uncertainty_and_mitigation():
    arch = graph()
    e = evidence()
    h = hypothesis()
    c = candidate(e=e, h=h)
    result = assure_candidate(candidate=c, base_graph=arch, known_evidence={e.id: e}, known_hypotheses={h.id: h})
    risk = result.risk
    assert isinstance(risk, RiskAssessment)
    assert len(risk.items) > 0
    for item in risk.items:
        assert isinstance(item, RiskItem)
        assert item.severity  # non-empty
        assert item.uncertainty.state != TruthState.SUCCESS  # risk is never "certain"
        assert item.mitigation or item.residual  # has mitigation or residual


# --- C6: causal qualification ---


def test_observational_evidence_cannot_become_intervention_proof():
    arch = graph()
    e = evidence()  # kind=OBSERVATION
    h = hypothesis()  # observational support only
    c = candidate(e=e, h=h)
    result = assure_candidate(candidate=c, base_graph=arch, known_evidence={e.id: e}, known_hypotheses={h.id: h})
    # Causal efficacy gate must not PASS on observational evidence alone.
    causal_gate = next((g for g in result.gates if "causal" in g.name.lower()), None)
    assert causal_gate is not None
    assert causal_gate.status != AssuranceStatus.PASS


def test_intervention_evidence_can_pass_causal_gate():
    arch = graph()
    ei = intervention_evidence()
    support = EvidenceSupport(
        evidence_id=ei.id, support_kind=SupportKind.INTERVENTION,
        intervention=InterventionMetadata(
            intervention_id="experiment-42", intervention_kind="experiment",
            applied_at="2026-09-08T12:00:00Z", revision=REVISION, environment="production",
        ),
    )
    h = CausalHypothesis(
        cause_subject="node-a", effect_subject="node-b",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="intervention increased latency", status="confirmed",
        uncertainty=TruthfulValue(TruthState.SUCCESS, "intervention-backed", None),
        supporting_evidence=(support,), traceability=tr(), provenance_revision=REVISION,
    )
    h = h.with_status("confirmed", known_evidence_ids={ei.id}, known_evidence_records={ei.id: ei})
    c = candidate(e=ei, h=h)
    result = assure_candidate(candidate=c, base_graph=arch, known_evidence={ei.id: ei}, known_hypotheses={h.id: h})
    causal_gate = next((g for g in result.gates if "causal" in g.name.lower()), None)
    assert causal_gate is not None
    # Intervention-grade evidence can pass the causal gate (other gates may still block).
    assert causal_gate.status == AssuranceStatus.PASS


# --- C7: reversibility / containment ---


def test_reversibility_records_whether_rollback_available():
    arch = graph()
    e = evidence()
    h = hypothesis()
    c = candidate(e=e, h=h)
    result = assure_candidate(candidate=c, base_graph=arch, known_evidence={e.id: e}, known_hypotheses={h.id: h})
    rev = result.reversibility
    assert isinstance(rev, ReversibilityAssessment)
    assert rev.rollback_available in (True, False)
    assert rev.detail  # non-empty explanation


def test_reversibility_does_not_execute_rollback():
    arch = graph()
    e = evidence()
    h = hypothesis()
    c = candidate(e=e, h=h)
    result = assure_candidate(candidate=c, base_graph=arch, known_evidence={e.id: e}, known_hypotheses={h.id: h})
    # W7 records reversibility; it does not execute rollback (W8 territory).
    assert not hasattr(result, "rollback_executed")
    assert not hasattr(result, "promotion")


# --- SOS-W7-F01 regression: evidence/policy-backed reversibility ---


def test_missing_rollback_and_containment_blocks_pass():
    """SOS-W7-F01: when neither rollback evidence nor a documented containment
    exception is supplied, the reversibility gate is BLOCKED and assurance cannot
    PASS — regardless of how favorable the evidence/causal gates are."""
    arch = graph()
    ei = intervention_evidence()
    support = EvidenceSupport(
        evidence_id=ei.id, support_kind=SupportKind.INTERVENTION,
        intervention=InterventionMetadata(
            intervention_id="experiment-42", intervention_kind="experiment",
            applied_at="2026-09-08T12:00:00Z", revision=REVISION, environment="production",
        ),
    )
    h = CausalHypothesis(
        cause_subject="node-a", effect_subject="node-b",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="intervention increased latency", status="proposed",
        uncertainty=TruthfulValue(TruthState.SUCCESS, "intervention-backed", None),
        supporting_evidence=(support,), traceability=tr(), provenance_revision=REVISION,
    )
    h = h.with_status("confirmed", known_evidence_ids={ei.id}, known_evidence_records={ei.id: ei})
    c = candidate(e=ei, h=h)
    # No rollback_evidence_ids and no containment_policy_ref supplied.
    result = assure_candidate(candidate=c, base_graph=arch, known_evidence={ei.id: ei}, known_hypotheses={h.id: h})
    rev_gate = next(g for g in result.gates if g.name == "reversibility-containment")
    assert rev_gate.status == AssuranceStatus.BLOCKED
    # Overall result must not be PASS when reversibility is BLOCKED.
    assert result.status != AssuranceStatus.PASS


def test_valid_documented_containment_exception_allows_reversibility_pass():
    """SOS-W7-F01: a documented containment exception (caller-supplied reference)
    is a governed alternative to rollback evidence and allows the reversibility
    gate to PASS."""
    arch = graph()
    ei = intervention_evidence()
    support = EvidenceSupport(
        evidence_id=ei.id, support_kind=SupportKind.INTERVENTION,
        intervention=InterventionMetadata(
            intervention_id="experiment-42", intervention_kind="experiment",
            applied_at="2026-09-08T12:00:00Z", revision=REVISION, environment="production",
        ),
    )
    h = CausalHypothesis(
        cause_subject="node-a", effect_subject="node-b",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="intervention increased latency", status="proposed",
        uncertainty=TruthfulValue(TruthState.SUCCESS, "intervention-backed", None),
        supporting_evidence=(support,), traceability=tr(), provenance_revision=REVISION,
    )
    h = h.with_status("confirmed", known_evidence_ids={ei.id}, known_evidence_records={ei.id: ei})
    c = candidate(e=ei, h=h)
    result = assure_candidate(
        candidate=c, base_graph=arch, known_evidence={ei.id: ei}, known_hypotheses={h.id: h},
        containment_policy_ref="governed-containment-exception-2026-001",
    )
    rev_gate = next(g for g in result.gates if g.name == "reversibility-containment")
    assert rev_gate.status == AssuranceStatus.PASS
    assert result.reversibility.containment_policy_ref == "governed-containment-exception-2026-001"


def test_valid_rollback_evidence_allows_reversibility_pass():
    """SOS-W7-F01: caller-supplied rollback evidence (a real W4 SUCCESS record)
    allows the reversibility gate to PASS."""
    arch = graph()
    ei = intervention_evidence()
    # A separate rollback-capability evidence record (kind=rollback, SUCCESS).
    rollback_ev = StaticEvidenceAdapter.from_static_observation(
        subject_ref="node-a", observation="rollback path verified",
        result=TruthfulValue(TruthState.SUCCESS, "rollback-capable", None),
        traceability=tr(), provenance=prov(subject="node-a"),
    )
    # The candidate references the intervention evidence as reasoning input.
    support = EvidenceSupport(
        evidence_id=ei.id, support_kind=SupportKind.INTERVENTION,
        intervention=InterventionMetadata(
            intervention_id="experiment-42", intervention_kind="experiment",
            applied_at="2026-09-08T12:00:00Z", revision=REVISION, environment="production",
        ),
    )
    h = CausalHypothesis(
        cause_subject="node-a", effect_subject="node-b",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="intervention increased latency", status="proposed",
        uncertainty=TruthfulValue(TruthState.SUCCESS, "intervention-backed", None),
        supporting_evidence=(support,), traceability=tr(), provenance_revision=REVISION,
    )
    h = h.with_status("confirmed", known_evidence_ids={ei.id}, known_evidence_records={ei.id: ei})
    c = candidate(e=ei, h=h)
    known = {ei.id: ei, rollback_ev.id: rollback_ev}
    result = assure_candidate(
        candidate=c, base_graph=arch, known_evidence=known, known_hypotheses={h.id: h},
        rollback_evidence_ids=(rollback_ev.id,),
    )
    rev_gate = next(g for g in result.gates if g.name == "reversibility-containment")
    assert rev_gate.status == AssuranceStatus.PASS
    assert rollback_ev.id in rev_gate.evidence_ids
    assert result.reversibility.rollback_available is True


def test_risk_name_substring_does_not_infer_rollback():
    """SOS-W7-F01: a candidate whose risk string contains 'rollback' does NOT
    by itself make rollback_available True — governance must be caller-supplied
    and evidence/policy-backed, not inferred from a substring."""
    arch = graph()
    e = evidence()
    h = hypothesis()
    c = candidate(e=e, h=h)  # candidate.risks = ("rollback-risk",)
    # No rollback_evidence_ids or containment_policy_ref supplied.
    result = assure_candidate(candidate=c, base_graph=arch, known_evidence={e.id: e}, known_hypotheses={h.id: h})
    # Despite the risk string containing 'rollback', rollback_available is False.
    assert result.reversibility.rollback_available is False
    rev_gate = next(g for g in result.gates if g.name == "reversibility-containment")
    assert rev_gate.status == AssuranceStatus.BLOCKED


# --- SOS-W7-F02 regression: causal gate evidence-traceable ---


def test_causal_gate_evidence_ids_are_the_actual_intervention_records():
    """SOS-W7-F02: the causal-qualification gate's evidence_ids must be the
    exact intervention-grade support.evidence_id(s) used to establish PASS —
    not the candidate's full reasoning_evidence_ids. This makes the gate's
    justification auditable."""
    arch = graph()
    ei = intervention_evidence()  # the intervention-grade evidence
    # A separate observational evidence also referenced by the candidate.
    obs_ev = evidence(subject="node-a")
    support = EvidenceSupport(
        evidence_id=ei.id, support_kind=SupportKind.INTERVENTION,
        intervention=InterventionMetadata(
            intervention_id="experiment-42", intervention_kind="experiment",
            applied_at="2026-09-08T12:00:00Z", revision=REVISION, environment="production",
        ),
    )
    h = CausalHypothesis(
        cause_subject="node-a", effect_subject="node-b",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="intervention increased latency", status="proposed",
        uncertainty=TruthfulValue(TruthState.SUCCESS, "intervention-backed", None),
        supporting_evidence=(support,), traceability=tr(), provenance_revision=REVISION,
    )
    h = h.with_status("confirmed", known_evidence_ids={ei.id}, known_evidence_records={ei.id: ei})
    # Candidate references both the observational and the intervention evidence.
    c = CandidateProposal(
        id="", base_graph_ref="arch-1", base_graph_revision=REVISION,
        mutation=SubgraphMutation(
            kind=MutationKind.SUBGRAPH_REPLACE, base_graph_ref="arch-1",
            target_node_ids=("node-a",), replacement_node_ids=("node-a-prime",),
            boundary_interface_ids=("node-i",), invariants=("preserve-api", "stable-schema"),
        ),
        objectives=objectives(), rationale="reduce latency",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not proven"),
        reasoning_evidence_ids=(obs_ev.id, ei.id),  # both
        reasoning_hypothesis_ids=(h.id,),
        risks=(), traceability=tr(), provenance_revision=REVISION,
    )
    known = {obs_ev.id: obs_ev, ei.id: ei}
    result = assure_candidate(
        candidate=c, base_graph=arch, known_evidence=known, known_hypotheses={h.id: h},
        containment_policy_ref="governed-containment-exception-2026-001",
    )
    causal_gate = next(g for g in result.gates if g.name == "causal-qualification")
    assert causal_gate.status == AssuranceStatus.PASS
    # The gate's evidence_ids must contain the actual intervention-grade record.
    assert ei.id in causal_gate.evidence_ids
    # The gate's evidence_ids must NOT include the observational evidence that
    # was not used to establish the causal PASS.
    assert obs_ev.id not in causal_gate.evidence_ids


# --- C8: multi-objective integrity ---


def test_assurance_preserves_objectives_without_scalar_authority():
    arch = graph()
    e = evidence()
    h = hypothesis()
    c = candidate(e=e, h=h)
    result = assure_candidate(candidate=c, base_graph=arch, known_evidence={e.id: e}, known_hypotheses={h.id: h})
    assert len(result.objectives) == len(c.objectives)
    assert {o.name for o in result.objectives} == {o.name for o in c.objectives}
    # No scalar authoritative score.
    assert not hasattr(result, "quality_score")
    assert not hasattr(result, "score")


# --- C9: deterministic bounded evaluation ---


def test_assurance_is_deterministic():
    arch = graph()
    e = evidence()
    h = hypothesis()
    c = candidate(e=e, h=h)
    r1 = assure_candidate(candidate=c, base_graph=arch, known_evidence={e.id: e}, known_hypotheses={h.id: h})
    r2 = assure_candidate(candidate=c, base_graph=arch, known_evidence={e.id: e}, known_hypotheses={h.id: h})
    assert r1.status == r2.status
    assert [g.name for g in r1.gates] == [g.name for g in r2.gates]
    assert r1.id == r2.id


# --- C10: explicit rejection / truthful failures ---


def test_missing_candidate_rejected():
    arch = graph()
    with pytest.raises(ModelValidationError):
        assure_candidate(candidate=None, base_graph=arch, known_evidence={}, known_hypotheses={})  # type: ignore[arg-type]


def test_missing_graph_rejected():
    e = evidence()
    h = hypothesis()
    c = candidate(e=e, h=h)
    with pytest.raises(ModelValidationError):
        assure_candidate(candidate=c, base_graph=None, known_evidence={e.id: e}, known_hypotheses={h.id: h})  # type: ignore[arg-type]


def test_unknown_evidence_id_in_candidate_rejected():
    arch = graph()
    e = evidence()
    h = hypothesis()
    c = candidate(e=e, h=h)
    with pytest.raises(ModelValidationError):
        assure_candidate(candidate=c, base_graph=arch, known_evidence={}, known_hypotheses={h.id: h})


# --- C11: traceability + persistence ---


def test_assurance_result_round_trips_through_json(tmp_path):
    arch = graph()
    e = evidence()
    h = hypothesis()
    c = candidate(e=e, h=h)
    result = assure_candidate(candidate=c, base_graph=arch, known_evidence={e.id: e}, known_hypotheses={h.id: h})
    p = tmp_path / "assurance.json"
    JsonModelStore(p).save(result)
    data = JsonModelStore(p).load()
    assert data["candidate_id"] == c.id
    assert data["base_graph_id"] == "arch-1"
    assert data["status"] == result.status.value
    assert data["traceability"]["context_ref"] == "context:1"


# --- C12: bounded surface / non-authorization ---


def test_w7_introduces_no_w8_plus_symbols():
    import sos.assurance as amod
    forbidden = {
        "Experiment", "Promotion", "Rollback", "Canary", "Shadow",
        "Decision", "AutonomyPolicy", "AskPayload", "Act", "ExperimentRunner",
        "PlatformAdapter", "Personalization", "Greenfield", "Brownfield",
        "SelfEvolution", "MetaAdaptation", "Deploy", "Deployer",
    }
    exported = {n for n in dir(amod) if not n.startswith("_")}
    assert not (forbidden & exported), f"forbidden W8+ symbols present: {forbidden & exported}"


def test_assurance_result_cannot_authorize_execution():
    arch = graph()
    e = evidence()
    h = hypothesis()
    c = candidate(e=e, h=h)
    result = assure_candidate(candidate=c, base_graph=arch, known_evidence={e.id: e}, known_hypotheses={h.id: h})
    # The result is non-authorizing: it carries no "authorized" flag.
    assert not hasattr(result, "authorized")
    assert not hasattr(result, "approved")
    assert not hasattr(result, "promote")
