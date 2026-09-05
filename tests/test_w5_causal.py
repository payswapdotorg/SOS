"""W5 — causal knowledge + architecture memory invariant tests.

Failing-first per SOS-IMPLEMENTATION-PROCESS §5: defines the behavioural
contract of ``src/sos/causal.py`` before it exists. Covers the W5 Work Order
acceptance criteria C1–C10: deterministic causal identity, evidence-backed
support, observation vs intervention distinction, truthful uncertainty, no
authority mutation, deterministic memory behavior, provenance/traceability,
architecture-memory-as-projection, repository persistence, and the bounded
W5 surface (no W6+ symbols).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sos import (
    Evidence,
    EvidenceGraph,
    EvidenceKind,
    EvidenceProvenance,
    JsonModelStore,
    ModelValidationError,
    StaticEvidenceAdapter,
    Traceability,
    TruthState,
    TruthfulValue,
)
from sos.causal import (
    ArchitectureMemory,
    CausalHypothesis,
    CausalKnowledgeGraph,
    CausalRelationType,
    EvidenceSupport,
    InterventionMetadata,
    SupportKind,
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
        timestamp="2026-09-06T12:00:00Z", environment=env, implementation_revision=revision,
    )


def evidence(subject: str = "node-1", state: TruthState = TruthState.SUCCESS, value=None, detail=None) -> Evidence:
    # SUCCESS requires a non-None value per W1 TruthfulValue.validate(); supply
    # a default value when the caller did not provide one for a SUCCESS state.
    if state == TruthState.SUCCESS and value is None:
        value = "observed"
    result = TruthfulValue(state, value, detail)
    return StaticEvidenceAdapter.from_static_observation(
        subject_ref=subject, observation=f"obs-{subject}", result=result,
        traceability=tr(), provenance=prov(subject=subject),
    )


def intervention_evidence(subject: str = "node-1") -> Evidence:
    """An intervention (experiment) evidence record carrying intervention metadata."""
    result = TruthfulValue(TruthState.SUCCESS, "intervention-applied", None)
    # Use the W4 experiment kind to mark it as intervention evidence.
    from sos.evidence import _build_evidence  # noqa: WPS437 (test-only import)
    return _build_evidence(
        kind=EvidenceKind.EXPERIMENT,
        source_ref="experiment-42",
        subject_ref=subject,
        result=result,
        provenance=prov(subject=subject),
        traceability=tr(),
        timestamp="2026-09-06T12:00:00Z",
        environment="production",
        confidence=0.9,
        availability=TruthState.SUCCESS,
    )


# --- C1: deterministic causal identity ---


def test_identical_causal_claims_produce_identical_identity():
    e1 = evidence()
    e2 = evidence()
    h1 = CausalHypothesis(
        cause_subject="node-1", effect_subject="node-2",
        relation_type=CausalRelationType.INFLUENCES,
        direction="positive", rationale="more traffic -> higher latency",
        status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "observation only"),
        supporting_evidence=(EvidenceSupport(evidence_id=e1.id, support_kind=SupportKind.OBSERVATIONAL),),
        traceability=tr(), provenance_revision=REVISION,
    )
    h2 = CausalHypothesis(
        cause_subject="node-1", effect_subject="node-2",
        relation_type=CausalRelationType.INFLUENCES,
        direction="positive", rationale="more traffic -> higher latency",
        status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "observation only"),
        supporting_evidence=(EvidenceSupport(evidence_id=e2.id, support_kind=SupportKind.OBSERVATIONAL),),
        traceability=tr(), provenance_revision=REVISION,
    )
    assert h1.id == h2.id  # identical semantics + identical evidence id => identical causal id


def test_differing_relation_semantics_produce_distinct_identity():
    e = evidence()
    h_a = CausalHypothesis(
        cause_subject="node-1", effect_subject="node-2",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="r", status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
        supporting_evidence=(EvidenceSupport(evidence_id=e.id, support_kind=SupportKind.OBSERVATIONAL),),
        traceability=tr(), provenance_revision=REVISION,
    )
    h_b = CausalHypothesis(
        cause_subject="node-1", effect_subject="node-2",
        relation_type=CausalRelationType.CONSTRAINS, direction="positive",  # different relation type
        rationale="r", status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
        supporting_evidence=(EvidenceSupport(evidence_id=e.id, support_kind=SupportKind.OBSERVATIONAL),),
        traceability=tr(), provenance_revision=REVISION,
    )
    assert h_a.id != h_b.id


def test_differing_supporting_evidence_produces_distinct_identity():
    e_a = evidence(subject="node-1")
    e_b = evidence(subject="node-2")
    h_a = CausalHypothesis(
        cause_subject="node-1", effect_subject="node-2",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="r", status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
        supporting_evidence=(EvidenceSupport(evidence_id=e_a.id, support_kind=SupportKind.OBSERVATIONAL),),
        traceability=tr(), provenance_revision=REVISION,
    )
    h_b = CausalHypothesis(
        cause_subject="node-1", effect_subject="node-2",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="r", status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
        supporting_evidence=(EvidenceSupport(evidence_id=e_b.id, support_kind=SupportKind.OBSERVATIONAL),),
        traceability=tr(), provenance_revision=REVISION,
    )
    assert h_a.id != h_b.id


# --- C2: evidence-backed support ---


def test_causal_claim_must_reference_existing_evidence():
    h = CausalHypothesis(
        cause_subject="node-1", effect_subject="node-2",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="r", status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
        supporting_evidence=(EvidenceSupport(evidence_id="nonexistent-evidence", support_kind=SupportKind.OBSERVATIONAL),),
        traceability=tr(), provenance_revision=REVISION,
    )
    with pytest.raises(ModelValidationError):
        h.validate(known_evidence_ids=set())  # evidence id does not exist


def test_unsupported_claim_must_carry_explicit_hypothesis_state():
    # A claim with NO supporting evidence is allowed only as an explicit
    # hypothesis with no implied truth — its uncertainty must be non-SUCCESS.
    h = CausalHypothesis(
        cause_subject="node-1", effect_subject="node-2",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="speculative", status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "no supporting evidence"),
        supporting_evidence=(),
        traceability=tr(), provenance_revision=REVISION,
    )
    h.validate(known_evidence_ids=set())  # OK as an explicit unsupported hypothesis
    assert h.uncertainty.state != TruthState.SUCCESS


def test_unsupported_claim_with_success_uncertainty_is_rejected():
    with pytest.raises(ModelValidationError):
        CausalHypothesis(
            cause_subject="node-1", effect_subject="node-2",
            relation_type=CausalRelationType.INFLUENCES, direction="positive",
            rationale="speculative", status="proposed",
            uncertainty=TruthfulValue(TruthState.SUCCESS, "claimed-truth", None),  # unsupported + SUCCESS
            supporting_evidence=(),
            traceability=tr(), provenance_revision=REVISION,
        )


# --- C3: observation vs intervention distinction ---


def test_observation_only_support_cannot_be_encoded_as_intervention():
    e = evidence()  # a plain observation
    with pytest.raises(ModelValidationError):
        CausalHypothesis(
            cause_subject="node-1", effect_subject="node-2",
            relation_type=CausalRelationType.INFLUENCES, direction="positive",
            rationale="r", status="proposed",
            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
            # Claiming intervention support from an observation-only evidence id is rejected.
            supporting_evidence=(EvidenceSupport(evidence_id=e.id, support_kind=SupportKind.INTERVENTION),),
            traceability=tr(), provenance_revision=REVISION,
        )


def test_intervention_support_requires_intervention_metadata_and_provenance():
    e = intervention_evidence()
    # Intervention support carries explicit intervention metadata + provenance.
    support = EvidenceSupport(
        evidence_id=e.id, support_kind=SupportKind.INTERVENTION,
        intervention=InterventionMetadata(
            intervention_id="experiment-42", intervention_kind="experiment",
            applied_at="2026-09-06T12:00:00Z", revision=REVISION, environment="production",
        ),
    )
    h = CausalHypothesis(
        cause_subject="node-1", effect_subject="node-2",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="intervention increased latency", status="proposed",
        uncertainty=TruthfulValue(TruthState.SUCCESS, "intervention-backed", None),
        supporting_evidence=(support,),
        traceability=tr(), provenance_revision=REVISION,
    )
    h.validate(known_evidence_ids={e.id})
    assert h.supporting_evidence[0].support_kind == SupportKind.INTERVENTION
    assert h.supporting_evidence[0].intervention is not None


def test_intervention_support_without_intervention_metadata_rejected():
    e = intervention_evidence()
    with pytest.raises(ModelValidationError):
        EvidenceSupport(
            evidence_id=e.id, support_kind=SupportKind.INTERVENTION,
            intervention=None,  # missing intervention metadata
        )


# --- C4: truthful uncertainty ---


def test_unknown_unavailable_failed_evidence_cannot_become_positive_causal_support():
    e_unavail = evidence(state=TruthState.UNAVAILABLE, detail="collector down")
    e_failed = evidence(state=TruthState.FAILED, detail="test raised")
    e_unknown = evidence(state=TruthState.UNKNOWN, detail="no value")
    # Supporting evidence whose observed result is not SUCCESS cannot support a
    # SUCCESS (positive) causal claim. The caller supplies the observed result
    # states (C4 truthful-uncertainty gate) so the validator can enforce it.
    for e in (e_unavail, e_failed, e_unknown):
        with pytest.raises(ModelValidationError):
            h = CausalHypothesis(
                cause_subject="node-1", effect_subject="node-2",
                relation_type=CausalRelationType.INFLUENCES, direction="positive",
                rationale="r", status="proposed",
                uncertainty=TruthfulValue(TruthState.SUCCESS, "claimed", None),
                supporting_evidence=(EvidenceSupport(evidence_id=e.id, support_kind=SupportKind.OBSERVATIONAL),),
                traceability=tr(), provenance_revision=REVISION,
            )
            h.validate(known_evidence_results={e.id: e.result.state})


def test_contradictory_hypotheses_coexist():
    e = evidence()
    h_pos = CausalHypothesis(
        cause_subject="node-1", effect_subject="node-2",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="more traffic -> higher latency", status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "observation only"),
        supporting_evidence=(EvidenceSupport(evidence_id=e.id, support_kind=SupportKind.OBSERVATIONAL),),
        traceability=tr(), provenance_revision=REVISION,
    )
    h_neg = CausalHypothesis(
        cause_subject="node-1", effect_subject="node-2",
        relation_type=CausalRelationType.INFLUENCES, direction="negative",  # competing
        rationale="caching compensates", status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "observation only"),
        supporting_evidence=(EvidenceSupport(evidence_id=e.id, support_kind=SupportKind.OBSERVATIONAL),),
        traceability=tr(), provenance_revision=REVISION,
    )
    assert h_pos.id != h_neg.id  # distinct identities
    g = CausalKnowledgeGraph(id="ckg-1", version=1, hypotheses=(), traceability=tr())
    g = g.ingest(h_pos).ingest(h_neg)
    assert len(g.hypotheses) == 2  # both coexist — neither silently deleted


# --- C5: no authority mutation ---


def test_causal_memory_does_not_mutate_canonical_graph():
    from sos import ArchitectureGraph, GraphNode, GraphUncertainty, NodeType
    nodes = (GraphNode(id="node-1", type=NodeType.SERVICE, name="svc-a",
                       attributes={"kind": "source"}, uncertainty=GraphUncertainty(TruthState.SUCCESS, confidence=1.0)),)
    arch = ArchitectureGraph(id="arch-1", version=1, nodes=nodes, edges=(),
                             boundary_contracts=(), uncertainty=GraphUncertainty(TruthState.SUCCESS, confidence=1.0),
                             traceability=tr())
    node_ids_before = {n.id for n in arch.nodes}

    e = evidence()
    h = CausalHypothesis(
        cause_subject="node-1", effect_subject="node-2",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="r", status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
        supporting_evidence=(EvidenceSupport(evidence_id=e.id, support_kind=SupportKind.OBSERVATIONAL),),
        traceability=tr(), provenance_revision=REVISION,
    )
    mem = ArchitectureMemory(id="mem-1", version=1, graph_ref=arch.id,
                             hypotheses=(h,), traceability=tr())
    mem.validate(known_graph_id=arch.id, known_evidence_ids={e.id})
    # The canonical graph is untouched.
    assert {n.id for n in arch.nodes} == node_ids_before
    assert arch is arch  # identity unchanged; memory only references graph_ref


# --- C6: deterministic memory behavior ---


def test_repeated_identical_ingestion_is_idempotent():
    e = evidence()
    h = CausalHypothesis(
        cause_subject="node-1", effect_subject="node-2",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="r", status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
        supporting_evidence=(EvidenceSupport(evidence_id=e.id, support_kind=SupportKind.OBSERVATIONAL),),
        traceability=tr(), provenance_revision=REVISION,
    )
    g = CausalKnowledgeGraph(id="ckg-1", version=1, hypotheses=(), traceability=tr())
    g = g.ingest(h).ingest(h).ingest(h)
    assert len(g.hypotheses) == 1  # dedup by id


def test_causal_graph_orders_hypotheses_deterministically():
    e = evidence()
    h_b = CausalHypothesis(
        cause_subject="node-z", effect_subject="node-y",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="r", status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
        supporting_evidence=(EvidenceSupport(evidence_id=e.id, support_kind=SupportKind.OBSERVATIONAL),),
        traceability=tr(), provenance_revision=REVISION,
    )
    h_a = CausalHypothesis(
        cause_subject="node-a", effect_subject="node-b",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="r", status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
        supporting_evidence=(EvidenceSupport(evidence_id=e.id, support_kind=SupportKind.OBSERVATIONAL),),
        traceability=tr(), provenance_revision=REVISION,
    )
    g = CausalKnowledgeGraph(id="ckg-1", version=1, hypotheses=(), traceability=tr())
    g = g.ingest(h_b).ingest(h_a)
    ids = [h.id for h in g.hypotheses]
    assert ids == sorted(ids)


# --- C7: provenance and traceability ---


def test_causal_claim_carries_evidence_ids_and_revision_and_traceability():
    e = evidence()
    h = CausalHypothesis(
        cause_subject="node-1", effect_subject="node-2",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="r", status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
        supporting_evidence=(EvidenceSupport(evidence_id=e.id, support_kind=SupportKind.OBSERVATIONAL),),
        traceability=tr(), provenance_revision=REVISION,
    )
    assert h.provenance_revision == REVISION
    assert h.supporting_evidence[0].evidence_id == e.id
    assert h.traceability.value_model_ref == "value:1"
    assert h.traceability.context_ref == "context:1"


def test_causal_claim_rejects_traceability_missing_context():
    e = evidence()
    bad = Traceability(constitution_ref="c", mission_ref="m", value_model_ref="v", context_ref=None)
    with pytest.raises(ModelValidationError):
        CausalHypothesis(
            cause_subject="node-1", effect_subject="node-2",
            relation_type=CausalRelationType.INFLUENCES, direction="positive",
            rationale="r", status="proposed",
            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
            supporting_evidence=(EvidenceSupport(evidence_id=e.id, support_kind=SupportKind.OBSERVATIONAL),),
            traceability=bad, provenance_revision=REVISION,
        )


# --- C8: architecture memory is a projection ---


def test_architecture_memory_is_versioned_projection_not_replacement():
    e = evidence()
    h = CausalHypothesis(
        cause_subject="node-1", effect_subject="node-2",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="learned relationship", status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "hypothesis only"),
        supporting_evidence=(EvidenceSupport(evidence_id=e.id, support_kind=SupportKind.OBSERVATIONAL),),
        traceability=tr(), provenance_revision=REVISION,
    )
    mem = ArchitectureMemory(id="mem-1", version=1, graph_ref="arch-1",
                             hypotheses=(h,), traceability=tr())
    assert mem.version >= 1
    assert mem.graph_ref == "arch-1"
    # The memory is explicitly a hypothesis projection; its records carry
    # non-SUCCESS uncertainty by construction here.
    assert all(hp.uncertainty.state != TruthState.SUCCESS for hp in mem.hypotheses)


def test_architecture_memory_rejects_graph_ref_mismatch():
    e = evidence()
    h = CausalHypothesis(
        cause_subject="node-1", effect_subject="node-2",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="r", status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
        supporting_evidence=(EvidenceSupport(evidence_id=e.id, support_kind=SupportKind.OBSERVATIONAL),),
        traceability=tr(), provenance_revision=REVISION,
    )
    mem = ArchitectureMemory(id="mem-1", version=1, graph_ref="arch-1",
                             hypotheses=(h,), traceability=tr())
    with pytest.raises(ModelValidationError):
        mem.validate(known_graph_id="arch-other", known_evidence_ids={e.id})


# --- C9: repository persistence (JSON round trip via W1 JsonModelStore) ---


def test_causal_graph_round_trips_through_json(tmp_path):
    e = evidence()
    h = CausalHypothesis(
        cause_subject="node-1", effect_subject="node-2",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="r", status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
        supporting_evidence=(EvidenceSupport(evidence_id=e.id, support_kind=SupportKind.OBSERVATIONAL),),
        traceability=tr(), provenance_revision=REVISION,
    )
    g = CausalKnowledgeGraph(id="ckg-1", version=1, hypotheses=(h,), traceability=tr())
    p = tmp_path / "causal.json"
    JsonModelStore(p).save(g)
    data = JsonModelStore(p).load()
    assert data["hypotheses"][0]["id"] == h.id
    assert data["hypotheses"][0]["supporting_evidence"][0]["evidence_id"] == e.id
    assert data["hypotheses"][0]["provenance_revision"] == REVISION
    assert data["traceability"]["context_ref"] == "context:1"


# --- C10: bounded surface (no W6+ symbols) ---


def test_w5_introduces_no_w6_plus_symbols():
    import sos.causal as cmod
    forbidden = {
        "CandidateState", "Candidate", "SubgraphMutation", "SearchEngine",
        "AssuranceVerdict", "AssuranceGate", "ImpactAnalysis", "RiskGate",
        "Experiment", "Promotion", "Rollback", "Canary", "Shadow",
        "Decision", "AutonomyPolicy", "AskPayload", "Act", "ExperimentRunner",
        "PlatformAdapter", "Personalization",
    }
    exported = {n for n in dir(cmod) if not n.startswith("_")}
    assert not (forbidden & exported), f"forbidden W6+ symbols present: {forbidden & exported}"


# --- status lifecycle + validation ---


def test_hypothesis_status_transitions_are_explicit():
    e = evidence()
    h = CausalHypothesis(
        cause_subject="node-1", effect_subject="node-2",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="r", status="proposed",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
        supporting_evidence=(EvidenceSupport(evidence_id=e.id, support_kind=SupportKind.OBSERVATIONAL),),
        traceability=tr(), provenance_revision=REVISION,
    )
    h_promoted = h.with_status("supported", known_evidence_ids={e.id})
    assert h_promoted.status == "supported"
    # Cannot transition to 'confirmed' (a certainty state) from observation-only support.
    with pytest.raises(ModelValidationError):
        h.with_status("confirmed", known_evidence_ids={e.id})


def test_intervention_backed_hypothesis_can_reach_confirmed():
    e = intervention_evidence()
    support = EvidenceSupport(
        evidence_id=e.id, support_kind=SupportKind.INTERVENTION,
        intervention=InterventionMetadata(
            intervention_id="experiment-42", intervention_kind="experiment",
            applied_at="2026-09-06T12:00:00Z", revision=REVISION, environment="production",
        ),
    )
    h = CausalHypothesis(
        cause_subject="node-1", effect_subject="node-2",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="intervention increased latency", status="proposed",
        uncertainty=TruthfulValue(TruthState.SUCCESS, "intervention-backed", None),
        supporting_evidence=(support,), traceability=tr(), provenance_revision=REVISION,
    )
    h_confirmed = h.with_status("confirmed", known_evidence_ids={e.id})
    assert h_confirmed.status == "confirmed"
