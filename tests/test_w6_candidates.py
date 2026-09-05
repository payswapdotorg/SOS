"""W6 — candidate generation + bounded search invariant tests.

Failing-first per SOS-IMPLEMENTATION-PROCESS §5: defines the behavioural
contract of ``src/sos/candidates.py`` before it exists. Covers the W6 Work Order
acceptance criteria C1–C10: deterministic candidate identity, bounded mutation
representation (no canonical mutation), finite deterministic search, multi-
objective/Pareto semantics, uncertainty/truthfulness, evidence/causal
traceability, deterministic dedup/order, explicit rejection, repository
persistence, and the bounded W6 surface (no W7+ symbols).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sos import (
    ArchitectureGraph,
    BoundaryContract,
    CausalHypothesis,
    CausalKnowledgeGraph,
    CausalRelationType,
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
    NodeType,
    StaticEvidenceAdapter,
    SubgraphReplacement,
    SupportKind,
    SystemState,
    StateReference,
    Traceability,
    TruthState,
    TruthfulValue,
)
from sos.candidates import (
    CandidateEvaluation,
    CandidateObjective,
    CandidateProposal,
    CandidateSpace,
    MutationKind,
    ObjectiveDirection,
    ParetoFrontier,
    SearchBounds,
    SearchEngine,
    SubgraphMutation,
)


REVISION = "deadbeefcafebabe1234567890abcdef12345678"


def tr() -> Traceability:
    return Traceability(
        constitution_ref="constitution:1",
        mission_ref="mission:1",
        value_model_ref="value:1",
        context_ref="context:1",
    )


def prov(*, source: str = "static-recovery", subject: str = "node-1", env: str = "production", revision: str = REVISION) -> EvidenceProvenance:
    return EvidenceProvenance(
        source=source, observed_subject=subject,
        timestamp="2026-09-07T12:00:00Z", environment=env, implementation_revision=revision,
    )


def evidence(subject: str = "node-1", state: TruthState = TruthState.SUCCESS, value=None, detail=None) -> Evidence:
    if state == TruthState.SUCCESS and value is None:
        value = "observed"
    result = TruthfulValue(state, value, detail)
    return StaticEvidenceAdapter.from_static_observation(
        subject_ref=subject, observation=f"obs-{subject}", result=result,
        traceability=tr(), provenance=prov(subject=subject),
    )


def _node(node_id: str, name: str = "svc") -> GraphNode:
    return GraphNode(
        id=node_id, type=NodeType.SERVICE, name=name,
        attributes={"kind": "source", "source_path": name, "revision": REVISION},
        uncertainty=GraphUncertainty(TruthState.SUCCESS, confidence=1.0),
    )


def graph(graph_id: str = "arch-1") -> ArchitectureGraph:
    """A recovered graph with real candidate replacement nodes available.

    Includes node-a-prime and node-b-prime as real nodes in the graph so that
    candidate mutations replacing node-a -> node-a-prime (and node-b ->
    node-b-prime) satisfy the SOS-W6-F01 contract that replacement ids must be
    known nodes in the recovered graph.
    """
    nodes = (
        _node("node-a", "service-a"),
        GraphNode(id="node-i", type=NodeType.INTERFACE, name="api",
                  attributes={"kind": "source", "source_path": "api", "revision": REVISION},
                  uncertainty=GraphUncertainty(TruthState.SUCCESS, confidence=1.0)),
        _node("node-b", "service-b"),
        _node("node-a-prime", "service-a-prime"),
        _node("node-b-prime", "service-b-prime"),
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


def mutation(graph_id: str = "arch-1") -> SubgraphMutation:
    """Replace service-a with a faster service-a-prime, preserving the api boundary."""
    return SubgraphMutation(
        kind=MutationKind.SUBGRAPH_REPLACE,
        base_graph_ref=graph_id,
        target_node_ids=("node-a",),
        replacement_node_ids=("node-a-prime",),
        boundary_interface_ids=("node-i",),
        invariants=("preserve-api", "stable-schema"),
    )


def objectives() -> tuple[CandidateObjective, ...]:
    return (
        CandidateObjective(name="latency", direction=ObjectiveDirection.MINIMIZE,
                            predicted_value=150.0, uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not measured")),
        CandidateObjective(name="cost", direction=ObjectiveDirection.MINIMIZE,
                            predicted_value=1000.0, uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not measured")),
        CandidateObjective(name="throughput", direction=ObjectiveDirection.MAXIMIZE,
                            predicted_value=2000.0, uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not measured")),
    )


# --- C1: deterministic candidate identity ---


def test_identical_candidates_produce_identical_identity():
    e = evidence()
    h = hypothesis()
    m = mutation()
    a = CandidateProposal(
        id="", base_graph_ref="arch-1", base_graph_revision=REVISION,
        mutation=m, objectives=objectives(), rationale="reduce latency",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted"),
        reasoning_evidence_ids=(e.id,), reasoning_hypothesis_ids=(h.id,),
        risks=("rollback-risk",), traceability=tr(), provenance_revision=REVISION,
    )
    b = CandidateProposal(
        id="", base_graph_ref="arch-1", base_graph_revision=REVISION,
        mutation=m, objectives=objectives(), rationale="reduce latency",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted"),
        reasoning_evidence_ids=(e.id,), reasoning_hypothesis_ids=(h.id,),
        risks=("rollback-risk",), traceability=tr(), provenance_revision=REVISION,
    )
    assert a.id == b.id


def test_differing_mutation_produces_distinct_identity():
    e = evidence()
    h = hypothesis()
    m1 = mutation()
    m2 = SubgraphMutation(
        kind=MutationKind.SUBGRAPH_REPLACE, base_graph_ref="arch-1",
        target_node_ids=("node-b",), replacement_node_ids=("node-b-prime",),
        boundary_interface_ids=("node-i",), invariants=("preserve-api",),
    )
    a = CandidateProposal(
        id="", base_graph_ref="arch-1", base_graph_revision=REVISION,
        mutation=m1, objectives=objectives(), rationale="r",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
        reasoning_evidence_ids=(e.id,), reasoning_hypothesis_ids=(h.id,),
        risks=(), traceability=tr(), provenance_revision=REVISION,
    )
    b = CandidateProposal(
        id="", base_graph_ref="arch-1", base_graph_revision=REVISION,
        mutation=m2, objectives=objectives(), rationale="r",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
        reasoning_evidence_ids=(e.id,), reasoning_hypothesis_ids=(h.id,),
        risks=(), traceability=tr(), provenance_revision=REVISION,
    )
    assert a.id != b.id


# --- C2: bounded mutation representation; canonical graph immutable ---


def test_candidate_mutation_validates_against_graph_without_mutating_it():
    arch = graph()
    node_ids_before = {n.id for n in arch.nodes}
    m = mutation(arch.id)
    m.validate(arch)  # must not raise
    # Canonical graph unchanged.
    assert {n.id for n in arch.nodes} == node_ids_before


def test_candidate_mutation_rejects_unknown_target_nodes():
    arch = graph()
    bad = SubgraphMutation(
        kind=MutationKind.SUBGRAPH_REPLACE, base_graph_ref=arch.id,
        target_node_ids=("does-not-exist",), replacement_node_ids=("new",),
        boundary_interface_ids=("node-i",), invariants=("preserve-api",),
    )
    with pytest.raises(ModelValidationError):
        bad.validate(arch)


def test_candidate_mutation_rejects_unknown_boundary_node():
    arch = graph()
    # A boundary interface id that is not a known node in the graph is rejected.
    bad = SubgraphMutation(
        kind=MutationKind.SUBGRAPH_REPLACE, base_graph_ref=arch.id,
        target_node_ids=("node-a",), replacement_node_ids=("node-a-prime",),
        boundary_interface_ids=("does-not-exist",), invariants=("preserve-api",),
    )
    with pytest.raises(ModelValidationError):
        bad.validate(arch)


def test_candidate_mutation_rejects_unknown_replacement_node():
    """SOS-W6-F01: a replacement node id not present in the recovered graph is
    rejected by SubgraphMutation.validate(). A candidate may only replace a real
    node with another real node — not an arbitrary/nonexistent replacement id."""
    arch = graph()
    bad = SubgraphMutation(
        kind=MutationKind.SUBGRAPH_REPLACE, base_graph_ref=arch.id,
        target_node_ids=("node-a",), replacement_node_ids=("nonexistent-replacement",),
        boundary_interface_ids=("node-i",), invariants=("preserve-api",),
    )
    with pytest.raises(ModelValidationError, match="replacement references unknown nodes"):
        bad.validate(arch)


def test_candidate_space_rejects_unknown_replacement_node():
    """SOS-W6-F01: CandidateSpace.validate() rejects replacement ids not present
    in the base graph, so SearchEngine cannot emit structurally invalid candidates."""
    arch = graph()
    with pytest.raises(ModelValidationError, match="replacement 'nonexistent-replacement' is not in the base graph"):
        CandidateSpace(
            base_graph=arch, base_graph_revision=REVISION, traceability=tr(),
            reasoning_evidence_ids=(), reasoning_hypothesis_ids=(),
            available_replacements=(("node-a", "nonexistent-replacement"),),
        )


# --- C3: finite deterministic search ---


def test_search_terminates_within_bounds_and_is_deterministic():
    arch = graph()
    e = evidence()
    h = hypothesis()
    space = CandidateSpace(
        base_graph=arch, base_graph_revision=REVISION, traceability=tr(),
        reasoning_evidence_ids=(e.id,), reasoning_hypothesis_ids=(h.id,),
        available_replacements=(("node-a", "node-a-prime"), ("node-b", "node-b-prime")),
    )
    bounds = SearchBounds(max_candidates=5, max_depth=2, max_iterations=100)
    engine = SearchEngine(bounds=bounds)
    frontier_a = engine.search(space)
    frontier_b = engine.search(space)
    # Deterministic: same inputs -> same frontier.
    assert [c.id for c in frontier_a.candidates] == [c.id for c in frontier_b.candidates]
    # Bounded: never exceeds max_candidates.
    assert len(frontier_a.candidates) <= bounds.max_candidates


def test_search_rejects_unbounded_or_zero_bounds():
    arch = graph()
    space = CandidateSpace(
        base_graph=arch, base_graph_revision=REVISION, traceability=tr(),
        reasoning_evidence_ids=(), reasoning_hypothesis_ids=(),
        available_replacements=(("node-a", "node-a-prime"),),
    )
    with pytest.raises(ModelValidationError):
        SearchBounds(max_candidates=0, max_depth=2, max_iterations=100)
    with pytest.raises(ModelValidationError):
        SearchBounds(max_candidates=5, max_depth=0, max_iterations=100)
    with pytest.raises(ModelValidationError):
        SearchBounds(max_candidates=5, max_depth=2, max_iterations=0)


# --- C4: multi-objective / Pareto semantics ---


def test_pareto_dominance_is_deterministic():
    obj_a = objectives()
    # b dominates a on every objective (lower latency, lower cost, higher throughput)
    obj_b = (
        CandidateObjective(name="latency", direction=ObjectiveDirection.MINIMIZE, predicted_value=100.0,
                            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u")),
        CandidateObjective(name="cost", direction=ObjectiveDirection.MINIMIZE, predicted_value=900.0,
                            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u")),
        CandidateObjective(name="throughput", direction=ObjectiveDirection.MAXIMIZE, predicted_value=2500.0,
                            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u")),
    )
    ev_a = CandidateEvaluation(objectives=obj_a)
    ev_b = CandidateEvaluation(objectives=obj_b)
    assert ev_b.dominates(ev_a)
    assert not ev_a.dominates(ev_b)


def test_pareto_frontier_excludes_dominated_candidates():
    # Three candidates: a dominated by b; c non-dominated with b (trade-off).
    obj_a = (
        CandidateObjective(name="latency", direction=ObjectiveDirection.MINIMIZE, predicted_value=200.0,
                            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u")),
        CandidateObjective(name="cost", direction=ObjectiveDirection.MINIMIZE, predicted_value=1000.0,
                            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u")),
    )
    obj_b = (  # dominates a
        CandidateObjective(name="latency", direction=ObjectiveDirection.MINIMIZE, predicted_value=150.0,
                            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u")),
        CandidateObjective(name="cost", direction=ObjectiveDirection.MINIMIZE, predicted_value=900.0,
                            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u")),
    )
    obj_c = (  # trade-off with b: lower cost, higher latency
        CandidateObjective(name="latency", direction=ObjectiveDirection.MINIMIZE, predicted_value=180.0,
                            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u")),
        CandidateObjective(name="cost", direction=ObjectiveDirection.MINIMIZE, predicted_value=800.0,
                            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u")),
    )
    e = evidence()
    h = hypothesis()
    m = mutation()
    kw = dict(base_graph_ref="arch-1", base_graph_revision=REVISION, mutation=m,
              uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
              reasoning_evidence_ids=(e.id,), reasoning_hypothesis_ids=(h.id,),
              risks=(), traceability=tr(), provenance_revision=REVISION)
    ca = CandidateProposal(id="", objectives=obj_a, rationale="a", **kw)
    cb = CandidateProposal(id="", objectives=obj_b, rationale="b", **kw)
    cc = CandidateProposal(id="", objectives=obj_c, rationale="c", **kw)
    frontier = ParetoFrontier.from_candidates((ca, cb, cc))
    ids = {c.id for c in frontier.candidates}
    assert cb.id in ids  # non-dominated
    assert cc.id in ids  # non-dominated (trade-off)
    assert ca.id not in ids  # dominated by b


def test_no_single_scalar_quality_becomes_authoritative():
    # There is no "quality_score" scalar field; evaluation is multi-objective.
    ev = CandidateEvaluation(objectives=objectives())
    assert not hasattr(ev, "quality_score")
    assert not hasattr(ev, "score")


# --- C5: uncertainty / truthfulness ---


def test_candidate_scores_cannot_upgrade_truth():
    e = evidence()
    h = hypothesis()
    m = mutation()
    # A candidate's uncertainty is non-SUCCESS (predicted, not proven).
    c = CandidateProposal(
        id="", base_graph_ref="arch-1", base_graph_revision=REVISION,
        mutation=m, objectives=objectives(), rationale="r",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not proven"),
        reasoning_evidence_ids=(e.id,), reasoning_hypothesis_ids=(h.id,),
        risks=(), traceability=tr(), provenance_revision=REVISION,
    )
    assert c.uncertainty.state != TruthState.SUCCESS


def test_candidate_must_not_claim_success_without_intervention_evidence():
    e = evidence()  # observational
    h = hypothesis()
    m = mutation()
    # A candidate claiming SUCCESS (proven) uncertainty backed only by
    # observational evidence is rejected.
    with pytest.raises(ModelValidationError):
        CandidateProposal(
            id="", base_graph_ref="arch-1", base_graph_revision=REVISION,
            mutation=m, objectives=objectives(), rationale="r",
            uncertainty=TruthfulValue(TruthState.SUCCESS, "proven", None),
            reasoning_evidence_ids=(e.id,), reasoning_hypothesis_ids=(h.id,),
            risks=(), traceability=tr(), provenance_revision=REVISION,
        )


# --- C6: evidence/causal traceability ---


def test_candidate_records_graph_evidence_and_causal_references():
    e = evidence()
    h = hypothesis()
    m = mutation()
    c = CandidateProposal(
        id="", base_graph_ref="arch-1", base_graph_revision=REVISION,
        mutation=m, objectives=objectives(), rationale="r",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
        reasoning_evidence_ids=(e.id,), reasoning_hypothesis_ids=(h.id,),
        risks=("rollback-risk",), traceability=tr(), provenance_revision=REVISION,
    )
    assert c.base_graph_ref == "arch-1"
    assert c.base_graph_revision == REVISION
    assert c.provenance_revision == REVISION
    assert e.id in c.reasoning_evidence_ids
    assert h.id in c.reasoning_hypothesis_ids
    assert c.traceability.context_ref == "context:1"


def test_candidate_rejects_traceability_missing_context():
    e = evidence()
    h = hypothesis()
    m = mutation()
    bad = Traceability(constitution_ref="c", mission_ref="m", value_model_ref="v", context_ref=None)
    with pytest.raises(ModelValidationError):
        CandidateProposal(
            id="", base_graph_ref="arch-1", base_graph_revision=REVISION,
            mutation=m, objectives=objectives(), rationale="r",
            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
            reasoning_evidence_ids=(e.id,), reasoning_hypothesis_ids=(h.id,),
            risks=(), traceability=bad, provenance_revision=REVISION,
        )


# --- C7: deterministic dedup / order ---


def test_repeated_identical_candidates_deduplicate():
    arch = graph()
    e = evidence()
    h = hypothesis()
    space = CandidateSpace(
        base_graph=arch, base_graph_revision=REVISION, traceability=tr(),
        reasoning_evidence_ids=(e.id,), reasoning_hypothesis_ids=(h.id,),
        available_replacements=(("node-a", "node-a-prime"),),
    )
    bounds = SearchBounds(max_candidates=10, max_depth=2, max_iterations=100)
    engine = SearchEngine(bounds=bounds)
    f1 = engine.search(space)
    f2 = engine.search(space)
    assert [c.id for c in f1.candidates] == [c.id for c in f2.candidates]
    # No duplicate ids in a frontier.
    ids = [c.id for c in f1.candidates]
    assert len(ids) == len(set(ids))


def test_frontier_orders_candidates_deterministically():
    e = evidence()
    h = hypothesis()
    m = mutation()
    kw = dict(base_graph_ref="arch-1", base_graph_revision=REVISION, mutation=m,
              uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
              reasoning_evidence_ids=(e.id,), reasoning_hypothesis_ids=(h.id,),
              risks=(), traceability=tr(), provenance_revision=REVISION)
    c1 = CandidateProposal(id="", objectives=objectives(), rationale="c1", **kw)
    c2 = CandidateProposal(id="", objectives=objectives(), rationale="c2", **kw)  # different rationale
    f = ParetoFrontier.from_candidates((c2, c1))
    ids = [c.id for c in f.candidates]
    assert ids == sorted(ids)


# --- C8: explicit rejection ---


def test_candidate_rejects_missing_graph_reference():
    e = evidence()
    h = hypothesis()
    m = mutation()
    with pytest.raises(ModelValidationError):
        CandidateProposal(
            id="", base_graph_ref="", base_graph_revision=REVISION,  # empty graph ref
            mutation=m, objectives=objectives(), rationale="r",
            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
            reasoning_evidence_ids=(e.id,), reasoning_hypothesis_ids=(h.id,),
            risks=(), traceability=tr(), provenance_revision=REVISION,
        )


def test_candidate_rejects_empty_objectives():
    e = evidence()
    h = hypothesis()
    m = mutation()
    with pytest.raises(ModelValidationError):
        CandidateProposal(
            id="", base_graph_ref="arch-1", base_graph_revision=REVISION,
            mutation=m, objectives=(), rationale="r",  # no objectives
            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
            reasoning_evidence_ids=(e.id,), reasoning_hypothesis_ids=(h.id,),
            risks=(), traceability=tr(), provenance_revision=REVISION,
        )


def test_candidate_rejects_empty_mutation_targets():
    # An empty-target mutation is rejected at SubgraphMutation construction
    # (structural validation), so it can never reach a CandidateProposal.
    with pytest.raises(ModelValidationError):
        SubgraphMutation(
            kind=MutationKind.SUBGRAPH_REPLACE, base_graph_ref="arch-1",
            target_node_ids=(), replacement_node_ids=("new",),  # empty target
            boundary_interface_ids=("node-i",), invariants=("preserve-api",),
        )
    # And an empty-replacement mutation is likewise rejected.
    with pytest.raises(ModelValidationError):
        SubgraphMutation(
            kind=MutationKind.SUBGRAPH_REPLACE, base_graph_ref="arch-1",
            target_node_ids=("node-a",), replacement_node_ids=(),  # empty replacement
            boundary_interface_ids=("node-i",), invariants=("preserve-api",),
        )


# --- C9: repository persistence ---


def test_frontier_round_trips_through_json(tmp_path):
    e = evidence()
    h = hypothesis()
    m = mutation()
    c = CandidateProposal(
        id="", base_graph_ref="arch-1", base_graph_revision=REVISION,
        mutation=m, objectives=objectives(), rationale="r",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
        reasoning_evidence_ids=(e.id,), reasoning_hypothesis_ids=(h.id,),
        risks=("rollback-risk",), traceability=tr(), provenance_revision=REVISION,
    )
    f = ParetoFrontier.from_candidates((c,))
    p = tmp_path / "frontier.json"
    JsonModelStore(p).save(f)
    data = JsonModelStore(p).load()
    assert data["candidates"][0]["id"] == c.id
    assert data["candidates"][0]["base_graph_ref"] == "arch-1"
    assert data["candidates"][0]["base_graph_revision"] == REVISION
    assert data["candidates"][0]["reasoning_evidence_ids"] == [e.id]
    assert data["traceability"]["context_ref"] == "context:1"


# --- C10: bounded surface (no W7+ symbols) ---


def test_w6_introduces_no_w7_plus_symbols():
    import sos.candidates as cmod
    forbidden = {
        "AssuranceVerdict", "AssuranceGate", "ImpactAnalysis", "RiskGate",
        "Experiment", "Promotion", "Rollback", "Canary", "Shadow",
        "Decision", "AutonomyPolicy", "AskPayload", "Act", "ExperimentRunner",
        "PlatformAdapter", "Personalization", "Greenfield", "Brownfield",
        "SelfEvolution", "MetaAdaptation",
    }
    exported = {n for n in dir(cmod) if not n.startswith("_")}
    assert not (forbidden & exported), f"forbidden W7+ symbols present: {forbidden & exported}"


# --- candidate validation against known graph + evidence/causal records ---


def test_candidate_validates_reasoning_references_against_known_records():
    arch = graph()
    e = evidence()
    h = hypothesis()
    m = mutation(arch.id)
    c = CandidateProposal(
        id="", base_graph_ref=arch.id, base_graph_revision=REVISION,
        mutation=m, objectives=objectives(), rationale="r",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
        reasoning_evidence_ids=(e.id,), reasoning_hypothesis_ids=(h.id,),
        risks=(), traceability=tr(), provenance_revision=REVISION,
    )
    # Known graph + evidence + causal records: validation passes.
    c.validate(
        known_graph=arch,
        known_evidence_ids={e.id},
        known_hypothesis_ids={h.id},
    )
    # Unknown evidence id is rejected.
    with pytest.raises(ModelValidationError):
        c.validate(known_graph=arch, known_evidence_ids=set(), known_hypothesis_ids={h.id})
    # Unknown hypothesis id is rejected.
    with pytest.raises(ModelValidationError):
        c.validate(known_graph=arch, known_evidence_ids={e.id}, known_hypothesis_ids=set())
    # Graph id mismatch is rejected.
    other = graph("arch-other")
    with pytest.raises(ModelValidationError):
        c.validate(known_graph=other, known_evidence_ids={e.id}, known_hypothesis_ids={h.id})
