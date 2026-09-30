"""W14 — shared deterministic fixture builders for the integrated verification
program (full dogfood + adversarial verification).

Work Order: ``spec/work-orders/W14-dogfood-adversarial-verification.md``
(the authoritative mission); design in
``docs/implementation/W14-DOGFOOD-ADVERSARIAL-DESIGN.md``.

This module contains NO test functions and is not collected by pytest's
default ``test_*.py`` discovery. It builds the W14 program's fixture systems
and scenario runners as pure, deterministic, hermetic data:

- the **brownfield fixture**: a multi-component repository recovered through
  the real W3 ``recover_repository`` with deliberate preserved uncertainty
  (an unparsed manifest → UNKNOWN dependency extraction; runtime facts →
  UNAVAILABLE);
- the **greenfield-seam fixture**: a directly-constructed W2 ``SystemState`` /
  ``ArchitectureGraph`` with deterministic ids (the uuid-based
  ``SystemState.create`` and W1 ``decide`` factories are deliberately NOT
  used anywhere in the W14 program — both draw fresh non-deterministic
  identifier values and would break the C6 determinism guarantee) whose
  first governed executions go through the W11 ``ExecutionSubstrate`` with
  the stub providers;
- the shared **W1 mission/value/context authorities**, including the one
  evidence-proposed, owner-authorized mission revision step;
- the stub W11 execution providers and the W12 stub simulator (injected
  deterministic port objects — the merged test-local provider pattern);
- the two integrated scenario runners that compose the Mission-diagram chain
  W1 → W2/W3 → W4 → W5 → W6 → W7 → W8 → W9 → W10 → W11 → W12 → W13 →
  promotion/rollback → W4/W5 closure.

Everything is clock-free and random-free: fixture revisions and timestamps
are fixed caller-supplied strings, and every produced record id is
content-addressed by the merged authorities (the ``<prefix>-<sha256[:16]>``
pattern).

Determinism note for the record bundles (``scenario_bundle``): the W3
``RepositoryInventory`` carries the fixture repository's absolute root path,
which differs between two independently built fixture roots even when the
repository bytes are identical. Bundles therefore serialize the inventory
with the root normalized to a fixed placeholder; every id-relevant field
(relative paths, classifications, revision) is covered by the normalized
serialization and by the recovered ``SystemState``.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, Mapping

from sos import (
    AdapterCapability,
    AdapterPlan,
    AssuranceResult,
    AssuranceStatus,
    AutonomyDecision,
    AutonomyDecisionState,
    AutonomyRequest,
    CandidateObjective,
    CandidateProposal,
    CandidateSpace,
    CausalHypothesis,
    CausalKnowledgeGraph,
    CausalRelationType,
    Constraint,
    ConstraintClass,
    Context,
    ContextDimension,
    ContextValue,
    DecisionAction,
    EdgeType,
    Evidence,
    EvidenceGraph,
    EvidenceKind,
    EvidenceProvenance,
    EvidenceSupport,
    Experiment,
    ExperimentEvaluation,
    ExperimentMode,
    ExperimentState,
    ExecutionActionScope,
    ExecutionLifecycleState,
    ExecutionReceipt,
    ExecutionRequest,
    ExecutionSubstrate,
    Incentive,
    InterventionMetadata,
    JsonModelStore,
    Mission,
    MissionRevision,
    MissionStatus,
    MutationKind,
    Objective,
    ObjectiveDirection,
    Opportunity,
    ParetoFrontier,
    PlatformAdapter,
    PlatformPolicyConstraint,
    PlatformSurface,
    PolicyCeiling,
    PromotionDecision,
    PromotionGate,
    ProposalOrigin,
    ProviderCapability,
    ProviderUnavailableSignal,
    RecoveryResult,
    RepositoryInventory,
    RollbackPath,
    RollbackReference,
    SearchBounds,
    SearchEngine,
    SelfEvolutionContractError,
    SelfEvolutionProposal,
    SelfEvolutionState,
    SelfEvolutionStep,
    SelfImprovementHypothesis,
    SideEffect,
    SideEffectKind,
    SourceChange,
    SourceChangeKind,
    StaticEvidenceAdapter,
    StopCondition,
    SubgraphMutation,
    SubgraphReplacement,
    SupportKind,
    SystemState,
    Traceability,
    TruthState,
    TruthfulValue,
    ValueModel,
    assure_candidate,
    constrain_policy,
    evaluate_autonomy,
    evaluate_experiment,
    evaluate_personalization,
    governed_experiment,
    receipt_to_w4_evidence,
    recover_repository,
    run_optimization_loop,
    select_policy,
    transition_experiment,
    transition_self_evolution,
    validate_adapter,
)
from sos.evidence import _build_evidence
from sos.model import RevisionStatus, _convert_for_json
from sos.personalization import ContextualSelector, PolicyAlternative, PolicySelection
from sos.optimization import OptimizationRun, SimulatedObservation
from sos.graph import (
    ArchitectureGraph,
    BoundaryContract,
    GraphEdge,
    GraphNode,
    GraphUncertainty,
    NodeType,
    StateReference,
)
from sos.causal import ArchitectureMemory

# ---------------------------------------------------------------------------
# Frozen fixture constants (caller-supplied data; no clocks, no randomness)
# ---------------------------------------------------------------------------

#: Exact fixture revisions (40-hex-shaped strings, fixed data).
BROWN_REVISION = "b14fd06f1234567890abcdef1234567890abcdef"
GREEN_REVISION = "914e5eed1234567890abcdef1234567890abcdef"
SEED_REVISION = "5eedfeed1234567890abcdef1234567890abcdef"
STALE_REVISION = "57a1e5aa1234567890abcdef1234567890abcdef"
DEPLOY_CHANGED_REVISION = "d14fd06f1234567890abcdef1234567890abcdef"

#: Fixed caller-supplied timestamps (ISO-8601 strings, never wall-clock).
TS = "2030-08-01T00:00:00Z"
TS_DEPLOY_START = "2030-08-01T10:00:00Z"
TS_DEPLOY_END = "2030-08-01T10:05:00Z"
TS_MISSION_V2 = "2030-08-02T00:00:00Z"

#: Stub provider identities (test-local port objects, never product code).
PROVIDER_DEPLOY = "w14-stub-deploy-provider"
PROVIDER_OBSERVE = "w14-stub-observe-provider"

#: Governed rollback references.
ROLLBACK_REF_BROWN = "rb-w14-brown-1"
ROLLBACK_REF_GREEN = "rb-w14-green-1"
ROLLBACK_REF_SEED = "rb-w14-seed-1"
SELF_EVO_ROLLBACK_REF = "rb-w14-selfevo-1"

#: W8-typed hard stop conditions (C5 hard stops).
STOP_CONDITIONS: tuple[StopCondition, ...] = (
    StopCondition(name="error-rate", threshold=0.05, metric="error-rate"),
)

#: Inert diff-shaped payload for lawful self-evolution proposals (data only).
SELF_EVO_PAYLOAD = "@@ -1,3 +1,4 @@\n context\n-baseline\n+improved\n+governed\n"

#: The simulator id of the W14 stub simulator (identifies loop experiment
#: evidence in the final graph).
SIMULATOR_ID = "w14-stub-simulator-1"

_MISSION_AUTHORITY = "owner-1"


def tr() -> Traceability:
    """The shared W1 traceability for every W14 fixture record."""
    return Traceability(
        constitution_ref="constitution:1", mission_ref="mission:1",
        value_model_ref="value:1", context_ref="context:1",
    )


# ---------------------------------------------------------------------------
# W1 fixture authorities (mission / value model / context / policy)
# ---------------------------------------------------------------------------


def mission_v1() -> Mission:
    """The v1 mission: collaboratively formalized, ACTIVE, fully populated."""
    initial = MissionRevision(
        version=1,
        statement="Continuously improve the realization of the ledger service mission",
        status=RevisionStatus.APPROVED,
        proposed_by=_MISSION_AUTHORITY,
        decided_by=_MISSION_AUTHORITY,
        reason="initial collaborative formalization with the owner (R2)",
        created_at=TS,
    )
    mission = Mission(
        id="mission-w14-1",
        version=1,
        authority=_MISSION_AUTHORITY,
        statement="Continuously improve the realization of the ledger service mission",
        goals=("reliable ledger updates", "bounded latency", "auditable changes"),
        desired_outcomes=("ledger p95 under 200ms", "zero data loss"),
        stakeholders=("owner-1", "ledger-users", "finance-operators"),
        measures=("latency-p95", "error-rate", "recovery-time"),
        assumptions=("traffic is bursty but bounded", "single region"),
        ambiguities=("exact compliance regime",),
        status=MissionStatus.ACTIVE,
        parent_version=None,
        history=(initial,),
        traceability=tr(),
    )
    mission.validate()
    return mission


def mission_revision_from_evidence(mission: Mission, trigger_evidence_id: str) -> Mission:
    """The explicit, evidence-proposed, owner-authorized mission revision step.

    Production evidence proposes (``propose_revision`` — status becomes
    PROPOSED_REVISION, never ACTIVE); only the mission authority may approve
    (Constitution principle 7 / R3). The revision reason cites the exact W4
    evidence id that triggered the proposal.

    OBSERVATION (non-blocking, recorded for the Architect — no ``src/sos``
    change is made in W14): the merged W1 ``Mission.approve_revision``
    reconstructs the approved record via ``asdict``, which deep-converts the
    nested ``Traceability`` into a plain dict, so the RETURNED record fails
    ``Mission.validate()`` (the existing W1 suite never validates the return
    value, so this is latent). The semantic content — statement, version,
    parent chain, history, status — is intact and authoritative. This fixture
    therefore re-issues the approved record through the public W1 constructor
    with the original ``Traceability`` object, changing no field values.
    """
    proposed = mission.propose_revision(
        statement=(
            "Continuously improve the realization of the ledger service mission "
            "while keeping recovery time under five minutes"
        ),
        proposed_by="w14-evidence-cycle",
        reason=(
            "evidence-proposed revision from W4 evidence "
            f"'{trigger_evidence_id}' (telemetry may propose, never silently rewrite)"
        ),
        created_at=TS_MISSION_V2,
    )
    approved = proposed.approve_revision(approver=_MISSION_AUTHORITY)
    reissued = Mission(
        id=approved.id,
        version=approved.version,
        authority=approved.authority,
        statement=approved.statement,
        goals=approved.goals,
        desired_outcomes=approved.desired_outcomes,
        stakeholders=approved.stakeholders,
        measures=approved.measures,
        assumptions=approved.assumptions,
        ambiguities=approved.ambiguities,
        status=approved.status,
        parent_version=approved.parent_version,
        history=approved.history,
        traceability=mission.traceability,
    )
    reissued.validate()
    return reissued


def value_model(hard_constraint_description: str) -> ValueModel:
    """The fixture value model with one HARD constraint (R4)."""
    constraint = Constraint(
        id="vc-hard-1",
        name="frozen-core-component",
        class_=ConstraintClass.HARD,
        description=hard_constraint_description,
        hard=True,
        traceability=tr(),
    )
    objective = Objective(
        id="vo-1", description="minimize total operating cost", priority=1,
        traceability=tr(),
    )
    incentive = Incentive(
        id="vi-1", description="reward reliability improvements", traceability=tr(),
    )
    opportunity = Opportunity(
        id="vop-1", description="cheaper storage tier available", traceability=tr(),
    )
    model = ValueModel(
        id="value-w14-1",
        version=1,
        business_model={"model": "subscription", "margin": "regulated"},
        economic_objectives=(objective,),
        budgets={"compute": 1000.0, "storage": 500.0},
        incentives=(incentive,),
        opportunities=(opportunity,),
        constraints=(constraint,),
        traceability=tr(),
    )
    model.validate()
    return model


def context_value(dimension: ContextDimension, key: str, value: Any) -> ContextValue:
    return ContextValue(
        dimension=dimension, key=key,
        value=TruthfulValue(TruthState.SUCCESS, value, None),
    )


def context_value_state(
    dimension: ContextDimension, key: str, state: TruthState, detail: str,
) -> ContextValue:
    return ContextValue(
        dimension=dimension, key=key, value=TruthfulValue(state, None, detail),
    )


def context_record() -> Context:
    """The fixture context (R5): resolved platform/user/device dimensions."""
    context = Context(
        id="context-w14-1",
        version=1,
        values=(
            context_value(ContextDimension.PLATFORM, "surface", "web"),
            context_value(ContextDimension.USER, "cohort", "cohort-a"),
            context_value(ContextDimension.DEVICE, "class", "mobile"),
        ),
        traceability=tr(),
    )
    context.validate()
    return context


def autonomy_policy(
    *,
    allow_act: bool = True,
    allow_rollback: bool = True,
    human_approval_for_act: bool = False,
    policy_id: str = "policy-w14-1",
) -> AutonomyRequest:
    """The fixture W9 policy with explicit ceilings (R15/R22)."""
    actions: list[DecisionAction] = [DecisionAction.EXPERIMENT, DecisionAction.GATHER_EVIDENCE]
    if allow_act:
        actions.append(DecisionAction.ACT)
    if allow_rollback:
        actions.append(DecisionAction.ROLLBACK)
    policy = AutonomyRequest(
        id=policy_id,
        version=1,
        allowed_actions=tuple(actions),
        ceilings=PolicyCeiling(
            max_risk=0.3, max_blast_radius="service", require_reversible=True,
            min_confidence=0.8, require_human_approval_for_act=human_approval_for_act,
        ),
        traceability=tr(),
    )
    policy.validate()
    return policy


# ---------------------------------------------------------------------------
# W4/W5 fixture records (evidence cycle + causal knowledge)
# ---------------------------------------------------------------------------


def prov(subject: str, revision: str) -> EvidenceProvenance:
    return EvidenceProvenance(
        source="w14-fixture-harness", observed_subject=subject,
        timestamp=None, environment="simulation", implementation_revision=revision,
    )


def intervention_evidence(
    subject: str, revision: str, *, source_ref: str = "experiment-w14-77",
    kind: EvidenceKind = EvidenceKind.EXPERIMENT,
) -> Evidence:
    """Intervention-grade W4 evidence (SUCCESS) at an exact revision."""
    return _build_evidence(
        kind=kind, source_ref=source_ref, subject_ref=subject,
        result=TruthfulValue(TruthState.SUCCESS, "intervention-applied", None),
        provenance=prov(subject, revision), traceability=tr(),
        timestamp=None, environment="simulation", confidence=0.9,
        availability=TruthState.SUCCESS,
    )


def rollback_evidence(subject: str, revision: str) -> Evidence:
    return StaticEvidenceAdapter.from_static_observation(
        subject_ref=subject, observation="rollback path verified",
        result=TruthfulValue(TruthState.SUCCESS, "rollback-capable", None),
        traceability=tr(), provenance=prov(subject, revision),
    )


def suite_evidence(subject: str, revision: str) -> Evidence:
    """A W4 TEST-kind evidence record (the green suite's passing result)."""
    return StaticEvidenceAdapter.from_test_result(
        subject_ref=subject, test_name="test-suite-green",
        result=TruthfulValue(TruthState.SUCCESS, "all-tests-passed", None),
        traceability=tr(), provenance=prov(subject, revision),
    )


def stateful_evidence(
    subject: str, revision: str, state: TruthState, detail: str,
    *, kind: EvidenceKind = EvidenceKind.OBSERVATION, source_ref: str = "obs-w14-1",
) -> Evidence:
    """A W4 observation carrying an arbitrary truthful state (distinction sweep)."""
    return _build_evidence(
        kind=kind, source_ref=source_ref, subject_ref=subject,
        result=TruthfulValue(state, None, detail),
        provenance=prov(subject, revision), traceability=tr(),
        timestamp=None, environment="simulation", confidence=None,
        availability=TruthState.SUCCESS,
    )


def otel_span_evidence(subject: str, revision: str) -> Evidence:
    """An OTel-shaped span observation through the merged W4 adapter."""
    from sos import OpenTelemetryShapedAdapter

    return OpenTelemetryShapedAdapter.from_otel_span(
        span={
            "span_id": "w14-span-1",
            "status": {"code": "OK"},
            "start_time_unix_nano": "2030-08-01T00:00:00Z",
            "end_time_unix_nano": "2030-08-01T00:00:01Z",
        },
        subject_ref=subject, traceability=tr(), provenance=prov(subject, revision),
    )


def unavailable_runtime_evidence(subject: str, revision: str, dimension: str) -> Evidence:
    """An explicit UNAVAILABLE runtime gap — never synthesized into success."""
    return StaticEvidenceAdapter.unavailable_runtime_observation(
        subject_ref=subject, dimension=dimension,
        reason=f"{dimension} not observable from the fixture boundary",
        traceability=tr(), provenance=prov(subject, revision),
    )


def selfevo_experiment_evidence(graph: ArchitectureGraph, revision: str) -> Evidence:
    """The W13 stage's simulated experiment evidence (deterministic rebuild:
    content-addressed over identical material, so re-building it yields the
    identical id)."""
    return _build_evidence(
        kind=EvidenceKind.EXPERIMENT, source_ref="sim-w14-selfevo-1",
        subject_ref=graph.id,
        result=TruthfulValue(TruthState.SUCCESS, "simulated-success", None),
        provenance=prov(graph.id, revision), traceability=tr(),
        timestamp=None, environment="simulation", confidence=None,
        availability=TruthState.SUCCESS,
    )


def observation_hypothesis(observation: Evidence, revision: str) -> CausalHypothesis:
    """An OBSERVATION-backed causal hypothesis: explicitly NOT confirmed."""
    hypothesis = CausalHypothesis(
        cause_subject="svc-payments", effect_subject="svc-latency",
        relation_type=CausalRelationType.INFLUENCES, direction="negative",
        rationale="observational correlation only; intervention evidence absent",
        status="proposed",
        uncertainty=TruthfulValue(
            TruthState.UNKNOWN, None,
            "observational support only; causal efficacy not established",
        ),
        supporting_evidence=(
            EvidenceSupport(evidence_id=observation.id, support_kind=SupportKind.OBSERVATIONAL),
        ),
        traceability=tr(), provenance_revision=revision,
    )
    hypothesis.validate()
    return hypothesis


def confirmed_hypothesis(intervention: Evidence, revision: str) -> CausalHypothesis:
    """An intervention-backed, W5-authoritatively confirmed causal hypothesis."""
    support = EvidenceSupport(
        evidence_id=intervention.id, support_kind=SupportKind.INTERVENTION,
        intervention=InterventionMetadata(
            intervention_id=intervention.source_ref, intervention_kind="experiment",
            applied_at=TS, revision=revision, environment="simulation",
        ),
    )
    hypothesis = CausalHypothesis(
        cause_subject="svc-component", effect_subject="mission-outcome",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="prior intervention improved the mission outcome",
        status="proposed",
        uncertainty=TruthfulValue(TruthState.SUCCESS, "intervention-backed", None),
        supporting_evidence=(support,), traceability=tr(), provenance_revision=revision,
    )
    return hypothesis.with_status(
        "confirmed",
        known_evidence_ids={intervention.id},
        known_evidence_records={intervention.id: intervention},
    )


def learning_hypothesis_confirmed(experiment_evidence: Evidence, revision: str) -> CausalHypothesis:
    """The post-cycle learning record: a NEW confirmed hypothesis whose
    intervention support is the experiment evidence the run itself produced."""
    support = EvidenceSupport(
        evidence_id=experiment_evidence.id, support_kind=SupportKind.INTERVENTION,
        intervention=InterventionMetadata(
            intervention_id=experiment_evidence.source_ref,
            intervention_kind="experiment", applied_at=TS,
            revision=revision, environment="simulation",
        ),
    )
    hypothesis = CausalHypothesis(
        cause_subject="evolved-candidate", effect_subject="mission-outcome",
        relation_type=CausalRelationType.INFLUENCES, direction="positive",
        rationale="the governed experiment confirmed the candidate's predicted effect",
        status="proposed",
        uncertainty=TruthfulValue(TruthState.SUCCESS, "intervention-backed", None),
        supporting_evidence=(support,), traceability=tr(), provenance_revision=revision,
    )
    return hypothesis.with_status(
        "confirmed",
        known_evidence_ids={experiment_evidence.id},
        known_evidence_records={experiment_evidence.id: experiment_evidence},
    )


def learning_hypothesis_failed(failure_evidence: Evidence, revision: str) -> CausalHypothesis:
    """The failure-informed learning record: observational support from the
    verbatim FAILED deployment evidence; uncertainty stays UNKNOWN (no causal
    claim from a failed intervention)."""
    hypothesis = CausalHypothesis(
        cause_subject="evolved-candidate", effect_subject="deploy-outcome",
        relation_type=CausalRelationType.INFLUENCES, direction="negative",
        rationale="the deployment failed in the stub environment; cause not established",
        status="proposed",
        uncertainty=TruthfulValue(
            TruthState.UNKNOWN, None,
            "failure observed verbatim; causal efficacy not established",
        ),
        supporting_evidence=(
            EvidenceSupport(evidence_id=failure_evidence.id, support_kind=SupportKind.OBSERVATIONAL),
        ),
        traceability=tr(), provenance_revision=revision,
    )
    hypothesis.validate()
    return hypothesis


# ---------------------------------------------------------------------------
# W6 fixture candidates (bounded, multi-objective, boundary-preserving)
# ---------------------------------------------------------------------------


def objectives_profile(
    latency: float, cost: float, throughput: float,
) -> tuple[CandidateObjective, ...]:
    return (
        CandidateObjective(
            name="latency", direction=ObjectiveDirection.MINIMIZE,
            predicted_value=latency,
            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not measured"),
        ),
        CandidateObjective(
            name="cost", direction=ObjectiveDirection.MINIMIZE, predicted_value=cost,
            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not measured"),
        ),
        CandidateObjective(
            name="throughput", direction=ObjectiveDirection.MAXIMIZE,
            predicted_value=throughput,
            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not measured"),
        ),
    )


def make_candidate(
    *,
    base_graph_id: str,
    revision: str,
    target_node_id: str,
    replacement_node_id: str,
    boundary_node_id: str,
    reasoning_evidence_ids: tuple[str, ...],
    reasoning_hypothesis_ids: tuple[str, ...],
    objectives: tuple[CandidateObjective, ...],
    rationale: str,
    candidate_id: str = "",
) -> CandidateProposal:
    mutation = SubgraphMutation(
        kind=MutationKind.SUBGRAPH_REPLACE, base_graph_ref=base_graph_id,
        target_node_ids=(target_node_id,), replacement_node_ids=(replacement_node_id,),
        boundary_interface_ids=(boundary_node_id,),
        invariants=("preserve-boundary", "preserve-interface-contract"),
    )
    candidate = CandidateProposal(
        id=candidate_id, base_graph_ref=base_graph_id, base_graph_revision=revision,
        mutation=mutation, objectives=objectives, rationale=rationale,
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not proven"),
        reasoning_evidence_ids=tuple(reasoning_evidence_ids),
        reasoning_hypothesis_ids=tuple(reasoning_hypothesis_ids),
        risks=("rollback-risk",), traceability=tr(), provenance_revision=revision,
    )
    candidate.validate()
    return candidate


# ---------------------------------------------------------------------------
# W11 stub providers + W12 stub simulator (injected deterministic ports)
# ---------------------------------------------------------------------------


class CountingExecutionProvider:
    """A deterministic stub W11 provider that counts every execute call.

    ``deploy_outcome`` configures DEPLOY-scope receipts (SUCCESS or FAILED);
    ROLLBACK-scope always returns a governed ROLLED_BACK receipt; OBSERVE-scope
    returns a SUCCEEDED observation receipt. All provenance fields are echoed
    verbatim from the request (the W11 contract).
    """

    def __init__(
        self,
        *,
        provider_id: str = PROVIDER_DEPLOY,
        deploy_outcome: TruthState = TruthState.SUCCESS,
    ):
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
        self._deploy_outcome = deploy_outcome
        self.execute_calls = 0

    def execute(self, request: ExecutionRequest) -> ExecutionReceipt:
        self.execute_calls += 1
        echo = dict(
            request_id=request.id,
            provider_id=self.provider_id,
            action_scope=request.action_scope,
            w9_decision_id=request.w9_decision_id,
            source_revision=request.source_revision,
            provenance_revision=request.provenance_revision,
            base_graph_id=request.base_graph_id,
            base_graph_revision=request.base_graph_revision,
            environment=request.environment,
        )
        if request.action_scope == ExecutionActionScope.ROLLBACK:
            return ExecutionReceipt(
                lifecycle=ExecutionLifecycleState.ROLLED_BACK,
                outcome=TruthfulValue(
                    TruthState.SUCCESS, request.rollback_reference.reference,
                    "governed rollback completed with recovery evidence",
                ),
                started_at=TS_DEPLOY_START, finished_at=TS_DEPLOY_END,
                log_ref=f"stub-log-{request.id}",
                rollback_reference=request.rollback_reference,
                **echo,
            )
        if request.action_scope == ExecutionActionScope.OBSERVE:
            return ExecutionReceipt(
                lifecycle=ExecutionLifecycleState.SUCCEEDED,
                outcome=TruthfulValue(
                    TruthState.SUCCESS, "observation captured", None
                ),
                started_at=TS_DEPLOY_START, finished_at=TS_DEPLOY_END,
                log_ref=f"stub-log-{request.id}",
                **echo,
            )
        # DEPLOY scope
        if self._deploy_outcome == TruthState.SUCCESS:
            return ExecutionReceipt(
                lifecycle=ExecutionLifecycleState.SUCCEEDED,
                outcome=TruthfulValue(
                    TruthState.SUCCESS, "deployed to isolated stub workspace", None
                ),
                started_at=TS_DEPLOY_START, finished_at=TS_DEPLOY_END,
                side_effects=(SideEffect(
                    SideEffectKind.SERVICE_STATE, "stub-workspace",
                    "candidate mutation applied in the isolated stub workspace",
                ),),
                changed_revisions=(DEPLOY_CHANGED_REVISION,),
                log_ref=f"stub-log-{request.id}",
                rollback_reference=request.rollback_reference,
                **echo,
            )
        return ExecutionReceipt(
            lifecycle=ExecutionLifecycleState.FAILED,
            outcome=TruthfulValue(
                TruthState.FAILED, None,
                "stub deploy exited non-zero before applying changes (partial failure)",
            ),
            started_at=TS_DEPLOY_START, finished_at=TS_DEPLOY_END,
            stdout_ref=f"stub-stdout-{request.id}",
            stderr_ref=f"stub-stderr-{request.id}",
            log_ref=f"stub-log-{request.id}",
            rollback_reference=request.rollback_reference,
            **echo,
        )


class UnavailableProvider:
    """A stub provider that signals unavailability (nothing executed)."""

    def __init__(self, *, provider_id: str = PROVIDER_DEPLOY):
        self.provider_id = provider_id
        self.capabilities = frozenset({
            ProviderCapability.EXECUTE_DEPLOY,
            ProviderCapability.EXECUTE_ROLLBACK,
            ProviderCapability.EXECUTE_OBSERVE,
        })
        self.execute_calls = 0

    def execute(self, request: ExecutionRequest) -> ExecutionReceipt:
        self.execute_calls += 1
        raise ProviderUnavailableSignal(
            f"stub provider '{self.provider_id}' is unavailable (maintenance window)"
        )


class NoDeployCapabilityProvider:
    """A fully-registered provider that lacks the execute-deploy capability."""

    def __init__(self, *, provider_id: str = PROVIDER_DEPLOY):
        self.provider_id = provider_id
        self.capabilities = frozenset({
            ProviderCapability.EXECUTE_OBSERVE,
            ProviderCapability.LOG_CAPTURE,
        })
        self.execute_calls = 0

    def execute(self, request: ExecutionRequest) -> ExecutionReceipt:
        self.execute_calls += 1
        raise AssertionError("an unsupported request must never reach the provider")


class StubSimulator:
    """The W12 injected deterministic experiment simulator (port object)."""

    def __init__(
        self,
        *,
        simulator_id: str = SIMULATOR_ID,
        outcome: TruthState = TruthState.SUCCESS,
        stop_triggered: tuple[str, ...] = (),
    ):
        self.simulator_id = simulator_id
        self._outcome = outcome
        self._stop = tuple(stop_triggered)
        self.calls = 0

    def simulate(self, experiment: Experiment) -> SimulatedObservation:
        self.calls += 1
        if self._outcome == TruthState.SUCCESS:
            return SimulatedObservation(
                TruthState.SUCCESS, "simulated-success",
                "simulated canary met its success criteria",
                stop_triggered=self._stop,
            )
        return SimulatedObservation(
            self._outcome, f"simulated {self._outcome.value} experiment outcome",
            None, stop_triggered=self._stop,
        )


# ---------------------------------------------------------------------------
# The brownfield fixture (W3 recovery over a fixture repository)
# ---------------------------------------------------------------------------


def make_brownfield_repository(root: Path) -> None:
    """A multi-component service/data-store repository with deliberate gaps."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "svc_payments.py").write_text("def payments():\n    return 1\n", encoding="utf-8")
    (root / "svc_notifications.py").write_text("def notifications():\n    return 2\n", encoding="utf-8")
    (root / "svc_reports.py").write_text("def reports():\n    return 3\n", encoding="utf-8")
    (root / "store_ledger.py").write_text("LEDGER = []\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "ledger-svc"\ndependencies = ["numpy", "pydantic"]\n',
        encoding="utf-8",
    )
    # A recognised-but-unparsed manifest: deliberate UNKNOWN dependency extraction.
    (root / "setup.py").write_text(
        "from setuptools import setup\n\nsetup(name='legacy-setup')\n", encoding="utf-8"
    )
    (root / "docker-compose.yml").write_text(
        "services:\n  ledger:\n    image: ledger:1\n", encoding="utf-8"
    )
    config = root / "config"
    config.mkdir(exist_ok=True)
    (config / "settings.yaml").write_text("log_level: info\n", encoding="utf-8")
    docs = root / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "architecture.md").write_text("# architecture\n", encoding="utf-8")


def make_greenfield_seed_repository(root: Path) -> None:
    """The realized greenfield system's seed repository (W12 convergence)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "greeter.py").write_text("def greet():\n    return 'hello'\n", encoding="utf-8")
    (root / "store.py").write_text("STORE = {}\n", encoding="utf-8")
    (root / "ledger.py").write_text("LEDGER = []\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "greenfield-seed"\ndependencies = ["numpy"]\n', encoding="utf-8"
    )


def node_for(recovery: RecoveryResult, path: str) -> str:
    for node in recovery.system_state.architecture.nodes:
        if node.name == path:
            return node.id
    raise AssertionError(f"node {path!r} was not recovered")


def normalized_inventory(recovery: RecoveryResult) -> RepositoryInventory:
    """The recovered inventory with the root path normalized (see module
    docstring: the absolute root differs between fixture roots; every
    id-relevant field is preserved)."""
    return dataclasses.replace(recovery.inventory, root="<fixture-root>")


@dataclasses.dataclass
class BrownfieldHarness:
    """The deterministic brownfield fixture chain (real W3/W4/W5/W6 records)."""

    recovery: RecoveryResult
    graph: ArchitectureGraph
    node_ids: dict[str, str]
    mission: Mission
    value_model: ValueModel
    context: Context
    policy: AutonomyRequest
    intervention: Evidence
    rollback_ev: Evidence
    test_ev: Evidence
    otel_span: Evidence
    unavailable_ev: Evidence
    observation_hyp: CausalHypothesis
    confirmed_hyp: CausalHypothesis
    evidence_graph: EvidenceGraph
    known_evidence: dict[str, Evidence]
    causal_graph: CausalKnowledgeGraph
    memory_v1: ArchitectureMemory
    pareto: ParetoFrontier
    selected_candidate: CandidateProposal
    violating_candidate: CandidateProposal
    subgraph_replacement: SubgraphReplacement

    @property
    def known_hypotheses(self) -> dict[str, CausalHypothesis]:
        return {
            self.observation_hyp.id: self.observation_hyp,
            self.confirmed_hyp.id: self.confirmed_hyp,
        }


def brownfield_harness(root: Path) -> BrownfieldHarness:
    make_brownfield_repository(root)
    recovery = recover_repository(root=root, revision=BROWN_REVISION, traceability=tr())
    graph = recovery.system_state.architecture
    node_ids = {
        path: node_for(recovery, path)
        for path in (
            "svc_payments.py", "svc_notifications.py", "svc_reports.py",
            "store_ledger.py", "pyproject.toml",
        )
    }

    mission = mission_v1()
    context = context_record()
    value_model_ = value_model(
        "the payments core component "
        f"'{node_ids['svc_payments.py']}' is frozen by the value model (hard)"
    )
    policy = autonomy_policy()

    intervention = intervention_evidence(graph.id, BROWN_REVISION)
    rollback_ev = rollback_evidence(graph.id, BROWN_REVISION)
    test_ev = suite_evidence(graph.id, BROWN_REVISION)
    span = otel_span_evidence(graph.id, BROWN_REVISION)
    unavailable_ev = unavailable_runtime_evidence(graph.id, BROWN_REVISION, "runtime-deployment")

    observation_hyp = observation_hypothesis(span, BROWN_REVISION)
    confirmed_hyp = confirmed_hypothesis(intervention, BROWN_REVISION)

    evidence_graph = EvidenceGraph(
        id="w14-brown-evidence", version=1, records=(), traceability=tr()
    )
    known: dict[str, Evidence] = {}
    for record in (intervention, rollback_ev, test_ev, span, unavailable_ev):
        evidence_graph = evidence_graph.ingest(record)
        known[record.id] = record

    causal_graph = (
        CausalKnowledgeGraph(
            id="w14-brown-causal", version=1, hypotheses=(), traceability=tr()
        )
        .ingest(observation_hyp)
        .ingest(confirmed_hyp)
    )
    memory_v1 = ArchitectureMemory(
        id="w14-memory-brown-1", version=1, graph_ref=graph.id,
        hypotheses=(observation_hyp, confirmed_hyp), traceability=tr(),
    )
    memory_v1.validate(known_graph_id=graph.id)

    # Multi-objective candidate set with a genuine trade-off (Pareto, R12):
    #   fast     (latency 80,  cost 400) and
    #   cheap    (latency 200, cost 150) are mutually non-dominated;
    #   dominated(latency 300, cost 500) is dominated by both.
    fast = make_candidate(
        base_graph_id=graph.id, revision=BROWN_REVISION,
        target_node_id=node_ids["svc_notifications.py"],
        replacement_node_id=node_ids["svc_reports.py"],
        boundary_node_id=node_ids["store_ledger.py"],
        reasoning_evidence_ids=(intervention.id,),
        reasoning_hypothesis_ids=(confirmed_hyp.id,),
        objectives=objectives_profile(80.0, 400.0, 3000.0),
        rationale="fast path: minimize latency at higher cost",
    )
    cheap = make_candidate(
        base_graph_id=graph.id, revision=BROWN_REVISION,
        target_node_id=node_ids["svc_notifications.py"],
        replacement_node_id=node_ids["svc_reports.py"],
        boundary_node_id=node_ids["store_ledger.py"],
        reasoning_evidence_ids=(intervention.id,),
        reasoning_hypothesis_ids=(confirmed_hyp.id,),
        objectives=objectives_profile(200.0, 150.0, 3000.0),
        rationale="cheap path: minimize cost at higher latency",
    )
    dominated = make_candidate(
        base_graph_id=graph.id, revision=BROWN_REVISION,
        target_node_id=node_ids["svc_notifications.py"],
        replacement_node_id=node_ids["svc_reports.py"],
        boundary_node_id=node_ids["store_ledger.py"],
        reasoning_evidence_ids=(intervention.id,),
        reasoning_hypothesis_ids=(confirmed_hyp.id,),
        objectives=objectives_profile(300.0, 500.0, 2000.0),
        rationale="dominated path: worse on every objective",
    )
    pareto = ParetoFrontier.from_candidates((fast, cheap, dominated), traceability=tr())

    # The value-model-violating candidate: better objectives, but it targets
    # the hard-frozen payments core (hard constraints outrank preferences).
    violating = make_candidate(
        base_graph_id=graph.id, revision=BROWN_REVISION,
        target_node_id=node_ids["svc_payments.py"],
        replacement_node_id=node_ids["svc_reports.py"],
        boundary_node_id=node_ids["store_ledger.py"],
        reasoning_evidence_ids=(intervention.id,),
        reasoning_hypothesis_ids=(confirmed_hyp.id,),
        objectives=objectives_profile(50.0, 100.0, 5000.0),
        rationale="best raw objectives, but violates the frozen-core hard constraint",
    )
    selected = pareto.candidates[0]  # deterministic (frontier is id-sorted)

    # The W2 boundary-preserving replacement record over the same subgraph
    # (A' = A - S + S' at the W2 authority; the W6 mutation mirrors it). The
    # W2 contract is stricter than the W6 one: the boundary interfaces must
    # belong to the declared target subgraph, so the W2 target includes the
    # boundary node the W6 mutation declares adjacent to it.
    subgraph_replacement = SubgraphReplacement(
        id="w14-brown-replacement-1", base_graph_ref=graph.id,
        target_node_ids=(
            selected.mutation.target_node_ids + selected.mutation.boundary_interface_ids
        ),
        replacement_node_ids=selected.mutation.replacement_node_ids,
        boundary_interface_ids=selected.mutation.boundary_interface_ids,
        invariants=("preserve-boundary", "preserve-interface-contract"),
        traceability=tr(),
    )
    subgraph_replacement.validate(graph)

    return BrownfieldHarness(
        recovery=recovery, graph=graph, node_ids=node_ids, mission=mission,
        value_model=value_model_, context=context, policy=policy,
        intervention=intervention, rollback_ev=rollback_ev, test_ev=test_ev,
        otel_span=span, unavailable_ev=unavailable_ev,
        observation_hyp=observation_hyp, confirmed_hyp=confirmed_hyp,
        evidence_graph=evidence_graph, known_evidence=known,
        causal_graph=causal_graph, memory_v1=memory_v1, pareto=pareto,
        selected_candidate=selected, violating_candidate=violating,
        subgraph_replacement=subgraph_replacement,
    )


# ---------------------------------------------------------------------------
# The greenfield-seam fixture (W2 direct construction + W11 substrate seam)
# ---------------------------------------------------------------------------


def greenfield_graph() -> tuple[ArchitectureGraph, dict[str, str]]:
    """The initial greenfield architecture hypothesis (deterministic ids).

    Deliberate uncertainty: the graph-level uncertainty is UNKNOWN (an
    unvalidated hypothesis, R8) and the SystemState's deployment/environment
    references are UNAVAILABLE (nothing has run yet — truthful, not fabricated).
    """
    certain = GraphUncertainty(TruthState.SUCCESS, confidence=1.0)
    nodes = (
        GraphNode(
            id="w14-gf-gateway", type=NodeType.INTERFACE, name="gateway",
            attributes={"kind": "api-gateway"}, uncertainty=certain,
        ),
        GraphNode(
            id="w14-gf-greeter", type=NodeType.SERVICE, name="greeter-service",
            attributes={"kind": "service"}, uncertainty=certain,
        ),
        GraphNode(
            id="w14-gf-greeter-v2", type=NodeType.SERVICE, name="greeter-service-v2",
            attributes={"kind": "service", "role": "parameterized-alternative"},
            uncertainty=certain,
        ),
        GraphNode(
            id="w14-gf-store", type=NodeType.DATA_STORE, name="greeting-store",
            attributes={"kind": "data-store"}, uncertainty=certain,
        ),
        GraphNode(
            id="w14-gf-cap", type=NodeType.CAPABILITY, name="greeting-capability",
            attributes={"kind": "capability"}, uncertainty=certain,
        ),
    )
    edges = (
        GraphEdge(
            id="w14-gf-edge-1", type=EdgeType.CALL,
            source_id="w14-gf-gateway", target_id="w14-gf-greeter",
            attributes={}, uncertainty=certain,
        ),
        GraphEdge(
            id="w14-gf-edge-2", type=EdgeType.DATA_FLOW,
            source_id="w14-gf-greeter", target_id="w14-gf-store",
            attributes={}, uncertainty=certain,
        ),
        GraphEdge(
            id="w14-gf-edge-3", type=EdgeType.REALIZES,
            source_id="w14-gf-greeter", target_id="w14-gf-cap",
            attributes={}, uncertainty=certain,
        ),
    )
    contracts = (
        BoundaryContract(
            id="w14-gf-bc-1", interface_node_id="w14-gf-gateway",
            contract="HTTP JSON greeting API",
            invariants=("status-code-200", "schema-stable"), uncertainty=certain,
        ),
    )
    graph = ArchitectureGraph(
        id="w14-gf-arch-1", version=1, nodes=nodes, edges=edges,
        boundary_contracts=contracts,
        uncertainty=GraphUncertainty(
            TruthState.UNKNOWN,
            reason="greenfield architecture is an unvalidated hypothesis (R8)",
        ),
        traceability=tr(),
    )
    graph.validate()
    return graph, {
        "gateway": "w14-gf-gateway", "greeter": "w14-gf-greeter",
        "greeter_v2": "w14-gf-greeter-v2", "store": "w14-gf-store",
        "capability": "w14-gf-cap",
    }


def greenfield_system_state(graph: ArchitectureGraph) -> SystemState:
    """The greenfield SystemState v1, directly constructed with fixed ids.

    ``SystemState.create`` is deliberately NOT used: it draws fresh
    non-deterministic identifier values for ``id``/``revision_id`` and would
    break the W14 determinism guarantee. Direct construction through the
    public dataclass is deterministic and runs the full ``validate()``
    contract.
    """
    state = SystemState(
        id="w14-gf-state-1", version=1, architecture_ref=graph.id,
        implementation_ref=StateReference(
            TruthfulValue(TruthState.SUCCESS, GREEN_REVISION, None)
        ),
        configuration_ref=StateReference(TruthfulValue(
            TruthState.UNKNOWN, None, "no static configuration artifacts yet (greenfield)"
        )),
        deployment_ref=StateReference(TruthfulValue(
            TruthState.UNAVAILABLE, None, "greenfield system not yet deployed"
        )),
        policy_ref=StateReference(TruthfulValue(
            TruthState.UNKNOWN, None, "no static policy artifacts yet (greenfield)"
        )),
        environment_ref=StateReference(TruthfulValue(
            TruthState.UNAVAILABLE, None, "greenfield runtime environment not yet observable"
        )),
        active_experiments=(), architecture=graph, traceability=tr(),
        revision_id="w14-gf-rev-1", parent_revision_id=None,
    )
    state.validate()
    return state


@dataclasses.dataclass
class GreenfieldHarness:
    """The deterministic greenfield-seam fixture chain (pre-execution)."""

    system_state: SystemState
    graph: ArchitectureGraph
    node_ids: dict[str, str]
    mission: Mission
    value_model: ValueModel
    context: Context
    policy: AutonomyRequest
    prior_canary: Evidence
    test_ev: Evidence
    otel_span: Evidence
    rollback_ev: Evidence
    unavailable_ev: Evidence
    observation_hyp: CausalHypothesis
    confirmed_hyp: CausalHypothesis
    evidence_graph: EvidenceGraph
    known_evidence: dict[str, Evidence]
    causal_graph: CausalKnowledgeGraph
    memory_v1: ArchitectureMemory
    generated_frontier: ParetoFrontier
    pareto: ParetoFrontier
    selected_candidate: CandidateProposal
    violating_candidate: CandidateProposal
    assurance: AssuranceResult
    experiment: Experiment
    experiment_evidence: Evidence
    rollback_path: RollbackPath
    evaluation: ExperimentEvaluation
    gate_decision: PromotionDecision

    @property
    def known_hypotheses(self) -> dict[str, CausalHypothesis]:
        return {
            self.observation_hyp.id: self.observation_hyp,
            self.confirmed_hyp.id: self.confirmed_hyp,
        }


def greenfield_harness() -> GreenfieldHarness:
    graph, node_ids = greenfield_graph()
    state = greenfield_system_state(graph)

    mission = mission_v1()
    context = context_record()
    value_model_ = value_model(
        "the greeting data store "
        f"'{node_ids['store']}' is frozen by the value model (hard)"
    )
    policy = autonomy_policy()

    # A prior prototype canary (intervention-grade) from the collaborative
    # formalization phase — the causal PRIOR the greenfield entry starts from.
    prior_canary = intervention_evidence(
        graph.id, GREEN_REVISION, source_ref="prototype-canary-w14-1",
        kind=EvidenceKind.CANARY,
    )
    test_ev = suite_evidence(graph.id, GREEN_REVISION)
    span = otel_span_evidence(graph.id, GREEN_REVISION)
    rollback_ev = rollback_evidence(graph.id, GREEN_REVISION)
    unavailable_ev = unavailable_runtime_evidence(graph.id, GREEN_REVISION, "runtime-deployment")

    observation_hyp = observation_hypothesis(span, GREEN_REVISION)
    confirmed_hyp = confirmed_hypothesis(prior_canary, GREEN_REVISION)

    evidence_graph = EvidenceGraph(
        id="w14-green-evidence", version=1, records=(), traceability=tr()
    )
    known: dict[str, Evidence] = {}
    for record in (prior_canary, test_ev, span, rollback_ev, unavailable_ev):
        evidence_graph = evidence_graph.ingest(record)
        known[record.id] = record

    causal_graph = (
        CausalKnowledgeGraph(
            id="w14-green-causal", version=1, hypotheses=(), traceability=tr()
        )
        .ingest(observation_hyp)
        .ingest(confirmed_hyp)
    )
    memory_v1 = ArchitectureMemory(
        id="w14-memory-green-1", version=1, graph_ref=graph.id,
        hypotheses=(observation_hyp, confirmed_hyp), traceability=tr(),
    )
    memory_v1.validate(known_graph_id=graph.id)

    # Bounded search through the REAL W6 SearchEngine (the greenfield graph
    # carries an INTERFACE node, so boundaries resolve).
    space = CandidateSpace(
        base_graph=graph, base_graph_revision=GREEN_REVISION, traceability=tr(),
        reasoning_evidence_ids=(prior_canary.id,),
        reasoning_hypothesis_ids=(confirmed_hyp.id,),
        available_replacements=((node_ids["greeter"], node_ids["greeter_v2"]),),
    )
    engine = SearchEngine(bounds=SearchBounds(3, 2, 5))
    generated_frontier = engine.search(space)

    fast = make_candidate(
        base_graph_id=graph.id, revision=GREEN_REVISION,
        target_node_id=node_ids["greeter"], replacement_node_id=node_ids["greeter_v2"],
        boundary_node_id=node_ids["gateway"],
        reasoning_evidence_ids=(prior_canary.id,),
        reasoning_hypothesis_ids=(confirmed_hyp.id,),
        objectives=objectives_profile(90.0, 350.0, 2800.0),
        rationale="greenfield fast path: minimize latency at higher cost",
    )
    cheap = make_candidate(
        base_graph_id=graph.id, revision=GREEN_REVISION,
        target_node_id=node_ids["greeter"], replacement_node_id=node_ids["greeter_v2"],
        boundary_node_id=node_ids["gateway"],
        reasoning_evidence_ids=(prior_canary.id,),
        reasoning_hypothesis_ids=(confirmed_hyp.id,),
        objectives=objectives_profile(180.0, 120.0, 2800.0),
        rationale="greenfield cheap path: minimize cost at higher latency",
    )
    dominated = make_candidate(
        base_graph_id=graph.id, revision=GREEN_REVISION,
        target_node_id=node_ids["greeter"], replacement_node_id=node_ids["greeter_v2"],
        boundary_node_id=node_ids["gateway"],
        reasoning_evidence_ids=(prior_canary.id,),
        reasoning_hypothesis_ids=(confirmed_hyp.id,),
        objectives=objectives_profile(290.0, 450.0, 1900.0),
        rationale="greenfield dominated path: worse on every objective",
    )
    pareto = ParetoFrontier.from_candidates((fast, cheap, dominated), traceability=tr())
    selected = pareto.candidates[0]
    violating = make_candidate(
        base_graph_id=graph.id, revision=GREEN_REVISION,
        target_node_id=node_ids["store"], replacement_node_id=node_ids["greeter_v2"],
        boundary_node_id=node_ids["gateway"],
        reasoning_evidence_ids=(prior_canary.id,),
        reasoning_hypothesis_ids=(confirmed_hyp.id,),
        objectives=objectives_profile(40.0, 90.0, 5100.0),
        rationale="best raw objectives, but targets the frozen greeting store",
    )

    # W7: the real assurance engine over the greenfield candidate.
    assurance = assure_candidate(
        candidate=selected, base_graph=graph, known_evidence=dict(known),
        known_hypotheses={confirmed_hyp.id: confirmed_hyp},
        hard_constraints=(value_model_.constraints[0].description,),
        rollback_evidence_ids=(rollback_ev.id,),
    )
    if assurance.status != AssuranceStatus.PASS:
        raise AssertionError(
            f"fixture integrity: real W7 engine must PASS the greenfield "
            f"candidate (got {assurance.status.value})"
        )

    # W8: the governed experiment lifecycle to COMPLETED (simulator SUCCESS).
    experiment = governed_experiment(
        assurance=assurance, candidate=selected, rollback_ref=ROLLBACK_REF_GREEN,
        traceability=tr(), stop_conditions=STOP_CONDITIONS, mode=ExperimentMode.SHADOW,
        observation_window=("2030-08-01T00:00:00Z", "2030-08-02T00:00:00Z"),
    )
    experiment = transition_experiment(experiment, ExperimentState.READY, known_assurance=assurance)
    experiment = transition_experiment(experiment, ExperimentState.RUNNING, known_assurance=assurance)
    experiment_evidence = _build_evidence(
        kind=EvidenceKind.EXPERIMENT, source_ref="sim-w14-green-1",
        subject_ref=graph.id,
        result=TruthfulValue(TruthState.SUCCESS, "simulated-success", None),
        provenance=prov(graph.id, GREEN_REVISION), traceability=tr(),
        timestamp=None, environment="simulation", confidence=None,
        availability=TruthState.SUCCESS,
    )
    known[experiment_evidence.id] = experiment_evidence
    experiment = transition_experiment(experiment, ExperimentState.COMPLETED, known_assurance=assurance)
    rollback_path = RollbackPath(
        reference=ROLLBACK_REF_GREEN, evidence_ids=(rollback_ev.id,),
        detail="governed rollback path bound to the experiment rollback reference",
    )
    evaluation = evaluate_experiment(
        experiment, known_evidence=dict(known),
        evidence_refs=(experiment_evidence.id,), evaluation_success=True,
        known_assurance=assurance, rollback_path=rollback_path,
    )
    gate_decision = PromotionGate().evaluate(experiment, evaluation, known_assurance=assurance)

    return GreenfieldHarness(
        system_state=state, graph=graph, node_ids=node_ids, mission=mission,
        value_model=value_model_, context=context, policy=policy,
        prior_canary=prior_canary, test_ev=test_ev, otel_span=span,
        rollback_ev=rollback_ev, unavailable_ev=unavailable_ev,
        observation_hyp=observation_hyp, confirmed_hyp=confirmed_hyp,
        evidence_graph=evidence_graph, known_evidence=known,
        causal_graph=causal_graph, memory_v1=memory_v1,
        generated_frontier=generated_frontier, pareto=pareto,
        selected_candidate=selected, violating_candidate=violating,
        assurance=assurance, experiment=experiment,
        experiment_evidence=experiment_evidence, rollback_path=rollback_path,
        evaluation=evaluation, gate_decision=gate_decision,
    )


# ---------------------------------------------------------------------------
# W9/W11 fixture helpers over the greenfield harness (real engines)
# ---------------------------------------------------------------------------


def gather_decision_for(harness: GreenfieldHarness) -> AutonomyDecision:
    return evaluate_autonomy(
        policy=harness.policy, action=DecisionAction.GATHER_EVIDENCE,
        assurance=None, experiment=None, promotion=None,
        evidence_ids=(harness.otel_span.id,), traceability=tr(),
        known_evidence=harness.known_evidence, human_authority_present=False,
        blast_radius="limited", risk=0.1, confidence=0.9, reversible=True,
    )


def act_decision_for(
    harness: GreenfieldHarness, *, policy: AutonomyRequest | None = None,
) -> AutonomyDecision:
    return evaluate_autonomy(
        policy=policy if policy is not None else harness.policy,
        action=DecisionAction.ACT,
        assurance=harness.assurance, experiment=harness.experiment,
        promotion=harness.gate_decision, evaluation=harness.evaluation,
        evidence_ids=tuple(harness.evaluation.evidence_ids), traceability=tr(),
        known_evidence=harness.known_evidence, human_authority_present=False,
        blast_radius="limited", risk=0.1, confidence=0.9, reversible=True,
    )


def ask_decision_for(harness: GreenfieldHarness) -> AutonomyDecision:
    """A real W9 ASK decision (human approval required, not present)."""
    return evaluate_autonomy(
        policy=autonomy_policy(human_approval_for_act=True),
        action=DecisionAction.ACT,
        assurance=harness.assurance, experiment=harness.experiment,
        promotion=harness.gate_decision, evaluation=harness.evaluation,
        evidence_ids=tuple(harness.evaluation.evidence_ids), traceability=tr(),
        known_evidence=harness.known_evidence, human_authority_present=False,
        blast_radius="limited", risk=0.1, confidence=0.9, reversible=True,
    )


def self_authorizing_act_decision_for(
    harness: GreenfieldHarness, provider_id: str,
) -> AutonomyDecision:
    """A real W9 ACT decision issued under a PROVIDER-OWNED policy id (the
    provider self-authorization attack surface — R22)."""
    return act_decision_for(harness, policy=autonomy_policy(policy_id=provider_id))


def rollback_decision_for(
    harness: GreenfieldHarness, experiment: Experiment | None = None,
) -> AutonomyDecision:
    experiment = harness.experiment if experiment is None else experiment
    return evaluate_autonomy(
        policy=harness.policy, action=DecisionAction.ROLLBACK,
        assurance=harness.assurance, experiment=experiment, promotion=None,
        evaluation=harness.evaluation,
        evidence_ids=tuple(harness.evaluation.evidence_ids), traceability=tr(),
        known_evidence=harness.known_evidence, human_authority_present=False,
        blast_radius="limited", risk=0.1, confidence=0.9, reversible=True,
        rollback_path=harness.rollback_path,
    )


def governed_rollback_reference(harness: GreenfieldHarness) -> RollbackReference:
    return RollbackReference(
        reference=harness.rollback_path.reference,
        evidence_ids=tuple(harness.rollback_path.evidence_ids),
        detail=harness.rollback_path.detail,
    )


def execution_request_for(
    decision: AutonomyDecision,
    harness: GreenfieldHarness,
    *,
    scope: ExecutionActionScope,
    provider_id: str,
    **overrides: Any,
) -> ExecutionRequest:
    """Build a W11 request bound to the harness chain (echoes decision refs).

    ``overrides`` replace any field (the adversarial injection seam); fields
    explicitly set to ``None`` fall back to the dataclass default, which is
    how "missing reference" injections are expressed.
    """
    fields: dict[str, Any] = dict(
        intent=f"w14 governed {scope.value} through the greenfield seam",
        action_scope=scope,
        provider_id=provider_id,
        source_revision=GREEN_REVISION,
        provenance_revision=GREEN_REVISION,
        base_graph_id=harness.graph.id,
        base_graph_revision=GREEN_REVISION,
        environment="greenfield-stub",
        w9_decision_id=decision.id,
        traceability=tr(),
        w7_assurance_id=decision.assurance_id or "",
        w8_experiment_id=decision.experiment_id,
        w8_promotion_ref=decision.promotion_id,
        rollback_reference=(
            governed_rollback_reference(harness)
            if scope in (ExecutionActionScope.DEPLOY, ExecutionActionScope.ROLLBACK)
            else None
        ),
    )
    fields.update(overrides)
    fields = {k: v for k, v in fields.items() if v is not None}
    return ExecutionRequest(**fields)


def substrate_for(
    provider: Any,
    harness: GreenfieldHarness,
    *decisions: AutonomyDecision,
) -> ExecutionSubstrate:
    return ExecutionSubstrate(
        providers={provider.provider_id: provider},
        known_decisions={d.id: d for d in decisions},
        known_assurance={harness.assurance.id: harness.assurance},
        known_experiments={harness.experiment.id: harness.experiment},
    )


# ---------------------------------------------------------------------------
# The W10 fixture stage (contextual + platform narrowing over a W9 decision)
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class W10Stage:
    selector: ContextualSelector
    alternative: PolicyAlternative
    selection: PolicySelection
    adapter: PlatformAdapter
    adapter_plan: AdapterPlan
    constraint: PlatformPolicyConstraint
    personalization: Any  # PersonalizationDecision


def run_w10_stage(policy: AutonomyRequest, act_decision: AutonomyDecision) -> W10Stage:
    """Contextual/platform narrowing over a resolved W9 ACT decision.

    The supplied context resolves every declared alternative dimension and
    carries only SUCCESS truth states, so the inherited ACT state is preserved
    (narrowing is monotonic: it may only restrict, never widen). The platform
    constraint narrows the allowed actions to (ACT, GATHER_EVIDENCE) — ACT
    remains lawful, direct ROLLBACK does not.
    """
    selector = ContextualSelector(
        id="w14-selector-1", version=1,
        dimensions=(
            context_value(ContextDimension.PLATFORM, "surface", "web"),
            context_value(ContextDimension.USER, "cohort", "cohort-a"),
            context_value(ContextDimension.DEVICE, "class", "mobile"),
        ),
        traceability=tr(),
    )
    declared = ContextualSelector(
        id="w14-alt-declared-1", version=1,
        dimensions=(
            context_value(ContextDimension.PLATFORM, "surface", "web"),
            context_value(ContextDimension.USER, "cohort", "cohort-a"),
        ),
        traceability=tr(),
    )
    alternative = PolicyAlternative(
        id="w14-alt-web-1", policy=policy, selector=declared, priority=0,
    )
    selection = select_policy(
        alternatives=(alternative,), selector=selector,
        w9_decision_state=AutonomyDecisionState.ACT, traceability=tr(),
    )

    adapter = PlatformAdapter(
        id="w14-adapter-web-1", version=1, surface=PlatformSurface.WEB,
        capabilities=(
            AdapterCapability(name="execute-deploy", supported=True),
            AdapterCapability(name="revision-pinning", supported=True),
            AdapterCapability(name="execute-rollback", supported=False),
            AdapterCapability(name="log-capture", supported=True),
        ),
        traceability=tr(),
    )
    adapter_plan = validate_adapter(
        adapter, required_capabilities=("execute-deploy", "revision-pinning")
    )
    constraint = constrain_policy(
        adapter,
        source_policy=policy,
        narrowed_allowed_actions=(DecisionAction.ACT, DecisionAction.GATHER_EVIDENCE),
        narrowed_ceilings=PolicyCeiling(
            max_risk=0.2, max_blast_radius="limited", require_reversible=True,
            min_confidence=0.85, require_human_approval_for_act=False,
        ),
        constraint_id="w14-platform-constraint-1", version=1,
    )
    personalization = evaluate_personalization(
        policy=policy, selector=selector,
        w9_decision_state=AutonomyDecisionState.ACT,
        w9_decision_id=act_decision.id,
        evidence_ids=tuple(act_decision.evidence_ids),
        alternatives=("w14-alt-web-1",),
        constraints=("surface=web narrows rollback; act preserved",),
        traceability=tr(),
    )
    return W10Stage(
        selector=selector, alternative=alternative, selection=selection,
        adapter=adapter, adapter_plan=adapter_plan, constraint=constraint,
        personalization=personalization,
    )


# ---------------------------------------------------------------------------
# The W13 fixture stage (self-evolution boundary check + lawful chain)
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class SelfEvolutionStage:
    citation_candidate: CandidateProposal
    proposal: SelfEvolutionProposal
    promoted: SelfEvolutionProposal
    steps: tuple[SelfEvolutionStep, ...]
    evidence: tuple[Evidence, ...]
    assurance: AssuranceResult
    experiment: Experiment
    evaluation: ExperimentEvaluation
    gate_decision: PromotionDecision
    rollback_path: RollbackPath
    act_decision: AutonomyDecision
    refusal_error: SelfEvolutionContractError | None
    refusal_evidence: Evidence


def attempt_frozen_authority_proposal(revision: str) -> SelfEvolutionContractError | None:
    """Attempt a self-evolution change against the Constitution (case 13).

    Returns the typed construction refusal when the merged W13 boundary
    contract holds (the expected governed outcome), or None if it does not.
    """
    try:
        SourceChange(
            path="spec/constitution.md", base_revision=revision,
            kind=SourceChangeKind.MODIFY, payload=SELF_EVO_PAYLOAD,
        )
    except SelfEvolutionContractError as exc:
        return exc
    return None


def run_self_evolution_stage(
    graph: ArchitectureGraph,
    revision: str,
    *,
    trigger_evidence: Evidence,
    rollback_evidence: Evidence,
    hypothesis: CausalHypothesis,
    target_node_id: str,
    replacement_node_id: str,
    boundary_node_id: str,
    policy: AutonomyRequest,
    target_path: str = "src/sos/optimization.py",
) -> SelfEvolutionStage:
    """The lawful W13 chain: a real proposal advancing through the real W7/W8/W9
    gates to PROMOTED-as-data, plus the frozen-authority refusal record."""
    citation = make_candidate(
        base_graph_id=graph.id, revision=revision,
        target_node_id=target_node_id, replacement_node_id=replacement_node_id,
        boundary_node_id=boundary_node_id,
        reasoning_evidence_ids=(trigger_evidence.id,),
        reasoning_hypothesis_ids=(hypothesis.id,),
        objectives=objectives_profile(120.0, 300.0, 2500.0),
        rationale="self-evolution citation candidate (provenance seam)",
    )
    proposal = SelfEvolutionProposal(
        target_revision=revision, target_paths=(target_path,),
        changes=(SourceChange(
            path=target_path, base_revision=revision,
            kind=SourceChangeKind.MODIFY, payload=SELF_EVO_PAYLOAD,
        ),),
        hypothesis=SelfImprovementHypothesis(
            rationale="the governed optimization loop's search ordering is latency-dominated",
            trigger_evidence_ids=(trigger_evidence.id,),
            predicted_effects=("self-evolution lowers the loop's search latency",),
            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted, not proven"),
            causal_hypothesis_ids=(hypothesis.id,),
        ),
        origin=ProposalOrigin.MODEL_GENERATED,
        rollback_ref=SELF_EVO_ROLLBACK_REF, meta_depth=0,
        candidate_ref=citation.id, traceability=tr(),
    )
    # The W6 projection carrying the proposal's explicit id, so the real W7
    # result binds to the exact proposal chain (the W13 test precedent).
    projection = make_candidate(
        base_graph_id=graph.id, revision=revision,
        target_node_id=target_node_id, replacement_node_id=replacement_node_id,
        boundary_node_id=boundary_node_id,
        reasoning_evidence_ids=(trigger_evidence.id,),
        reasoning_hypothesis_ids=(hypothesis.id,),
        objectives=objectives_profile(120.0, 300.0, 2500.0),
        rationale="self-evolution candidate projection",
        candidate_id=proposal.id,
    )
    known: dict[str, Evidence] = {
        trigger_evidence.id: trigger_evidence,
        rollback_evidence.id: rollback_evidence,
    }
    assurance = assure_candidate(
        candidate=projection, base_graph=graph, known_evidence=dict(known),
        known_hypotheses={hypothesis.id: hypothesis},
        rollback_evidence_ids=(rollback_evidence.id,),
    )
    if assurance.status != AssuranceStatus.PASS:
        raise AssertionError(
            f"fixture integrity: real W7 engine must PASS the projection "
            f"(got {assurance.status.value})"
        )
    experiment = Experiment(
        id="", candidate_id=proposal.id, assurance_result_id=assurance.id,
        base_graph_id=graph.id, base_graph_revision=revision,
        provenance_revision=revision, mode=ExperimentMode.SHADOW,
        scope=(proposal.id,),
        observation_window=("2030-08-01T00:00:00Z", "2030-08-02T00:00:00Z"),
        success_criteria=("objectives-not-dominated",),
        stop_conditions=STOP_CONDITIONS, rollback_ref=SELF_EVO_ROLLBACK_REF,
        traceability=tr(),
    )
    experiment.validate(known_assurance=assurance)
    experiment = transition_experiment(experiment, ExperimentState.READY, known_assurance=assurance)
    experiment = transition_experiment(experiment, ExperimentState.RUNNING, known_assurance=assurance)
    experiment_evidence = selfevo_experiment_evidence(graph, revision)
    known[experiment_evidence.id] = experiment_evidence
    experiment = transition_experiment(experiment, ExperimentState.COMPLETED, known_assurance=assurance)
    rollback_path = RollbackPath(
        reference=SELF_EVO_ROLLBACK_REF, evidence_ids=(rollback_evidence.id,),
        detail="governed rollback bound to the proposal's declared reference",
    )
    evaluation = evaluate_experiment(
        experiment, known_evidence=dict(known),
        evidence_refs=(experiment_evidence.id,), evaluation_success=True,
        known_assurance=assurance, rollback_path=rollback_path,
    )
    gate_decision = PromotionGate().evaluate(experiment, evaluation, known_assurance=assurance)
    act_decision = evaluate_autonomy(
        policy=policy, action=DecisionAction.ACT, assurance=assurance,
        experiment=experiment, promotion=gate_decision, evaluation=evaluation,
        evidence_ids=tuple(evaluation.evidence_ids), traceability=tr(),
        known_evidence=dict(known), human_authority_present=False,
        blast_radius="limited", risk=0.1, confidence=0.9, reversible=True,
    )
    registries: dict[str, Mapping[str, Any]] = dict(
        known_assurance={assurance.id: assurance},
        known_experiments={experiment.id: experiment},
        known_evaluations={evaluation.id: evaluation},
        known_promotions={f"{experiment.id}:{evaluation.id}": gate_decision},
        known_decisions={act_decision.id: act_decision},
        known_evidence=dict(known),
        known_proposals={},
        known_hypotheses={hypothesis.id: hypothesis},
        known_candidates={citation.id: citation},
    )
    steps: list[SelfEvolutionStep] = []
    evidence: list[Evidence] = []
    result = transition_self_evolution(
        proposal, SelfEvolutionState.UNDER_ASSURANCE, **registries, timestamp=TS,
    )
    steps.append(result.step); evidence.append(result.evidence)
    result = transition_self_evolution(
        result.proposal, SelfEvolutionState.UNDER_EXPERIMENT, **registries,
        assurance_result_id=assurance.id, timestamp=TS,
    )
    steps.append(result.step); evidence.append(result.evidence)
    result = transition_self_evolution(
        result.proposal, SelfEvolutionState.UNDER_AUTHORITY, **registries,
        experiment_id=experiment.id, evaluation_id=evaluation.id,
        promotion_id=f"{experiment.id}:{evaluation.id}",
        rollback_path=rollback_path, timestamp=TS,
    )
    steps.append(result.step); evidence.append(result.evidence)
    result = transition_self_evolution(
        result.proposal, SelfEvolutionState.PROMOTED, **registries,
        autonomy_decision_id=act_decision.id, rollback_path=rollback_path,
        adoption_revision=None, timestamp=TS,
    )
    steps.append(result.step); evidence.append(result.evidence)

    refusal_error = attempt_frozen_authority_proposal(revision)
    refusal_evidence = StaticEvidenceAdapter.from_static_observation(
        subject_ref=graph.id,
        observation="self-evolution boundary refusal: constitution target",
        result=TruthfulValue(
            TruthState.FAILED, None,
            "SelfEvolutionContractError: target path 'spec/constitution.md' is a "
            "frozen authority artifact; the violation is recorded as evidence and "
            "never applied",
        ),
        traceability=tr(), provenance=prov(graph.id, revision),
    )
    return SelfEvolutionStage(
        citation_candidate=citation, proposal=proposal, promoted=result.proposal,
        steps=tuple(steps), evidence=tuple(evidence), assurance=assurance,
        experiment=experiment, evaluation=evaluation, gate_decision=gate_decision,
        rollback_path=rollback_path, act_decision=act_decision,
        refusal_error=refusal_error, refusal_evidence=refusal_evidence,
    )


# ---------------------------------------------------------------------------
# Scenario 1 — the brownfield integrated dogfood (ends in governed promotion)
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class BrownfieldScenario:
    mission_v1: Mission
    mission_v2: Mission
    value_model: ValueModel
    context: Context
    policy: AutonomyRequest
    harness: BrownfieldHarness
    run: OptimizationRun
    provider: CountingExecutionProvider
    act_decision: AutonomyDecision
    w10: W10Stage
    selfevo: SelfEvolutionStage
    evidence_graph: EvidenceGraph
    learning_hypothesis: CausalHypothesis
    memory_v2: ArchitectureMemory

    @property
    def graph(self) -> ArchitectureGraph:
        return self.harness.graph


def run_brownfield_scenario(
    root: Path,
    *,
    deploy_outcome: TruthState = TruthState.SUCCESS,
    simulator_outcome: TruthState = TruthState.SUCCESS,
    policy: AutonomyRequest | None = None,
    provider: CountingExecutionProvider | None = None,
) -> BrownfieldScenario:
    """The brownfield Mission-diagram chain, ending in governed promotion.

    Stages: W1 mission/value/context (+ evidence-proposed owner-authorized
    revision) → W2/W3 recovery with preserved uncertainty → W4 evidence cycle
    → W5 causal knowledge → W6 multi-objective candidates + Pareto + W2
    boundary replacement → W12 loop composing W7 assurance, W9 gates, W8
    experiment/promotion, W11 governed deployment (stub provider) → W10
    narrowing over the ACT decision → W13 boundary check → closure (learning
    record + evidence-cycle closure).

    With ``deploy_outcome=FAILED`` the same chain ends in a governed rollback
    (the ADV-16 partial-failure configuration).
    """
    harness = brownfield_harness(root)
    mission_v2 = mission_revision_from_evidence(harness.mission, harness.intervention.id)
    policy_ = policy if policy is not None else harness.policy

    provider_ = provider if provider is not None else CountingExecutionProvider(
        deploy_outcome=deploy_outcome,
    )
    run = run_optimization_loop(
        recovery=harness.recovery,
        candidates=(harness.violating_candidate, harness.selected_candidate),
        policy=policy_,
        simulator=StubSimulator(outcome=simulator_outcome),
        traceability=tr(),
        max_iterations=4,
        stop_conditions=STOP_CONDITIONS,
        evidence_graph=harness.evidence_graph,
        causal_graph=harness.causal_graph,
        hard_constraints=(harness.value_model.constraints[0].description,),
        rollback_ref=ROLLBACK_REF_BROWN,
        rollback_evidence_ids=(harness.rollback_ev.id,),
        execution_providers={provider_.provider_id: provider_},
        execution_provider_id=provider_.provider_id,
    )

    # The W9 ACT decision that authorized the governed deployment.
    act_decision = next(
        d for d in run.decisions if d.state == AutonomyDecisionState.ACT
    )
    w10 = run_w10_stage(policy_, act_decision)
    selfevo = run_self_evolution_stage(
        harness.graph, BROWN_REVISION,
        trigger_evidence=harness.intervention,
        rollback_evidence=harness.rollback_ev,
        hypothesis=harness.confirmed_hyp,
        target_node_id=harness.node_ids["svc_notifications.py"],
        replacement_node_id=harness.node_ids["svc_reports.py"],
        boundary_node_id=harness.node_ids["store_ledger.py"],
        policy=policy_,
    )

    # Evidence-cycle closure: the refusal record and every W13 step record
    # join the run's evidence graph (verbatim, content-addressed).
    evidence_graph = run.evidence_graph
    for record in (selfevo.refusal_evidence, *selfevo.evidence):
        evidence_graph = evidence_graph.ingest(record)

    # The learning record (W19/R19): a NEW causal hypothesis whose support is
    # the experiment evidence the run itself produced. A SUCCESS experiment
    # yields a confirmed (intervention-backed) hypothesis; a FAILED one yields
    # a failure-informed observational hypothesis with UNKNOWN uncertainty.
    loop_experiment_evidence = next(
        r for r in evidence_graph.records
        if r.kind == EvidenceKind.EXPERIMENT
        and r.source_ref.startswith(SIMULATOR_ID)
        and r.provenance.implementation_revision == BROWN_REVISION
    )
    if loop_experiment_evidence.result.state == TruthState.SUCCESS:
        learning = learning_hypothesis_confirmed(loop_experiment_evidence, BROWN_REVISION)
    else:
        learning = learning_hypothesis_failed(loop_experiment_evidence, BROWN_REVISION)
    memory_v2 = ArchitectureMemory(
        id="w14-memory-brown-2", version=2, graph_ref=harness.graph.id,
        hypotheses=(harness.observation_hyp, harness.confirmed_hyp, learning),
        traceability=tr(),
    )
    memory_v2.validate(
        known_graph_id=harness.graph.id,
        known_evidence_ids={r.id for r in evidence_graph.records},
    )
    return BrownfieldScenario(
        mission_v1=harness.mission, mission_v2=mission_v2,
        value_model=harness.value_model, context=harness.context, policy=policy_,
        harness=harness, run=run, provider=provider_, act_decision=act_decision,
        w10=w10, selfevo=selfevo, evidence_graph=evidence_graph,
        learning_hypothesis=learning, memory_v2=memory_v2,
    )


# ---------------------------------------------------------------------------
# Scenario 2 — the greenfield-seam integrated dogfood (ends in governed rollback)
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class GreenfieldScenario:
    mission: Mission
    value_model: ValueModel
    context: Context
    policy: AutonomyRequest
    harness: GreenfieldHarness
    gather_decision: AutonomyDecision
    observe_provider: CountingExecutionProvider
    observe_receipt: ExecutionReceipt
    observe_evidence: Evidence
    act_decision: AutonomyDecision
    w10: W10Stage
    deploy_provider: CountingExecutionProvider
    deploy_receipt: ExecutionReceipt
    deploy_evidence: Evidence
    rollback_decision: AutonomyDecision
    rollback_receipt: ExecutionReceipt
    rollback_evidence: Evidence
    experiment: Experiment
    seed_recovery: RecoveryResult
    seed_run: OptimizationRun
    selfevo: SelfEvolutionStage
    evidence_graph: EvidenceGraph
    learning_hypothesis: CausalHypothesis
    memory_v2: ArchitectureMemory

    @property
    def graph(self) -> ArchitectureGraph:
        return self.harness.graph


def run_greenfield_scenario(
    root: Path,
    *,
    deploy_outcome: TruthState = TruthState.FAILED,
) -> GreenfieldScenario:
    """The greenfield-seam Mission-diagram chain, ending in governed rollback.

    Stages: W1 authorities → W2 greenfield SystemState (deterministic direct
    construction) → W4 evidence cycle → W5 causal knowledge → W6 bounded
    search + Pareto → W7 assurance → W8 governed experiment → W9
    GATHER_EVIDENCE → W11 OBSERVE (the first governed execution — the seam)
    → W9 ACT → W10 narrowing → W11 DEPLOY (partial failure: the provider
    fails after start) → W9 ROLLBACK + W11 ROLLBACK dispatch (governed
    recovery to a typed ROLLED_BACK state) → W12 convergence (the realized
    system's seed repository recovered through W3 enters the same brownfield
    loop, which ends in a governed rollback) → W13 boundary check → closure.
    """
    harness = greenfield_harness()
    evidence_graph = harness.evidence_graph

    # W9 → W11: the first governed execution is a read-only observation.
    gather_decision = gather_decision_for(harness)
    observe_provider = CountingExecutionProvider(provider_id=PROVIDER_OBSERVE)
    observe_request = execution_request_for(
        gather_decision, harness, scope=ExecutionActionScope.OBSERVE,
        provider_id=PROVIDER_OBSERVE,
    )
    observe_receipt = substrate_for(observe_provider, harness, gather_decision).submit(
        observe_request
    )
    observe_evidence = receipt_to_w4_evidence(observe_receipt, traceability=tr())
    evidence_graph = evidence_graph.ingest(observe_evidence)

    # W9 ACT → W10 narrowing → W11 DEPLOY through the seam.
    act_decision = act_decision_for(harness)
    w10 = run_w10_stage(harness.policy, act_decision)
    deploy_provider = CountingExecutionProvider(
        provider_id=PROVIDER_DEPLOY, deploy_outcome=deploy_outcome,
    )
    deploy_request = execution_request_for(
        act_decision, harness, scope=ExecutionActionScope.DEPLOY,
        provider_id=PROVIDER_DEPLOY,
    )
    deploy_receipt = substrate_for(deploy_provider, harness, act_decision).submit(
        deploy_request
    )
    deploy_evidence = receipt_to_w4_evidence(deploy_receipt, traceability=tr())
    evidence_graph = evidence_graph.ingest(deploy_evidence)

    # Governed rollback: W9 ROLLBACK decision → W11 ROLLBACK dispatch → the
    # W8 experiment lifecycle itself transitions to ROLLED_BACK.
    rollback_decision = rollback_decision_for(harness)
    rollback_request = execution_request_for(
        rollback_decision, harness, scope=ExecutionActionScope.ROLLBACK,
        provider_id=PROVIDER_DEPLOY,
    )
    rollback_receipt = substrate_for(
        deploy_provider, harness, rollback_decision,
    ).submit(rollback_request)
    rollback_exec_evidence = receipt_to_w4_evidence(rollback_receipt, traceability=tr())
    evidence_graph = evidence_graph.ingest(rollback_exec_evidence)
    experiment = transition_experiment(
        harness.experiment, ExperimentState.ROLLED_BACK,
    )

    # W12 convergence: the realized system's seed repository enters the same
    # brownfield evolution loop (architecture §10 symmetry). The second cycle
    # fails its experiment and ends in a governed rollback.
    seed_root = root / "greenfield-seed"
    make_greenfield_seed_repository(seed_root)
    seed_recovery = recover_repository(
        root=seed_root, revision=SEED_REVISION, traceability=tr()
    )
    seed_graph = seed_recovery.system_state.architecture
    seed_intervention = intervention_evidence(seed_graph.id, SEED_REVISION)
    seed_rollback = rollback_evidence(seed_graph.id, SEED_REVISION)
    seed_evidence = EvidenceGraph(
        id="w14-seed-evidence", version=1, records=(), traceability=tr()
    )
    for record in (seed_intervention, seed_rollback):
        seed_evidence = seed_evidence.ingest(record)
    seed_hyp = confirmed_hypothesis(seed_intervention, SEED_REVISION)
    seed_causal = CausalKnowledgeGraph(
        id="w14-seed-causal", version=1, hypotheses=(), traceability=tr()
    ).ingest(seed_hyp)
    seed_candidate = make_candidate(
        base_graph_id=seed_graph.id, revision=SEED_REVISION,
        target_node_id=node_for(seed_recovery, "greeter.py"),
        replacement_node_id=node_for(seed_recovery, "store.py"),
        boundary_node_id=node_for(seed_recovery, "ledger.py"),
        reasoning_evidence_ids=(seed_intervention.id,),
        reasoning_hypothesis_ids=(seed_hyp.id,),
        objectives=objectives_profile(100.0, 200.0, 2500.0),
        rationale="greenfield convergence candidate over the realized seed system",
    )
    seed_run = run_optimization_loop(
        recovery=seed_recovery, candidates=(seed_candidate,),
        policy=harness.policy,
        simulator=StubSimulator(outcome=TruthState.FAILED),
        traceability=tr(), max_iterations=2, stop_conditions=STOP_CONDITIONS,
        evidence_graph=seed_evidence, causal_graph=seed_causal,
        rollback_ref=ROLLBACK_REF_SEED,
        rollback_evidence_ids=(seed_rollback.id,),
    )

    # W13 boundary check + the lawful self-evolution chain (as data).
    selfevo = run_self_evolution_stage(
        harness.graph, GREEN_REVISION,
        trigger_evidence=harness.prior_canary,
        rollback_evidence=harness.rollback_ev,
        hypothesis=harness.confirmed_hyp,
        target_node_id=harness.node_ids["greeter"],
        replacement_node_id=harness.node_ids["greeter_v2"],
        boundary_node_id=harness.node_ids["gateway"],
        policy=harness.policy,
    )
    for record in (selfevo.refusal_evidence, *selfevo.evidence):
        evidence_graph = evidence_graph.ingest(record)

    # Closure: the failure-informed learning record (observational support
    # from the verbatim FAILED deployment evidence; uncertainty stays UNKNOWN).
    learning = learning_hypothesis_failed(deploy_evidence, GREEN_REVISION)
    memory_v2 = ArchitectureMemory(
        id="w14-memory-green-2", version=2, graph_ref=harness.graph.id,
        hypotheses=(harness.observation_hyp, learning), traceability=tr(),
    )
    memory_v2.validate(
        known_graph_id=harness.graph.id,
        known_evidence_ids={r.id for r in evidence_graph.records},
    )
    return GreenfieldScenario(
        mission=harness.mission, value_model=harness.value_model,
        context=harness.context, policy=harness.policy, harness=harness,
        gather_decision=gather_decision, observe_provider=observe_provider,
        observe_receipt=observe_receipt, observe_evidence=observe_evidence,
        act_decision=act_decision, w10=w10, deploy_provider=deploy_provider,
        deploy_receipt=deploy_receipt, deploy_evidence=deploy_evidence,
        rollback_decision=rollback_decision, rollback_receipt=rollback_receipt,
        rollback_evidence=rollback_exec_evidence, experiment=experiment,
        seed_recovery=seed_recovery, seed_run=seed_run, selfevo=selfevo,
        evidence_graph=evidence_graph, learning_hypothesis=learning,
        memory_v2=memory_v2,
    )


# ---------------------------------------------------------------------------
# Determinism helpers (record bundles for byte-equality comparisons)
# ---------------------------------------------------------------------------


def _state_token(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def record_id(record: Any) -> str:
    """The bundle key of a produced record.

    Content-addressed ids are unique per record CONTENT, but a few merged
    record types deliberately reuse one id across lifecycle states (the W8
    ``Experiment`` and W13 ``SelfEvolutionProposal`` precedents) or across
    versions (the W1 ``Mission``). The key appends ``version``/``state``
    discriminators when present so every distinct record in a bundle is
    compared byte-for-byte.
    """
    if isinstance(record, PromotionDecision):
        return f"promotion-decision:{record.experiment_id}:{record.evaluation_id}"
    base = str(getattr(record, "id", "") or type(record).__name__)
    if isinstance(record, (RepositoryInventory,)):
        base = f"inventory:{record.revision}"
    suffix = ""
    version = getattr(record, "version", None)
    if isinstance(version, int):
        suffix += f"#v{version}"
    state = getattr(record, "state", None)
    if state is not None and not isinstance(record, ExecutionRequest):
        suffix += f"#s{_state_token(state)}"
    return base + suffix


def serialize_record(record: Any) -> str:
    """A canonical byte-serialization (sorted keys) for equality checks."""
    return json.dumps(_convert_for_json(record), sort_keys=True, default=str)


def scenario_bundle(scenario: BrownfieldScenario | GreenfieldScenario) -> dict[str, str]:
    """Every produced record as {record key: canonical serialization}.

    The W3 inventory is included with its root path normalized (see the
    module docstring); the raw ``RecoveryResult`` wrapper is intentionally
    not serialized (it only re-embeds the inventory).
    """
    records: list[Any] = []
    if isinstance(scenario, BrownfieldScenario):
        harness = scenario.harness
        records.extend((
            scenario.mission_v1, scenario.mission_v2, scenario.value_model,
            scenario.context, scenario.policy,
            harness.recovery.system_state, normalized_inventory(harness.recovery),
            harness.memory_v1, harness.subgraph_replacement,
            scenario.run.loop, *scenario.run.candidates,
            *scenario.run.loop.iterations, *scenario.run.assurance_results,
            *scenario.run.experiments, *scenario.run.evaluations,
            *scenario.run.promotion_decisions, *scenario.run.decisions,
            *scenario.run.receipts, scenario.w10.selection,
            scenario.w10.adapter_plan, scenario.w10.constraint,
            scenario.w10.personalization, scenario.selfevo.proposal,
            scenario.selfevo.promoted, *scenario.selfevo.steps,
            *scenario.selfevo.evidence, scenario.learning_hypothesis,
            scenario.memory_v2, *scenario.evidence_graph.records,
            *harness.causal_graph.hypotheses,
        ))
    else:
        harness = scenario.harness
        records.extend((
            scenario.mission, scenario.value_model, scenario.context,
            scenario.policy, harness.system_state, harness.memory_v1,
            *harness.generated_frontier.candidates, *harness.pareto.candidates,
            harness.assurance, harness.experiment, harness.evaluation,
            harness.gate_decision, scenario.gather_decision,
            scenario.observe_receipt, scenario.act_decision,
            scenario.w10.selection, scenario.w10.adapter_plan,
            scenario.w10.constraint, scenario.w10.personalization,
            scenario.deploy_receipt, scenario.rollback_decision,
            scenario.rollback_receipt, scenario.experiment,
            scenario.seed_recovery.system_state,
            normalized_inventory(scenario.seed_recovery),
            scenario.seed_run.loop, *scenario.seed_run.candidates,
            *scenario.seed_run.loop.iterations,
            *scenario.seed_run.assurance_results, *scenario.seed_run.experiments,
            *scenario.seed_run.evaluations, *scenario.seed_run.promotion_decisions,
            *scenario.seed_run.decisions, *scenario.seed_run.receipts,
            scenario.selfevo.proposal, scenario.selfevo.promoted,
            *scenario.selfevo.steps, *scenario.selfevo.evidence,
            scenario.learning_hypothesis, scenario.memory_v2,
            *scenario.evidence_graph.records, *harness.causal_graph.hypotheses,
        ))
    bundle: dict[str, str] = {}
    for record in records:
        bundle[record_id(record)] = serialize_record(record)
    return bundle
