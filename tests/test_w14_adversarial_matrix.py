"""W14 — the adversarial verification program (the sixteen mandated cases).

Work Order: ``spec/work-orders/W14-dogfood-adversarial-verification.md``
(the operator-mandated adversarial case catalog; Required outcomes 2, 4, 5,
6; acceptance criteria C2, C3, C4, C7). Design §3 (the binding case table).

Every case re-runs (a slice of) the composed chain with exactly one injected
fault — a pure data mutation of the fixture inputs; the merged validation
paths are exactly what runs (no mocks, no monkey-patching of ``src/sos/``).
Each test asserts the precise TYPED governed outcome — construction
rejection in the W1 ``ModelValidationError`` family, ASK pause with an
explicit pending-authorization record, no-run truthful receipt, monotonic
narrowing, boundary refusal/containment, or governed rollback — never a
bare "did not crash", never silent success. FAILED / UNKNOWN / UNAVAILABLE /
UNSUPPORTED remain pairwise distinct in every case (R21).

The persisted matrix ``spec/development-state/W14-adversarial-evidence-
matrix.json`` is mechanically reconciled with this module by
``test_w14_adversarial_matrix_file_is_valid_and_reconciled``.
"""

from __future__ import annotations

import dataclasses
import json
import re
import sys
from pathlib import Path

import pytest

import w14_fixtures as w14
from sos import (
    AdapterCapability,
    AssuranceStatus,
    AutonomyDecision,
    AutonomyDecisionState,
    ContextDimension,
    DecisionAction,
    EvidenceKind,
    Experiment,
    ExperimentEvaluation,
    ExperimentMode,
    ExperimentState,
    ExecutionActionScope,
    ExecutionContractError,
    ExecutionLifecycleState,
    ExecutionReceipt,
    ModelValidationError,
    PlatformAdapter,
    PlatformSurface,
    PolicyCeiling,
    PromotionDecision,
    PromotionGate,
    RollbackPath,
    SourceChange,
    SourceChangeKind,
    TruthState,
    TruthfulValue,
    assure_candidate,
    constrain_policy,
    evaluate_autonomy,
    evaluate_experiment,
    evaluate_personalization,
    governed_experiment,
    narrow_decision_state,
    receipt_to_w4_evidence,
    recover_repository,
    run_optimization_loop,
    transition_self_evolution,
)
from sos.optimization import (
    AuthorizationResolution,
    IterationOutcome,
    LoopPromotion,
    LoopStopReason,
    OptimizationContractError,
    PromotionClass,
)
from sos.platform import PlatformPolicyConstraint
from sos.personalization import ContextualPolicy, ContextualSelector
from sos.selfevolution import (
    MAX_META_DEPTH,
    SelfEvolutionContractError,
    SelfEvolutionProposal,
    SelfEvolutionState,
    SelfImprovementHypothesis,
)

# ---------------------------------------------------------------------------
# Shared local helpers
# ---------------------------------------------------------------------------


def loop_with(harness, candidates, **overrides):
    """Run the W12 loop over the harness recovery with one injected change."""
    fields = dict(
        recovery=harness.recovery,
        candidates=list(candidates),
        policy=harness.policy,
        simulator=w14.StubSimulator(),
        traceability=w14.tr(),
        max_iterations=3,
        stop_conditions=w14.STOP_CONDITIONS,
        evidence_graph=harness.evidence_graph,
        causal_graph=harness.causal_graph,
        rollback_ref=w14.ROLLBACK_REF_BROWN,
        rollback_evidence_ids=(harness.rollback_ev.id,),
    )
    fields.update(overrides)
    return run_optimization_loop(**fields)


def candidate_citing(harness, evidence_ids, *, target=None, revision=None):
    return w14.make_candidate(
        base_graph_id=harness.graph.id,
        revision=revision or w14.BROWN_REVISION,
        target_node_id=target or harness.node_ids["svc_notifications.py"],
        replacement_node_id=harness.node_ids["svc_reports.py"],
        boundary_node_id=harness.node_ids["store_ledger.py"],
        reasoning_evidence_ids=tuple(evidence_ids),
        reasoning_hypothesis_ids=(harness.confirmed_hyp.id,),
        objectives=w14.objectives_profile(120.0, 300.0, 2500.0),
        rationale="adversarial candidate",
    )


def substrate_with(provider, harness, *decisions):
    return w14.ExecutionSubstrate(
        providers={provider.provider_id: provider},
        known_decisions={d.id: d for d in decisions},
        known_assurance={harness.assurance.id: harness.assurance},
        known_experiments={harness.experiment.id: harness.experiment},
    )


# ---------------------------------------------------------------------------
# ADV-01 — missing evidence
# ---------------------------------------------------------------------------


def test_adv_01_missing_evidence(tmp_path):
    """A consequential step citing an absent/unresolvable evidence id is
    rejected at construction (W1 ModelValidationError family) and routed to
    an explicit gather outcome at W9 — never a silent proceed."""
    harness = w14.brownfield_harness(tmp_path / "repo")
    missing_id = "evidence-does-not-exist"
    forged = candidate_citing(harness, (missing_id,))

    # W7 boundary: construction rejection — the candidate cannot be assured
    with pytest.raises(ModelValidationError, match="unknown evidence id"):
        assure_candidate(
            candidate=forged, base_graph=harness.graph,
            known_evidence=dict(harness.known_evidence),
            known_hypotheses=dict(harness.known_hypotheses),
            rollback_evidence_ids=(harness.rollback_ev.id,),
        )

    # W12 boundary: the loop refuses before any governed record exists
    with pytest.raises(ModelValidationError, match="unknown evidence id"):
        loop_with(harness, (forged,))

    # W9 boundary: an ACT attempt whose cited evidence is absent from the
    # store routes to GATHER_EVIDENCE — the missing id is recorded verbatim
    green = w14.greenfield_harness()
    decision = evaluate_autonomy(
        policy=green.policy, action=DecisionAction.ACT,
        assurance=green.assurance, experiment=green.experiment,
        promotion=green.gate_decision, evaluation=green.evaluation,
        evidence_ids=tuple(green.evaluation.evidence_ids),
        traceability=w14.tr(),
        known_evidence={},  # the cited evidence record is absent (missing)
        blast_radius="limited", risk=0.1, confidence=0.9, reversible=True,
    )
    assert decision.state is AutonomyDecisionState.GATHER_EVIDENCE
    assert any(
        eid in r and "not found" in r for eid in green.evaluation.evidence_ids
        for r in decision.reasons
    )
    assert decision.state is not AutonomyDecisionState.ACT


# ---------------------------------------------------------------------------
# ADV-02 — FAILED evidence
# ---------------------------------------------------------------------------


