"""W11 — provider-neutral execution-substrate contract tests (promoted).

Deterministic, offline tests for the W11 execution boundary
``ExecutionRequest → ExecutionProvider → ExecutionReceipt → Evidence``
(frozen W11 Work Order `spec/work-orders/W11-execution-substrate.md`;
design in `docs/implementation/W11-EXECUTION-SUBSTRATE-DESIGN.md`).

Promotion note: this module is the PREP-W11 contract suite
(`tests/test_prep_w11_execution_contract.py`, prep branch
`work/w11-execution-substrate-prep` @ `816f62e5`) promoted to the real
`src/sos/execution.py` contract. Every PREP invariant name and assertion is
kept, adapted to the promoted module; the suite is extended (W9 REJECT
refusal, UNKNOWN timeout path, OBSERVE-under-ACT, W1 JSON round-trip,
idempotent receipt re-ingestion into a W4 EvidenceGraph, W1 error-family
anchoring, bounded authority surface), never weakened.

Contract shape under test (the promoted W11 surface):

- every request carries a REQUIRED pre-execution W9 authorization reference
  (``AutonomyDecision``); a request without one is rejected at construction
  (required outcome 3);
- providers cannot self-authorize: a decision issued under a provider-owned
  policy is rejected at submit (C1);
- provider capability (``ProviderCapability``) is checked separately from — and
  can never substitute for — W9 authorization (C3);
- receipts preserve exact revision / environment / time provenance and convert
  verbatim into W4 evidence (C4, C9);
- FAILED / UNKNOWN / UNAVAILABLE / UNSUPPORTED outcomes stay distinct, and the
  no-run outcomes cannot claim side effects or timestamps (C5);
- rollback exists only as a governed ``RollbackReference`` bound to the W8
  experiment's rollback path (C6);
- two independently-written stub providers implement the same contract
  unchanged — provider neutrality (C7).

Per the Work Order port boundary, the two stub providers
(``StubWorkspaceExecutionProvider``, ``StubReadOnlyExecutionProvider``) stay
LOCAL to this test module: they are injected port objects, not core code. All
authority types (W1 truth/traceability/persistence, W4 evidence, W7 assurance,
W8 experiment, W9 autonomy) are the real merged types — referenced, never
duplicated. No live execution, no network, no provider-specific semantics
(provider names appear only as stub names). The tests are fully deterministic:
fixed revisions, fixed ISO-8601 timestamps, no wall clock, no randomness.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from sos import (
    AssuranceGate,
    AssuranceResult,
    AssuranceStatus,
    BlastRadius,
    DecisionAction,
    Evidence,
    EvidenceGraph,
    EvidenceKind,
    EvidenceProvenance,
    Experiment,
    ExperimentMode,
    ExperimentState,
    ImpactAnalysis,
    JsonModelStore,
    ReversibilityAssessment,
    RiskAssessment,
    RiskItem,
    StaticEvidenceAdapter,
    StopCondition,
    Traceability,
    TruthState,
    TruthfulValue,
    # W11 promoted contract surface (src/sos/execution.py, W11 exports)
    ExecutionActionScope,
    ExecutionContractError,
    ExecutionLifecycleState,
    ExecutionProviderPort,
    ExecutionReceipt,
    ExecutionRequest,
    ExecutionSubstrate,
    ProviderCapability,
    ProviderUnavailableSignal,
    RollbackReference,
    SideEffect,
    SideEffectKind,
    receipt_to_w4_evidence,
    validate_lifecycle_transition,
)
from sos.autonomy import AutonomyDecision, AutonomyDecisionState


REVISION = "c0ffee1234567890abcdef1234567890abcdef12"
CHANGED_REVISION = "d00d01234567890abcdef1234567890abcdefab"
REVERTED_REVISION = "5eed1234567890abcdef1234567890abcdefcd"
PROVIDER_ALPHA = "stub-provider-alpha"
PROVIDER_BETA = "stub-provider-beta"
ALPHA_STARTED = "2030-04-01T10:00:00Z"
ALPHA_FINISHED = "2030-04-01T10:05:00Z"
BETA_STARTED = "2030-04-01T11:00:00Z"
BETA_FINISHED = "2030-04-01T11:02:00Z"


def tr() -> Traceability:
    return Traceability(
        constitution_ref="constitution:1", mission_ref="mission:1",
        value_model_ref="value:1", context_ref="context:1",
    )


# ---------------------------------------------------------------------------
# Stub providers (injected port objects — stay in the test module per the
# Work Order port boundary; NO stub contract types remain in this file)
# ---------------------------------------------------------------------------


def _provenance_echo(request: ExecutionRequest) -> dict[str, Any]:
    return dict(
        request_id=request.id, provider_id=None, action_scope=request.action_scope,
        w9_decision_id=request.w9_decision_id,
        w7_assurance_id=request.w7_assurance_id or None,
        source_revision=request.source_revision,
        provenance_revision=request.provenance_revision,
        base_graph_id=request.base_graph_id,
        base_graph_revision=request.base_graph_revision,
        environment=request.environment,
    )


class StubWorkspaceExecutionProvider:
    """First stub provider: a workspace-style deploy/rollback/observe provider.

    Simulates the full capability set; ``simulated_outcome`` and ``available``
    are deterministic test knobs. Builds receipts with typed side effects,
    exact changed revisions, stream refs, and the governed rollback echo.
    """

    def __init__(
        self,
        *,
        provider_id: str = PROVIDER_ALPHA,
        capabilities: frozenset[ProviderCapability] | None = None,
        simulated_outcome: TruthState = TruthState.SUCCESS,
        available: bool = True,
    ):
        self.provider_id = provider_id
        if capabilities is None:
            capabilities = frozenset({
                ProviderCapability.EXECUTE_DEPLOY,
                ProviderCapability.EXECUTE_ROLLBACK,
                ProviderCapability.EXECUTE_OBSERVE,
                ProviderCapability.ISOLATED_WORKSPACE,
                ProviderCapability.REVISION_PINNING,
                ProviderCapability.LOG_CAPTURE,
                ProviderCapability.SIDE_EFFECT_REPORT,
                ProviderCapability.ENVIRONMENT_ISOLATION,
            })
        self.capabilities = frozenset(capabilities)
        self._simulated_outcome = simulated_outcome
        self._available = available
        self.execute_calls = 0

    def execute(self, request: ExecutionRequest) -> ExecutionReceipt:
        self.execute_calls += 1
        if not self._available:
            raise ProviderUnavailableSignal(f"provider '{self.provider_id}' could not be engaged")
        echo = _provenance_echo(request)
        echo["provider_id"] = self.provider_id
        rb = request.rollback_reference
        if request.action_scope == ExecutionActionScope.OBSERVE:
            return ExecutionReceipt(
                lifecycle=ExecutionLifecycleState.SUCCEEDED,
                outcome=TruthfulValue(TruthState.SUCCESS, "observation complete", None),
                started_at=ALPHA_STARTED, finished_at=ALPHA_FINISHED,
                log_ref=f"alpha-log-{request.id}",
                **echo,
            )
        if request.action_scope == ExecutionActionScope.ROLLBACK:
            return ExecutionReceipt(
                lifecycle=ExecutionLifecycleState.ROLLED_BACK,
                outcome=TruthfulValue(TruthState.SUCCESS, "reverted to governed reference", None),
                started_at=ALPHA_STARTED, finished_at=ALPHA_FINISHED,
                side_effects=(SideEffect(
                    SideEffectKind.SERVICE_STATE, "node-a",
                    "service reverted to the governed rollback reference",
                ),),
                log_ref=f"alpha-log-{request.id}",
                changed_revisions=(REVERTED_REVISION,),
                rollback_reference=rb,
                **echo,
            )
        # DEPLOY scope
        if self._simulated_outcome == TruthState.FAILED:
            return ExecutionReceipt(
                lifecycle=ExecutionLifecycleState.FAILED,
                outcome=TruthfulValue(TruthState.FAILED, None, "deploy command exited non-zero before applying changes"),
                started_at=ALPHA_STARTED, finished_at=ALPHA_FINISHED,
                stdout_ref=f"alpha-stdout-{request.id}", stderr_ref=f"alpha-stderr-{request.id}",
                log_ref=f"alpha-log-{request.id}",
                rollback_reference=rb,
                **echo,
            )
        if self._simulated_outcome == TruthState.UNKNOWN:
            return ExecutionReceipt(
                lifecycle=ExecutionLifecycleState.OUTCOME_UNKNOWN,
                outcome=TruthfulValue(TruthState.UNKNOWN, None, "lost contact after dispatch; completion unconfirmed"),
                started_at=ALPHA_STARTED, finished_at=None,
                side_effects=(SideEffect(
                    SideEffectKind.FILE_CHANGE, "workspace",
                    "partial write observed before contact was lost",
                ),),
                log_ref=f"alpha-log-{request.id}",
                rollback_reference=rb,
                **echo,
            )
        return ExecutionReceipt(
            lifecycle=ExecutionLifecycleState.SUCCEEDED,
            outcome=TruthfulValue(TruthState.SUCCESS, "deployed at pinned revision", None),
            started_at=ALPHA_STARTED, finished_at=ALPHA_FINISHED,
            side_effects=(SideEffect(
                SideEffectKind.SERVICE_STATE, "node-a",
                "service restarted at the pinned source revision",
            ),),
            stdout_ref=f"alpha-stdout-{request.id}", stderr_ref=f"alpha-stderr-{request.id}",
            log_ref=f"alpha-log-{request.id}",
            changed_revisions=(CHANGED_REVISION,),
            rollback_reference=rb,
            **echo,
        )


class StubReadOnlyExecutionProvider:
    """Second stub provider: independently written, read-only (OBSERVE only).

    A different class with a different implementation — same contract, no
    shared code with the first provider. Proves provider neutrality
    (C7): swapping providers changes exactly one request field
    (``provider_id``) and zero contract semantics.
    """

    provider_id = PROVIDER_BETA
    capabilities = frozenset({
        ProviderCapability.EXECUTE_OBSERVE,
        ProviderCapability.REVISION_PINNING,
        ProviderCapability.LOG_CAPTURE,
    })

    def __init__(self) -> None:
        self.execute_calls = 0

    def execute(self, request: ExecutionRequest) -> ExecutionReceipt:
        self.execute_calls += 1
        return ExecutionReceipt(
            request_id=request.id,
            provider_id=self.provider_id,
            action_scope=request.action_scope,
            lifecycle=ExecutionLifecycleState.SUCCEEDED,
            outcome=TruthfulValue(TruthState.SUCCESS, "read-only observation finished", None),
            w9_decision_id=request.w9_decision_id,
            w7_assurance_id=request.w7_assurance_id or None,
            source_revision=request.source_revision,
            provenance_revision=request.provenance_revision,
            base_graph_id=request.base_graph_id,
            base_graph_revision=request.base_graph_revision,
            environment=request.environment,
            started_at=BETA_STARTED, finished_at=BETA_FINISHED,
            log_ref=f"beta-log-{request.id}",
        )


# ---------------------------------------------------------------------------
# Authority fixtures (REAL W1/W4/W7/W8/W9 types — referenced, not duplicated)
# ---------------------------------------------------------------------------


def recovery_evidence() -> Evidence:
    """Real W4 evidence demonstrating the rollback/recovery path."""
    return StaticEvidenceAdapter.from_static_observation(
        subject_ref="node-a",
        observation="rollback path verified",
        result=TruthfulValue(TruthState.SUCCESS, "rollback-capable", None),
        traceability=tr(),
        provenance=EvidenceProvenance(
            source="static-recovery", observed_subject="node-a",
            timestamp="2030-01-10T12:00:00Z", environment="production",
            implementation_revision=REVISION,
        ),
    )


def make_pass_assurance(*, status: AssuranceStatus = AssuranceStatus.PASS) -> AssuranceResult:
    """A real W7 assurance result (direct construction; non-authorizing)."""
    return AssuranceResult(
        id="",
        candidate_id="cand-1",
        base_graph_id="arch-1",
        base_graph_revision=REVISION,
        provenance_revision=REVISION,
        status=status,
        gates=(
            AssuranceGate(
                name="evidence-availability", status=AssuranceStatus.PASS,
                evidence_ids=("ev-obs-1",), detail="reasoning evidence present",
            ),
        ),
        impact=ImpactAnalysis(
            affected_node_ids=("node-a",), affected_edge_ids=(),
            boundary_interface_ids=(), dependency_reach=(),
            blast_radius=BlastRadius(level="limited", affected_count=1, detail="single service node"),
        ),
        risk=RiskAssessment(items=(
            RiskItem(
                name="rollback-risk", severity="low",
                uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "assessed residual risk"),
                mitigation="bounded rollback path rb-001",
                residual=None,
            ),
        )),
        reversibility=ReversibilityAssessment(
            rollback_available=True, detail="rollback evidence bound",
            rollback_evidence_ids=("ev-rb-1",),
        ),
        objectives=(),
        traceability=tr(),
    )


def make_completed_experiment(
    ar: AssuranceResult,
    *,
    assurance_result_id: str | None = None,
) -> Experiment:
    """A real W8 experiment in COMPLETED state with rollback_ref 'rb-001'."""
    return Experiment(
        id="",
        candidate_id=ar.candidate_id,
        assurance_result_id=assurance_result_id if assurance_result_id is not None else ar.id,
        base_graph_id=ar.base_graph_id,
        base_graph_revision=ar.base_graph_revision,
        provenance_revision=ar.provenance_revision,
        mode=ExperimentMode.CANARY,
        scope=("node-a",),
        observation_window=("2030-01-15T00:00:00Z", "2030-01-16T00:00:00Z"),
        success_criteria=("latency<200",),
        stop_conditions=(StopCondition(name="error-rate", threshold=0.05, metric="error-rate"),),
        rollback_ref="rb-001",
        traceability=tr(),
        state=ExperimentState.COMPLETED,
    )


def make_act_decision(
    ar: AssuranceResult, exp: Experiment, *, policy_id: str = "policy-human-1",
) -> AutonomyDecision:
    """A real W9 ACT decision binding the exact W7/W8 chain."""
    return AutonomyDecision(
        id="",
        state=AutonomyDecisionState.ACT,
        action=DecisionAction.ACT,
        rationale="ACT authorized: policy + assurance PASS + promotion + ceilings + evidence",
        reasons=("policy allows action", "assurance PASS", "promotion granted"),
        evidence_ids=(recovery_evidence().id,),
        assurance_id=ar.id,
        experiment_id=exp.id,
        promotion_id=f"{exp.id}:eval-1",
        policy_id=policy_id,
        traceability=tr(),
    )


def make_rollback_decision(
    exp: Experiment, *, policy_id: str = "policy-human-1",
) -> AutonomyDecision:
    """A real W9 ROLLBACK decision with governed recovery evidence."""
    return AutonomyDecision(
        id="",
        state=AutonomyDecisionState.ROLLBACK,
        action=DecisionAction.ROLLBACK,
        rationale="rollback authorized by policy with governed recovery evidence",
        reasons=("rollback action with governed recovery evidence",),
        evidence_ids=(recovery_evidence().id,),
        assurance_id="",
        experiment_id=exp.id,
        promotion_id=None,
        policy_id=policy_id,
        traceability=tr(),
    )


def make_gather_decision(*, policy_id: str = "policy-human-1") -> AutonomyDecision:
    """A real W9 GATHER_EVIDENCE decision authorizing read-only observation."""
    return AutonomyDecision(
        id="",
        state=AutonomyDecisionState.GATHER_EVIDENCE,
        action=DecisionAction.GATHER_EVIDENCE,
        rationale="evidence gathering authorized by policy",
        reasons=("policy allows action",),
        evidence_ids=(),
        assurance_id="",
        experiment_id=None,
        promotion_id=None,
        policy_id=policy_id,
        traceability=tr(),
    )


def governed_rollback_reference() -> RollbackReference:
    return RollbackReference(
        reference="rb-001",
        evidence_ids=(recovery_evidence().id,),
        detail="bounded rollback path for the node-a replacement",
    )


_UNSET = object()  # sentinel distinguishing "not supplied" from explicit None


def deploy_request(
    decision: AutonomyDecision,
    *,
    provider_id: str = PROVIDER_ALPHA,
    w7_assurance_id: str | None = None,
    w8_experiment_id: str | None = None,
    environment: str = "production",
    base_graph_revision: str = REVISION,
    rollback_reference: Any = _UNSET,
) -> ExecutionRequest:
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    return ExecutionRequest(
        intent="deploy candidate cand-1 to production at the pinned revision",
        action_scope=ExecutionActionScope.DEPLOY,
        provider_id=provider_id,
        source_revision=REVISION,
        provenance_revision=REVISION,
        base_graph_id="arch-1",
        base_graph_revision=base_graph_revision,
        environment=environment,
        w9_decision_id=decision.id,
        w7_assurance_id=(
            w7_assurance_id if w7_assurance_id is not None
            else (decision.assurance_id or ar.id)
        ),
        w8_experiment_id=(
            w8_experiment_id if w8_experiment_id is not None
            else (decision.experiment_id or exp.id)
        ),
        w8_promotion_ref=decision.promotion_id,
        rollback_reference=(
            governed_rollback_reference() if rollback_reference is _UNSET
            else rollback_reference
        ),
        traceability=tr(),
    )


def rollback_request(decision: AutonomyDecision, *, provider_id: str = PROVIDER_ALPHA) -> ExecutionRequest:
    return ExecutionRequest(
        intent="revert the deployed change via the governed rollback path",
        action_scope=ExecutionActionScope.ROLLBACK,
        provider_id=provider_id,
        source_revision=REVISION,
        provenance_revision=REVISION,
        base_graph_id="arch-1",
        base_graph_revision=REVISION,
        environment="production",
        w9_decision_id=decision.id,
        w8_experiment_id=decision.experiment_id,
        rollback_reference=governed_rollback_reference(),
        traceability=tr(),
    )


def observe_request(decision: AutonomyDecision, *, provider_id: str = PROVIDER_ALPHA) -> ExecutionRequest:
    return ExecutionRequest(
        intent="read-only observation run against the pinned revision",
        action_scope=ExecutionActionScope.OBSERVE,
        provider_id=provider_id,
        source_revision=REVISION,
        provenance_revision=REVISION,
        base_graph_id="arch-1",
        base_graph_revision=REVISION,
        environment="production",
        w9_decision_id=decision.id,
        traceability=tr(),
    )


def deploy_substrate(
    provider: ExecutionProviderPort,
    *,
    decision: AutonomyDecision | None = None,
    assurance: AssuranceResult | None = None,
    experiment: Experiment | None = None,
) -> ExecutionSubstrate:
    ar = assurance if assurance is not None else make_pass_assurance()
    exp = experiment if experiment is not None else make_completed_experiment(ar)
    dec = decision if decision is not None else make_act_decision(ar, exp)
    return ExecutionSubstrate(
        providers={provider.provider_id: provider},
        known_decisions={dec.id: dec},
        known_assurance={ar.id: ar},
        known_experiments={exp.id: exp},
    )


# ---------------------------------------------------------------------------
# C1/required-outcome-3 — a request cannot bypass W9 authority
# ---------------------------------------------------------------------------


def test_request_without_w9_authorization_reference_is_rejected():
    """A request with no W9 reference is rejected at construction (criterion 2)."""
    dec = make_act_decision(make_pass_assurance(), make_completed_experiment(make_pass_assurance()))
    with pytest.raises(ExecutionContractError, match="w9_decision_id is required"):
        ExecutionRequest(
            intent="deploy candidate cand-1 to production at the pinned revision",
            action_scope=ExecutionActionScope.DEPLOY,
            provider_id=PROVIDER_ALPHA,
            source_revision=REVISION,
            provenance_revision=REVISION,
            base_graph_id="arch-1",
            base_graph_revision=REVISION,
            environment="production",
            w9_decision_id="",
            w7_assurance_id=dec.assurance_id,
            w8_experiment_id=dec.experiment_id,
            rollback_reference=governed_rollback_reference(),
            traceability=tr(),
        )


def test_unresolved_w9_reference_is_rejected_before_dispatch():
    """A forged W9 id is rejected at submit; the provider is never called."""
    provider = StubWorkspaceExecutionProvider()
    dec = make_act_decision(make_pass_assurance(), make_completed_experiment(make_pass_assurance()))
    request = dataclasses.replace(deploy_request(dec), id="", w9_decision_id="autonomy-forged")
    substrate = deploy_substrate(provider, decision=dec)
    with pytest.raises(ExecutionContractError, match="unresolved W9 authorization reference"):
        substrate.submit(request)
    assert provider.execute_calls == 0


def test_ask_decision_cannot_authorize_execution():
    """ASK (human authority required) never authorizes a DEPLOY execution."""
    provider = StubWorkspaceExecutionProvider()
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    ask = AutonomyDecision(
        id="", state=AutonomyDecisionState.ASK, action=DecisionAction.ASK,
        rationale="human authority required", reasons=("scope unsafe",),
        evidence_ids=(), assurance_id=ar.id, experiment_id=exp.id,
        promotion_id=f"{exp.id}:eval-1", policy_id="policy-human-1", traceability=tr(),
    )
    request = deploy_request(ask)
    substrate = deploy_substrate(provider, decision=ask)
    with pytest.raises(ExecutionContractError, match="does not authorize scope deploy"):
        substrate.submit(request)
    assert provider.execute_calls == 0


def test_request_authority_chain_must_match_w9_decision():
    """The request must run under the EXACT W9 decision references (criterion 2)."""
    provider = StubWorkspaceExecutionProvider()
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    dec = make_act_decision(ar, exp)
    substrate = deploy_substrate(provider, decision=dec)
    mismatched_assurance = deploy_request(dec, w7_assurance_id="assurance-forged")
    with pytest.raises(ExecutionContractError, match="assurance binding"):
        substrate.submit(mismatched_assurance)
    mismatched_experiment = deploy_request(dec, w8_experiment_id="experiment-forged")
    with pytest.raises(ExecutionContractError, match="experiment binding"):
        substrate.submit(mismatched_experiment)
    assert provider.execute_calls == 0


def test_deploy_requires_w7_pass_assurance_bound_to_exact_chain():
    """W7 must resolve, be PASS, and match the exact graph/revision chain (criterion 8)."""
    provider = StubWorkspaceExecutionProvider()
    ar_fail = make_pass_assurance(status=AssuranceStatus.FAIL)
    exp_fail = make_completed_experiment(ar_fail)
    dec_fail = make_act_decision(ar_fail, exp_fail)
    substrate = deploy_substrate(provider, decision=dec_fail, assurance=ar_fail, experiment=exp_fail)
    with pytest.raises(ExecutionContractError, match="not PASS"):
        substrate.submit(deploy_request(dec_fail))
    # chain mismatch: request pins a different graph revision than the assurance
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    dec = make_act_decision(ar, exp)
    substrate2 = deploy_substrate(provider, decision=dec)
    with pytest.raises(ExecutionContractError, match="graph/revision/provenance chain"):
        substrate2.submit(deploy_request(dec, base_graph_revision="f" * 40))
    # experiment not bound to the exact assurance
    exp_mismatch = make_completed_experiment(ar, assurance_result_id="assurance-other")
    dec_m = make_act_decision(ar, exp_mismatch)
    substrate3 = deploy_substrate(provider, decision=dec_m, assurance=ar, experiment=exp_mismatch)
    with pytest.raises(ExecutionContractError, match="not bound to the exact W7 assurance"):
        substrate3.submit(deploy_request(dec_m))
    assert provider.execute_calls == 0


# ---------------------------------------------------------------------------
# C1 — no provider can authorize itself
# ---------------------------------------------------------------------------


def test_provider_cannot_self_authorize():
    """A decision issued under a provider-owned policy is rejected (criterion 1)."""
    provider = StubWorkspaceExecutionProvider()
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    self_authorized = make_act_decision(ar, exp, policy_id=PROVIDER_ALPHA)
    substrate = deploy_substrate(provider, decision=self_authorized)
    with pytest.raises(ExecutionContractError, match="cannot authorize its own execution"):
        substrate.submit(deploy_request(self_authorized))
    assert provider.execute_calls == 0
    # the same decision is fine when a DIFFERENT (non-provider) policy authorizes it
    dec = make_act_decision(ar, exp, policy_id="policy-human-1")
    substrate2 = deploy_substrate(provider, decision=dec)
    receipt = substrate2.submit(deploy_request(dec))
    assert receipt.outcome.state == TruthState.SUCCESS


# ---------------------------------------------------------------------------
# C3 — capability is separate from authorization
# ---------------------------------------------------------------------------


def test_capability_is_separate_from_authorization():
    """Capability failure and authorization failure are distinct classes."""
    alpha = StubWorkspaceExecutionProvider()
    beta = StubReadOnlyExecutionProvider()
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    dec = make_act_decision(ar, exp)
    # fully authorized request + provider WITHOUT the capability -> truthful
    # UNSUPPORTED receipt (a capability fact, not a policy violation)
    substrate_beta = deploy_substrate(beta, decision=dec)
    receipt = substrate_beta.submit(deploy_request(dec, provider_id=PROVIDER_BETA))
    assert receipt.lifecycle == ExecutionLifecycleState.UNSUPPORTED
    assert receipt.outcome.state == TruthState.UNSUPPORTED
    assert beta.execute_calls == 0
    # unauthorized request + provider WITH the capability -> rejected request
    # (an exception, not a receipt: nothing was attempted)
    gather = make_gather_decision()
    substrate_alpha = ExecutionSubstrate(
        providers={alpha.provider_id: alpha},
        known_decisions={gather.id: gather},  # no ACT decision registered
    )
    with pytest.raises(ExecutionContractError, match="unresolved W9 authorization reference"):
        substrate_alpha.submit(
            dataclasses.replace(deploy_request(dec), id="", w9_decision_id="autonomy-forged")
        )
    assert alpha.execute_calls == 0


def test_fully_authorized_request_without_capability_is_unsupported_not_rejected():
    """The distinctness of the two failure modes, positively asserted."""
    beta = StubReadOnlyExecutionProvider()
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    dec = make_act_decision(ar, exp)
    substrate = deploy_substrate(beta, decision=dec)
    receipt = substrate.submit(deploy_request(dec, provider_id=PROVIDER_BETA))
    assert receipt.outcome.state == TruthState.UNSUPPORTED
    assert receipt.outcome.detail and "lacks capability" in receipt.outcome.detail
    # no-run invariant: nothing executed
    assert receipt.started_at is None and receipt.finished_at is None
    assert receipt.side_effects == () and receipt.changed_revisions == ()
    assert receipt.rollback_reference is None


# ---------------------------------------------------------------------------
# C4 — exact receipt provenance
# ---------------------------------------------------------------------------


def test_receipt_provenance_is_exact():
    """Revisions, environment, time, provider, and authorization echo exactly."""
    provider = StubWorkspaceExecutionProvider()
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    dec = make_act_decision(ar, exp)
    substrate = deploy_substrate(provider, decision=dec)
    request = deploy_request(dec)
    receipt = substrate.submit(request)
    assert receipt.request_id == request.id
    assert receipt.provider_id == PROVIDER_ALPHA
    assert receipt.action_scope == ExecutionActionScope.DEPLOY
    assert receipt.lifecycle == ExecutionLifecycleState.SUCCEEDED
    assert receipt.w9_decision_id == dec.id
    assert receipt.w7_assurance_id == ar.id
    assert receipt.source_revision == REVISION
    assert receipt.provenance_revision == REVISION
    assert receipt.base_graph_id == "arch-1"
    assert receipt.base_graph_revision == REVISION
    assert receipt.environment == "production"
    assert receipt.started_at == ALPHA_STARTED
    assert receipt.finished_at == ALPHA_FINISHED
    assert receipt.changed_revisions == (CHANGED_REVISION,)
    assert receipt.rollback_reference == request.rollback_reference
    assert receipt.stdout_ref == f"alpha-stdout-{request.id}"
    assert receipt.stderr_ref == f"alpha-stderr-{request.id}"
    assert receipt.log_ref == f"alpha-log-{request.id}"
    assert receipt.side_effects == (
        SideEffect(SideEffectKind.SERVICE_STATE, "node-a", "service restarted at the pinned source revision"),
    )


def test_receipt_id_is_content_addressed_and_deterministic():
    """Identical executions yield identical ids; distinct inputs differ."""
    provider = StubWorkspaceExecutionProvider()
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    dec = make_act_decision(ar, exp)
    substrate = deploy_substrate(provider, decision=dec)
    request_a = deploy_request(dec)
    request_b = deploy_request(dec)
    assert request_a.id == request_b.id  # content-addressed request identity
    receipt_a = substrate.submit(request_a)
    receipt_b = substrate.submit(request_b)
    assert receipt_a.id == receipt_b.id
    request_staging = deploy_request(dec, environment="staging")
    assert request_staging.id != request_a.id
    receipt_staging = substrate.submit(request_staging)
    assert receipt_staging.id != receipt_a.id


# ---------------------------------------------------------------------------
# C5 — FAILED / UNKNOWN / UNAVAILABLE / UNSUPPORTED stay distinct
# ---------------------------------------------------------------------------


def test_outcomes_remain_distinct():
    """Four non-success outcomes, pairwise distinct, with distinct semantics."""
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    dec = make_act_decision(ar, exp)

    failed_provider = StubWorkspaceExecutionProvider(simulated_outcome=TruthState.FAILED)
    failed = deploy_substrate(failed_provider, decision=dec).submit(deploy_request(dec))

    unknown_provider = StubWorkspaceExecutionProvider(simulated_outcome=TruthState.UNKNOWN)
    unknown = deploy_substrate(unknown_provider, decision=dec).submit(deploy_request(dec))

    unavailable_provider = StubWorkspaceExecutionProvider(available=False)
    unavailable = deploy_substrate(unavailable_provider, decision=dec).submit(deploy_request(dec))

    beta = StubReadOnlyExecutionProvider()
    unsupported = deploy_substrate(beta, decision=dec).submit(deploy_request(dec, provider_id=PROVIDER_BETA))

    receipts = (failed, unknown, unavailable, unsupported)
    states = [r.outcome.state for r in receipts]
    assert set(states) == {
        TruthState.FAILED, TruthState.UNKNOWN,
        TruthState.UNAVAILABLE, TruthState.UNSUPPORTED,
    }
    assert len(set(states)) == 4  # pairwise distinct
    # every non-SUCCESS outcome carries an explanatory detail
    for r in receipts:
        assert r.outcome.detail and r.outcome.detail.strip()
    # executions that ran keep time provenance
    assert failed.started_at == ALPHA_STARTED and failed.finished_at == ALPHA_FINISHED
    assert unknown.started_at == ALPHA_STARTED and unknown.finished_at is None
    # executions that never ran keep none (no-run invariant)
    for r in (unavailable, unsupported):
        assert r.started_at is None and r.finished_at is None
        assert r.side_effects == () and r.changed_revisions == ()
    # UNKNOWN may carry partial observation; FAILED reports confirmed failure
    assert unknown.side_effects != () and unknown.changed_revisions == ()
    assert failed.side_effects == ()
    # receipts are pairwise distinct records
    assert len({r.id for r in receipts}) == 4


def test_unavailable_provider_yields_unavailable_receipt():
    """An unreachable provider yields a truthful UNAVAILABLE receipt."""
    provider = StubWorkspaceExecutionProvider(available=False)
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    dec = make_act_decision(ar, exp)
    substrate = deploy_substrate(provider, decision=dec)
    receipt = substrate.submit(deploy_request(dec))
    assert receipt.lifecycle == ExecutionLifecycleState.UNAVAILABLE
    assert receipt.outcome.state == TruthState.UNAVAILABLE
    assert "could not be engaged" in receipt.outcome.detail
    assert receipt.started_at is None and receipt.finished_at is None
    assert receipt.side_effects == () and receipt.changed_revisions == ()
    assert receipt.rollback_reference is None
    assert provider.execute_calls == 1  # the provider itself signaled unavailability


def test_unknown_provider_id_yields_unavailable_receipt():
    """A request selecting an unregistered provider id is UNAVAILABLE, not lost."""
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    dec = make_act_decision(ar, exp)
    substrate = deploy_substrate(StubWorkspaceExecutionProvider(), decision=dec)
    receipt = substrate.submit(deploy_request(dec, provider_id="stub-provider-nowhere"))
    assert receipt.lifecycle == ExecutionLifecycleState.UNAVAILABLE
    assert receipt.outcome.state == TruthState.UNAVAILABLE
    assert "no provider registered" in receipt.outcome.detail


def test_empty_is_not_a_lawful_execution_outcome():
    """EMPTY is a W4 observation-capture state, never an execution outcome."""
    request = deploy_request(make_act_decision(make_pass_assurance(), make_completed_experiment(make_pass_assurance())))
    with pytest.raises(ExecutionContractError, match="EMPTY is not a lawful execution outcome"):
        ExecutionReceipt(
            request_id=request.id, provider_id=PROVIDER_ALPHA,
            action_scope=ExecutionActionScope.DEPLOY,
            lifecycle=ExecutionLifecycleState.SUCCEEDED,
            outcome=TruthfulValue(TruthState.EMPTY, None, None),
            w9_decision_id=request.w9_decision_id,
            source_revision=REVISION, provenance_revision=REVISION,
            base_graph_id="arch-1", base_graph_revision=REVISION,
            environment="production", started_at=ALPHA_STARTED, finished_at=ALPHA_FINISHED,
            rollback_reference=governed_rollback_reference(),
        )


def test_no_run_receipts_cannot_claim_side_effects():
    """The no-run invariant is enforced by receipt construction."""
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    dec = make_act_decision(ar, exp)
    substrate = deploy_substrate(StubReadOnlyExecutionProvider(), decision=dec)
    unsupported = substrate.submit(deploy_request(dec, provider_id=PROVIDER_BETA))
    assert unsupported.outcome.state == TruthState.UNSUPPORTED
    with pytest.raises(ExecutionContractError, match="side effects are forbidden"):
        dataclasses.replace(unsupported, id="", side_effects=(
            SideEffect(SideEffectKind.SERVICE_STATE, "node-a", "claimed side effect"),
        ))
    with pytest.raises(ExecutionContractError, match="changed revisions are forbidden"):
        dataclasses.replace(unsupported, id="", changed_revisions=(CHANGED_REVISION,))
    with pytest.raises(ExecutionContractError, match="timestamps are forbidden"):
        dataclasses.replace(unsupported, id="", started_at=ALPHA_STARTED)
    with pytest.raises(ExecutionContractError, match="rollback references are forbidden"):
        dataclasses.replace(unsupported, id="", rollback_reference=governed_rollback_reference())
    with pytest.raises(ExecutionContractError, match="stream references are forbidden"):
        dataclasses.replace(unsupported, id="", log_ref="alpha-log-x")


def test_terminal_lifecycle_and_outcome_must_agree():
    """Machine state and truth state cannot disagree on terminals."""
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    dec = make_act_decision(ar, exp)
    substrate = deploy_substrate(StubWorkspaceExecutionProvider(), decision=dec)
    succeeded = substrate.submit(deploy_request(dec))
    with pytest.raises(ExecutionContractError, match="requires outcome SUCCESS"):
        dataclasses.replace(
            succeeded, id="",
            outcome=TruthfulValue(TruthState.UNAVAILABLE, None, "claimed unavailable"),
        )


# ---------------------------------------------------------------------------
# C6 — rollback is governed behavior
# ---------------------------------------------------------------------------


def test_deploy_request_requires_bounded_rollback_reference():
    """Every automated production change carries a bounded rollback path."""
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    dec = make_act_decision(ar, exp)
    with pytest.raises(ExecutionContractError, match="requires a governed rollback reference"):
        deploy_request(dec, rollback_reference=None)


def test_observe_request_needs_no_rollback_reference():
    """Read-only observation carries no rollback semantics."""
    gather = make_gather_decision()
    with pytest.raises(ExecutionContractError, match="must not carry a rollback reference"):
        ExecutionRequest(
            intent="read-only observation run against the pinned revision",
            action_scope=ExecutionActionScope.OBSERVE,
            provider_id=PROVIDER_ALPHA,
            source_revision=REVISION,
            provenance_revision=REVISION,
            base_graph_id="arch-1",
            base_graph_revision=REVISION,
            environment="production",
            w9_decision_id=gather.id,
            rollback_reference=governed_rollback_reference(),
            traceability=tr(),
        )


def test_rollback_reference_must_bind_to_experiment_rollback_ref():
    """The rollback reference must equal the W8 experiment's rollback_ref."""
    provider = StubWorkspaceExecutionProvider()
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    dec = make_act_decision(ar, exp)
    substrate = deploy_substrate(provider, decision=dec)
    mismatched = RollbackReference(
        reference="rb-other", evidence_ids=(recovery_evidence().id,),
        detail="not the experiment's governed path",
    )
    with pytest.raises(ExecutionContractError, match="does not match"):
        substrate.submit(deploy_request(dec, rollback_reference=mismatched))
    assert provider.execute_calls == 0


