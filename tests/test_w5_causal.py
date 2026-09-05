import pytest

from sos import (
    ArchitectureMemoryStore,
    CausalHypothesis,
    EvidenceKind,
    EvidenceMode,
    EvidenceRecord,
    HypothesisStatus,
    ModelValidationError,
    Traceability,
    TruthState,
    TruthfulValue,
    record_memory,
)


def trace():
    return Traceability("constitution:1", "mission:1", "value:1", "context:1")


def evidence(identifier: str, mode: EvidenceMode):
    return EvidenceRecord(
        id=identifier, kind=EvidenceKind.TEST, mode=mode, source_ref="test", subject_ref="state:1",
        timestamp="2026-09-05T15:00:00Z", environment="ci",
        result=TruthfulValue(TruthState.SUCCESS, value=True),
        provenance={"source_revision": "rev-1", "observed_at": "2026-09-05T15:00:00Z"},
        confidence=0.9, availability=TruthState.SUCCESS, traceability=trace(),
    )


def hypothesis(refs=("e1",)):
    return CausalHypothesis(
        id="h1", cause="cache enabled", mechanism="fewer repeated lookups", effect="lower latency",
        context="production web", expected_direction="decrease", expected_magnitude="10%",
        confidence=0.7, evidence_refs=refs, status=HypothesisStatus.PROPOSED, traceability=trace(),
    )


def memory(identifier="m1"):
    return record_memory(
        identifier=identifier, context_signature="web/prod", candidate_pattern="cache", predictions=("latency down",),
        observations=("latency down",), outcome="positive", learned_rule="cache for repeated reads",
        source_revision="rev-1", recorded_at="2026-09-05T15:00:00Z", confidence=0.8, traceability=trace(),
    )


def test_high_impact_causal_use_requires_intervention_evidence():
    obs = evidence("e1", EvidenceMode.OBSERVATIONAL)
    assert not hypothesis().eligible_for_high_impact({"e1": obs})
    inter = evidence("e2", EvidenceMode.INTERVENTION)
    assert hypothesis(("e2",)).eligible_for_high_impact({"e2": inter})


def test_causal_hypothesis_requires_evidence_reference():
    with pytest.raises(ModelValidationError):
        hypothesis(refs=()).validate()


def test_memory_is_append_only_and_deduplicated(tmp_path):
    store = ArchitectureMemoryStore()
    item = memory()
    store.append(item)
    with pytest.raises(ModelValidationError):
        store.append(item)
    store.export_json(tmp_path / "memory.json")


def test_memory_export_is_deterministic(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    for path in (first, second):
        store = ArchitectureMemoryStore()
        store.append(memory("m2"))
        store.append(memory("m1"))
        store.export_json(path)
    assert first.read_text() == second.read_text()