def test_adv_02_failed_evidence(tmp_path):
    """FAILED evidence propagates as FAILED end-to-end: the W7 gate blocks
    (FAIL), the loop records ASSURANCE_NOT_PASSED with the distinct status
    preserved verbatim, W9 refuses ACT, and W10-style narrowing fires on the
    non-SUCCESS context state. No collapse to SUCCESS/EMPTY anywhere."""
    harness = w14.brownfield_harness(tmp_path / "repo")
    failed_ev = w14.stateful_evidence(
        harness.graph.id, w14.BROWN_REVISION, TruthState.FAILED,
        "observed degradation under load",
    )
    harness.evidence_graph = harness.evidence_graph.ingest(failed_ev)
    harness.known_evidence[failed_ev.id] = failed_ev
    candidate = candidate_citing(harness, (failed_ev.id,))

    # W7: the evidence gate maps FAILED to FAIL (blocking, distinct)
    assurance = assure_candidate(
        candidate=candidate, base_graph=harness.graph,
        known_evidence=dict(harness.known_evidence),
        known_hypotheses=dict(harness.known_hypotheses),
        rollback_evidence_ids=(harness.rollback_ev.id,),
    )
    assert assurance.status is AssuranceStatus.FAIL
    evidence_gate = next(g for g in assurance.gates if g.name == "evidence-availability")
    assert evidence_gate.status is AssuranceStatus.FAIL

    # the loop records the governed refusal with the status preserved
    run = loop_with(harness, (candidate,))
    iteration = run.loop.iterations[0]
    assert iteration.outcome is IterationOutcome.ASSURANCE_NOT_PASSED
    assert iteration.assurance_status is AssuranceStatus.FAIL
    assert iteration.experiment_id is None
    refusal_evidence = next(
        r for r in run.evidence_graph.records if r.id == iteration.evidence_ids[-1]
    )
    assert refusal_evidence.result.state is TruthState.FAILED  # verbatim

    # W9: FAILED evidence cannot authorize ACT — an optimistic evaluation
    # citing FAILED evidence is refused at the evidence gate
    green = w14.greenfield_harness()
    failed_green = w14.stateful_evidence(
        green.graph.id, w14.GREEN_REVISION, TruthState.FAILED,
        "observed degradation under load",
    )
    known_green = dict(green.known_evidence)
    known_green[failed_green.id] = failed_green
    optimistic_evaluation = ExperimentEvaluation(
        id="", experiment_id=green.experiment.id,
        assurance_result_id=green.assurance.id,
        candidate_id=green.experiment.candidate_id,
        base_graph_id=green.assurance.base_graph_id,
        base_graph_revision=green.assurance.base_graph_revision,
        provenance_revision=green.assurance.provenance_revision,
        evidence_ids=(failed_green.id,),
        evidence_results={failed_green.id: TruthState.FAILED},
        objectives=(), promotion_eligible=True, stopped=False,
        detail="optimistic evaluation over FAILED evidence",
        traceability=w14.tr(),
    )
    optimistic_promotion = PromotionDecision(
        promoted=True, rationale="forged gate decision over FAILED evidence",
        experiment_id=green.experiment.id,
        evaluation_id=optimistic_evaluation.id,
    )
    decision = evaluate_autonomy(
        policy=green.policy, action=DecisionAction.ACT,
        assurance=green.assurance, experiment=green.experiment,
        promotion=optimistic_promotion, evaluation=optimistic_evaluation,
        evidence_ids=(failed_green.id,), traceability=w14.tr(),
        known_evidence=known_green,
        blast_radius="limited", risk=0.1, confidence=0.9, reversible=True,
    )
    assert decision.state is AutonomyDecisionState.GATHER_EVIDENCE
    assert any(failed_green.id in r and "FAILED" in r for r in decision.reasons)

    # W10: a FAILED context value narrows the decision (A2: no non-SUCCESS
    # state is collapsed into success)
    selector = ContextualSelector(
        id="w14-adv-sel-2", version=1,
        dimensions=(w14.context_value_state(
            ContextDimension.DEVICE, "class", TruthState.FAILED,
            "device class observation failed",
        ),),
        traceability=w14.tr(),
    )
    personalization = evaluate_personalization(
        policy=green.policy, selector=selector,
        w9_decision_state=AutonomyDecisionState.ACT,
        w9_decision_id=decision.id,
        traceability=w14.tr(),
    )
    assert personalization.state == "ASK"

    # the evidence record itself never collapsed
    assert failed_ev.result.state is TruthState.FAILED
    assert failed_ev.availability is TruthState.SUCCESS  # capture succeeded


# ---------------------------------------------------------------------------
# ADV-03 — UNKNOWN evidence
# ---------------------------------------------------------------------------


def test_adv_03_unknown_evidence(tmp_path):
    """UNKNOWN evidence cannot authorize ACT: W9 routes to GATHER_EVIDENCE
    with the state recorded verbatim; the W7 gate is UNKNOWN (distinct from
    FAIL); the loop records ASSURANCE_NOT_PASSED with the UNKNOWN status
    preserved."""
    harness = w14.brownfield_harness(tmp_path / "repo")
    unknown_ev = w14.stateful_evidence(
        harness.graph.id, w14.BROWN_REVISION, TruthState.UNKNOWN,
        "observation not yet resolved",
    )
    harness.evidence_graph = harness.evidence_graph.ingest(unknown_ev)
    harness.known_evidence[unknown_ev.id] = unknown_ev
    candidate = candidate_citing(harness, (unknown_ev.id,))

    assurance = assure_candidate(
        candidate=candidate, base_graph=harness.graph,
        known_evidence=dict(harness.known_evidence),
        known_hypotheses=dict(harness.known_hypotheses),
        rollback_evidence_ids=(harness.rollback_ev.id,),
    )
    assert assurance.status is AssuranceStatus.UNKNOWN  # distinct from FAIL
    evidence_gate = next(g for g in assurance.gates if g.name == "evidence-availability")
    assert evidence_gate.status is AssuranceStatus.UNKNOWN

    run = loop_with(harness, (candidate,))
    iteration = run.loop.iterations[0]
    assert iteration.outcome is IterationOutcome.ASSURANCE_NOT_PASSED
    assert iteration.assurance_status is AssuranceStatus.UNKNOWN
    refusal_evidence = next(
        r for r in run.evidence_graph.records if r.id == iteration.evidence_ids[-1]
    )
    assert refusal_evidence.result.state is TruthState.UNKNOWN  # verbatim

    # W9: UNKNOWN evidence cannot authorize ACT — an optimistic evaluation
    # citing UNKNOWN evidence is refused at the evidence gate
    green = w14.greenfield_harness()
    unknown_green = w14.stateful_evidence(
        green.graph.id, w14.GREEN_REVISION, TruthState.UNKNOWN,
        "observation not yet resolved",
    )
    known_green = dict(green.known_evidence)
    known_green[unknown_green.id] = unknown_green
    optimistic_evaluation = ExperimentEvaluation(
        id="", experiment_id=green.experiment.id,
        assurance_result_id=green.assurance.id,
        candidate_id=green.experiment.candidate_id,
        base_graph_id=green.assurance.base_graph_id,
        base_graph_revision=green.assurance.base_graph_revision,
        provenance_revision=green.assurance.provenance_revision,
        evidence_ids=(unknown_green.id,),
        evidence_results={unknown_green.id: TruthState.UNKNOWN},
        objectives=(), promotion_eligible=True, stopped=False,
        detail="optimistic evaluation over UNKNOWN evidence",
        traceability=w14.tr(),
    )
    optimistic_promotion = PromotionDecision(
        promoted=True, rationale="forged gate decision over UNKNOWN evidence",
        experiment_id=green.experiment.id,
        evaluation_id=optimistic_evaluation.id,
    )
    decision = evaluate_autonomy(
        policy=green.policy, action=DecisionAction.ACT,
        assurance=green.assurance, experiment=green.experiment,
        promotion=optimistic_promotion, evaluation=optimistic_evaluation,
        evidence_ids=(unknown_green.id,), traceability=w14.tr(),
        known_evidence=known_green,
        blast_radius="limited", risk=0.1, confidence=0.9, reversible=True,
    )
    assert decision.state is AutonomyDecisionState.GATHER_EVIDENCE
    assert any(unknown_green.id in r and "UNKNOWN" in r for r in decision.reasons)
    assert unknown_ev.result.state is TruthState.UNKNOWN


# ---------------------------------------------------------------------------
# ADV-04 — UNAVAILABLE provider
# ---------------------------------------------------------------------------