def test_rollback_execution_is_governed():
    """ROLLBACK runs only under a W9 ROLLBACK decision and lands ROLLED_BACK."""
    provider = StubWorkspaceExecutionProvider()
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    dec = make_rollback_decision(exp)
    substrate = deploy_substrate(provider, decision=dec)
    request = rollback_request(dec)
    receipt = substrate.submit(request)
    assert receipt.lifecycle == ExecutionLifecycleState.ROLLED_BACK
    assert receipt.outcome.state == TruthState.SUCCESS
    assert receipt.rollback_reference == request.rollback_reference
    assert receipt.rollback_reference.reference == exp.rollback_ref == "rb-001"
    assert receipt.changed_revisions == (REVERTED_REVISION,)
    # a rolled-back claim without the governed reference is unconstructible
    with pytest.raises(ExecutionContractError, match="requires the governed rollback reference"):
        dataclasses.replace(receipt, id="", rollback_reference=None)
    # an ACT decision does not authorize a rollback scope
    act_dec = make_act_decision(ar, exp)
    substrate_act = deploy_substrate(provider, decision=act_dec)
    with pytest.raises(ExecutionContractError, match="does not authorize scope rollback"):
        substrate_act.submit(rollback_request(act_dec))


# ---------------------------------------------------------------------------
# C7 — provider neutrality (second provider, same contract)
# ---------------------------------------------------------------------------


