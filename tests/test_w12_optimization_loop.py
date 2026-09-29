"""W12 — brownfield optimization loop contract tests (first bounded slice).

Deterministic, offline tests for the governed orchestrator in
``src/sos/optimization.py`` (frozen W12 Work Order
`spec/work-orders/W12-optimization-loop.md`; design in
`docs/implementation/W12-OPTIMIZATION-LOOP-DESIGN.md`).

The suite composes the REAL merged authorities end-to-end: the recovered
system is produced by the real W3 ``recover_repository`` over a fixture
repository; candidates, hypotheses, and evidence are real W6/W5/W4 records;
assurance, experiments, evaluations, promotion gates, and autonomy decisions
are produced by the real W7/W8/W9 engines; deployments (when exercised) go
through the real W11 ``ExecutionSubstrate`` against a test-local stub
provider (an injected port object, per the W11 port boundary).

The injected deterministic stub evaluator (``StubSimulator``) and the stub
deploy provider stay LOCAL to this test module — the Work Order's
"deterministic stub evaluators". All tests are fully deterministic: fixed
revisions, fixed ISO-8601 timestamps, no wall clock, no randomness, no
running systems. The required regression coverage list of the Work Order is
mapped one-to-one onto the tests below.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from sos import (
    AssuranceGate,
    AssuranceResult,
    AssuranceStatus,
    AutonomyDecisionState,
    AutonomyRequest,
    BlastRadius,
    CandidateObjective,
    CausalHypothesis,
    CausalKnowledgeGraph,
    CausalRelationType,
    CandidateProposal,
    DecisionAction,
    Evidence,
    EvidenceGraph,
    EvidenceKind,
    EvidenceProvenance,
    EvidenceSupport,
    ExperimentState,
    ImpactAnalysis,
    InterventionMetadata,
    JsonModelStore,
    ModelValidationError,
    MutationKind,
    ObjectiveDirection,
    PolicyCeiling,
    PromotionDecision,
    ProviderCapability,
    RecoveryResult,
    RiskAssessment,
    RiskItem,
    RollbackPath,
    ReversibilityAssessment,
    StaticEvidenceAdapter,
    StopCondition,
    SubgraphMutation,
    SupportKind,
    Traceability,
    TruthState,
    TruthfulValue,
    ExecutionLifecycleState,
    ExecutionReceipt,
    SideEffect,
    SideEffectKind,
    # W12 orchestrator surface (src/sos/optimization.py, W12 exports)
    AuthorizationResolution,
    IterationOutcome,
    LoopPromotion,
    LoopStopReason,
    OptimizationContractError,
    OptimizationLoop,
    OptimizationRun,
    PendingAuthorization,
    PromotionClass,
    SimulatedObservation,
    apply_promotion,
    governed_experiment,
    run_optimization_loop,
    validate_iteration_transition,
)
from sos.evidence import _build_evidence
from sos.model import _convert_for_json
from sos.recovery import recover_repository


REVISION = "f00dfeed1234567890abcdef1234567890abcdef"
CHANGED_REVISION = "baadf00d1234567890abcdef1234567890abc"
DEPLOY_STARTED = "2030-06-01T10:00:00Z"
DEPLOY_FINISHED = "2030-06-01T10:05:00Z"
PROVIDER_ID = "stub-deploy-provider"
STOP_CONDITIONS = (StopCondition(name="error-rate", threshold=0.05, metric="error-rate"),)


def tr() -> Traceability:
    return Traceability(
        constitution_ref="constitution:1", mission_ref="mission:1",
        value_model_ref="value:1", context_ref="context:1",
    )


# ---------------------------------------------------------------------------
# Fixture recovered system (the REAL W3 recovery over a fixture repository)
# ---------------------------------------------------------------------------


def make_repository(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "svc_a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (root / "svc_b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    (root / "svc_c.py").write_text("def c():\n    return 3\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "svc"\ndependencies = ["numpy"]\n', encoding="utf-8"
    )


def prov(subject: str) -> EvidenceProvenance:
    return EvidenceProvenance(
        source="w12-test-harness", observed_subject=subject,
        timestamp=None, environment="simulation", implementation_revision=REVISION,
    )


def intervention_evidence(subject: str) -> Evidence:
    return _build_evidence(
        kind=EvidenceKind.EXPERIMENT, source_ref="experiment-77",
        subject_ref=subject,
        result=TruthfulValue(TruthState.SUCCESS, "intervention-applied", None),
        provenance=prov(subject), traceability=tr(),
        timestamp=None, environment="simulation", confidence=0.9,
        availability=TruthState.SUCCESS,
    )


def rollback_evidence(subject: str) -> Evidence:
    return StaticEvidenceAdapter.from_static_observation(
        subject_ref=subject, observation="rollback path verified",
        result=TruthfulValue(TruthState.SUCCESS, "rollback-capable", None),
        traceability=tr(), provenance=prov(subject),
    )


def failed_evidence(subject: str) -> Evidence:
    return StaticEvidenceAdapter.from_static_observation(
        subject_ref=subject, observation="observed degradation",
        result=TruthfulValue(TruthState.FAILED, None, "observed failed outcome"),
        traceability=tr(), provenance=prov(subject),
    )


def causal_hypothesis(intervention: Evidence) -> CausalHypothesis:
    support = EvidenceSupport(
        evidence_id=intervention.id, support_kind=SupportKind.INTERVENTION,
        intervention=InterventionMetadata(
            intervention_id="experiment-77", intervention_kind="experiment",
            applied_at="2026-09-10T12:00:00Z", revision=REVISION,
            environment="simulation",
        ),
    )
    h = CausalHypothesis(
        cause_subject="svc_a.py", effect_subject="svc_b.py",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="intervention degraded latency", status="proposed",
        uncertainty=TruthfulValue(TruthState.SUCCESS, "intervention-backed", None),
        supporting_evidence=(support,), traceability=tr(), provenance_revision=REVISION,
    )
    return h.with_status(
        "confirmed",
        known_evidence_ids={intervention.id},
        known_evidence_records={intervention.id: intervention},
    )


def objectives() -> tuple[CandidateObjective, ...]:
    return (
        CandidateObjective(
            name="latency", direction=ObjectiveDirection.MINIMIZE, predicted_value=150.0,
            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted"),
        ),
        CandidateObjective(
            name="cost", direction=ObjectiveDirection.MINIMIZE, predicted_value=1000.0,
            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted"),
        ),
    )


def node_for(recovery: RecoveryResult, path: str) -> str:
    for n in recovery.system_state.architecture.nodes:
        if n.name == path:
            return n.id
    raise AssertionError(f"node {path!r} was not recovered")


def make_candidate(
    recovery: RecoveryResult,
    *,
    target: str,
    replacement: str,
    boundary: str,
    intervention: Evidence,
    hypothesis: CausalHypothesis,
    rationale: str = "reduce latency",
    reasoning_evidence_ids: tuple[str, ...] | None = None,
    reasoning_hypothesis_ids: tuple[str, ...] | None = None,
) -> CandidateProposal:
    graph = recovery.system_state.architecture
    mutation = SubgraphMutation(
        kind=MutationKind.SUBGRAPH_REPLACE, base_graph_ref=graph.id,
        target_node_ids=(node_for(recovery, target),),
        replacement_node_ids=(node_for(recovery, replacement),),
        boundary_interface_ids=(node_for(recovery, boundary),),
        invariants=("preserve-boundary",),
    )
    return CandidateProposal(
        id="", base_graph_ref=graph.id, base_graph_revision=REVISION,
        mutation=mutation, objectives=objectives(), rationale=rationale,
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not proven"),
        reasoning_evidence_ids=(
            (intervention.id,) if reasoning_evidence_ids is None else reasoning_evidence_ids
        ),
        reasoning_hypothesis_ids=(
            (hypothesis.id,) if reasoning_hypothesis_ids is None else reasoning_hypothesis_ids
        ),
        risks=("rollback-risk",), traceability=tr(), provenance_revision=REVISION,
    )


@dataclasses.dataclass
class Harness:
    recovery: RecoveryResult
    graph_id: str
    candidates: tuple[CandidateProposal, ...]
    intervention_evidence: Evidence
    rollback_evidence: Evidence
    hypothesis: CausalHypothesis
    evidence_graph: EvidenceGraph
    causal_graph: CausalKnowledgeGraph


def harness_at(
    root: Path,
    *,
    candidate_specs: tuple[tuple[str, str, str], ...] = (
        ("svc_a.py", "svc_b.py", "svc_c.py"),
    ),
    extra_evidence: tuple[Evidence, ...] = (),
) -> Harness:
    make_repository(root)
    recovery = recover_repository(root=root, revision=REVISION, traceability=tr())
    graph_id = recovery.system_state.architecture.id
    intervention = intervention_evidence(graph_id)
    rollback = rollback_evidence(graph_id)
    hypothesis = causal_hypothesis(intervention)
    evidence_graph = EvidenceGraph(id="w12-test-evidence", version=1, records=(), traceability=tr())
    for record in (intervention, rollback, *extra_evidence):
        evidence_graph = evidence_graph.ingest(record)
    causal_graph = CausalKnowledgeGraph(
        id="w12-test-causal", version=1, hypotheses=(), traceability=tr()
    ).ingest(hypothesis)
    candidates = tuple(
        make_candidate(
            recovery, target=t, replacement=r, boundary=b,
            intervention=intervention, hypothesis=hypothesis,
        )
        for t, r, b in candidate_specs
    )
    return Harness(
        recovery=recovery, graph_id=graph_id, candidates=candidates,
        intervention_evidence=intervention, rollback_evidence=rollback,
        hypothesis=hypothesis, evidence_graph=evidence_graph, causal_graph=causal_graph,
    )


# ---------------------------------------------------------------------------
# Injected deterministic stub evaluators (test-local port objects)
# ---------------------------------------------------------------------------


class StubSimulator:
    """Deterministic model-only experiment simulator (injected port object)."""

    def __init__(
        self,
        *,
        simulator_id: str = "stub-simulator-1",
        outcome: TruthState = TruthState.SUCCESS,
        stop_triggered: tuple[str, ...] = (),
    ):
        self.simulator_id = simulator_id
        self._outcome = outcome
        self._stop = tuple(stop_triggered)
        self.calls = 0

    def simulate(self, experiment: Any) -> SimulatedObservation:
        self.calls += 1
        if self._outcome == TruthState.SUCCESS:
            return SimulatedObservation(
                TruthState.SUCCESS, "simulated-success",
                "simulated canary met its success criteria",
                stop_triggered=self._stop,
            )
        return SimulatedObservation(
            self._outcome,
            f"simulated {self._outcome.value} experiment outcome",
            None,
            stop_triggered=self._stop,
        )


class StubDeployProvider:
    """Test-local W11 port object: an isolated stub deployment provider."""

    def __init__(self, *, provider_id: str = PROVIDER_ID, outcome: TruthState = TruthState.SUCCESS):
        self.provider_id = provider_id
        self.capabilities = frozenset({
            ProviderCapability.EXECUTE_DEPLOY,
            ProviderCapability.EXECUTE_ROLLBACK,
            ProviderCapability.EXECUTE_OBSERVE,
            ProviderCapability.ISOLATED_WORKSPACE,
            ProviderCapability.REVISION_PINNING,
            ProviderCapability.LOG_CAPTURE,
            ProviderCapability.SIDE_EFFECT_REPORT,
            ProviderCapability.ENVIRONMENT_ISOLATION,
        })
        self._outcome = outcome
        self.execute_calls = 0

    def execute(self, request: Any) -> ExecutionReceipt:
        self.execute_calls += 1
        echo = dict(
            request_id=request.id,
            provider_id=self.provider_id,
            action_scope=request.action_scope,
            w9_decision_id=request.w9_decision_id,
            w7_assurance_id=request.w7_assurance_id or None,
            source_revision=request.source_revision,
            provenance_revision=request.provenance_revision,
            base_graph_id=request.base_graph_id,
            base_graph_revision=request.base_graph_revision,
            environment=request.environment,
        )
        rollback = request.rollback_reference
        if self._outcome == TruthState.FAILED:
            return ExecutionReceipt(
                lifecycle=ExecutionLifecycleState.FAILED,
                outcome=TruthfulValue(
                    TruthState.FAILED, None,
                    "stub deploy exited non-zero before applying changes",
                ),
                started_at=DEPLOY_STARTED, finished_at=DEPLOY_FINISHED,
                stdout_ref=f"stub-stdout-{request.id}",
                stderr_ref=f"stub-stderr-{request.id}",
                log_ref=f"stub-log-{request.id}",
                rollback_reference=rollback,
                **echo,
            )
        return ExecutionReceipt(
            lifecycle=ExecutionLifecycleState.SUCCEEDED,
            outcome=TruthfulValue(
                TruthState.SUCCESS, "deployed to isolated stub workspace", None
            ),
            started_at=DEPLOY_STARTED, finished_at=DEPLOY_FINISHED,
            side_effects=(SideEffect(
                SideEffectKind.SERVICE_STATE, "stub-workspace",
                "candidate mutation applied in the isolated stub workspace",
            ),),
            changed_revisions=(CHANGED_REVISION,),
            log_ref=f"stub-log-{request.id}",
            rollback_reference=rollback,
            **echo,
        )


def default_policy(
    *,
    allow_act: bool = True,
    allow_rollback: bool = True,
    human_approval_for_act: bool = False,
) -> AutonomyRequest:
    actions: list[DecisionAction] = [DecisionAction.EXPERIMENT, DecisionAction.GATHER_EVIDENCE]
    if allow_act:
        actions.append(DecisionAction.ACT)
    if allow_rollback:
        actions.append(DecisionAction.ROLLBACK)
    return AutonomyRequest(
        id="policy-1", version=1, allowed_actions=tuple(actions),
        ceilings=PolicyCeiling(
            max_risk=0.3, max_blast_radius="service", require_reversible=True,
            min_confidence=0.8, require_human_approval_for_act=human_approval_for_act,
        ),
        traceability=tr(),
    )


def run_loop(
    harness: Harness,
    *,
    candidates: Any = None,
    policy: AutonomyRequest | None = None,
    simulator: StubSimulator | None = None,
    max_iterations: int = 3,
    providers: dict[str, StubDeployProvider] | None = None,
    provider_id: str | None = None,
    rollback_ref: str = "rb-loop-1",
) -> OptimizationRun:
    return run_optimization_loop(
        recovery=harness.recovery,
        candidates=harness.candidates if candidates is None else list(candidates),
        policy=policy if policy is not None else default_policy(),
        simulator=simulator if simulator is not None else StubSimulator(),
        traceability=tr(),
        max_iterations=max_iterations,
        stop_conditions=STOP_CONDITIONS,
        evidence_graph=harness.evidence_graph,
        causal_graph=harness.causal_graph,
        rollback_ref=rollback_ref,
        rollback_evidence_ids=(harness.rollback_evidence.id,),
        execution_providers=providers,
        execution_provider_id=provider_id,
    )


def assurance_record(
    *,
    candidate_id: str,
    base_graph_id: str,
    status: AssuranceStatus,
    revision: str = REVISION,
) -> AssuranceResult:
    """A directly-constructed W7 record for boundary tests (W7 types, W12 test)."""
    return AssuranceResult(
        id="",
        candidate_id=candidate_id,
        base_graph_id=base_graph_id,
        base_graph_revision=revision,
        provenance_revision=revision,
        status=status,
        gates=(AssuranceGate(
            name="evidence-availability", status=status, evidence_ids=(),
            detail=f"stub gate status {status.value}",
        ),),
        impact=ImpactAnalysis(
            affected_node_ids=("node-x",), affected_edge_ids=(), boundary_interface_ids=(),
            dependency_reach=(),
            blast_radius=BlastRadius(level="limited", affected_count=1, detail="bounded"),
        ),
        risk=RiskAssessment(items=(RiskItem(
            name="stub-risk", severity="medium",
            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "not quantified"),
            mitigation="monitor", residual=None,
        ),)),
        reversibility=ReversibilityAssessment(
            rollback_available=True, detail="verified",
            rollback_evidence_ids=("evidence-stub-rollback",),
        ),
        objectives=(),
        traceability=tr(),
    )


# ---------------------------------------------------------------------------
# Full-loop happy path + determinism (C6, C8, C9)
# ---------------------------------------------------------------------------


def test_full_loop_happy_path_produces_governed_deterministic_record(tmp_path):
    harness = harness_at(tmp_path / "repo")
    run = run_loop(harness)

    assert run.loop.stop.reason == LoopStopReason.COMPLETED
    assert run.loop.recovered_state_ref == harness.recovery.system_state.id
    assert run.loop.recovered_revision == REVISION
    assert run.loop.max_iterations == 3
    assert len(run.loop.iterations) == 1

    it = run.loop.iterations[0]
    assert it.outcome == IterationOutcome.PROMOTED
    assert it.assurance_status == AssuranceStatus.PASS
    assert it.decision_state == AutonomyDecisionState.ACT
    assert it.promotion is not None
    assert it.promotion.promotion_class == PromotionClass.MODEL_ONLY
    assert it.promotion.receipt_id is None  # model-only: nothing dispatched
    assert it.promotion.rollback is not None
    assert it.promotion.experiment_rollback_ref == "rb-loop-1"
    assert run.receipts == ()

    # W7-before-W8 visible in the record: experiment requires assurance.
    assert it.experiment_id is not None and it.assurance_id is not None
    experiment = next(e for e in run.experiments if e.id == it.experiment_id)
    assert experiment.state == ExperimentState.COMPLETED
    assert experiment.assurance_result_id == it.assurance_id
    assert experiment.candidate_id == it.candidate_id
    evaluation = next(ev for ev in run.evaluations if ev.id == it.evaluation_id)
    assert evaluation.promotion_eligible is True
    gate = run.promotion_decisions[0]
    assert gate.promoted is True

    # the W9 chain: launch decision (EXPERIMENT) then the authorizing ACT decision
    decisions_by_id = {d.id: d for d in run.decisions}
    assert it.decision_ids[-1] == it.promotion.decision_id
    assert decisions_by_id[it.decision_ids[-1]].state == AutonomyDecisionState.ACT

    # identical inputs -> identical loop records (content-addressed ids)
    again = run_loop(harness)
    assert again.loop.id == run.loop.id
    assert [i.id for i in again.loop.iterations] == [i.id for i in run.loop.iterations]
    assert [r.id for r in again.evidence_graph.records] == [r.id for r in run.evidence_graph.records]
    assert again.loop.iterations[0].promotion.id == it.promotion.id


def test_identical_inputs_from_distinct_repositories_produce_identical_ids(tmp_path):
    # recovery ids are root-independent (content-addressed over relative paths)
    harness_a = harness_at(tmp_path / "repo-one")
    harness_b = harness_at(tmp_path / "repo-two")
    run_a = run_loop(harness_a)
    run_b = run_loop(harness_b)
    assert run_a.loop.id == run_b.loop.id
    assert run_a.loop.base_graph_id == run_b.loop.base_graph_id
    assert [r.id for r in run_a.evidence_graph.records] == [r.id for r in run_b.evidence_graph.records]


def test_deterministic_candidate_ordering_and_dedup(tmp_path):
    harness = harness_at(
        tmp_path / "repo",
        candidate_specs=(
            ("svc_a.py", "svc_b.py", "svc_c.py"),
            ("svc_b.py", "svc_c.py", "svc_a.py"),
            ("svc_c.py", "svc_a.py", "svc_b.py"),
        ),
    )
    run = run_loop(harness, candidates=list(reversed(harness.candidates)), max_iterations=5)
    ids = [it.candidate_id for it in run.loop.iterations]
    assert ids == sorted(ids)  # deterministic order with stable id tie-breaks
    assert len(ids) == 3

    # duplicate (identical) candidates collapse to a single iteration
    run_dup = run_loop(harness, candidates=[harness.candidates[0], harness.candidates[0]])
    assert len(run_dup.loop.iterations) == 1


def test_max_iteration_bound_bounds_the_loop(tmp_path):
    harness = harness_at(
        tmp_path / "repo",
        candidate_specs=(
            ("svc_a.py", "svc_b.py", "svc_c.py"),
            ("svc_b.py", "svc_c.py", "svc_a.py"),
            ("svc_c.py", "svc_a.py", "svc_b.py"),
        ),
    )
    run = run_loop(harness, max_iterations=2)
    assert len(run.loop.iterations) == 2
    assert [it.index for it in run.loop.iterations] == [1, 2]
    assert run.loop.stop.reason == LoopStopReason.MAX_ITERATIONS

    # the record itself is bounded: exceeding the declared bound is unconstructible
    first, second = run.loop.iterations
    with pytest.raises(OptimizationContractError, match="exceeding the fixed"):
        dataclasses.replace(
            run.loop, max_iterations=1, iterations=(first, second),
        )


# ---------------------------------------------------------------------------
# W9 gate mechanics (C2)
# ---------------------------------------------------------------------------


def test_w9_ask_pauses_loop_with_explicit_pending_authorization_record(tmp_path):
    harness = harness_at(tmp_path / "repo")
    run = run_loop(harness, policy=default_policy(human_approval_for_act=True))

    assert run.loop.stop.reason == LoopStopReason.PAUSED_FOR_AUTHORIZATION
    it = run.loop.iterations[0]
    assert it.outcome == IterationOutcome.PAUSED_PENDING_AUTHORIZATION
    assert it.promotion is None

    pending = it.pending_authorization
    assert pending is not None
    assert pending.resolution == AuthorizationResolution.PENDING
    assert pending.decision_state == AutonomyDecisionState.ASK
    assert pending.iteration_index == 1
    decisions_by_id = {d.id: d for d in run.decisions}
    ask_decision = decisions_by_id[pending.decision_id]
    assert ask_decision.state == AutonomyDecisionState.ASK
    assert ask_decision.rationale == pending.rationale

    # the pause is itself recorded as truthful UNKNOWN evidence — never silent
    paused_records = [
        r for r in run.evidence_graph.records
        if r.id in it.evidence_ids and r.result.state == TruthState.UNKNOWN
    ]
    assert len(paused_records) == 1
    assert "pending human authorization" in paused_records[0].result.detail


def test_pending_authorization_can_never_auto_approve(tmp_path):
    harness = harness_at(tmp_path / "repo")
    paused = run_loop(harness, policy=default_policy(human_approval_for_act=True))
    pending = paused.loop.iterations[0].pending_authorization

    # PENDING is the only resolution state; no granting API exists on the record
    assert [s.name for s in AuthorizationResolution] == ["PENDING"]
    granters = {"approve", "grant", "resolve", "authorize", "with_resolution", "promote"}
    assert not granters & {n for n in dir(pending) if not n.startswith("_") and callable(getattr(pending, n))}
    # and the paused loop promoted nothing
    assert paused.loop.iterations[0].promotion is None


def test_w9_reject_refuses_the_iteration_and_the_loop_continues(tmp_path):
    harness = harness_at(tmp_path / "repo")
    run = run_loop(harness, policy=default_policy(allow_act=False))

    it = run.loop.iterations[0]
    assert it.outcome == IterationOutcome.REFUSED
    assert it.decision_state == AutonomyDecisionState.REJECT
    assert it.promotion is None
    decisions_by_id = {d.id: d for d in run.decisions}
    assert decisions_by_id[it.decision_ids[-1]].state == AutonomyDecisionState.REJECT
    # the refusal terminated the ITERATION, not the loop
    assert run.loop.stop.reason == LoopStopReason.COMPLETED


def test_unresolved_w9_reference_is_rejected_at_the_run_boundary(tmp_path):
    harness = harness_at(tmp_path / "repo")
    run = run_loop(harness)
    iteration = run.loop.iterations[0]
    dangling = dataclasses.replace(iteration, decision_ids=("autonomy-bogus",))
    bad_loop = dataclasses.replace(run.loop, iterations=(dangling,))
    bad_run = dataclasses.replace(run, loop=bad_loop)
    with pytest.raises(OptimizationContractError, match="unresolved W9 decision"):
        bad_run.validate()


def test_pending_authorization_requires_a_real_ask_decision(tmp_path):
    harness = harness_at(tmp_path / "repo")
    run = run_loop(harness)
    act_decision = next(d for d in run.decisions if d.state == AutonomyDecisionState.ACT)
    with pytest.raises(OptimizationContractError, match="ASK decision"):
        PendingAuthorization.from_decision(act_decision, iteration_index=1)
    with pytest.raises(OptimizationContractError, match="AutonomyDecision"):
        PendingAuthorization.from_decision({"state": "ASK"}, iteration_index=1)


# ---------------------------------------------------------------------------
# W7-before-W8 ordering invariant (C3)
# ---------------------------------------------------------------------------


def test_governed_experiment_requires_w7_pass_bound_to_exact_chain(tmp_path):
    harness = harness_at(tmp_path / "repo")
    candidate = harness.candidates[0]
    run = run_loop(harness)
    pass_assurance = next(a for a in run.assurance_results if a.status == AssuranceStatus.PASS)

    experiment = governed_experiment(
        assurance=pass_assurance, candidate=candidate,
        rollback_ref="rb-loop-1", traceability=tr(), stop_conditions=STOP_CONDITIONS,
    )
    assert experiment.candidate_id == candidate.id
    assert experiment.assurance_result_id == pass_assurance.id
    assert experiment.base_graph_id == harness.graph_id
    assert experiment.rollback_ref == "rb-loop-1"

    # FAIL assurance: no experiment is constructible
    fail_assurance = assurance_record(
        candidate_id=candidate.id, base_graph_id=harness.graph_id,
        status=AssuranceStatus.FAIL,
    )
    with pytest.raises(OptimizationContractError, match="W7-before-W8"):
        governed_experiment(
            assurance=fail_assurance, candidate=candidate,
            rollback_ref="rb-loop-1", traceability=tr(), stop_conditions=STOP_CONDITIONS,
        )

    # UNKNOWN assurance: still no experiment
    unknown_assurance = assurance_record(
        candidate_id=candidate.id, base_graph_id=harness.graph_id,
        status=AssuranceStatus.UNKNOWN,
    )
    with pytest.raises(OptimizationContractError, match="W7-before-W8"):
        governed_experiment(
            assurance=unknown_assurance, candidate=candidate,
            rollback_ref="rb-loop-1", traceability=tr(), stop_conditions=STOP_CONDITIONS,
        )

    # PASS assurance bound to a DIFFERENT candidate: chain mismatch rejected
    foreign_assurance = assurance_record(
        candidate_id="candidate-someone-else", base_graph_id=harness.graph_id,
        status=AssuranceStatus.PASS,
    )
    with pytest.raises(OptimizationContractError, match="not the candidate"):
        governed_experiment(
            assurance=foreign_assurance, candidate=candidate,
            rollback_ref="rb-loop-1", traceability=tr(), stop_conditions=STOP_CONDITIONS,
        )

    # a non-assurance object cannot construct an experiment
    with pytest.raises(OptimizationContractError, match="AssuranceResult"):
        governed_experiment(
            assurance={"status": "PASS"}, candidate=candidate,
            rollback_ref="rb-loop-1", traceability=tr(), stop_conditions=STOP_CONDITIONS,
        )


def test_loop_records_assurance_not_passed_without_any_experiment(tmp_path):
    subject = None  # built below from the recovered graph
    root = tmp_path / "repo"
    make_repository(root)
    recovery = recover_repository(root=root, revision=REVISION, traceability=tr())
    graph_id = recovery.system_state.architecture.id
    subject = graph_id
    intervention = intervention_evidence(subject)
    rollback = rollback_evidence(subject)
    hypothesis = causal_hypothesis(intervention)
    failed = failed_evidence(subject)
    evidence_graph = EvidenceGraph(id="w12-test-evidence", version=1, records=(), traceability=tr())
    for record in (intervention, rollback, failed):
        evidence_graph = evidence_graph.ingest(record)
    causal_graph = CausalKnowledgeGraph(
        id="w12-test-causal", version=1, hypotheses=(), traceability=tr()
    ).ingest(hypothesis)
    failing_candidate = make_candidate(
        recovery, target="svc_a.py", replacement="svc_b.py", boundary="svc_c.py",
        intervention=intervention, hypothesis=hypothesis,
        reasoning_evidence_ids=(failed.id,), reasoning_hypothesis_ids=(),
    )
    run = run_optimization_loop(
        recovery=recovery, candidates=[failing_candidate], policy=default_policy(),
        simulator=StubSimulator(), traceability=tr(), max_iterations=2,
        stop_conditions=STOP_CONDITIONS, evidence_graph=evidence_graph,
        causal_graph=causal_graph, rollback_ref="rb-loop-1",
        rollback_evidence_ids=(rollback.id,),
    )
    it = run.loop.iterations[0]
    assert it.outcome == IterationOutcome.ASSURANCE_NOT_PASSED
    assert it.assurance_status == AssuranceStatus.FAIL
    assert it.experiment_id is None  # W7-fail: the loop never constructs an experiment
    assert run.experiments == ()
    assert run.evaluations == ()
    assert it.promotion is None
    # the failing status is preserved verbatim in the TEST-kind evidence
    assurance_records = [
        r for r in run.evidence_graph.records
        if r.id in it.evidence_ids and r.kind == EvidenceKind.TEST
    ]
    assert len(assurance_records) == 1
    assert assurance_records[0].result.state == TruthState.FAILED
    assert run.loop.stop.reason == LoopStopReason.COMPLETED


# ---------------------------------------------------------------------------
# Promotion governance (C4)
# ---------------------------------------------------------------------------


def test_promotion_requires_the_promotion_gate_decision(tmp_path):
    harness = harness_at(tmp_path / "repo")
    run = run_loop(harness)
    it = run.loop.iterations[0]
    experiment = next(e for e in run.experiments if e.id == it.experiment_id)
    evaluation = next(ev for ev in run.evaluations if ev.id == it.evaluation_id)
    assurance = next(a for a in run.assurance_results if a.id == it.assurance_id)
    act_decision = next(d for d in run.decisions if d.id == it.promotion.decision_id)
    rollback_path = RollbackPath(
        reference=experiment.rollback_ref,
        evidence_ids=(harness.rollback_evidence.id,),
        detail="verified rollback path",
    )

    # a non-promoted gate decision cannot promote
    not_promoted = PromotionDecision(
        promoted=False, rationale="not promoted",
        experiment_id=experiment.id, evaluation_id=evaluation.id,
    )
    with pytest.raises(OptimizationContractError, match="PromotionGate"):
        apply_promotion(
            gate_decision=not_promoted, experiment=experiment, evaluation=evaluation,
            assurance=assurance, autonomy_decision=act_decision,
            rollback_path=rollback_path, promotion_class=PromotionClass.MODEL_ONLY,
        )

    # a non-gate object cannot promote
    with pytest.raises(OptimizationContractError, match="PromotionDecision"):
        apply_promotion(
            gate_decision={"promoted": True}, experiment=experiment, evaluation=evaluation,
            assurance=assurance, autonomy_decision=act_decision,
            rollback_path=rollback_path, promotion_class=PromotionClass.MODEL_ONLY,
        )

    promotion = apply_promotion(
        gate_decision=run.promotion_decisions[0], experiment=experiment,
        evaluation=evaluation, assurance=assurance, autonomy_decision=act_decision,
        rollback_path=rollback_path, promotion_class=PromotionClass.MODEL_ONLY,
    )
    assert promotion.promotion_ref == f"{experiment.id}:{evaluation.id}"
    assert promotion.decision_id == act_decision.id


def test_promotion_requires_a_resolved_w9_act_decision(tmp_path):
    harness = harness_at(tmp_path / "repo")
    run = run_loop(harness)
    it = run.loop.iterations[0]
    experiment = next(e for e in run.experiments if e.id == it.experiment_id)
    evaluation = next(ev for ev in run.evaluations if ev.id == it.evaluation_id)
    assurance = next(a for a in run.assurance_results if a.id == it.assurance_id)
    rollback_path = RollbackPath(
        reference=experiment.rollback_ref,
        evidence_ids=(harness.rollback_evidence.id,),
        detail="verified rollback path",
    )
    ask_run = run_loop(harness, policy=default_policy(human_approval_for_act=True))
    ask_decision = next(d for d in ask_run.decisions if d.state == AutonomyDecisionState.ASK)

    with pytest.raises(OptimizationContractError, match="ACT decision"):
        apply_promotion(
            gate_decision=run.promotion_decisions[0], experiment=experiment,
            evaluation=evaluation, assurance=assurance, autonomy_decision=ask_decision,
            rollback_path=rollback_path, promotion_class=PromotionClass.MODEL_ONLY,
        )


def test_deploy_class_promotion_requires_a_bounded_rollback_path(tmp_path):
    harness = harness_at(tmp_path / "repo")
    run = run_loop(harness)
    it = run.loop.iterations[0]
    experiment = next(e for e in run.experiments if e.id == it.experiment_id)
    evaluation = next(ev for ev in run.evaluations if ev.id == it.evaluation_id)

    common = dict(
        candidate_id=it.candidate_id,
        assurance_id=it.assurance_id,
        experiment_id=experiment.id,
        evaluation_id=evaluation.id,
        decision_id=it.promotion.decision_id,
        promotion_ref=f"{experiment.id}:{evaluation.id}",
        experiment_rollback_ref=experiment.rollback_ref,
    )
    # DEPLOY class without a rollback path is unconstructible
    with pytest.raises(OptimizationContractError, match="bounded W8 RollbackPath"):
        LoopPromotion(promotion_class=PromotionClass.DEPLOY, rollback=None, receipt_id="exec-receipt-x", **common)
    # DEPLOY class with a rollback path bound to the wrong reference
    with pytest.raises(OptimizationContractError, match="does not match"):
        LoopPromotion(
            promotion_class=PromotionClass.DEPLOY,
            rollback=RollbackPath(
                reference="some-other-reference",
                evidence_ids=("evidence-stub-rollback",),
                detail="misbound",
            ),
            receipt_id="exec-receipt-x", **common,
        )
    # DEPLOY class without a receipt reference
    with pytest.raises(OptimizationContractError, match="receipt"):
        LoopPromotion(
            promotion_class=PromotionClass.DEPLOY,
            rollback=RollbackPath(
                reference=experiment.rollback_ref,
                evidence_ids=("evidence-stub-rollback",),
                detail="verified",
            ),
            receipt_id=None, **common,
        )
    # MODEL_ONLY class must not claim a receipt
    with pytest.raises(OptimizationContractError, match="MODEL_ONLY"):
        LoopPromotion(
            promotion_class=PromotionClass.MODEL_ONLY, receipt_id="exec-receipt-x", **common
        )


def test_stop_condition_fires_and_terminates_the_loop(tmp_path):
    harness = harness_at(
        tmp_path / "repo",
        candidate_specs=(
            ("svc_a.py", "svc_b.py", "svc_c.py"),
            ("svc_b.py", "svc_c.py", "svc_a.py"),
        ),
    )
    simulator = StubSimulator(outcome=TruthState.FAILED, stop_triggered=("error-rate",))
    run = run_loop(harness, simulator=simulator)

    assert run.loop.stop.reason == LoopStopReason.STOP_CONDITION
    stop_condition = run.loop.stop.stop_condition
    assert isinstance(stop_condition, StopCondition)
    assert (stop_condition.name, stop_condition.metric, stop_condition.threshold) == (
        "error-rate", "error-rate", 0.05,
    )
    it = run.loop.iterations[0]
    assert it.outcome == IterationOutcome.STOPPED_BY_CONDITION
    assert it.stop_condition_name == "error-rate"
    assert it.promotion is None
    # the loop terminated: the second candidate was never processed
    assert len(run.loop.iterations) == 1


# ---------------------------------------------------------------------------
# W4 verbatim evidence (C5) + provenance citation (required outcome 6)
# ---------------------------------------------------------------------------


def test_w4_evidence_appended_at_every_consequential_step(tmp_path):
    harness = harness_at(tmp_path / "repo")
    run = run_loop(harness)
    it = run.loop.iterations[0]
    records = [r for r in run.evidence_graph.records if r.id in it.evidence_ids]
    kinds = {r.kind for r in records}
    # selection (OBSERVATION), assurance gate (TEST), experiment (EXPERIMENT),
    # model-only promotion record (OBSERVATION)
    assert kinds == {EvidenceKind.OBSERVATION, EvidenceKind.TEST, EvidenceKind.EXPERIMENT}
    assert len(records) == 4
    # every appended id resolves through the W4 ingestion path (sorted, deduped)
    ids = [r.id for r in run.evidence_graph.records]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)
    # loop evidence carries exact provenance (revision-bound, no invented facts)
    for record in records:
        assert record.provenance.implementation_revision == REVISION
        assert record.traceability.context_ref == "context:1"


def test_candidate_provenance_is_cited_in_iteration_records(tmp_path):
    harness = harness_at(tmp_path / "repo")
    run = run_loop(harness)
    it = run.loop.iterations[0]
    candidate = harness.candidates[0]
    assert it.candidate_id == candidate.id
    assert it.candidate_mutation_kind == candidate.mutation.kind.value
    assert it.candidate_mutation_kind == MutationKind.SUBGRAPH_REPLACE.value
    assert it.candidate_hypothesis_ids == candidate.reasoning_hypothesis_ids
    assert it.candidate_hypothesis_ids == (harness.hypothesis.id,)
    assert it.candidate_evidence_ids == candidate.reasoning_evidence_ids
    assert it.candidate_evidence_ids == (harness.intervention_evidence.id,)


# ---------------------------------------------------------------------------
# Distinction preservation (C7)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("state", [
    TruthState.FAILED, TruthState.UNKNOWN, TruthState.UNAVAILABLE, TruthState.UNSUPPORTED,
])
def test_distinctions_preserved_through_the_loop(state, tmp_path):
    harness = harness_at(tmp_path / "repo")
    run = run_loop(harness, simulator=StubSimulator(outcome=state))
    it = run.loop.iterations[0]
    experiment_records = [
        r for r in run.evidence_graph.records
        if r.id in it.evidence_ids and r.kind == EvidenceKind.EXPERIMENT
    ]
    assert len(experiment_records) == 1
    # the exact truth state survives the whole chain — never collapsed
    assert experiment_records[0].result.state == state
    assert experiment_records[0].result.state != TruthState.SUCCESS
    # a non-success evaluation is never promoted; the governed rollback decides
    assert it.promotion is None
    assert it.outcome == IterationOutcome.ROLLED_BACK
    assert it.decision_state == AutonomyDecisionState.ROLLBACK


def test_simulated_observation_preserves_truthful_distinctions():
    with pytest.raises(OptimizationContractError, match="EMPTY"):
        SimulatedObservation(TruthState.EMPTY, "empty is a capture state, not an outcome", None)
    with pytest.raises(ModelValidationError):
        SimulatedObservation(TruthState.SUCCESS, None, None)  # W1: SUCCESS requires a value (no detail, no value)
    with pytest.raises(ModelValidationError):
        SimulatedObservation(TruthState.FAILED, "", None)  # W1: non-SUCCESS requires detail
    observation = SimulatedObservation(TruthState.UNSUPPORTED, "simulator cannot model this", None)
    assert observation.outcome_state == TruthState.UNSUPPORTED


# ---------------------------------------------------------------------------
# W11 substrate seam (optional; model-only without it) — C8
# ---------------------------------------------------------------------------


def test_w11_seam_model_only_mode_without_providers(tmp_path):
    harness = harness_at(tmp_path / "repo")
    provider = StubDeployProvider()
    run = run_loop(harness)  # no providers supplied: model-only mode
    assert run.receipts == ()
    assert provider.execute_calls == 0
    it = run.loop.iterations[0]
    assert it.promotion is not None
    assert it.promotion.promotion_class == PromotionClass.MODEL_ONLY
    deployment_records = [
        r for r in run.evidence_graph.records if r.kind == EvidenceKind.DEPLOYMENT
    ]
    assert deployment_records == []


def test_w11_seam_dispatches_governed_deployment(tmp_path):
    harness = harness_at(tmp_path / "repo")
    provider = StubDeployProvider()
    run = run_loop(harness, providers={PROVIDER_ID: provider}, provider_id=PROVIDER_ID)

    assert provider.execute_calls == 1
    assert len(run.receipts) == 1
    receipt = run.receipts[0]
    assert receipt.lifecycle == ExecutionLifecycleState.SUCCEEDED
    assert receipt.outcome.state == TruthState.SUCCESS
    assert receipt.changed_revisions == (CHANGED_REVISION,)

    it = run.loop.iterations[0]
    assert it.outcome == IterationOutcome.PROMOTED
    assert it.promotion is not None
    assert it.promotion.promotion_class == PromotionClass.DEPLOY
    assert it.promotion.receipt_id == receipt.id
    assert it.promotion.rollback is not None
    assert it.promotion.rollback.reference == "rb-loop-1"
    assert it.promotion.rollback.evidence_ids == (harness.rollback_evidence.id,)

    # the receipt is bound to the exact authorizing chain
    decisions_by_id = {d.id: d for d in run.decisions}
    act_decision = decisions_by_id[it.promotion.decision_id]
    assert receipt.w9_decision_id == act_decision.id
    assert receipt.w7_assurance_id == it.assurance_id
    assert receipt.provenance_revision == REVISION
    assert receipt.base_graph_id == harness.graph_id

    # the receipt converts verbatim into DEPLOYMENT evidence (W11 binding)
    deployment_records = [
        r for r in run.evidence_graph.records if r.kind == EvidenceKind.DEPLOYMENT
    ]
    assert len(deployment_records) == 1
    assert deployment_records[0].id in it.evidence_ids
    assert deployment_records[0].result.state == TruthState.SUCCESS
    assert deployment_records[0].provenance.implementation_revision == REVISION


def test_failed_deployment_routes_to_governed_rollback(tmp_path):
    harness = harness_at(tmp_path / "repo")
    provider = StubDeployProvider(outcome=TruthState.FAILED)
    run = run_loop(harness, providers={PROVIDER_ID: provider}, provider_id=PROVIDER_ID)

    assert provider.execute_calls == 1
    receipt = run.receipts[0]
    assert receipt.lifecycle == ExecutionLifecycleState.FAILED
    it = run.loop.iterations[0]
    assert it.promotion is None  # a failed deployment promotes nothing
    assert it.outcome == IterationOutcome.ROLLED_BACK
    assert it.decision_state == AutonomyDecisionState.ROLLBACK
    experiment = next(e for e in run.experiments if e.id == it.experiment_id)
    assert experiment.state == ExperimentState.ROLLED_BACK

    # the failure evidence is preserved verbatim (FAILED, not "success")
    deployment_records = [
        r for r in run.evidence_graph.records if r.kind == EvidenceKind.DEPLOYMENT
    ]
    assert deployment_records[0].result.state == TruthState.FAILED


def test_unavailable_provider_yields_truthful_unavailable_receipt(tmp_path):
    harness = harness_at(tmp_path / "repo")
    provider = StubDeployProvider()
    run = run_loop(
        harness, providers={PROVIDER_ID: provider}, provider_id="unregistered-provider",
    )
    assert provider.execute_calls == 0  # capability/availability is not a rejection
    receipt = run.receipts[0]
    assert receipt.lifecycle == ExecutionLifecycleState.UNAVAILABLE
    assert receipt.outcome.state == TruthState.UNAVAILABLE
    it = run.loop.iterations[0]
    assert it.outcome == IterationOutcome.ROLLED_BACK  # governed rollback after no-run


def test_model_only_failed_experiment_routes_to_governed_rollback(tmp_path):
    harness = harness_at(tmp_path / "repo")
    run = run_loop(harness, simulator=StubSimulator(outcome=TruthState.FAILED))
    it = run.loop.iterations[0]
    assert it.outcome == IterationOutcome.ROLLED_BACK
    assert it.decision_state == AutonomyDecisionState.ROLLBACK
    experiment = next(e for e in run.experiments if e.id == it.experiment_id)
    assert experiment.state == ExperimentState.ROLLED_BACK
    rollback_records = [
        r for r in run.evidence_graph.records if r.kind == EvidenceKind.ROLLBACK
    ]
    assert len(rollback_records) == 1
    assert rollback_records[0].id in it.evidence_ids
    assert rollback_records[0].result.state == TruthState.SUCCESS
    assert rollback_records[0].result.value == "rb-loop-1"


# ---------------------------------------------------------------------------
# Persistence round-trip (C9)
# ---------------------------------------------------------------------------


def test_loop_record_round_trips_through_w1_json_store(tmp_path):
    harness = harness_at(tmp_path / "repo")
    run = run_loop(harness)
    path = tmp_path / "loop.json"
    JsonModelStore(path).save(run.loop)
    data = JsonModelStore(path).load()
    assert data == _convert_for_json(run.loop)
    assert data["id"] == run.loop.id
    assert data["recovered_revision"] == REVISION
    assert data["iterations"][0]["outcome"] == IterationOutcome.PROMOTED.value
    assert data["iterations"][0]["promotion"]["promotion_class"] == PromotionClass.MODEL_ONLY.value
    assert data["iterations"][0]["promotion"]["rollback"]["reference"] == "rb-loop-1"
    assert data["stop"]["reason"] == LoopStopReason.COMPLETED.value


# ---------------------------------------------------------------------------
# Bounded authority surface (C10)
# ---------------------------------------------------------------------------


def test_no_successor_stage_or_live_execution_symbols():
    import inspect
    import sos.optimization as omod

    forbidden = {
        "SelfEvolution", "MetaAdaptation", "AdversarialVerifier", "Dogfood",
        "ConstitutionMutation", "RoadmapMutation", "LiveSystemAdapter",
    }
    exported = {n for n in dir(omod) if not n.startswith("_")}
    assert not (forbidden & exported), f"forbidden successor-stage symbols: {forbidden & exported}"
    src = inspect.getsource(omod).lower()
    for token in (
        "w13", "w14", "self-evolution", "selfevolution", "meta-adapt", "dogfood",
        "subprocess", "socket", "urllib", "requests.post", "uuid4",
        "time.time", "datetime.now", "os.system", "popen", "http://", "https://",
    ):
        assert token not in src, f"forbidden token in src/sos/optimization.py: {token!r}"


def test_w12_references_frozen_authorities_without_redefining():
    import sos.assurance as assurance_mod
    import sos.autonomy as autonomy_mod
    import sos.candidates as candidates_mod
    import sos.causal as causal_mod
    import sos.evidence as evidence_mod
    import sos.execution as execution_mod
    import sos.experimentation as experimentation_mod
    import sos.model as model_mod
    import sos.optimization as omod

    assert omod.OptimizationContractError.__bases__[0] is model_mod.ModelValidationError
    assert omod.ModelValidationError is model_mod.ModelValidationError
    assert omod.TruthState is model_mod.TruthState
    assert omod.TruthfulValue is model_mod.TruthfulValue
    assert omod.Traceability is model_mod.Traceability
    assert omod.DecisionAction is model_mod.DecisionAction
    assert omod.RecoveryResult is __import__("sos.recovery", fromlist=["RecoveryResult"]).RecoveryResult
    assert omod.Evidence is evidence_mod.Evidence
    assert omod.EvidenceKind is evidence_mod.EvidenceKind
    assert omod.EvidenceProvenance is evidence_mod.EvidenceProvenance
    assert omod._build_evidence is evidence_mod._build_evidence  # the single assembly authority
    assert omod.CausalHypothesis is causal_mod.CausalHypothesis
    assert omod.CandidateProposal is candidates_mod.CandidateProposal
    assert omod.AssuranceStatus is assurance_mod.AssuranceStatus
    assert omod.assure_candidate is assurance_mod.assure_candidate
    assert omod.Experiment is experimentation_mod.Experiment
    assert omod.evaluate_experiment is experimentation_mod.evaluate_experiment
    assert omod.PromotionGate is experimentation_mod.PromotionGate
    assert omod.evaluate_autonomy is autonomy_mod.evaluate_autonomy
    assert omod.AutonomyDecision is autonomy_mod.AutonomyDecision
    assert omod.ExecutionSubstrate is execution_mod.ExecutionSubstrate
    assert omod.receipt_to_w4_evidence is execution_mod.receipt_to_w4_evidence
    # every W12-owned record belongs to this module only
    for name in (
        "OptimizationLoop", "OptimizationRun", "LoopIteration", "LoopPromotion",
        "LoopStop", "PendingAuthorization", "SimulatedObservation", "LoopStopReason",
        "IterationOutcome", "PromotionClass", "AuthorizationResolution",
    ):
        assert getattr(omod, name).__module__ == "sos.optimization", name


# ---------------------------------------------------------------------------
# Deterministic iteration state machine (required outcome 2)
# ---------------------------------------------------------------------------


def test_iteration_state_machine_rejects_free_form_transitions():
    chain = (
        IterationOutcome.PROPOSED, IterationOutcome.ASSURED, IterationOutcome.EXPERIMENTED,
        IterationOutcome.EVALUATED, IterationOutcome.DECIDED, IterationOutcome.PROMOTED,
    )
    for before, after in zip(chain, chain[1:]):
        validate_iteration_transition(before, after)
    # refusal/pause branches are lawful from their gate phases
    validate_iteration_transition(IterationOutcome.ASSURED, IterationOutcome.REFUSED)
    validate_iteration_transition(IterationOutcome.ASSURED, IterationOutcome.PAUSED_PENDING_AUTHORIZATION)
    validate_iteration_transition(IterationOutcome.DECIDED, IterationOutcome.ROLLED_BACK)
    validate_iteration_transition(IterationOutcome.DECIDED, IterationOutcome.GATHER_EVIDENCE)
    validate_iteration_transition(IterationOutcome.PROPOSED, IterationOutcome.ASSURANCE_NOT_PASSED)
    validate_iteration_transition(IterationOutcome.EVALUATED, IterationOutcome.STOPPED_BY_CONDITION)

    # skipping gates is refused
    with pytest.raises(OptimizationContractError, match="invalid iteration transition"):
        validate_iteration_transition(IterationOutcome.PROPOSED, IterationOutcome.PROMOTED)
    with pytest.raises(OptimizationContractError, match="invalid iteration transition"):
        validate_iteration_transition(IterationOutcome.ASSURED, IterationOutcome.DECIDED)
    # terminal outcomes are terminal
    with pytest.raises(OptimizationContractError, match="invalid iteration transition"):
        validate_iteration_transition(IterationOutcome.PROMOTED, IterationOutcome.ASSURED)
    with pytest.raises(OptimizationContractError, match="invalid iteration transition"):
        validate_iteration_transition(IterationOutcome.REFUSED, IterationOutcome.DECIDED)
    # non-enum states are refused
    with pytest.raises(OptimizationContractError, match="must be an IterationOutcome"):
        validate_iteration_transition("proposed", IterationOutcome.ASSURED)


def test_loop_record_enforces_terminal_outcomes_and_chain_consistency(tmp_path):
    harness = harness_at(tmp_path / "repo")
    run = run_loop(harness)

    # a non-terminal outcome cannot appear in a finished loop record
    with pytest.raises(OptimizationContractError, match="not terminal"):
        in_progress = dataclasses.replace(
            run.loop.iterations[0],
            outcome=IterationOutcome.DECIDED, promotion=None,
        )
        dataclasses.replace(run.loop, iterations=(in_progress,))

    # a promotion record cannot survive on a non-PROMOTED iteration
    with pytest.raises(OptimizationContractError):
        dataclasses.replace(run.loop.iterations[0], outcome=IterationOutcome.ROLLED_BACK)

    # a paused stop requires a paused last iteration
    with pytest.raises(OptimizationContractError, match="pending-authorization"):
        dataclasses.replace(
            run.loop,
            stop=dataclasses.replace(
                run.loop.stop,
                reason=LoopStopReason.PAUSED_FOR_AUTHORIZATION,
                pending_authorization=run.loop.iterations[0].pending_authorization,
            ),
        )


def test_loop_rejects_candidates_targeting_foreign_systems(tmp_path):
    harness = harness_at(tmp_path / "repo")
    recovery = harness.recovery
    graph = recovery.system_state.architecture
    foreign = CandidateProposal(
        id="", base_graph_ref="arch-foreign", base_graph_revision=REVISION,
        mutation=SubgraphMutation(
            kind=MutationKind.SUBGRAPH_REPLACE, base_graph_ref="arch-foreign",
            target_node_ids=(node_for(recovery, "svc_a.py"),),
            replacement_node_ids=(node_for(recovery, "svc_b.py"),),
            boundary_interface_ids=(node_for(recovery, "svc_c.py"),),
            invariants=("preserve-boundary",),
        ),
        objectives=objectives(), rationale="foreign candidate",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not proven"),
        reasoning_evidence_ids=(harness.intervention_evidence.id,),
        reasoning_hypothesis_ids=(harness.hypothesis.id,),
        risks=("rollback-risk",), traceability=tr(), provenance_revision=REVISION,
    )
    assert graph.id != "arch-foreign"
    with pytest.raises(OptimizationContractError, match="not the recovered"):
        run_loop(harness, candidates=[foreign])