def test_adv_04_unavailable_provider(tmp_path):
    """An unknown provider id, or a provider raising its unavailability
    signal, yields a no-run UNAVAILABLE receipt — distinct from FAILED and
    UNSUPPORTED — and the W4 conversion preserves the distinction."""
    harness = w14.greenfield_harness()
    act = w14.act_decision_for(harness)

    # (a) unknown provider id: no-run UNAVAILABLE receipt
    request = w14.execution_request_for(
        act, harness, scope=ExecutionActionScope.DEPLOY,
        provider_id="w14-no-such-provider",
    )
    receipt = substrate_with(w14.CountingExecutionProvider(), harness, act).submit(
        request
    )
    assert receipt.lifecycle is ExecutionLifecycleState.UNAVAILABLE
    assert receipt.outcome.state is TruthState.UNAVAILABLE
    assert receipt.started_at is None and receipt.finished_at is None
    assert receipt.side_effects == () and receipt.changed_revisions == ()

    # (b) a registered provider raising its unavailability signal
    unavailable = w14.UnavailableProvider()
    request_b = w14.execution_request_for(
        act, harness, scope=ExecutionActionScope.DEPLOY,
        provider_id=unavailable.provider_id,
    )
    receipt_b = substrate_with(unavailable, harness, act).submit(request_b)
    assert receipt_b.lifecycle is ExecutionLifecycleState.UNAVAILABLE
    assert receipt_b.outcome.state is TruthState.UNAVAILABLE
    assert unavailable.execute_calls == 1  # engaged, then signaled unavailability

    # pairwise distinct: the FAILED and UNSUPPORTED counterparts
    failed_provider = w14.CountingExecutionProvider(deploy_outcome=TruthState.FAILED)
    failed_receipt = substrate_with(failed_provider, harness, act).submit(
        w14.execution_request_for(
            act, harness, scope=ExecutionActionScope.DEPLOY,
            provider_id=failed_provider.provider_id,
        )
    )
    unsupported_provider = w14.NoDeployCapabilityProvider()
    unsupported_receipt = substrate_with(unsupported_provider, harness, act).submit(
        w14.execution_request_for(
            act, harness, scope=ExecutionActionScope.DEPLOY,
            provider_id=unsupported_provider.provider_id,
        )
    )
    assert failed_receipt.lifecycle is ExecutionLifecycleState.FAILED
    assert failed_receipt.outcome.state is TruthState.FAILED
    assert unsupported_receipt.lifecycle is ExecutionLifecycleState.UNSUPPORTED
    assert unsupported_receipt.outcome.state is TruthState.UNSUPPORTED
    # all three non-success execution truth states are present and pairwise
    # distinct (UNAVAILABLE appears twice — from both injection paths)
    assert {
        receipt.outcome.state, receipt_b.outcome.state,
        failed_receipt.outcome.state, unsupported_receipt.outcome.state,
    } == {TruthState.UNAVAILABLE, TruthState.FAILED, TruthState.UNSUPPORTED}

    # the W4 conversion keeps availability distinct from the observed result:
    # an UNAVAILABLE execution never renders as success downstream
    unavailable_evidence = receipt_to_w4_evidence(receipt, traceability=w14.tr())
    assert unavailable_evidence.result.state is TruthState.UNAVAILABLE
    assert unavailable_evidence.availability is TruthState.SUCCESS
    failed_evidence = receipt_to_w4_evidence(failed_receipt, traceability=w14.tr())
    assert failed_evidence.result.state is TruthState.FAILED
    assert unavailable_evidence.id != failed_evidence.id


# ---------------------------------------------------------------------------
# ADV-05 — UNSUPPORTED capability
# ---------------------------------------------------------------------------


def test_adv_05_unsupported_capability(tmp_path):
    """A fully-authorized DEPLOY request beyond the provider's capability set
    yields a truthful no-run UNSUPPORTED receipt — not a rejection of the
    request's validity, and distinct from UNAVAILABLE."""
    harness = w14.greenfield_harness()
    act = w14.act_decision_for(harness)
    provider = w14.NoDeployCapabilityProvider()

    request = w14.execution_request_for(
        act, harness, scope=ExecutionActionScope.DEPLOY,
        provider_id=provider.provider_id,
    )
    receipt = substrate_with(provider, harness, act).submit(
        request
    )  # no ExecutionContractError: a truthful outcome, not a rejection

    assert receipt.lifecycle is ExecutionLifecycleState.UNSUPPORTED
    assert receipt.outcome.state is TruthState.UNSUPPORTED
    assert "lacks capability" in (receipt.outcome.detail or "")
    assert receipt.started_at is None and receipt.side_effects == ()
    assert receipt.changed_revisions == ()
    assert provider.execute_calls == 0  # never reached the provider
    # the request itself remains valid — its references all resolved
    request.validate()


# ---------------------------------------------------------------------------
# ADV-06 — forged authority references
# ---------------------------------------------------------------------------


def test_adv_06_forged_authority_references(tmp_path):
    """Decision/assurance/experiment ids that do not resolve are rejected
    pre-dispatch with zero provider engagement; a forged reference never
    satisfies any gate; the W12 chain-check rejects dangling records."""
    harness = w14.greenfield_harness()
    act = w14.act_decision_for(harness)
    provider = w14.CountingExecutionProvider()

    # (a) forged W9 decision id on the request
    forged_request = w14.execution_request_for(
        act, harness, scope=ExecutionActionScope.DEPLOY,
        provider_id=provider.provider_id, w9_decision_id="autonomy-forged-0000",
    )
    with pytest.raises(ExecutionContractError, match="unresolved W9 authorization"):
        substrate_with(provider, harness, act).submit(forged_request)
    assert provider.execute_calls == 0

    # (b) a decision CLAIMING a forged W7 assurance reference: the claim
    # passes the echo gate, and the registry lookup refuses it
    forged_assurance_decision = AutonomyDecision(
        id="", state=AutonomyDecisionState.ACT, action=DecisionAction.ACT,
        rationale="forged authority reference", reasons=("forged",),
        evidence_ids=(), assurance_id="assurance-forged-0000",
        experiment_id=harness.experiment.id,
        promotion_id=f"{harness.experiment.id}:{harness.evaluation.id}",
        policy_id="policy-forged", traceability=w14.tr(),
    )
    forged_w7 = w14.execution_request_for(
        forged_assurance_decision, harness, scope=ExecutionActionScope.DEPLOY,
        provider_id=provider.provider_id,
    )
    with pytest.raises(ExecutionContractError, match="unresolved W7 assurance"):
        substrate_with(provider, harness, forged_assurance_decision).submit(forged_w7)
    assert provider.execute_calls == 0

    # (c) a decision CLAIMING a forged W8 experiment reference
    forged_experiment_decision = AutonomyDecision(
        id="", state=AutonomyDecisionState.ACT, action=DecisionAction.ACT,
        rationale="forged authority reference", reasons=("forged",),
        evidence_ids=(), assurance_id=harness.assurance.id,
        experiment_id="experiment-forged-0000",
        promotion_id="experiment-forged-0000:eval-forged",
        policy_id="policy-forged", traceability=w14.tr(),
    )
    forged_w8 = w14.execution_request_for(
        forged_experiment_decision, harness, scope=ExecutionActionScope.DEPLOY,
        provider_id=provider.provider_id,
    )
    with pytest.raises(ExecutionContractError, match="unresolved W8 experiment"):
        substrate_with(provider, harness, forged_experiment_decision).submit(forged_w8)
    assert provider.execute_calls == 0

    # (d) the W12 chain-check: a loop record citing an unknown decision is
    # refused at validation (the forged reference never satisfies the gate)
    brown = w14.brownfield_harness(tmp_path / "repo")
    run = loop_with(brown, (brown.selected_candidate,))
    forged_run = dataclasses.replace(
        run,
        loop=dataclasses.replace(
            run.loop,
            iterations=tuple(
                dataclasses.replace(it, decision_ids=("autonomy-forged-0000",))
                if it.outcome is IterationOutcome.PROMOTED else it
                for it in run.loop.iterations
            ),
        ),
    )
    with pytest.raises(OptimizationContractError, match="unresolved W9 decision"):
        forged_run.validate()