def test_second_provider_implements_the_same_contract():
    """Two independently written providers satisfy the same port shape."""
    alpha = StubWorkspaceExecutionProvider()
    beta = StubReadOnlyExecutionProvider()
    assert isinstance(alpha, ExecutionProviderPort)
    assert isinstance(beta, ExecutionProviderPort)
    gather = make_gather_decision()
    substrate = ExecutionSubstrate(
        providers={alpha.provider_id: alpha, beta.provider_id: beta},
        known_decisions={gather.id: gather},
    )
    receipt_alpha = substrate.submit(observe_request(gather, provider_id=PROVIDER_ALPHA))
    receipt_beta = substrate.submit(observe_request(gather, provider_id=PROVIDER_BETA))
    assert receipt_alpha.outcome.state == TruthState.SUCCESS
    assert receipt_beta.outcome.state == TruthState.SUCCESS
    assert receipt_alpha.provider_id == PROVIDER_ALPHA
    assert receipt_beta.provider_id == PROVIDER_BETA
    # read-only receipts carry no side effects, changes, or rollback
    for receipt in (receipt_alpha, receipt_beta):
        assert receipt.side_effects == () and receipt.changed_revisions == ()
        assert receipt.rollback_reference is None
    assert beta.execute_calls == 1


def test_provider_selection_changes_only_the_provider_field():
    """Swapping providers changes exactly the provider selection — nothing else."""
    alpha = StubWorkspaceExecutionProvider()
    beta = StubReadOnlyExecutionProvider()
    gather = make_gather_decision()
    substrate = ExecutionSubstrate(
        providers={alpha.provider_id: alpha, beta.provider_id: beta},
        known_decisions={gather.id: gather},
    )
    request_alpha = observe_request(gather, provider_id=PROVIDER_ALPHA)
    request_beta = observe_request(gather, provider_id=PROVIDER_BETA)
    # identical authorization and provenance; only the provider field differs
    assert request_alpha.w9_decision_id == request_beta.w9_decision_id == gather.id
    assert request_alpha.source_revision == request_beta.source_revision == REVISION
    assert request_alpha.environment == request_beta.environment == "production"
    assert request_alpha.id != request_beta.id  # provider selection is part of request identity
    receipt_alpha = substrate.submit(request_alpha)
    receipt_beta = substrate.submit(request_beta)
    assert receipt_alpha.provider_id != receipt_beta.provider_id
    assert receipt_alpha.outcome.state == receipt_beta.outcome.state == TruthState.SUCCESS
    assert receipt_alpha.source_revision == receipt_beta.source_revision == REVISION
    assert receipt_alpha.base_graph_id == receipt_beta.base_graph_id == "arch-1"
    assert receipt_alpha.w9_decision_id == receipt_beta.w9_decision_id == gather.id


