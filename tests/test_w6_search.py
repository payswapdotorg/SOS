import pytest

from sos import (
    ArchitectureMemory,
    CandidateMetrics,
    CandidateState,
    GraphEdge,
    GraphNode,
    GraphUncertainty,
    ArchitectureGraph,
    BoundaryContract,
    EdgeType,
    NodeType,
    SearchBudget,
    SubgraphReplacement,
    Traceability,
    TruthState,
    generate_candidates,
    pareto_front,
    ModelValidationError,
)


def trace():
    return Traceability("constitution:1", "mission:1", "value:1", "context:1")


def graph():
    certain = GraphUncertainty(TruthState.SUCCESS, confidence=1.0)
    nodes = (
        GraphNode("service", NodeType.SERVICE, "service", {}, certain),
        GraphNode("api", NodeType.INTERFACE, "api", {}, certain),
    )
    edges = (GraphEdge("e", EdgeType.CALL, "service", "api", {}, certain),)
    contracts = (BoundaryContract("bc", "api", "HTTP", ("stable",), certain),)
    return ArchitectureGraph("arch", 1, nodes, edges, contracts, certain, trace())


def replacement(name="r", target=("service",), replacement=("cache-service",)):
    return SubgraphReplacement(name, "arch", target, replacement, ("service",) if target == ("service",) else target[-1:], ("preserve-interface",), trace())


def metrics(benefit, cost, risk, uncertainty, reversibility, blast):
    return CandidateMetrics(benefit, cost, risk, uncertainty, reversibility, blast)


def test_search_is_bounded_and_deterministic():
    result = generate_candidates(
        graph=graph(), base_system_state_ref="state:1",
        replacements=(replacement("r1"), replacement("r2")),
        metrics=(metrics(.8,.4,.2,.2,.8,.2), metrics(.6,.2,.1,.3,.9,.1)),
        authority_required="assurance:required", predicted_effects=("latency improves",), risks=("cache invalidation",),
        traceability=trace(), budget=SearchBudget(3),
    )
    assert len(result.candidates) == 3
    result2 = generate_candidates(
        graph=graph(), base_system_state_ref="state:1", replacements=(replacement("r1"), replacement("r2")),
        metrics=(metrics(.8,.4,.2,.2,.8,.2), metrics(.6,.2,.1,.3,.9,.1)), authority_required="assurance:required",
        predicted_effects=("latency improves",), risks=("cache invalidation",), traceability=trace(), budget=SearchBudget(3),
    )
    assert [c.id for c in result.candidates] == [c.id for c in result2.candidates]


def test_pareto_front_keeps_non_dominated_tradeoffs():
    g = graph()
    base = replacement("r")
    candidates = (
        CandidateState("a", "state", base, ("benefit",), ("risk",), "assurance", metrics(.9,.8,.5,.2,.5,.5), trace()),
        CandidateState("b", "state", base, ("benefit",), ("risk",), "assurance", metrics(.7,.2,.1,.2,.9,.1), trace()),
        CandidateState("c", "state", base, ("benefit",), ("risk",), "assurance", metrics(.8,.5,.2,.2,.7,.2), trace()),
    )
    front = pareto_front(candidates)
    assert {c.id for c in front} == {"a", "b", "c"}


def test_dominated_candidate_is_removed():
    g = graph()
    base = replacement("r")
    better = CandidateState("better", "state", base, ("effect",), ("risk",), "assurance", metrics(.9,.2,.1,.1,.9,.1), trace())
    worse = CandidateState("worse", "state", base, ("effect",), ("risk",), "assurance", metrics(.7,.4,.2,.2,.6,.3), trace())
    assert [c.id for c in pareto_front((better, worse))] == ["better"]


def test_memory_is_only_a_prior_signal():
    g = graph()
    mem = ArchitectureMemory("m1", "ctx", "cache", ("x",), ("y",), "positive", "cache repeats", {"source_revision":"rev","recorded_at":"t"}, .9, trace())
    replacement_for_cache = replacement("r-cache", replacement=("cache-service",))
    result = generate_candidates(
        graph=g, base_system_state_ref="state", replacements=(replacement_for_cache,),
        metrics=(metrics(.5,.5,.5,.5,.5,.5),), authority_required="assurance", predicted_effects=("x",), risks=("y",),
        traceability=trace(), budget=SearchBudget(1), memories=(mem,),
    )
    assert result.candidates[0].metrics.memory_prior == .9
    assert result.candidates[0].memory_refs == ("m1",)


def test_invalid_boundary_is_rejected_before_generation():
    with pytest.raises(ModelValidationError):
        generate_candidates(
            graph=graph(), base_system_state_ref="state", replacements=(SubgraphReplacement("bad", "arch", ("missing",), ("new",), ("missing",), ("x",), trace()),),
            metrics=(metrics(.5,.5,.5,.5,.5,.5),), authority_required="assurance", predicted_effects=("x",), risks=("y",), traceability=trace(), budget=SearchBudget(1),
        )