# ---------------------------------------------------------------------------
# ADV-07 — mismatched revisions
# ---------------------------------------------------------------------------


def test_adv_07_mismatched_revisions(tmp_path):
    """An assurance/experiment/request pinned to a different revision than
    the candidate chain is rejected at construction or submit; provenance
    echo mismatches are refused; no cross-revision grafting."""
    harness = w14.greenfield_harness()
    assurance = harness.assurance

    # (a) W8 chain-check: an experiment citing a mismatched graph revision
    mismatched_experiment = Experiment(
        id="", candidate_id=harness.selected_candidate.id,
        assurance_result_id=assurance.id,
        base_graph_id=assurance.base_graph_id,
        base_graph_revision=w14.STALE_REVISION,  # grafted from another revision
        provenance_revision=assurance.provenance_revision,
        mode=ExperimentMode.SHADOW, scope=(harness.selected_candidate.id,),
        observation_window=("2030-08-01T00:00:00Z", "2030-08-02T00:00:00Z"),
        success_criteria=("objectives-not-dominated",),
        stop_conditions=w14.STOP_CONDITIONS, rollback_ref=w14.ROLLBACK_REF_GREEN,
        traceability=w14.tr(),
    )
    with pytest.raises(ModelValidationError, match="does not match assurance result's revision"):
        mismatched_experiment.validate(known_assurance=assurance)

    # (b) W11 submit boundary: the request's provenance does not match the
    # W7/W8 chain
    act = w14.act_decision_for(harness)
    provider = w14.CountingExecutionProvider()
    stale_request = w14.execution_request_for(
        act, harness, scope=ExecutionActionScope.DEPLOY,
        provider_id=provider.provider_id,
        provenance_revision=w14.STALE_REVISION,
    )
    with pytest.raises(
        ExecutionContractError, match="graph/revision/provenance chain",
    ):
        substrate_with(provider, harness, act).submit(stale_request)
    assert provider.execute_calls == 0

    # (c) W12 governed-experiment gate: a candidate carrying the assured id
    # but a stale revision is refused (no cross-revision grafting)
    stale_candidate = w14.make_candidate(
        base_graph_id=harness.graph.id, revision=w14.STALE_REVISION,
        target_node_id=harness.node_ids["greeter"],
        replacement_node_id=harness.node_ids["greeter_v2"],
        boundary_node_id=harness.node_ids["gateway"],
        reasoning_evidence_ids=(harness.prior_canary.id,),
        reasoning_hypothesis_ids=(harness.confirmed_hyp.id,),
        objectives=w14.objectives_profile(90.0, 350.0, 2800.0),
        rationale="stale-revision graft of the assured candidate",
        candidate_id=harness.selected_candidate.id,
    )
    with pytest.raises(
        OptimizationContractError, match="base graph revision does not match",
    ):
        governed_experiment(
            assurance=assurance, candidate=stale_candidate,
            rollback_ref=w14.ROLLBACK_REF_GREEN, traceability=w14.tr(),
            stop_conditions=w14.STOP_CONDITIONS,
        )


# ---------------------------------------------------------------------------
# ADV-08 — mismatched candidates
# ---------------------------------------------------------------------------


def test_adv_08_mismatched_candidates(tmp_path):
    """An experiment/evaluation/assurance bound to a different candidate id
    than the one proposed is rejected — the chain-check never equates
    distinct candidates, and W9 REJECTs the mismatched chain."""
    harness = w14.greenfield_harness()
    assurance = harness.assurance

    # (a) W8: experiment candidate_id != assurance candidate_id
    other_candidate = w14.make_candidate(
        base_graph_id=harness.graph.id, revision=w14.GREEN_REVISION,
        target_node_id=harness.node_ids["greeter"],
        replacement_node_id=harness.node_ids["greeter_v2"],
        boundary_node_id=harness.node_ids["gateway"],
        reasoning_evidence_ids=(harness.prior_canary.id,),
        reasoning_hypothesis_ids=(harness.confirmed_hyp.id,),
        objectives=w14.objectives_profile(150.0, 250.0, 2600.0),
        rationale="the other candidate",
    )
    mismatched_experiment = Experiment(
        id="", candidate_id=other_candidate.id,
        assurance_result_id=assurance.id,
        base_graph_id=assurance.base_graph_id,
        base_graph_revision=assurance.base_graph_revision,
        provenance_revision=assurance.provenance_revision,
        mode=ExperimentMode.SHADOW, scope=(other_candidate.id,),
        observation_window=("2030-08-01T00:00:00Z", "2030-08-02T00:00:00Z"),
        success_criteria=("objectives-not-dominated",),
        stop_conditions=w14.STOP_CONDITIONS, rollback_ref=w14.ROLLBACK_REF_GREEN,
        traceability=w14.tr(), state=ExperimentState.COMPLETED,
    )
    with pytest.raises(ModelValidationError, match="does not match assurance result's candidate"):
        mismatched_experiment.validate(known_assurance=assurance)

    # (b) the W8 PromotionGate: evaluation candidate mismatch
    mismatched_evaluation = ExperimentEvaluation(
        id="", experiment_id=harness.experiment.id,
        assurance_result_id=assurance.id,
        candidate_id=other_candidate.id,  # not the experiment's candidate
        base_graph_id=assurance.base_graph_id,
        base_graph_revision=assurance.base_graph_revision,
        provenance_revision=assurance.provenance_revision,
        evidence_ids=(harness.experiment_evidence.id,),
        evidence_results={harness.experiment_evidence.id: TruthState.SUCCESS},
        objectives=(), promotion_eligible=True, stopped=False,
        detail="forged evaluation over a different candidate",
        traceability=w14.tr(),
    )
    with pytest.raises(ModelValidationError, match="evaluation.candidate_id .* does not match experiment's"):
        PromotionGate().evaluate(
            harness.experiment, mismatched_evaluation, known_assurance=assurance,
        )

    # (c) W9: the experiment/assurance candidate mismatch is REJECTed — an
    # evaluation bound to the mismatched experiment passes the earlier chain
    # checks, and the experiment/assurance candidate mismatch is caught
    bound_evaluation = ExperimentEvaluation(
        id="", experiment_id=mismatched_experiment.id,
        assurance_result_id=assurance.id,
        candidate_id=mismatched_experiment.candidate_id,
        base_graph_id=assurance.base_graph_id,
        base_graph_revision=assurance.base_graph_revision,
        provenance_revision=assurance.provenance_revision,
        evidence_ids=(harness.experiment_evidence.id,),
        evidence_results={harness.experiment_evidence.id: TruthState.SUCCESS},
        objectives=(), promotion_eligible=True, stopped=False,
        detail="evaluation bound to the mismatched experiment",
        traceability=w14.tr(),
    )
    forged_promotion = PromotionDecision(
        promoted=True, rationale="forged gate decision",
        experiment_id=mismatched_experiment.id,
        evaluation_id=bound_evaluation.id,
    )
    decision = evaluate_autonomy(
        policy=harness.policy, action=DecisionAction.ACT,
        assurance=assurance, experiment=mismatched_experiment,
        promotion=forged_promotion, evaluation=bound_evaluation,
        evidence_ids=(harness.experiment_evidence.id,),
        traceability=w14.tr(),
        known_evidence=dict(harness.known_evidence),
        blast_radius="limited", risk=0.1, confidence=0.9, reversible=True,
    )
    assert decision.state is AutonomyDecisionState.REJECT
    assert any(
        "does not match assurance.candidate_id" in r for r in decision.reasons
    )


