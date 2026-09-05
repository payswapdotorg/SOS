import pytest

from sos import AuthorityAction, AuthorityGrant, DecisionRequest, EvidenceQuality, ModelValidationError, Traceability, evaluate


def trace():
    return Traceability("constitution:1", "mission:1", "value:1", "context:1")


def grant(**overrides):
    values = dict(
        id="grant-1", owner="owner-1", action=AuthorityAction.ACT, environment="prod",
        min_confidence=.8, max_risk=.2, max_impact=.2, max_blast_radius=.2, require_reversible=True,
        allow_gather_evidence=True, gather_min_confidence=.3, gather_max_risk=.4,
        gather_max_blast_radius=.4, require_human_approval=False,
        valid_from="2026-09-05T00:00:00Z", valid_until=None, traceability=trace(),
    )
    values.update(overrides)
    return AuthorityGrant(**values)


def request(action=AuthorityAction.ACT, confidence=.95, quality=EvidenceQuality.HIGH, risk=.1, impact=.1, reversible=True):
    return DecisionRequest(action, "prod", confidence, "calibrated", quality, risk, impact, reversible, .1, "req-1", trace())


def test_authorized_act_is_allowed_by_explicit_grant():
    decision = evaluate(request(), (grant(),))
    assert decision.outcome == AuthorityAction.ACT
    assert decision.grant_ref == "grant-1"
    assert decision.ask is None


def test_no_grant_becomes_ask():
    decision = evaluate(request(), ())
    assert decision.outcome == AuthorityAction.ASK
    assert decision.ask is not None


def test_risk_impact_or_blast_radius_exceeding_grant_becomes_ask():
    assert evaluate(request(risk=.9), (grant(),)).outcome == AuthorityAction.ASK
    assert evaluate(request(impact=.9), (grant(),)).outcome == AuthorityAction.ASK
    assert evaluate(request(), (grant(max_blast_radius=.05),)).outcome == AuthorityAction.ASK


def test_low_confidence_can_request_more_evidence_when_granted():
    decision = evaluate(request(confidence=.5, quality=EvidenceQuality.MEDIUM), (grant(),))
    assert decision.outcome == AuthorityAction.GATHER_EVIDENCE


def test_low_confidence_high_risk_cannot_bypass_to_gather():
    decision = evaluate(request(confidence=.5, quality=EvidenceQuality.LOW, risk=.5), (grant(),))
    assert decision.outcome == AuthorityAction.ASK


def test_human_approval_grant_always_asks():
    decision = evaluate(request(), (grant(require_human_approval=True),))
    assert decision.outcome == AuthorityAction.ASK


def test_grants_reject_invalid_thresholds():
    with pytest.raises(ModelValidationError):
        grant(max_risk=2).validate()
