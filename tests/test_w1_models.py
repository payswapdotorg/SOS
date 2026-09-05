from pathlib import Path

import pytest

from sos import *


def trace(value=None, context=None):
    return Traceability("constitution:1", "mission:1", value, context)


def test_mission_revision_requires_explicit_authority_approval():
    mission = Mission(
        id="mission-1", version=1, authority="owner-1", statement="Improve X",
        goals=("g1",), desired_outcomes=("o1",), stakeholders=("owner",),
        measures=("m1",), assumptions=(), ambiguities=("a1",), status=MissionStatus.ACTIVE,
        parent_version=None, history=(), traceability=trace(),
    )
    proposed = mission.propose_revision(statement="Improve Y", proposed_by="agent", reason="new evidence", created_at="2026-09-05T00:00:00Z")
    assert proposed.status == MissionStatus.PROPOSED_REVISION
    with pytest.raises(ModelValidationError):
        proposed.approve_revision(approver="not-owner")
    approved = proposed.approve_revision(approver="owner-1")
    assert approved.status == MissionStatus.ACTIVE
    assert approved.history[-1].status == RevisionStatus.APPROVED


def test_constraint_class_and_hard_flag_are_consistent():
    with pytest.raises(ModelValidationError):
        Constraint("c", "x", ConstraintClass.SOFT, "soft", True, trace("value:1")).validate()


def test_truthful_failure_unknown_unavailable_are_distinct_from_success_and_empty():
    empty = TruthfulValue(TruthState.EMPTY)
    empty.validate()
    success = TruthfulValue(TruthState.SUCCESS, value=[])
    success.validate()
    for state in (TruthState.FAILED, TruthState.UNKNOWN, TruthState.UNAVAILABLE, TruthState.UNSUPPORTED):
        value = TruthfulValue(state, detail="not available")
        value.validate()
    with pytest.raises(ModelValidationError):
        TruthfulValue(TruthState.UNKNOWN, value="guessed").validate()


def test_context_supports_platform_and_environment_with_truthful_states():
    context = Context(
        id="ctx-1", version=1,
        values=(
            ContextValue(ContextDimension.PLATFORM, "platform", TruthfulValue(TruthState.SUCCESS, "web")),
            ContextValue(ContextDimension.ENVIRONMENT, "region", TruthfulValue(TruthState.UNAVAILABLE, detail="runtime unavailable")),
        ),
        traceability=trace("value:1", "context:1"),
    )
    context.validate()


def test_policy_turns_unauthorized_action_into_ask():
    policy = AutonomyPolicy(
        id="policy-1", version=1,
        rules=(AutonomyRule(DecisionAction.ACT, "prod", 0.9, 0.1, True, 0.2, False),),
        traceability=trace("value:1", "context:1"),
    )
    ask = AskPayload("Deploy change", ("deploy", "do not deploy"), "high", "medium", ("risk vs benefit",))
    decision = decide(
        requested_action=DecisionAction.ACT, environment="prod", confidence=0.8,
        calibration="validated", risk=0.05, reversible=True, blast_radius=0.1,
        policy=policy, authority_ref="authority:1", mission_ref="mission:1",
        value_model_ref="value:1", context_ref="context:1", ask=ask,
    )
    assert decision.action == DecisionAction.ASK
    assert decision.ask == ask


def test_policy_allows_authorized_action():
    policy = AutonomyPolicy(
        id="policy-1", version=1,
        rules=(AutonomyRule(DecisionAction.ACT, "prod", 0.9, 0.1, True, 0.2, False),),
        traceability=trace(),
    )
    decision = decide(
        requested_action=DecisionAction.ACT, environment="prod", confidence=0.95,
        calibration="validated", risk=0.05, reversible=True, blast_radius=0.1,
        policy=policy, authority_ref="authority:1", mission_ref="mission:1",
    )
    assert decision.action == DecisionAction.ACT


def test_ask_payload_is_complete_and_round_trips_through_json(tmp_path: Path):
    artifact = AskPayload(
        exact_decision="Choose deployment strategy",
        alternatives=("canary", "rollback"),
        evidence_quality="mixed: tests strong, runtime evidence unavailable",
        uncertainty="deployment impact uncertain",
        trade_offs=("speed vs risk",),
    )
    artifact.validate()
    path = tmp_path / "ask.json"
    store = JsonModelStore(path)
    store.save(artifact)
    assert store.load()["exact_decision"] == artifact.exact_decision


def test_value_model_traceability_and_business_constraints():
    value = ValueModel(
        id="value-1", version=1, business_model={"revenue": "subscription"},
        economic_objectives=(Objective("o", "sustainable margin", 1, trace("value-1")),),
        budgets={"monthly": 1000},
        incentives=(Incentive("i", "reduce churn", trace("value-1")),),
        opportunities=(Opportunity("op", "new market", trace("value-1")),),
        constraints=(Constraint("c", "privacy", ConstraintClass.HARD, "No unapproved data use", True, trace("value-1")),),
        traceability=trace("value-1"),
    )
    value.validate()