# ---------------------------------------------------------------------------
# ADV-09 — platform widening attempts
# ---------------------------------------------------------------------------


def test_adv_09_platform_widening_attempts(tmp_path):
    """A platform/personalization constraint that widens allowed_actions or
    relaxes ceilings is deterministically rejected at construction; the
    monotonic narrowing invariant holds; the widened policy never exists."""
    harness = w14.greenfield_harness()
    policy = harness.policy
    empty_selector = ContextualSelector(
        id="w14-adv-cp-sel", version=1, dimensions=(), traceability=w14.tr(),
    )
    base_ceilings = dict(
        max_risk=0.3, max_blast_radius="service", require_reversible=True,
        min_confidence=0.8, require_human_approval_for_act=False,
    )

    # widening allowed_actions (W10 ContextualPolicy)
    with pytest.raises(ModelValidationError, match="cannot expand allowed_actions"):
        ContextualPolicy(
            id="w14-adv-cp-1", version=1, source_policy=policy,
            selector=empty_selector,
            narrowed_allowed_actions=(
                DecisionAction.ACT, DecisionAction.ROLLBACK, DecisionAction.EXPERIMENT,
                DecisionAction.GATHER_EVIDENCE, DecisionAction.ASK,
            ),
            narrowed_ceilings=PolicyCeiling(**base_ceilings),
            traceability=w14.tr(),
        )

    # relaxing each ceiling in turn (ContextualPolicy)
    relaxations = (
        ("max_risk", 0.5),
        ("max_blast_radius", "system"),
        ("require_reversible", False),
        ("min_confidence", 0.5),
    )
    for field, relaxed in relaxations:
        ceilings = dict(base_ceilings)
        ceilings[field] = relaxed
        with pytest.raises(ModelValidationError, match=r"cannot (relax|widen|lower)"):
            ContextualPolicy(
                id="w14-adv-cp-2", version=1, source_policy=policy,
                selector=empty_selector,
                narrowed_allowed_actions=(DecisionAction.ACT,),
                narrowed_ceilings=PolicyCeiling(**ceilings),
                traceability=w14.tr(),
            )

    # the same widening attempts through the typed platform constraint
    adapter = PlatformAdapter(
        id="w14-adv-adapter-1", version=1, surface=PlatformSurface.WEB,
        capabilities=(AdapterCapability(name="execute-deploy", supported=True),),
        traceability=w14.tr(),
    )
    with pytest.raises(ModelValidationError, match="cannot expand allowed_actions"):
        constrain_policy(
            adapter, source_policy=policy,
            narrowed_allowed_actions=(DecisionAction.ACT, DecisionAction.ASK),
            narrowed_ceilings=PolicyCeiling(**base_ceilings),
            constraint_id="w14-adv-pc-1",
        )
    ceilings = dict(base_ceilings)
    ceilings["max_risk"] = 0.9
    with pytest.raises(ModelValidationError, match="cannot relax max_risk"):
        constrain_policy(
            adapter, source_policy=policy,
            narrowed_allowed_actions=(DecisionAction.ACT,),
            narrowed_ceilings=PolicyCeiling(**ceilings),
            constraint_id="w14-adv-pc-2",
        )

    # the monotonic narrowing primitive never widens
    assert narrow_decision_state(
        AutonomyDecisionState.ACT, AutonomyDecisionState.ASK
    ) is AutonomyDecisionState.ASK
    assert narrow_decision_state(
        AutonomyDecisionState.REJECT, AutonomyDecisionState.ASK
    ) is AutonomyDecisionState.REJECT  # inherited REJECT survives
    assert narrow_decision_state(
        AutonomyDecisionState.ASK, AutonomyDecisionState.ACT
    ) is AutonomyDecisionState.ASK  # widening refused


# ---------------------------------------------------------------------------
# ADV-10 — provider self-authorization
# ---------------------------------------------------------------------------


def test_adv_10_provider_self_authorization(tmp_path):
    """An execution request whose authorizer is the provider itself, or one
    lacking the W9 decision reference, is unconstructible or rejected before
    any provider call — the provider is never the authorizer (R22)."""
    harness = w14.greenfield_harness()
    provider = w14.CountingExecutionProvider()

    # (a) a request without a W9 reference cannot even be constructed
    act = w14.act_decision_for(harness)
    with pytest.raises(ExecutionContractError, match="w9_decision_id is required"):
        w14.execution_request_for(
            act, harness, scope=ExecutionActionScope.DEPLOY,
            provider_id=provider.provider_id, w9_decision_id="",
        )

    # (b) a decision issued under a provider-owned policy is rejected before
    # any provider call
    self_authorizing = w14.self_authorizing_act_decision_for(
        harness, provider.provider_id,
    )
    assert self_authorizing.state is AutonomyDecisionState.ACT  # otherwise valid
    request = w14.execution_request_for(
        self_authorizing, harness, scope=ExecutionActionScope.DEPLOY,
        provider_id=provider.provider_id,
    )
    with pytest.raises(ExecutionContractError, match="cannot authorize its own execution"):
        substrate_with(provider, harness, self_authorizing).submit(request)
    assert provider.execute_calls == 0


# ---------------------------------------------------------------------------
# ADV-11 — ASK bypass attempts
# ---------------------------------------------------------------------------