# ---------------------------------------------------------------------------
# C6/C3 (lifecycle) — governed state machine
# ---------------------------------------------------------------------------


def test_lifecycle_is_a_governed_state_machine():
    """Transitions come from a frozen table; invalid jumps are rejected."""
    L = ExecutionLifecycleState
    for from_state, to_state in (
        (L.REQUESTED, L.DISPATCHED), (L.DISPATCHED, L.RUNNING),
        (L.RUNNING, L.SUCCEEDED), (L.RUNNING, L.FAILED),
        (L.RUNNING, L.OUTCOME_UNKNOWN), (L.DISPATCHED, L.UNAVAILABLE),
        (L.DISPATCHED, L.UNSUPPORTED), (L.SUCCEEDED, L.ROLLING_BACK),
        (L.FAILED, L.ROLLING_BACK), (L.ROLLING_BACK, L.ROLLED_BACK),
        (L.OUTCOME_UNKNOWN, L.OUTCOME_UNKNOWN),
    ):
        validate_lifecycle_transition(from_state, to_state)
    for from_state, to_state in (
        (L.REQUESTED, L.SUCCEEDED),          # cannot skip dispatch/run
        (L.REQUESTED, L.ROLLED_BACK),        # rollback cannot bypass semantics
        (L.UNAVAILABLE, L.ROLLING_BACK),     # nothing ran; nothing to roll back
        (L.UNSUPPORTED, L.ROLLING_BACK),     # nothing ran; nothing to roll back
        (L.ROLLED_BACK, L.RUNNING),          # terminal is terminal
        (L.UNSUPPORTED, L.DISPATCHED),       # terminal is terminal
        (L.REJECTED, L.DISPATCHED),          # rejected requests never dispatch
    ):
        with pytest.raises(ExecutionContractError, match="invalid execution lifecycle transition"):
            validate_lifecycle_transition(from_state, to_state)
    with pytest.raises(ExecutionContractError, match="must be an ExecutionLifecycleState"):
        validate_lifecycle_transition("requested", L.DISPATCHED)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# C9 — receipt → W4 evidence binding
