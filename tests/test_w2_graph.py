import pytest
from sos import *


def tr():
    return Traceability("constitution:1", "mission:1", "value:1", "context:1")


def certain():
    return GraphUncertainty(TruthState.SUCCESS, confidence=1.0)


def graph():
    nodes = (
        GraphNode("a", NodeType.SERVICE, "service-a", {}, certain()),
        GraphNode("i", NodeType.INTERFACE, "api", {}, certain()),
        GraphNode("b", NodeType.COMPONENT, "component-b", {}, certain()),
    )
    edges = (GraphEdge("e", EdgeType.CALL, "a", "i", {}, certain()),)
    contracts = (BoundaryContract("bc", "i", "HTTP interface", ("stable-schema",), certain()),)
    result = ArchitectureGraph("arch-1", 1, nodes, edges, contracts, certain(), tr())
    result.validate()
    return result


def refs(state=TruthState.SUCCESS):
    return StateReference(TruthfulValue(state, "rev-1" if state == TruthState.SUCCESS else None, None if state == TruthState.SUCCESS else "not available"))


def test_graph_supports_frozen_node_and_edge_types():
    assert len(NodeType) == 11
    assert len(EdgeType) == 11


def test_graph_rejects_broken_edge_reference_and_duplicate_ids():
    base = graph()
    broken = GraphEdge("broken", EdgeType.DEPENDENCY, "a", "missing", {}, certain())
    with pytest.raises(ModelValidationError):
        ArchitectureGraph(base.id, 1, base.nodes, base.edges + (broken,), base.boundary_contracts, certain(), tr()).validate()
    with pytest.raises(ModelValidationError):
        ArchitectureGraph(base.id, 1, base.nodes + (base.nodes[0],), base.edges, base.boundary_contracts, certain(), tr()).validate()


def test_unknown_graph_state_cannot_claim_confidence():
    GraphUncertainty(TruthState.UNKNOWN, reason="manifest missing").validate()
    with pytest.raises(ModelValidationError):
        GraphUncertainty(TruthState.UNKNOWN, confidence=0.99).validate()


def test_system_state_contains_versioned_architecture_and_all_references():
    arch = graph()
    state = SystemState.create(version=1, architecture=arch, implementation_ref=refs(), configuration_ref=refs(), deployment_ref=refs(), policy_ref=refs(), environment_ref=refs(), active_experiments=("experiment:pending",), traceability=tr())
    state.validate()
    assert state.architecture_ref == arch.id and state.revision_id


def test_system_state_revision_lineage_is_explicit():
    state = SystemState.create(version=1, architecture=graph(), implementation_ref=refs(), configuration_ref=refs(), deployment_ref=refs(), policy_ref=refs(), environment_ref=refs(), active_experiments=(), traceability=tr())
    child = state.next_revision(deployment_ref=refs())
    assert child.version == 2
    assert child.parent_revision_id == state.revision_id
    assert child.revision_id != state.revision_id
    with pytest.raises(ModelValidationError):
        SystemState(state.id, 2, state.architecture_ref, state.implementation_ref, state.configuration_ref, state.deployment_ref, state.policy_ref, state.environment_ref, (), state.architecture, state.traceability, "unrelated-revision").validate()


def test_system_state_rejects_architecture_reference_mismatch():
    arch = graph()
    state = SystemState.create(version=1, architecture=arch, implementation_ref=refs(), configuration_ref=refs(), deployment_ref=refs(), policy_ref=refs(), environment_ref=refs(), active_experiments=(), traceability=tr())
    broken = SystemState(state.id, state.version, "other-arch", state.implementation_ref, state.configuration_ref, state.deployment_ref, state.policy_ref, state.environment_ref, (), arch, state.traceability, state.revision_id)
    with pytest.raises(ModelValidationError):
        broken.validate()


def test_subgraph_replacement_requires_boundary_interfaces_and_invariants():
    arch = graph()
    SubgraphReplacement("candidate-1", arch.id, ("a", "i"), ("new-a",), ("i",), ("preserve-api",), tr()).validate(arch)
    with pytest.raises(ModelValidationError):
        SubgraphReplacement("candidate-2", arch.id, ("a",), ("new-a",), (), ("preserve-api",), tr()).validate(arch)
    with pytest.raises(ModelValidationError):
        SubgraphReplacement("candidate-3", "other", ("a",), ("new-a",), ("i",), ("preserve-api",), tr()).validate(arch)


def test_json_round_trip_preserves_graph_boundaries_and_truth_states(tmp_path):
    arch = graph()
    state = SystemState.create(version=1, architecture=arch, implementation_ref=refs(), configuration_ref=refs(), deployment_ref=refs(TruthState.UNAVAILABLE), policy_ref=refs(), environment_ref=refs(), active_experiments=(), traceability=tr())
    path = tmp_path / "state.json"
    JsonModelStore(path).save(state)
    data = JsonModelStore(path).load()
    assert data["architecture"]["boundary_contracts"][0]["invariants"] == ["stable-schema"]
    assert data["deployment_ref"]["ref"]["state"] == "UNAVAILABLE"
    assert data["architecture"]["nodes"][0]["type"] == "service"