def test_adv_11_ask_bypass_attempts(tmp_path):
    """Promotion/execution attempted under an ASK or unresolved decision: the
    substrate refuses (zero engagement); the loop pauses with an explicit
    pending-authorization record; the W13 pause can only be left by a NEW
    resolved ACT decision; nothing auto-approves."""
    harness = w14.greenfield_harness()
    provider = w14.CountingExecutionProvider()

    # (a) W11: an ASK decision authorizes no scope
    ask = w14.ask_decision_for(harness)
    assert ask.state is AutonomyDecisionState.ASK
    request = w14.execution_request_for(
        ask, harness, scope=ExecutionActionScope.DEPLOY,
        provider_id=provider.provider_id,
    )
    with pytest.raises(ExecutionContractError, match="does not authorize scope deploy"):
        substrate_with(provider, harness, ask).submit(request)
    assert provider.execute_calls == 0

    # (b) W12: the loop under a human-approval policy pauses with the
    # explicit pending-authorization record (never a silent default)
    brown = w14.brownfield_harness(tmp_path / "repo")
    paused_run = loop_with(
        brown, (brown.selected_candidate,),
        policy=w14.autonomy_policy(human_approval_for_act=True),
    )
    assert paused_run.loop.stop.reason is LoopStopReason.PAUSED_FOR_AUTHORIZATION
    paused_iteration = paused_run.loop.iterations[0]
    assert paused_iteration.outcome is IterationOutcome.PAUSED_PENDING_AUTHORIZATION
    pending = paused_iteration.pending_authorization
    assert pending is not None
    assert pending.resolution is AuthorizationResolution.PENDING
    assert pending.decision_state is AutonomyDecisionState.ASK
    assert paused_iteration.promotion is None
    # PENDING is the only resolution member: no auto-approve path exists
    assert [s.name for s in AuthorizationResolution] == ["PENDING"]
    granters = {"approve", "grant", "resolve", "authorize", "with_resolution"}
    assert not granters & {
        n for n in dir(pending) if not n.startswith("_")
        and callable(getattr(pending, n))
    }

    # (c) W13: leaving PAUSED_ASKING requires a NEW resolved ACT decision —
    # the SAME ASK decision cannot resume the pause (no auto-approve)
    selfevo = w14.run_self_evolution_stage(
        brown.graph, w14.BROWN_REVISION,
        trigger_evidence=brown.intervention,
        rollback_evidence=brown.rollback_ev,
        hypothesis=brown.confirmed_hyp,
        target_node_id=brown.node_ids["svc_notifications.py"],
        replacement_node_id=brown.node_ids["svc_reports.py"],
        boundary_node_id=brown.node_ids["store_ledger.py"],
        policy=brown.policy,
    )
    selfevo_ev = w14.selfevo_experiment_evidence(brown.graph, w14.BROWN_REVISION)
    known = dict(brown.known_evidence)
    known[selfevo_ev.id] = selfevo_ev
    # a real W9 ASK decision bound to the self-evolution chain
    bound_ask = evaluate_autonomy(
        policy=w14.autonomy_policy(human_approval_for_act=True),
        action=DecisionAction.ACT, assurance=selfevo.assurance,
        experiment=selfevo.experiment, promotion=selfevo.gate_decision,
        evaluation=selfevo.evaluation,
        evidence_ids=tuple(selfevo.evaluation.evidence_ids),
        traceability=w14.tr(), known_evidence=known,
        human_authority_present=False,
        blast_radius="limited", risk=0.1, confidence=0.9, reversible=True,
    )
    assert bound_ask.state is AutonomyDecisionState.ASK
    registries = dict(
        known_assurance={selfevo.assurance.id: selfevo.assurance},
        known_experiments={selfevo.experiment.id: selfevo.experiment},
        known_evaluations={selfevo.evaluation.id: selfevo.evaluation},
        known_promotions={
            f"{selfevo.experiment.id}:{selfevo.evaluation.id}": selfevo.gate_decision
        },
        known_decisions={bound_ask.id: bound_ask},
        known_evidence=known,
        known_proposals={},
        known_hypotheses=dict(brown.known_hypotheses),
        known_candidates={selfevo.citation_candidate.id: selfevo.citation_candidate},
    )
    r = transition_self_evolution(
        selfevo.proposal, SelfEvolutionState.UNDER_ASSURANCE, **registries,
        timestamp=w14.TS,
    )
    r = transition_self_evolution(
        r.proposal, SelfEvolutionState.UNDER_EXPERIMENT, **registries,
        assurance_result_id=selfevo.assurance.id, timestamp=w14.TS,
    )
    r = transition_self_evolution(
        r.proposal, SelfEvolutionState.UNDER_AUTHORITY, **registries,
        experiment_id=selfevo.experiment.id,
        evaluation_id=selfevo.evaluation.id,
        promotion_id=f"{selfevo.experiment.id}:{selfevo.evaluation.id}",
        rollback_path=selfevo.rollback_path, timestamp=w14.TS,
    )
    paused = transition_self_evolution(
        r.proposal, SelfEvolutionState.PAUSED_ASKING, **registries,
        autonomy_decision_id=bound_ask.id, timestamp=w14.TS,
    )
    assert paused.proposal.state is SelfEvolutionState.PAUSED_ASKING
    # resuming with the SAME ASK decision is refused (no auto-approve)
    with pytest.raises(SelfEvolutionContractError, match="NEW resolved W9 ACT decision"):
        transition_self_evolution(
            paused.proposal, SelfEvolutionState.UNDER_AUTHORITY, **registries,
            autonomy_decision_id=bound_ask.id, timestamp=w14.TS,
        )


# ---------------------------------------------------------------------------
# ADV-12 — rollback bypass attempts
# ---------------------------------------------------------------------------


def test_adv_12_rollback_bypass_attempts(tmp_path):
    """DEPLOY-class promotion without a bounded rollback path, and ROLLED_BACK
    without a governed rollback reference, are unconstructible or rejected;
    a W9 ROLLBACK without a governed path routes to ASK (architecture §13.10)."""
    harness = w14.greenfield_harness()
    act = w14.act_decision_for(harness)

    # (a) a DEPLOY request without a governed rollback reference is
    # unconstructible at the type level
    with pytest.raises(ExecutionContractError, match="requires a governed rollback reference"):
        w14.execution_request_for(
            act, harness, scope=ExecutionActionScope.DEPLOY,
            provider_id=w14.PROVIDER_DEPLOY, rollback_reference=None,
        )

    # (b) a DEPLOY-class loop promotion without a bounded rollback path is
    # unconstructible
    with pytest.raises(OptimizationContractError, match="requires a bounded W8 RollbackPath"):
        LoopPromotion(
            candidate_id="candidate-x", assurance_id="assurance-x",
            experiment_id="experiment-x", evaluation_id="eval-x",
            decision_id="autonomy-x", promotion_ref="experiment-x:eval-x",
            promotion_class=PromotionClass.DEPLOY,
            experiment_rollback_ref=w14.ROLLBACK_REF_GREEN,
            rollback=None, receipt_id="exec-receipt-x",
        )

    # (c) a ROLLED_BACK receipt without a governed rollback reference (with
    # recovery evidence) is unconstructible
    with pytest.raises(ExecutionContractError, match="requires the governed rollback reference"):
        ExecutionReceipt(
            request_id="exec-request-x", provider_id=w14.PROVIDER_DEPLOY,
            action_scope=ExecutionActionScope.ROLLBACK,
            lifecycle=ExecutionLifecycleState.ROLLED_BACK,
            outcome=TruthfulValue(TruthState.SUCCESS, "rolled-back", None),
            w9_decision_id="autonomy-x",
            source_revision=w14.GREEN_REVISION,
            provenance_revision=w14.GREEN_REVISION,
            base_graph_id=harness.graph.id,
            base_graph_revision=w14.GREEN_REVISION,
            environment="greenfield-stub",
            started_at=w14.TS_DEPLOY_START, finished_at=w14.TS_DEPLOY_END,
        )

    # (d) a W9 ROLLBACK action without a governed rollback path routes to ASK
    decision = evaluate_autonomy(
        policy=harness.policy, action=DecisionAction.ROLLBACK,
        assurance=harness.assurance, experiment=harness.experiment,
        promotion=None, evaluation=harness.evaluation,
        evidence_ids=tuple(harness.evaluation.evidence_ids),
        traceability=w14.tr(), known_evidence=dict(harness.known_evidence),
        blast_radius="limited", risk=0.1, confidence=0.9, reversible=True,
        rollback_path=None,
    )
    assert decision.state is AutonomyDecisionState.ASK
    assert any("without governed rollback path" in r for r in decision.reasons)


# ---------------------------------------------------------------------------
# ADV-13 — self-evolution boundary violations
# ---------------------------------------------------------------------------