# ---------------------------------------------------------------------------


def test_receipt_binds_to_w4_evidence_with_exact_provenance():
    """Receipts convert verbatim into real W4 evidence records."""
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    dec = make_act_decision(ar, exp)
    # deploy receipt -> deployment evidence
    deploy_receipt = deploy_substrate(
        StubWorkspaceExecutionProvider(), decision=dec,
    ).submit(deploy_request(dec))
    evidence = receipt_to_w4_evidence(deploy_receipt, traceability=tr())
    assert isinstance(evidence, Evidence)
    assert evidence.kind == EvidenceKind.DEPLOYMENT
    assert evidence.source_ref == PROVIDER_ALPHA
    assert evidence.subject_ref == "arch-1"
    assert evidence.result.state == TruthState.SUCCESS
    assert evidence.availability == TruthState.SUCCESS
    assert evidence.provenance.implementation_revision == REVISION
    assert evidence.provenance.environment == "production"
    assert evidence.provenance.timestamp == ALPHA_FINISHED
    # rollback receipt -> rollback evidence
    rollback_dec = make_rollback_decision(exp)
    rollback_receipt = deploy_substrate(
        StubWorkspaceExecutionProvider(), decision=rollback_dec,
    ).submit(rollback_request(rollback_dec))
    rollback_evidence = receipt_to_w4_evidence(rollback_receipt, traceability=tr())
    assert rollback_evidence.kind == EvidenceKind.ROLLBACK
    assert rollback_evidence.result.state == TruthState.SUCCESS
    # unavailable receipt -> truthful UNAVAILABLE evidence (observed, not inferred)
    unavailable_receipt = deploy_substrate(
        StubWorkspaceExecutionProvider(available=False), decision=dec,
    ).submit(deploy_request(dec))
    unavailable_evidence = receipt_to_w4_evidence(unavailable_receipt, traceability=tr())
    assert unavailable_evidence.result.state == TruthState.UNAVAILABLE
    assert unavailable_evidence.availability == TruthState.SUCCESS  # capture succeeded; execution did not run
    assert unavailable_evidence.provenance.timestamp is None       # nothing ran; no fabricated time
    assert unavailable_evidence.provenance.implementation_revision == REVISION


