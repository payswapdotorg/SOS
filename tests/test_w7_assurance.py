import pytest

from sos import (
    ArchitectureGraph, AssuranceCheck, AssurancePolicy, AssuranceVerdict, BoundaryContract,
    CandidateMetrics, CheckKind, CheckState, EdgeType, EvidenceKind, EvidenceMode,
    EvidenceRecord, GraphEdge, GraphNode, GraphUncertainty, ImpactAssessment, ModelValidationError,
    NodeType, RiskAssessment, SearchBudget, SubgraphReplacement, Traceability, TruthState,
    TruthfulValue, generate_candidates, assure_candidate, export_assurance,
)


def trace(): return Traceability("constitution:1", "mission:1", "value:1", "context:1")

def graph():
    u = GraphUncertainty(TruthState.SUCCESS, confidence=1.0)
    nodes = (GraphNode("s", NodeType.SERVICE, "service", {}, u), GraphNode("i", NodeType.INTERFACE, "api", {}, u))
    return ArchitectureGraph("arch", 1, nodes, (GraphEdge("e", EdgeType.CALL, "s", "i", {}, u),), (BoundaryContract("bc", "i", "HTTP", ("stable",), u),), u, trace())

def candidate():
    return generate_candidates(
        graph=graph(), base_system_state_ref="state:1",
        replacements=(SubgraphReplacement("r", "arch", ("s",), ("new-service",), ("s",), ("preserve",), trace()),),
        metrics=(CandidateMetrics(.8,.2,.1,.1,.9,.1),), authority_required="assurance:required",
        predicted_effects=("latency improves",), risks=("cache invalidation",), traceability=trace(), budget=SearchBudget(1),
    ).candidates[0]

def evidence_record(state=TruthState.SUCCESS):
    return EvidenceRecord("test-evidence", EvidenceKind.TEST, EvidenceMode.OBSERVATIONAL, "ci", "state:1", "2026-09-05T15:00:00Z", "ci", TruthfulValue(state, value=True) if state == TruthState.SUCCESS else TruthfulValue(state, detail="not established"), {"source_revision":"rev-1", "observed_at":"2026-09-05T15:00:00Z"}, 1.0 if state == TruthState.SUCCESS else None, state, trace())

def policy(*required):
    return AssurancePolicy("policy", 1, required or (CheckKind.TEST,), .3, .3, .2, trace())

def good_check(kind=CheckKind.TEST):
    return AssuranceCheck("check-1", kind, CheckState.PASS, "verification", ("test-evidence",), "rev-1")

def impact(): return ImpactAssessment(.1, ("s",), .1, .1)
def risk(): return RiskAssessment(.1, ("safety",), True, .1)

def test_pass_requires_successfully_evidenced_required_check():
    result = assure_candidate(candidate=candidate(), graph=graph(), checks=(good_check(),), impact=impact(), risk=risk(), policy=policy(), evidence={"test-evidence": evidence_record()})
    assert result.verdict == AssuranceVerdict.PASS


def test_unknown_or_missing_required_evidence_blocks():
    result = assure_candidate(candidate=candidate(), graph=graph(), checks=(good_check(),), impact=impact(), risk=risk(), policy=policy(), evidence={"test-evidence": evidence_record(TruthState.UNKNOWN)})
    assert result.verdict == AssuranceVerdict.BLOCK


def test_risk_and_blast_radius_thresholds_block():
    result = assure_candidate(candidate=candidate(), graph=graph(), checks=(good_check(),), impact=ImpactAssessment(.9, ("s",), .9, .9), risk=RiskAssessment(.9, ("safety",), True, .9), policy=policy(), evidence={"test-evidence": evidence_record()})
    assert result.verdict == AssuranceVerdict.BLOCK
    assert len(result.reasons) == 3


def test_pass_check_without_evidence_is_not_pass():
    with pytest.raises(ModelValidationError):
        AssuranceCheck("check", CheckKind.TEST, CheckState.PASS, "missing evidence", (), "rev").validate()


def test_assurance_export_is_deterministic(tmp_path):
    result = assure_candidate(candidate=candidate(), graph=graph(), checks=(good_check(),), impact=impact(), risk=risk(), policy=policy(), evidence={"test-evidence": evidence_record()})
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    export_assurance(result, a); export_assurance(result, b)
    assert a.read_text() == b.read_text()