def test_adv_13_self_evolution_boundary_violations(tmp_path):
    """Self-evolution attempts against frozen authority surfaces, DELETE
    attacks on authority modules, and recursion overflow are refused at
    construction; the violation is recorded as evidence and never applied;
    lawful proposals still pass the same gates."""
    revision = w14.BROWN_REVISION

    # (a) frozen authority artifacts may never be targeted
    frozen_targets = (
        "spec/constitution.md",
        "spec/architecture.md",
        "spec/architecture-lock.md",
        "spec/implementation-roadmap.md",
        "spec/requirements.md",
        "spec/work-orders/W1-mission-value-context-model.md",
    )
    for path in frozen_targets:
        with pytest.raises(SelfEvolutionContractError, match="frozen authority"):
            SourceChange(
                path=path, base_revision=revision,
                kind=SourceChangeKind.MODIFY, payload=w14.SELF_EVO_PAYLOAD,
            )

    # (b) DELETE-class changes on authority-implementation modules are refused
    authority_modules = (
        "src/sos/model.py", "src/sos/assurance.py", "src/sos/autonomy.py",
        "src/sos/selfevolution.py",
    )
    for path in authority_modules:
        with pytest.raises(SelfEvolutionContractError, match="cannot be DELETEd"):
            SourceChange(
                path=path, base_revision=revision,
                kind=SourceChangeKind.DELETE, payload="",
            )

    # (c) the recursion bound is fixed
    with pytest.raises(SelfEvolutionContractError, match="meta_depth"):
        SelfEvolutionProposal(
            target_revision=revision, target_paths=("docs/some-notes.md",),
            changes=(SourceChange(
                path="docs/some-notes.md", base_revision=revision,
                kind=SourceChangeKind.MODIFY, payload="notes",
            ),),
            hypothesis=SelfImprovementHypothesis(
                rationale="overflow attempt", trigger_evidence_ids=("evidence-x",),
                predicted_effects=("e",),
                uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted"),
            ),
            origin=w14.ProposalOrigin.MODEL_GENERATED,
            rollback_ref="rb-x", meta_depth=MAX_META_DEPTH + 1,
            traceability=w14.tr(),
        )

    # (d) the violation is recorded as evidence, never applied: the scenario's
    # refusal record is a verbatim FAILED W4 observation and no proposal
    # record for the frozen target exists; the lawful MODIFY on an authority
    # module still passes the same gates (the gate is selective, not blanket)
    scenario = w14.run_brownfield_scenario(tmp_path / "repo")
    refusal = scenario.selfevo.refusal_error
    assert isinstance(refusal, SelfEvolutionContractError)
    refusal_evidence = scenario.selfevo.refusal_evidence
    refusal_evidence.validate()
    assert refusal_evidence.result.state is TruthState.FAILED
    assert "spec/constitution.md" in refusal_evidence.result.detail
    assert scenario.selfevo.promoted.target_paths == ("src/sos/optimization.py",)
    assert scenario.selfevo.promoted.state is SelfEvolutionState.PROMOTED


# ---------------------------------------------------------------------------
# ADV-14 — non-deterministic outputs (the meta-case)
# ---------------------------------------------------------------------------


def test_adv_14_non_deterministic_outputs(tmp_path):
    """Identical scenario inputs run twice produce byte-identical records
    (identical content-addressed ids and identical canonical serializations).
    This assertion IS the meta-check: the suite fails if the merged stack is
    ever non-deterministic under identical inputs."""
    brown_a = w14.run_brownfield_scenario(tmp_path / "repo-one")
    brown_b = w14.run_brownfield_scenario(tmp_path / "repo-two")
    assert w14.scenario_bundle(brown_a) == w14.scenario_bundle(brown_b)
    assert brown_a.run.loop.id == brown_b.run.loop.id

    green_a = w14.run_greenfield_scenario(tmp_path / "green-one")
    green_b = w14.run_greenfield_scenario(tmp_path / "green-two")
    assert w14.scenario_bundle(green_a) == w14.scenario_bundle(green_b)


# ---------------------------------------------------------------------------
# ADV-15 — stale-state recovery
# ---------------------------------------------------------------------------


def test_adv_15_stale_state_recovery(tmp_path):
    """A chain continuing from a recovered system whose revision is stale
    relative to the cited evidence/assurance is rejected or typed: the loop
    refuses cross-revision candidates; stale SUCCESS evidence becomes typed
    UNKNOWN and cannot make an evaluation promotion-eligible; the recovery
    keeps its uncertainty at both revisions."""
    # (a) the W12 loop refuses a candidate pinned to a stale revision
    brown = w14.brownfield_harness(tmp_path / "repo")
    stale_candidate = candidate_citing(
        brown, (brown.intervention.id,), revision=w14.STALE_REVISION,
    )
    with pytest.raises(OptimizationContractError, match="not bound to the recovered revision"):
        loop_with(brown, (stale_candidate,))

    # (b) stale SUCCESS evidence (a different revision) is not silently
    # reused: it becomes typed UNKNOWN and blocks promotion eligibility
    harness = w14.greenfield_harness()
    stale_success = w14.intervention_evidence(harness.graph.id, w14.STALE_REVISION)
    known = dict(harness.known_evidence)
    known[stale_success.id] = stale_success
    evaluation = evaluate_experiment(
        harness.experiment, known_evidence=known,
        evidence_refs=(stale_success.id,), evaluation_success=True,
        known_assurance=harness.assurance, rollback_path=harness.rollback_path,
    )
    assert evaluation.evidence_results[stale_success.id] is TruthState.UNKNOWN
    assert evaluation.promotion_eligible is False
    assert "provenance-mismatched" in evaluation.detail

    # (c) the recovered system at two revisions is two distinct states, and
    # the uncertainty is preserved at both
    recovery_fresh = recover_repository(
        root=tmp_path / "repo", revision=w14.BROWN_REVISION, traceability=w14.tr(),
    )
    recovery_stale = recover_repository(
        root=tmp_path / "repo", revision=w14.STALE_REVISION, traceability=w14.tr(),
    )
    assert recovery_fresh.system_state.architecture.id != (
        recovery_stale.system_state.architecture.id
    )
    for recovery in (recovery_fresh, recovery_stale):
        assert recovery.system_state.deployment_ref.ref.state is TruthState.UNAVAILABLE
        assert any(
            f.truth.state is TruthState.UNAVAILABLE for f in recovery.unresolved_facts
        )


# ---------------------------------------------------------------------------
# ADV-16 — partial-failure recovery
# ---------------------------------------------------------------------------


def test_adv_16_partial_failure_recovery(tmp_path):
    """Mid-lifecycle failure (a provider that fails after start; an
    experiment that fails mid-way) ends in explicitly typed recovered /
    rolled-back states with the failure recorded verbatim in W4 evidence and
    governed rollback; no partial record is rendered as success."""
    # (a) the brownfield loop with a provider that fails after start
    scenario = w14.run_brownfield_scenario(
        tmp_path / "repo", deploy_outcome=TruthState.FAILED,
    )
    run = scenario.run
    rolled_back = next(
        it for it in run.loop.iterations
        if it.outcome is IterationOutcome.ROLLED_BACK
    )
    assert rolled_back.decision_state is AutonomyDecisionState.ROLLBACK
    assert rolled_back.promotion is None  # no partial record as success
    assert len(run.receipts) == 1
    failed_receipt = run.receipts[0]
    assert failed_receipt.lifecycle is ExecutionLifecycleState.FAILED
    assert failed_receipt.outcome.state is TruthState.FAILED
    assert failed_receipt.started_at == w14.TS_DEPLOY_START  # it ran, then failed
    assert failed_receipt.rollback_reference is not None
    # the failure is preserved verbatim as W4 deployment evidence
    failed_evidence = next(
        r for r in run.evidence_graph.records
        if r.kind is EvidenceKind.DEPLOYMENT
        and r.result.state is TruthState.FAILED
    )
    assert failed_evidence.result.state is TruthState.FAILED
    # governed rollback evidence is present and SUCCESS
    rollback_evidence = [
        r for r in run.evidence_graph.records
        if r.kind is EvidenceKind.ROLLBACK and r.result.state is TruthState.SUCCESS
    ]
    assert rollback_evidence
    # the experiment lifecycle itself reached the typed ROLLED_BACK state
    rolled_experiment = next(
        e for e in run.experiments if e.id == rolled_back.experiment_id
    )
    assert rolled_experiment.state is ExperimentState.ROLLED_BACK
    assert scenario.provider.execute_calls == 1  # engaged once, then recovered

    # (b) the greenfield seam: the failed deploy recovers through a governed
    # W11 ROLLBACK dispatch to a typed ROLLED_BACK receipt
    green = w14.run_greenfield_scenario(tmp_path / "green")
    assert green.deploy_receipt.lifecycle is ExecutionLifecycleState.FAILED
    assert green.rollback_receipt.lifecycle is ExecutionLifecycleState.ROLLED_BACK
    assert green.rollback_receipt.outcome.state is TruthState.SUCCESS
    assert green.rollback_receipt.rollback_reference.evidence_ids == (
        green.harness.rollback_ev.id,
    )
    assert green.experiment.state is ExperimentState.ROLLED_BACK
    # the W12 convergence loop also ended in a governed rollback
    seed_iteration = green.seed_run.loop.iterations[0]
    assert seed_iteration.outcome is IterationOutcome.ROLLED_BACK
    assert seed_iteration.promotion is None