# ---------------------------------------------------------------------------
# W11 Work-Order-mandated extensions (extend, never weaken)
# ---------------------------------------------------------------------------


def test_w9_reject_decision_cannot_authorize_any_scope():
    """W9 REJECT refusal: an explicit policy refusal authorizes no scope (C1)."""
    provider = StubWorkspaceExecutionProvider()
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    # the REJECT decision binds the same W7/W8 chain so only its STATE can refuse
    reject = AutonomyDecision(
        id="", state=AutonomyDecisionState.REJECT, action=DecisionAction.REJECT,
        rationale="action not authorized by policy",
        reasons=("action not in policy.allowed_actions",),
        evidence_ids=(), assurance_id=ar.id, experiment_id=exp.id,
        promotion_id=f"{exp.id}:eval-1", policy_id="policy-human-1", traceability=tr(),
    )
    substrate = deploy_substrate(provider, decision=reject, assurance=ar, experiment=exp)
    # REJECT refuses DEPLOY
    with pytest.raises(ExecutionContractError, match="does not authorize scope deploy"):
        substrate.submit(deploy_request(reject))
    # REJECT refuses ROLLBACK
    with pytest.raises(ExecutionContractError, match="does not authorize scope rollback"):
        substrate.submit(rollback_request(reject))
    # REJECT refuses OBSERVE too (read-only is still an execution)
    with pytest.raises(ExecutionContractError, match="does not authorize scope observe"):
        substrate.submit(observe_request(reject))
    assert provider.execute_calls == 0


