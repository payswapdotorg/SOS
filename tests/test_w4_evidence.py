"""W4 — evidence / observability boundary invariant tests.

Failing-first per SOS-IMPLEMENTATION-PROCESS §5: defines the behavioural
contract of ``src/sos/evidence.py`` before it exists. Covers the W4 Work Order
acceptance criteria: deterministic identity + provenance, subject linkage to
recovered W2/W3 facts without semantic authority change, truth-state separation
(SUCCESS/FAILED/UNKNOWN/UNAVAILABLE/EMPTY), no runtime fabrication from static
evidence, W1 traceability, deterministic duplicate ingestion, invalid-subject
rejection, and the evidence-only boundary (no causal/candidate/assurance/
experiment semantics).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sos import (
    ArchitectureGraph,
    EdgeType,
    GraphNode,
    GraphUncertainty,
    JsonModelStore,
    ModelValidationError,
    NodeType,
    SystemState,
    Traceability,
    TruthState,
    TruthfulValue,
)
from sos.evidence import (
    Evidence,
    EvidenceGraph,
    EvidenceKind,
    EvidenceProvenance,
    OpenTelemetryShapedAdapter,
    StaticEvidenceAdapter,
)


REVISION = "deadbeefcafebabe1234567890abcdef12345678"


def tr() -> Traceability:
    return Traceability(
        constitution_ref="constitution:1",
        mission_ref="mission:1",
        value_model_ref="value:1",
        context_ref="context:1",
    )


def prov(*, source: str = "static-recovery", subject: str = "system-state-1", revision: str = REVISION) -> EvidenceProvenance:
    return EvidenceProvenance(
        source=source,
        observed_subject=subject,
        timestamp="2026-09-05T12:00:00Z",
        environment="production",
        implementation_revision=revision,
    )


def _node(node_id: str, name: str = "svc-a") -> GraphNode:
    return GraphNode(
        id=node_id,
        type=NodeType.SERVICE,
        name=name,
        attributes={"kind": "source", "source_path": name, "revision": REVISION},
        uncertainty=GraphUncertainty(TruthState.SUCCESS, confidence=1.0),
    )


def _graph(graph_id: str = "arch-1") -> ArchitectureGraph:
    nodes = (_node("node-1", "service-a"), _node("node-2", "api"))
    return ArchitectureGraph(
        id=graph_id, version=1, nodes=nodes, edges=(),
        boundary_contracts=(), uncertainty=GraphUncertainty(TruthState.SUCCESS, confidence=1.0),
        traceability=tr(),
    )


def _state(state_id: str = "system-state-1") -> SystemState:
    from sos import StateReference
    ref = StateReference(TruthfulValue(TruthState.SUCCESS, REVISION, None))
    return SystemState(
        id=state_id, version=1, architecture_ref="arch-1",
        implementation_ref=ref, configuration_ref=ref, deployment_ref=ref,
        policy_ref=ref, environment_ref=ref, active_experiments=(),
        architecture=_graph(), traceability=tr(),
        revision_id="rev-1", parent_revision_id=None,
    )


# --- acceptance criterion 1: deterministic identity + exact provenance ---


def test_evidence_has_deterministic_identity_and_exact_provenance():
    e = StaticEvidenceAdapter.from_test_result(
        subject_ref="node-1",
        test_name="tests/test_app.py::test_main",
        result=TruthfulValue(TruthState.SUCCESS, "pass", None),
        traceability=tr(),
        provenance=prov(),
    )
    assert isinstance(e, Evidence)
    assert e.id  # non-empty deterministic id
    assert e.kind == EvidenceKind.TEST
    assert e.provenance.source == "static-recovery"
    assert e.provenance.implementation_revision == REVISION
    assert e.provenance.observed_subject == "system-state-1"


def test_identical_evidence_inputs_produce_identical_identity():
    a = StaticEvidenceAdapter.from_test_result(
        subject_ref="node-1", test_name="tests/test_app.py::test_main",
        result=TruthfulValue(TruthState.SUCCESS, "pass", None),
        traceability=tr(), provenance=prov(),
    )
    b = StaticEvidenceAdapter.from_test_result(
        subject_ref="node-1", test_name="tests/test_app.py::test_main",
        result=TruthfulValue(TruthState.SUCCESS, "pass", None),
        traceability=tr(), provenance=prov(),
    )
    assert a.id == b.id


# --- acceptance criterion 2: subject linkage without semantic authority change ---


def test_evidence_references_recovered_subjects_without_mutating_graph():
    state = _state()
    arch_before = state.architecture
    node_ids_before = {n.id for n in arch_before.nodes}

    e = StaticEvidenceAdapter.from_static_observation(
        subject_ref="node-1",
        observation="service-a present in recovered architecture",
        result=TruthfulValue(TruthState.SUCCESS, "present", None),
        traceability=tr(),
        provenance=prov(subject="node-1"),
    )
    e.validate(known_subject_ids=node_ids_before)
    assert e.subject_ref == "node-1"

    # The recovered architecture graph is unchanged — evidence does not edit it.
    arch_after = state.architecture
    assert {n.id for n in arch_after.nodes} == node_ids_before
    assert arch_after is arch_before


# --- acceptance criterion 3: truth-state separation ---


@pytest.mark.parametrize(
    "state,value,detail",
    [
        (TruthState.SUCCESS, "pass", None),
        (TruthState.FAILED, None, "test raised AssertionError"),
        (TruthState.UNKNOWN, None, "metric source did not return"),
        (TruthState.UNAVAILABLE, None, "collector unreachable"),
        (TruthState.EMPTY, None, None),
    ],
)
def test_truthful_states_remain_distinct(state, value, detail):
    result = TruthfulValue(state, value, detail)
    e = StaticEvidenceAdapter.from_static_observation(
        subject_ref="node-1",
        observation=f"probe-{state.value}",
        result=result,
        traceability=tr(),
        provenance=prov(),
    )
    e.validate()
    assert e.result.state == state
    # The five states are structurally distinct enum members.
    distinct = {TruthState.SUCCESS, TruthState.FAILED, TruthState.UNKNOWN, TruthState.UNAVAILABLE, TruthState.EMPTY}
    assert len(distinct) == 5
    assert state in distinct


def test_success_requires_value_and_non_success_rejects_value():
    with pytest.raises(ModelValidationError):
        StaticEvidenceAdapter.from_static_observation(
            subject_ref="node-1", observation="bad",
            result=TruthfulValue(TruthState.SUCCESS, None, None),  # SUCCESS without value
            traceability=tr(), provenance=prov(),
        )
    with pytest.raises(ModelValidationError):
        StaticEvidenceAdapter.from_static_observation(
            subject_ref="node-1", observation="bad",
            result=TruthfulValue(TruthState.FAILED, "should-not-have-value", "detail"),
            traceability=tr(), provenance=prov(),
        )


# --- acceptance criterion 4: no runtime fabrication from static evidence ---


def test_static_evidence_does_not_claim_runtime_reality():
    # A static observation carries kind=OBSERVATION and may have timestamp None;
    # it must NOT be labelled as a runtime deployment/runtime-environment fact.
    e = StaticEvidenceAdapter.from_static_observation(
        subject_ref="node-1",
        observation="file recovered from repository at this revision",
        result=TruthfulValue(TruthState.SUCCESS, "present", None),
        traceability=tr(),
        provenance=prov(source="static-recovery"),
    )
    e.validate()
    assert e.kind == EvidenceKind.OBSERVATION
    assert e.provenance.source == "static-recovery"
    # Static evidence carries an implementation_revision (the repo fact), but
    # does not fabricate a runtime environment observation.
    assert e.provenance.implementation_revision == REVISION


def test_unavailable_runtime_observation_is_explicit_not_synthesized():
    # When a runtime metric is not actually observed, the evidence records
    # UNAVAILABLE — never a fabricated SUCCESS value.
    e = StaticEvidenceAdapter.unavailable_runtime_observation(
        subject_ref="node-1",
        dimension="p99-latency",
        reason="live collector not configured",
        traceability=tr(),
        provenance=prov(),
    )
    e.validate()
    assert e.result.state == TruthState.UNAVAILABLE
    assert e.result.value is None
    assert e.result.detail == "live collector not configured"
    assert e.availability == TruthState.UNAVAILABLE


# --- acceptance criterion 5: traceability preserved ---


def test_evidence_carries_w1_traceability():
    t = tr()
    e = StaticEvidenceAdapter.from_test_result(
        subject_ref="node-1", test_name="t",
        result=TruthfulValue(TruthState.SUCCESS, "pass", None),
        traceability=t, provenance=prov(),
    )
    assert e.traceability == t
    assert e.traceability.value_model_ref == "value:1"
    assert e.traceability.context_ref == "context:1"


def test_evidence_rejects_traceability_missing_context():
    bad = Traceability(
        constitution_ref="constitution:1", mission_ref="mission:1",
        value_model_ref="value:1", context_ref=None,
    )
    with pytest.raises(ModelValidationError):
        StaticEvidenceAdapter.from_test_result(
            subject_ref="node-1", test_name="t",
            result=TruthfulValue(TruthState.SUCCESS, "pass", None),
            traceability=bad, provenance=prov(),
        )


# --- acceptance criterion 6: deterministic duplicate ingestion ---


def test_repeated_identical_ingestion_is_deterministic():
    g = EvidenceGraph(id="eg-1", version=1, records=(), traceability=tr())
    inputs = [
        StaticEvidenceAdapter.from_test_result(
            subject_ref="node-1", test_name="t",
            result=TruthfulValue(TruthState.SUCCESS, "pass", None),
            traceability=tr(), provenance=prov(),
        )
        for _ in range(3)
    ]
    for e in inputs:
        g = g.ingest(e)
    # Identical evidence deduplicates by deterministic id — not 3 copies.
    assert len(g.records) == 1
    assert g.records[0].id == inputs[0].id
    g.validate()


def test_evidence_graph_orders_records_deterministically():
    e_b = StaticEvidenceAdapter.from_test_result(
        subject_ref="node-b", test_name="t-b",
        result=TruthfulValue(TruthState.SUCCESS, "pass", None),
        traceability=tr(), provenance=prov(subject="node-b"),
    )
    e_a = StaticEvidenceAdapter.from_test_result(
        subject_ref="node-a", test_name="t-a",
        result=TruthfulValue(TruthState.SUCCESS, "pass", None),
        traceability=tr(), provenance=prov(subject="node-a"),
    )
    g = EvidenceGraph(id="eg-1", version=1, records=(), traceability=tr()).ingest(e_b).ingest(e_a)
    ids = [r.id for r in g.records]
    assert ids == sorted(ids)


# --- acceptance criterion 7: invalid subject references / malformed evidence ---


def test_invalid_subject_reference_rejected():
    e = StaticEvidenceAdapter.from_test_result(
        subject_ref="does-not-exist", test_name="t",
        result=TruthfulValue(TruthState.SUCCESS, "pass", None),
        traceability=tr(), provenance=prov(),
    )
    with pytest.raises(ModelValidationError):
        e.validate(known_subject_ids={"node-1", "node-2"})


def test_malformed_evidence_rejected():
    with pytest.raises(ModelValidationError):
        Evidence(
            id="",  # empty id
            kind=EvidenceKind.OBSERVATION,
            source_ref="src", subject_ref="node-1",
            timestamp=None, environment=None,
            result=TruthfulValue(TruthState.SUCCESS, "x", None),
            provenance=prov(), confidence=None,
            availability=TruthState.SUCCESS, traceability=tr(),
        )
    with pytest.raises(ModelValidationError):
        Evidence(
            id="e-1",
            kind=EvidenceKind.OBSERVATION,
            source_ref="src", subject_ref="",  # empty subject
            timestamp=None, environment=None,
            result=TruthfulValue(TruthState.SUCCESS, "x", None),
            provenance=prov(), confidence=None,
            availability=TruthState.SUCCESS, traceability=tr(),
        )


def test_out_of_range_confidence_rejected():
    with pytest.raises(ModelValidationError):
        Evidence(
            id="e-1", kind=EvidenceKind.OBSERVATION,
            source_ref="src", subject_ref="node-1",
            timestamp=None, environment=None,
            result=TruthfulValue(TruthState.SUCCESS, "x", None),
            provenance=prov(), confidence=1.5,  # > 1
            availability=TruthState.SUCCESS, traceability=tr(),
        )


# --- acceptance criterion 8: evidence-only boundary (no causal/candidate/assurance/experiment) ---


def test_w4_introduces_evidence_only_no_downstream_semantics():
    import sos.evidence as evmod
    # No causal/candidate/assurance/experiment/promotion/rollback symbols exported.
    forbidden = {
        "CausalHypothesis", "CausalEvidence", "CandidateState", "Candidate",
        "AssuranceVerdict", "AssuranceGate", "Experiment", "Promotion",
        "Rollback", "Decision", "AutonomyPolicy", "AskPayload",
    }
    exported = {n for n in dir(evmod) if not n.startswith("_")}
    assert not (forbidden & exported), f"forbidden downstream symbols present: {forbidden & exported}"


# --- OpenTelemetry-shaped ingestion boundary (no live collector) ---


def test_otel_span_ingestion_preserves_truth_and_provenance():
    span = {
        "trace_id": "abcdef0123456789abcdef0123456789",
        "span_id": "1234567890abcdef",
        "name": "GET /api",
        "status": {"code": "ERROR", "message": "500"},
        "start_time_unix_nano": 1725500000000000000,
        "end_time_unix_nano": 1725500001000000000,
    }
    e = OpenTelemetryShapedAdapter.from_otel_span(
        span=span, subject_ref="node-1",
        traceability=tr(), provenance=prov(source="otel-span"),
    )
    e.validate()
    assert e.kind == EvidenceKind.OBSERVATION
    assert e.provenance.source == "otel-span"
    assert e.source_ref == span["span_id"]


def test_otel_ingestion_does_not_fabricate_runtime_when_fields_missing():
    # A span missing its status/end-time is an incomplete runtime observation;
    # the evidence must record UNKNOWN/UNAVAILABLE, never a fabricated SUCCESS.
    span = {"trace_id": "t", "span_id": "s", "name": "GET /api"}  # no status, no timing
    e = OpenTelemetryShapedAdapter.from_otel_span(
        span=span, subject_ref="node-1",
        traceability=tr(), provenance=prov(source="otel-span"),
    )
    e.validate()
    assert e.result.state in (TruthState.UNKNOWN, TruthState.UNAVAILABLE)
    assert e.result.value is None
    assert e.result.detail  # explanatory detail required


# --- serialization round trip (W2 persistence boundary reuse) ---


def test_evidence_graph_round_trips_through_json(tmp_path):
    e = StaticEvidenceAdapter.from_test_result(
        subject_ref="node-1", test_name="t",
        result=TruthfulValue(TruthState.SUCCESS, "pass", None),
        traceability=tr(), provenance=prov(),
    )
    g = EvidenceGraph(id="eg-1", version=1, records=(e,), traceability=tr())
    p = tmp_path / "evidence.json"
    JsonModelStore(p).save(g)
    data = JsonModelStore(p).load()
    assert data["records"][0]["id"] == e.id
    assert data["records"][0]["result"]["state"] == "SUCCESS"
    assert data["records"][0]["provenance"]["implementation_revision"] == REVISION
    assert data["traceability"]["context_ref"] == "context:1"


# --- by-subject lookup ---


def test_evidence_graph_indexes_by_subject():
    e1 = StaticEvidenceAdapter.from_test_result(
        subject_ref="node-1", test_name="t1",
        result=TruthfulValue(TruthState.SUCCESS, "pass", None),
        traceability=tr(), provenance=prov(subject="node-1"),
    )
    e2 = StaticEvidenceAdapter.from_test_result(
        subject_ref="node-2", test_name="t2",
        result=TruthfulValue(TruthState.SUCCESS, "pass", None),
        traceability=tr(), provenance=prov(subject="node-2"),
    )
    g = EvidenceGraph(id="eg-1", version=1, records=(), traceability=tr()).ingest(e1).ingest(e2)
    assert {r.id for r in g.by_subject("node-1")} == {e1.id}
    assert {r.id for r in g.by_subject("node-2")} == {e2.id}
    assert g.by_subject("node-3") == ()
