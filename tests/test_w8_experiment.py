import pytest

from sos import (
    AssuranceResult, AssuranceVerdict, CheckKind, CheckState, AssuranceCheck,
    Experiment, ExperimentDesign, ExperimentStage, GuardrailTrigger, ImpactAssessment,
    ModelValidationError, PromotionDecision, RiskAssessment, Traceability, advance,
    promotion_from_assurance, rollback,
)


def trace():
    return Traceability("constitution:1", "mission:1", "value:1", "context:1")


def design():
    return ExperimentDesign("cohort-a", "web/prod", "10%", ("success-rate",), ("error-rate",))


def experiment():
    return Experiment.propose(
        identifier="exp-1", candidate_ref="candidate-1", base_system_state_ref="state-1",
        design=design(), traceability=trace(), transition_revision="rev-1",
    )


def assurance(verdict=AssuranceVerdict.PASS):
    return AssuranceResult(
        candidate_ref="candidate-1", base_system_state_ref="state-1", checks=(),
        impact=ImpactAssessment(.1, ("node",), .1, .1),
        risk=RiskAssessment(.1, ("safety",), True, .1), verdict=verdict,
        reasons=() if verdict == AssuranceVerdict.PASS else ("blocked",), traceability=trace(),
    )


def test_lifecycle_requires_sequential_steps_and_assurance():
    exp = experiment()
    with pytest.raises(ModelValidationError):
        advance(exp, target=ExperimentStage.SHADOW, transition_revision="rev-2")
    analyzed = advance(exp, target=ExperimentStage.ANALYZED, transition_revision="rev-2")
    with pytest.raises(ModelValidationError):
        advance(analyzed, target=ExperimentStage.ASSURED, transition_revision="rev-3", assurance=assurance(AssuranceVerdict.BLOCK))
    assured = advance(analyzed, target=ExperimentStage.ASSURED, transition_revision="rev-3", assurance=assurance())
    tested = advance(assured, target=ExperimentStage.TESTED, transition_revision="rev-4")
    simulated = advance(tested, target=ExperimentStage.SIMULATED, transition_revision="rev-5")
    shadow = advance(simulated, target=ExperimentStage.SHADOW, transition_revision="rev-6")
    assert shadow.current_stage == ExperimentStage.SHADOW


def test_promotion_requires_explicit_authority_and_assurance():
    exp = experiment()
    for target, rev in (
        (ExperimentStage.ANALYZED, "2"), (ExperimentStage.ASSURED, "3"),
        (ExperimentStage.TESTED, "4"), (ExperimentStage.REPLAYED, "5"),
        (ExperimentStage.SHADOW, "6"), (ExperimentStage.CANARY, "7"),
        (ExperimentStage.EXPERIMENTAL, "8"),
    ):
        exp = advance(exp, target=target, transition_revision=rev, assurance=assurance() if target == ExperimentStage.ASSURED else None)
    with pytest.raises(ModelValidationError):
        advance(exp, target=ExperimentStage.PROMOTED, transition_revision="9")
    promotion = promotion_from_assurance(assurance(), authority_ref="owner-1", authority_evidence_ref="auth-e1", decision_revision="9")
    promoted = advance(exp, target=ExperimentStage.PROMOTED, transition_revision="9", promotion=promotion)
    assert promoted.current_stage == ExperimentStage.PROMOTED
    assert promoted.promotion == promotion


def test_guardrail_can_record_rollback_from_live_stage():
    exp = experiment()
    for target, rev in ((ExperimentStage.ANALYZED, "2"), (ExperimentStage.ASSURED, "3"), (ExperimentStage.TESTED, "4"), (ExperimentStage.SIMULATED, "5"), (ExperimentStage.SHADOW, "6")):
        exp = advance(exp, target=target, transition_revision=rev, assurance=assurance() if target == ExperimentStage.ASSURED else None)
    trigger = GuardrailTrigger("g1", "error-rate", "> 5%", "7%", "e-rollback")
    rolled = rollback(exp, trigger=trigger, recovery_target_ref="state-1", transition_revision="rev-7")
    assert rolled.current_stage == ExperimentStage.ROLLBACK
    assert rolled.rollback is not None
    assert rolled.rollback.trigger.evidence_ref == "e-rollback"


def test_rollback_is_rejected_before_live_stage():
    with pytest.raises(ModelValidationError):
        rollback(experiment(), trigger=GuardrailTrigger("g", "x", ">", "1", "e"), recovery_target_ref="state", transition_revision="r")