def test_unknown_timeout_yields_outcome_unknown_receipt():
    """UNKNOWN timeout path: lost contact stays UNKNOWN, never success (C5).

    The substrate is clock-free: the timeout manifests as provider-supplied
    data (started_at set, finished_at unknown, UNKNOWN outcome with an
    explanatory detail) — the core invents no deadline of its own.
    """
    provider = StubWorkspaceExecutionProvider(simulated_outcome=TruthState.UNKNOWN)
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    dec = make_act_decision(ar, exp)
    substrate = deploy_substrate(provider, decision=dec)
    receipt = substrate.submit(deploy_request(dec))
    assert receipt.lifecycle == ExecutionLifecycleState.OUTCOME_UNKNOWN
    assert receipt.outcome.state == TruthState.UNKNOWN
    assert receipt.outcome.detail and "unconfirmed" in receipt.outcome.detail
    assert receipt.outcome.value is None  # UNKNOWN never masquerades as a value
    assert receipt.started_at == ALPHA_STARTED and receipt.finished_at is None
    # partial observation is lawful; confirmed change is not
    assert receipt.side_effects != () and receipt.changed_revisions == ()
    # deterministic: the same submit again yields the identical receipt id
    assert substrate.submit(deploy_request(dec)).id == receipt.id


def test_observe_authorizes_under_gather_evidence_and_act():
    """Frozen W11 resolution: OBSERVE accepts GATHER_EVIDENCE and ACT decisions."""
    alpha = StubWorkspaceExecutionProvider()
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    gather = make_gather_decision()
    act = make_act_decision(ar, exp)
    substrate = ExecutionSubstrate(
        providers={alpha.provider_id: alpha},
        known_decisions={gather.id: gather, act.id: act},
    )
    receipt_gather = substrate.submit(observe_request(gather))
    receipt_act = substrate.submit(observe_request(act))
    assert receipt_gather.outcome.state == TruthState.SUCCESS
    assert receipt_act.outcome.state == TruthState.SUCCESS
    assert receipt_gather.w9_decision_id == gather.id
    assert receipt_act.w9_decision_id == act.id