# ---------------------------------------------------------------------------
# Required-coverage support assertions (Work Order "Required regression
# coverage": dangling-reference rejection + zero provider engagement)
# ---------------------------------------------------------------------------


def test_w14_dangling_reference_rejection(tmp_path):
    """Every authority rejects a dangling reference at its own boundary:
    W5 hypotheses, W6 candidates, W8 rollback paths, W13 proposals."""
    harness = w14.brownfield_harness(tmp_path / "repo")
    dangling = "evidence-dangling-0000"

    # W5: a hypothesis citing an unknown evidence id
    with pytest.raises(ModelValidationError, match="unknown evidence id"):
        w14.observation_hypothesis(
            w14.otel_span_evidence(harness.graph.id, w14.BROWN_REVISION),
            w14.BROWN_REVISION,
        ).validate(known_evidence_ids=set())

    # W6: a candidate citing an unknown hypothesis id
    with pytest.raises(ModelValidationError, match="unknown hypothesis id"):
        candidate_citing(harness, (harness.intervention.id,)).validate(
            known_graph=harness.graph,
            known_evidence_ids=set(harness.known_evidence),
            known_hypothesis_ids=set(),  # nothing resolves
        )

    # W8: a rollback path citing unknown recovery evidence
    with pytest.raises(ModelValidationError, match="unknown evidence id"):
        RollbackPath(
            reference=w14.ROLLBACK_REF_BROWN, evidence_ids=(dangling,),
            detail="dangling recovery evidence",
        ).validate(known_evidence=dict(harness.known_evidence))

    # W13: a proposal citing trigger evidence absent from the registry
    proposal = SelfEvolutionProposal(
        target_revision=w14.BROWN_REVISION,
        target_paths=("src/sos/optimization.py",),
        changes=(SourceChange(
            path="src/sos/optimization.py", base_revision=w14.BROWN_REVISION,
            kind=SourceChangeKind.MODIFY, payload=w14.SELF_EVO_PAYLOAD,
        ),),
        hypothesis=SelfImprovementHypothesis(
            rationale="dangling citation", trigger_evidence_ids=(dangling,),
            predicted_effects=("e",),
            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted"),
        ),
        origin=w14.ProposalOrigin.MODEL_GENERATED,
        rollback_ref=w14.SELF_EVO_ROLLBACK_REF, meta_depth=0,
        traceability=w14.tr(),
    )
    with pytest.raises(SelfEvolutionContractError, match="not present"):
        proposal.validate(known_evidence=dict(harness.known_evidence))


def test_w14_zero_provider_engagement_on_pre_gate_rejection(tmp_path):
    """Every pre-gate rejection (forged references, ASK decisions, provider
    self-authorization, mismatched experiment bindings) leaves the provider
    untouched."""
    harness = w14.greenfield_harness()
    provider = w14.CountingExecutionProvider()
    act = w14.act_decision_for(harness)
    ask = w14.ask_decision_for(harness)
    self_auth = w14.self_authorizing_act_decision_for(
        harness, provider.provider_id,
    )

    rejections = (
        # forged W9 reference
        (w14.execution_request_for(
            act, harness, scope=ExecutionActionScope.DEPLOY,
            provider_id=provider.provider_id, w9_decision_id="autonomy-forged-0000",
        ), (act,)),
        # ASK decision authorizes nothing
        (w14.execution_request_for(
            ask, harness, scope=ExecutionActionScope.DEPLOY,
            provider_id=provider.provider_id,
        ), (ask,)),
        # provider-owned policy cannot authorize its own execution
        (w14.execution_request_for(
            self_auth, harness, scope=ExecutionActionScope.DEPLOY,
            provider_id=provider.provider_id,
        ), (self_auth,)),
        # request citing a W8 experiment the decision never bound
        (w14.execution_request_for(
            act, harness, scope=ExecutionActionScope.DEPLOY,
            provider_id=provider.provider_id, w8_experiment_id="experiment-forged",
        ), (act,)),
    )
    for request, decisions in rejections:
        with pytest.raises(ExecutionContractError):
            substrate_with(provider, harness, *decisions).submit(request)
    assert provider.execute_calls == 0


# ---------------------------------------------------------------------------
# The persisted matrix reconciliation (C10)
# ---------------------------------------------------------------------------

MATRIX_PATH = (
    Path(__file__).resolve().parent.parent
    / "spec" / "development-state" / "W14-adversarial-evidence-matrix.json"
)

#: The frozen sixteen-case enum from the Work Order (verbatim case names).
FROZEN_CASE_NAMES = (
    "missing evidence",
    "FAILED evidence",
    "UNKNOWN evidence",
    "UNAVAILABLE provider",
    "UNSUPPORTED capability",
    "forged authority references",
    "mismatched revisions",
    "mismatched candidates",
    "platform widening attempts",
    "provider self-authorization",
    "ASK bypass attempts",
    "rollback bypass attempts",
    "self-evolution boundary violations",
    "non-deterministic outputs",
    "stale-state recovery",
    "partial-failure recovery",
)

VALID_DISTINCTIONS = {"FAILED", "UNKNOWN", "UNAVAILABLE", "UNSUPPORTED"}


def test_w14_adversarial_matrix_file_is_valid_and_reconciled():
    """The persisted matrix parses against its schema, carries every required
    case id exactly once, cites real owning tests in THIS module, and carries
    all-PASS verdicts reconciled with the exact test run (this suite failing
    fails the repo; the matrix may not claim otherwise)."""
    data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))

    assert data["schema"] == "sos-w14-adversarial-evidence-matrix/1.0"
    assert data["workOrder"] == (
        "spec/work-orders/W14-dogfood-adversarial-verification.md"
    )
    assert re.fullmatch(r"[0-9a-f]{40}", data["repoHead"]), (
        "repoHead must cite the exact 40-hex run head"
    )
    assert data["generatedBy"].strip()

    rows = data["rows"]
    assert len(rows) == 16
    case_ids = [row["caseId"] for row in rows]
    assert len(set(case_ids)) == 16  # no case counted twice
    case_names = [row["case"] for row in rows]
    assert set(case_names) == set(FROZEN_CASE_NAMES)  # every case, no renames
    assert len(case_names) == len(set(case_names))

    this_module = sys.modules[__name__]
    for row in rows:
        assert row["verdict"] == "PASS"
        assert row["testId"].startswith("tests/test_w14_adversarial_matrix.py::")
        function_name = row["testId"].split("::", 1)[1]
        owning_test = getattr(this_module, function_name, None)
        assert callable(owning_test), f"unknown owning test {function_name}"
        assert function_name.startswith("test_adv_")
        assert row["authorityAttacked"], "the attacked authority must be named"
        assert row["injectedFault"].strip()
        assert row["expectedGovernedOutcome"].strip()
        assert row["expectedEvidenceRecord"].strip()
        assert row["distinctionGuarantee"], "the distinction guarantee must be stated"
        assert set(row["distinctionGuarantee"]) <= VALID_DISTINCTIONS
        assert isinstance(row["notes"], str)