def test_request_and_receipt_round_trip_through_w1_json_store(tmp_path):
    """C9: requests/receipts persist via the W1 JsonModelStore (no new authority)."""
    provider = StubWorkspaceExecutionProvider()
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    dec = make_act_decision(ar, exp)
    substrate = deploy_substrate(provider, decision=dec)
    request = deploy_request(dec)
    receipt = substrate.submit(request)
    # request round-trip
    req_path = tmp_path / "w11-request.json"
    JsonModelStore(req_path).save(request)
    req_data = JsonModelStore(req_path).load()
    assert req_data["id"] == request.id
    assert req_data["action_scope"] == ExecutionActionScope.DEPLOY.value
    assert req_data["w9_decision_id"] == dec.id
    assert req_data["w7_assurance_id"] == ar.id
    assert req_data["w8_experiment_id"] == exp.id
    assert req_data["rollback_reference"]["reference"] == "rb-001"
    assert req_data["traceability"]["context_ref"] == "context:1"
    # receipt round-trip
    rcpt_path = tmp_path / "w11-receipt.json"
    JsonModelStore(rcpt_path).save(receipt)
    rcpt_data = JsonModelStore(rcpt_path).load()
    assert rcpt_data["id"] == receipt.id
    assert rcpt_data["request_id"] == request.id
    assert rcpt_data["provider_id"] == PROVIDER_ALPHA
    assert rcpt_data["lifecycle"] == ExecutionLifecycleState.SUCCEEDED.value
    assert rcpt_data["outcome"]["state"] == TruthState.SUCCESS.value
    assert rcpt_data["w9_decision_id"] == dec.id
    assert rcpt_data["source_revision"] == REVISION
    assert rcpt_data["changed_revisions"] == [CHANGED_REVISION]
    assert rcpt_data["side_effects"][0]["kind"] == SideEffectKind.SERVICE_STATE.value
    assert rcpt_data["started_at"] == ALPHA_STARTED and rcpt_data["finished_at"] == ALPHA_FINISHED


def test_identical_receipt_reingestion_is_idempotent():
    """Required outcome 9: re-ingesting an identical receipt is idempotent (W4 dedup)."""
    provider = StubWorkspaceExecutionProvider()
    ar = make_pass_assurance()
    exp = make_completed_experiment(ar)
    dec = make_act_decision(ar, exp)
    substrate = deploy_substrate(provider, decision=dec)
    receipt = substrate.submit(deploy_request(dec))
    # identical receipt -> identical content-addressed evidence identity
    evidence_a = receipt_to_w4_evidence(receipt, traceability=tr())
    evidence_b = receipt_to_w4_evidence(receipt, traceability=tr())
    assert evidence_a.id == evidence_b.id
    graph = EvidenceGraph(id="evgraph-1", version=1, records=(), traceability=tr())
    graph_once = graph.ingest(evidence_a)
    assert len(graph_once.records) == 1
    graph_twice = graph_once.ingest(evidence_b)  # W4 dedup: no duplicate record
    assert graph_twice.records == graph_once.records
    assert len(graph_twice.records) == 1
    # a DIFFERENT receipt (different environment) is distinct evidence, not dedup
    other_receipt = substrate.submit(deploy_request(dec, environment="staging"))
    other_evidence = receipt_to_w4_evidence(other_receipt, traceability=tr())
    assert other_evidence.id != evidence_a.id
    graph_three = graph_twice.ingest(other_evidence)
    assert len(graph_three.records) == 2
    assert [r.id for r in graph_three.records] == sorted(r.id for r in graph_three.records)


def test_execution_contract_error_is_anchored_in_w1_validation_family():
    """C10: ExecutionContractError subclasses the W1 ModelValidationError family."""
    import sos.model as model_mod

    assert issubclass(ExecutionContractError, model_mod.ModelValidationError)
    assert issubclass(ExecutionContractError, ValueError)
    # a contract violation IS a W1-family validation failure at the boundary
    with pytest.raises(model_mod.ModelValidationError, match="w9_decision_id is required"):
        ExecutionRequest(
            intent="no authorization",
            action_scope=ExecutionActionScope.OBSERVE,
            provider_id=PROVIDER_ALPHA,
            source_revision=REVISION,
            provenance_revision=REVISION,
            base_graph_id="arch-1",
            base_graph_revision=REVISION,
            environment="production",
            w9_decision_id="",
            traceability=tr(),
        )


def test_w11_introduces_no_w12_w13_or_provider_integration_symbols():
    """C10/exclusions: no W12/W13/integration symbols; no live-execution surface."""
    import inspect
    import sos.execution as emod

    forbidden = {
        "OpenMuse", "CodeOSS", "CodeOss", "MuseAdapter", "ExtensionHost",
        "Subprocess", "Socket", "HttpClient", "Credential", "CredentialStore",
        "OptimizationLoop", "BrownfieldLoop", "SelfEvolution", "MetaAdaptation",
        "AdversarialVerifier", "Dogfood",
    }
    exported = {n for n in dir(emod) if not n.startswith("_")}
    assert not (forbidden & exported), f"forbidden W12/W13/integration symbols: {forbidden & exported}"
    # source-level scan: no provider names, transports, or live-execution APIs in core
    src = inspect.getsource(emod).lower()
    for token in (
        "openmuse", "code-oss", "codeoss", "github", "http://", "https://",
        "ftp://", "subprocess", "socket", "urllib", "requests.post",
        "uuid4", "time.time", "datetime.now", "os.system", "popen",
    ):
        assert token not in src, f"forbidden live/provider token in src/sos/execution.py: {token!r}"


def test_w11_references_frozen_authorities_without_redefining():
    """C10: W1/W4/W7/W9 authorities are referenced, never redefined."""
    import sos.assurance as assurance_mod
    import sos.autonomy as autonomy_mod
    import sos.evidence as evidence_mod
    import sos.execution as emod
    import sos.model as model_mod

    assert emod.ModelValidationError is model_mod.ModelValidationError
    assert emod.TruthState is model_mod.TruthState
    assert emod.TruthfulValue is model_mod.TruthfulValue
    assert emod.Traceability is model_mod.Traceability
    assert emod.AssuranceStatus is assurance_mod.AssuranceStatus
    assert emod.AutonomyDecisionState is autonomy_mod.AutonomyDecisionState
    assert emod.Evidence is evidence_mod.Evidence
    assert emod.EvidenceKind is evidence_mod.EvidenceKind
    assert emod.EvidenceProvenance is evidence_mod.EvidenceProvenance
    assert emod._build_evidence is evidence_mod._build_evidence  # the single assembly authority
    # every authority class still belongs to its owning module
    assert emod.TruthState.__module__ == "sos.model"
    assert emod.AssuranceStatus.__module__ == "sos.assurance"
    assert emod.AutonomyDecisionState.__module__ == "sos.autonomy"
    assert emod.Evidence.__module__ == "sos.evidence"
    # the substrate registries reference the real decision type
    decision_cls = type(make_gather_decision())
    assert decision_cls is autonomy_mod.AutonomyDecision
