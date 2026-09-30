"""W13 — self-evolution proposal lifecycle contract tests (first bounded slice).

Deterministic, offline tests for the governed self-evolution lifecycle in
``src/sos/selfevolution.py`` (frozen W13 Work Order
`spec/work-orders/W13-self-evolution.md`; design in
`docs/implementation/W13-SELF-EVOLUTION-DESIGN.md`).

The suite composes the REAL merged authorities end-to-end: the happy path
recovers a fixture repository with the real W3 ``recover_repository`` and runs
the REAL W7 ``assure_candidate`` over a W6 candidate projection carrying the
proposal's identity, the REAL W8 experiment lifecycle
(``transition_experiment`` / ``evaluate_experiment`` / ``PromotionGate``), and
the REAL W9 ``evaluate_autonomy`` — before the W13 lifecycle machine consumes
the resulting records. Boundary tests use directly-constructed W7/W8/W9
records (W13 types, construction-validated — the W12 ``assurance_record``
precedent) to probe every gate rejection path.

All tests are fully deterministic: fixed revisions, fixed ISO-8601 timestamps,
no wall clock, no randomness, no running systems, no network. The Work
Order's "Required regression coverage" list is mapped one-to-one onto the
tests below (see the design doc §14 for the mapping table).
"""

from __future__ import annotations

import dataclasses
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from sos import (
    AssuranceGate,
    AssuranceResult,
    AssuranceStatus,
    AutonomyDecision,
    AutonomyDecisionState,
    AutonomyRequest,
    BlastRadius,
    CandidateObjective,
    CandidateProposal,
    CausalHypothesis,
    CausalRelationType,
    DecisionAction,
    Evidence,
    EvidenceGraph,
    EvidenceKind,
    EvidenceProvenance,
    EvidenceSupport,
    Experiment,
    ExperimentEvaluation,
    ExperimentMode,
    ExperimentState,
    ImpactAnalysis,
    InterventionMetadata,
    JsonModelStore,
    ModelValidationError,
    MutationKind,
    ObjectiveDirection,
    PolicyCeiling,
    PromotionDecision,
    PromotionGate,
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
    assure_candidate,
    evaluate_autonomy,
    evaluate_experiment,
    recover_repository,
    transition_experiment,
    ArchitectureMemory,
    # W13 self-evolution surface (src/sos/selfevolution.py, W13 exports)
    AUTHORITY_MODULE_PATHS,
    FROZEN_AUTHORITY_PATHS,
    FROZEN_AUTHORITY_PATH_PREFIXES,
    MAX_META_DEPTH,
    PendingProposalAuthorization,
    PendingProposalEvidence,
    PendingResolution,
    ProposalOrigin,
    SelfEvolutionContractError,
    SelfEvolutionGate,
    SelfEvolutionProposal,
    SelfEvolutionState,
    SelfEvolutionStep,
    SelfEvolutionTransitionResult,
    SelfImprovementHypothesis,
    SourceChange,
    SourceChangeKind,
    defer_self_evolution,
    resolve_meta_chain,
    step_to_w4_evidence,
    transition_self_evolution,
    validate_self_evolution_transition,
)
from sos.evidence import _build_evidence
from sos.model import _convert_for_json


REVISION = "0da1ca09885b0cc618cdddebc6da5acfc3f0c978"
OTHER_REVISION = "baadf00d1234567890abcdef1234567890abc"
TS = "2030-07-01T12:00:00Z"
ROLLBACK_REF = "rb-selfevo-1"
PREDICTED_EFFECT = "self-evolution lowers the optimization loop's search latency"
PAYLOAD_TEXT = "@@ -1,3 +1,4 @@\n context\n-baseline\n+improved\n+governed\n"
TARGET_MODULE = "src/sos/optimization.py"


def tr() -> Traceability:
    return Traceability(
        constitution_ref="constitution:1", mission_ref="mission:1",
        value_model_ref="value:1", context_ref="context:1",
    )


def prov(subject: str, revision: str = REVISION) -> EvidenceProvenance:
    return EvidenceProvenance(
        source="w13-test-harness", observed_subject=subject,
        timestamp=None, environment="simulation", implementation_revision=revision,
    )


def trigger_evidence(subject: str) -> Evidence:
    """Intervention-grade W4 evidence (kind EXPERIMENT) that triggers the
    self-improvement hypothesis."""
    return _build_evidence(
        kind=EvidenceKind.EXPERIMENT, source_ref="experiment-w13-77",
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
            intervention_id="experiment-w13-77", intervention_kind="experiment",
            applied_at="2030-06-01T00:00:00Z", revision=REVISION,
            environment="simulation",
        ),
    )
    h = CausalHypothesis(
        cause_subject="sos:optimization-loop", effect_subject="sos:search-latency",
        relation_type=CausalRelationType.INFLUENCES, direction="negative",
        rationale="the loop's candidate ordering dominates its latency", status="proposed",
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
            name="search-latency", direction=ObjectiveDirection.MINIMIZE,
            predicted_value=120.0,
            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted"),
        ),
        CandidateObjective(
            name="risk", direction=ObjectiveDirection.MINIMIZE, predicted_value=0.1,
            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted"),
        ),
    )


def make_repository(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "svc_a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (root / "svc_b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    (root / "svc_c.py").write_text("def c():\n    return 3\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "svc"\ndependencies = ["numpy"]\n', encoding="utf-8"
    )


def node_for(recovery: RecoveryResult, path: str) -> str:
    for n in recovery.system_state.architecture.nodes:
        if n.name == path:
            return n.id
    raise AssertionError(f"node {path!r} was not recovered")


@dataclasses.dataclass
class Harness:
    """The deterministic fixture chain: real W3 recovery + real W4 evidence +
    a real confirmed W5 hypothesis + a real W6 citation candidate."""

    recovery: RecoveryResult
    graph_id: str
    intervention: Evidence
    rollback_ev: Evidence
    hypothesis: CausalHypothesis
    citation_candidate: CandidateProposal
    evidence_graph: EvidenceGraph
    known_evidence: dict[str, Evidence]

    @property
    def known_hypotheses(self) -> dict[str, CausalHypothesis]:
        return {self.hypothesis.id: self.hypothesis}

    @property
    def known_candidates(self) -> dict[str, CandidateProposal]:
        return {self.citation_candidate.id: self.citation_candidate}


def harness_at(root: Path) -> Harness:
    make_repository(root)
    recovery = recover_repository(root=root, revision=REVISION, traceability=tr())
    graph_id = recovery.system_state.architecture.id
    intervention = trigger_evidence(graph_id)
    rollback = rollback_evidence(graph_id)
    hypothesis = causal_hypothesis(intervention)
    citation_candidate = CandidateProposal(
        id="", base_graph_ref=graph_id, base_graph_revision=REVISION,
        mutation=SubgraphMutation(
            kind=MutationKind.SUBGRAPH_REPLACE, base_graph_ref=graph_id,
            target_node_ids=(node_for(recovery, "svc_a.py"),),
            replacement_node_ids=(node_for(recovery, "svc_b.py"),),
            boundary_interface_ids=(node_for(recovery, "svc_c.py"),),
            invariants=("preserve-boundary",),
        ),
        objectives=objectives(), rationale="w13 citation candidate (provenance seam)",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not proven"),
        reasoning_evidence_ids=(intervention.id,),
        reasoning_hypothesis_ids=(hypothesis.id,),
        risks=("rollback-risk",), traceability=tr(), provenance_revision=REVISION,
    )
    evidence_graph = EvidenceGraph(
        id="w13-test-evidence", version=1, records=(), traceability=tr()
    )
    known: dict[str, Evidence] = {}
    for record in (intervention, rollback):
        evidence_graph = evidence_graph.ingest(record)
        known[record.id] = record
    return Harness(
        recovery=recovery, graph_id=graph_id, intervention=intervention,
        rollback_ev=rollback, hypothesis=hypothesis,
        citation_candidate=citation_candidate, evidence_graph=evidence_graph,
        known_evidence=known,
    )


def make_proposal(
    harness: Harness,
    *,
    origin: ProposalOrigin = ProposalOrigin.MODEL_GENERATED,
    target: str = TARGET_MODULE,
    kind: SourceChangeKind = SourceChangeKind.MODIFY,
    payload: str | None = None,
    rollback_ref: str = ROLLBACK_REF,
    meta_depth: int = 0,
    ancestor_proposal_id: str | None = None,
    candidate_ref: str | None = None,
    trigger_evidence_ids: tuple[str, ...] | None = None,
    causal_hypothesis_ids: tuple[str, ...] | None = None,
    target_revision: str = REVISION,
) -> SelfEvolutionProposal:
    hypothesis = SelfImprovementHypothesis(
        rationale="the governed optimization loop's search ordering is latency-dominated",
        trigger_evidence_ids=(
            (harness.intervention.id,) if trigger_evidence_ids is None else trigger_evidence_ids
        ),
        predicted_effects=(PREDICTED_EFFECT,),
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted, not proven"),
        causal_hypothesis_ids=(
            (harness.hypothesis.id,) if causal_hypothesis_ids is None else causal_hypothesis_ids
        ),
    )
    return SelfEvolutionProposal(
        target_revision=target_revision,
        target_paths=(target,),
        changes=(SourceChange(
            path=target, base_revision=target_revision, kind=kind,
            payload=PAYLOAD_TEXT if payload is None else payload,
        ),),
        hypothesis=hypothesis,
        origin=origin,
        rollback_ref=rollback_ref,
        meta_depth=meta_depth,
        ancestor_proposal_id=ancestor_proposal_id,
        candidate_ref=(
            harness.citation_candidate.id if candidate_ref is None else candidate_ref
        ),
        traceability=tr(),
    )


def assurance_record(
    *,
    candidate_id: str,
    status: AssuranceStatus,
    revision: str = REVISION,
) -> AssuranceResult:
    """A directly-constructed W7 record for boundary tests (W7 types, W13 test)."""
    return AssuranceResult(
        id="",
        candidate_id=candidate_id,
        base_graph_id="sos-self-projection",
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


@dataclasses.dataclass
class Gates:
    """The real W7/W8 gate bundle for one proposal (all engines are real)."""

    assurance: AssuranceResult
    experiment: Experiment
    evaluation: ExperimentEvaluation
    gate_decision: PromotionDecision
    rollback_path: RollbackPath
    known_evidence: dict[str, Evidence]


def gates_for(
    harness: Harness,
    proposal: SelfEvolutionProposal,
    *,
    evaluation_success: bool = True,
    stop_trigger: tuple[str, ...] = (),
) -> Gates:
    """Run the REAL W7 engine (over a W6 candidate projection carrying the
    proposal's identity) and the REAL W8 lifecycle for the proposal."""
    graph = harness.recovery.system_state.architecture
    # The W6 projection: a real CandidateProposal whose explicit id is the
    # proposal's id, so the W7 result binds to the exact proposal chain.
    projection = CandidateProposal(
        id=proposal.id, base_graph_ref=graph.id, base_graph_revision=REVISION,
        mutation=SubgraphMutation(
            kind=MutationKind.SUBGRAPH_REPLACE, base_graph_ref=graph.id,
            target_node_ids=(node_for(harness.recovery, "svc_a.py"),),
            replacement_node_ids=(node_for(harness.recovery, "svc_b.py"),),
            boundary_interface_ids=(node_for(harness.recovery, "svc_c.py"),),
            invariants=("preserve-boundary",),
        ),
        objectives=objectives(), rationale="self-evolution candidate projection",
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not proven"),
        reasoning_evidence_ids=(harness.intervention.id,),
        reasoning_hypothesis_ids=(harness.hypothesis.id,),
        risks=("rollback-risk",), traceability=tr(), provenance_revision=REVISION,
    )
    known = dict(harness.known_evidence)
    assurance = assure_candidate(
        candidate=projection, base_graph=graph,
        known_evidence=known, known_hypotheses=harness.known_hypotheses,
        rollback_evidence_ids=(harness.rollback_ev.id,),
    )
    assert assurance.status == AssuranceStatus.PASS, (
        f"real W7 engine must PASS the fixture projection (got {assurance.status.value})"
    )
    experiment = Experiment(
        id="", candidate_id=proposal.id, assurance_result_id=assurance.id,
        base_graph_id=graph.id, base_graph_revision=REVISION, provenance_revision=REVISION,
        mode=ExperimentMode.SHADOW, scope=(proposal.id,),
        observation_window=("2030-07-01T00:00:00Z", "2030-07-02T00:00:00Z"),
        success_criteria=("objectives-not-dominated",),
        stop_conditions=(StopCondition(name="error-rate", threshold=0.05, metric="error-rate"),),
        rollback_ref=proposal.rollback_ref, traceability=tr(),
    )
    experiment.validate(known_assurance=assurance)
    experiment = transition_experiment(experiment, ExperimentState.READY, known_assurance=assurance)
    experiment = transition_experiment(experiment, ExperimentState.RUNNING, known_assurance=assurance)
    terminal = ExperimentState.STOPPED if stop_trigger else ExperimentState.COMPLETED
    experiment = transition_experiment(experiment, terminal, known_assurance=assurance)
    experiment_evidence = _build_evidence(
        kind=EvidenceKind.EXPERIMENT, source_ref=f"simulator:{experiment.id}",
        subject_ref=graph.id,
        result=TruthfulValue(
            TruthState.SUCCESS if evaluation_success else TruthState.FAILED,
            "simulated-success" if evaluation_success else None,
            None if evaluation_success else "simulated failed experiment outcome",
        ),
        provenance=prov(graph.id), traceability=tr(),
        timestamp=None, environment="simulation", confidence=None,
        availability=TruthState.SUCCESS,
    )
    known[experiment_evidence.id] = experiment_evidence
    rollback_path = RollbackPath(
        reference=proposal.rollback_ref, evidence_ids=(harness.rollback_ev.id,),
        detail="governed rollback path bound to the declared rollback reference",
    )
    evaluation = evaluate_experiment(
        experiment, known_evidence=known, evidence_refs=(experiment_evidence.id,),
        evaluation_success=evaluation_success, stop_trigger=stop_trigger,
        known_assurance=assurance, rollback_path=rollback_path,
    )
    gate_decision = PromotionGate().evaluate(experiment, evaluation, known_assurance=assurance)
    return Gates(
        assurance=assurance, experiment=experiment, evaluation=evaluation,
        gate_decision=gate_decision, rollback_path=rollback_path, known_evidence=known,
    )


def promotion_ref(gates: Gates) -> str:
    return f"{gates.experiment.id}:{gates.evaluation.id}"


def act_policy(*, human_approval_for_act: bool = False, allow_act: bool = True) -> AutonomyRequest:
    actions: list[DecisionAction] = [DecisionAction.GATHER_EVIDENCE, DecisionAction.ROLLBACK]
    if allow_act:
        actions.append(DecisionAction.ACT)
    return AutonomyRequest(
        id="policy-selfevo-1", version=1, allowed_actions=tuple(actions),
        ceilings=PolicyCeiling(
            max_risk=0.3, max_blast_radius="service", require_reversible=True,
            min_confidence=0.8, require_human_approval_for_act=human_approval_for_act,
        ),
        traceability=tr(),
    )


def decide(
    gates: Gates,
    *,
    action: DecisionAction,
    policy: AutonomyRequest | None = None,
    human_authority_present: bool = False,
) -> AutonomyDecision:
    """Produce a real W9 decision with the real evaluate_autonomy engine."""
    return evaluate_autonomy(
        policy=policy if policy is not None else act_policy(),
        action=action,
        assurance=gates.assurance,
        experiment=gates.experiment,
        promotion=gates.gate_decision if action == DecisionAction.ACT else None,
        evaluation=gates.evaluation,
        evidence_ids=tuple(gates.evaluation.evidence_ids),
        traceability=tr(),
        known_evidence=gates.known_evidence,
        human_authority_present=human_authority_present,
        blast_radius="limited", risk=0.1, confidence=0.9, reversible=True,
        rollback_path=gates.rollback_path if action == DecisionAction.ROLLBACK else None,
    )


def registries_for(
    harness: Harness,
    gates: Gates,
    decisions: tuple[AutonomyDecision, ...] = (),
    *,
    promotions: dict[str, PromotionDecision] | None = None,
) -> dict[str, Any]:
    return dict(
        known_assurance={gates.assurance.id: gates.assurance},
        known_experiments={gates.experiment.id: gates.experiment},
        known_evaluations={gates.evaluation.id: gates.evaluation},
        known_promotions={
            promotion_ref(gates): gates.gate_decision,
            **(promotions or {}),
        },
        known_decisions={d.id: d for d in decisions},
        known_evidence=dict(gates.known_evidence),
        known_proposals={},
        known_hypotheses=harness.known_hypotheses,
        known_candidates=harness.known_candidates,
    )


@dataclasses.dataclass
class Chain:
    proposal: SelfEvolutionProposal
    steps: list[SelfEvolutionStep]
    evidence: list[Evidence]
    gates: Gates
    registries: dict[str, Any]
    act: AutonomyDecision


def advance(
    proposal: SelfEvolutionProposal,
    new_state: SelfEvolutionState,
    registries: dict[str, Any],
    *,
    steps: list[SelfEvolutionStep] | None = None,
    evidence: list[Evidence] | None = None,
    **kwargs: Any,
) -> SelfEvolutionTransitionResult:
    result = transition_self_evolution(
        proposal, new_state, **registries, timestamp=TS, **kwargs
    )
    if steps is not None:
        steps.append(result.step)
    if evidence is not None:
        evidence.append(result.evidence)
    return result


def run_happy(
    harness: Harness,
    proposal: SelfEvolutionProposal | None = None,
    *,
    adoption_revision: str | None = None,
) -> Chain:
    """The full governed happy path with the REAL W7/W8/W9 authorities."""
    proposal = make_proposal(harness) if proposal is None else proposal
    gates = gates_for(harness, proposal)
    act = decide(gates, action=DecisionAction.ACT)
    assert act.state == AutonomyDecisionState.ACT
    registries = registries_for(harness, gates, (act,))
    steps: list[SelfEvolutionStep] = []
    evidence: list[Evidence] = []
    r = advance(proposal, SelfEvolutionState.UNDER_ASSURANCE, registries, steps=steps, evidence=evidence)
    r = advance(
        r.proposal, SelfEvolutionState.UNDER_EXPERIMENT, registries,
        steps=steps, evidence=evidence, assurance_result_id=gates.assurance.id,
    )
    r = advance(
        r.proposal, SelfEvolutionState.UNDER_AUTHORITY, registries,
        steps=steps, evidence=evidence,
        experiment_id=gates.experiment.id, evaluation_id=gates.evaluation.id,
        promotion_id=promotion_ref(gates), rollback_path=gates.rollback_path,
    )
    r = advance(
        r.proposal, SelfEvolutionState.PROMOTED, registries,
        steps=steps, evidence=evidence,
        autonomy_decision_id=act.id, rollback_path=gates.rollback_path,
        adoption_revision=adoption_revision,
    )
    return Chain(
        proposal=r.proposal, steps=steps, evidence=evidence, gates=gates,
        registries=registries, act=act,
    )


def run_to_authority(
    harness: Harness,
    proposal: SelfEvolutionProposal | None = None,
) -> tuple[SelfEvolutionProposal, Gates, dict[str, Any], list[SelfEvolutionStep], list[Evidence]]:
    """Advance the proposal to UNDER_AUTHORITY (gates all real)."""
    proposal = make_proposal(harness) if proposal is None else proposal
    gates = gates_for(harness, proposal)
    registries = registries_for(harness, gates)
    steps: list[SelfEvolutionStep] = []
    evidence: list[Evidence] = []
    r = advance(proposal, SelfEvolutionState.UNDER_ASSURANCE, registries, steps=steps, evidence=evidence)
    r = advance(
        r.proposal, SelfEvolutionState.UNDER_EXPERIMENT, registries,
        steps=steps, evidence=evidence, assurance_result_id=gates.assurance.id,
    )
    r = advance(
        r.proposal, SelfEvolutionState.UNDER_AUTHORITY, registries,
        steps=steps, evidence=evidence,
        experiment_id=gates.experiment.id, evaluation_id=gates.evaluation.id,
        promotion_id=promotion_ref(gates), rollback_path=gates.rollback_path,
    )
    return r.proposal, gates, registries, steps, evidence


# ---------------------------------------------------------------------------
# 1. Full governed happy path + determinism (byte-identical re-run)
# ---------------------------------------------------------------------------


def test_full_governed_happy_path_produces_deterministic_promoted_record(tmp_path):
    harness = harness_at(tmp_path / "repo")
    chain = run_happy(harness)
    promoted = chain.proposal

    assert promoted.state == SelfEvolutionState.PROMOTED
    assert promoted.assurance_status == AssuranceStatus.PASS
    assert promoted.assurance_result_id == chain.gates.assurance.id
    assert promoted.experiment_id == chain.gates.experiment.id
    assert promoted.evaluation_id == chain.gates.evaluation.id
    assert promoted.promotion_id == promotion_ref(chain.gates)
    assert promoted.autonomy_decision_id == chain.act.id
    assert promoted.adoption_revision is None  # truthful: no adoption citation supplied
    assert promoted.pending_authorization is None and promoted.pending_evidence is None

    # the gate sequence and the truthful outcomes of every consequential step
    assert [s.gate for s in chain.steps] == [
        SelfEvolutionGate.INTAKE,
        SelfEvolutionGate.W7_ASSURANCE,
        SelfEvolutionGate.W8_PROMOTION,
        SelfEvolutionGate.W9_AUTHORITY,
    ]
    assert all(s.outcome.state == TruthState.SUCCESS for s in chain.steps)
    assert all(s.from_state != s.to_state for s in chain.steps)

    # W4 evidence appended at EVERY consequential step, bound to the proposal
    assert len(promoted.evidence_ids) == 4
    assert [e.id for e in chain.evidence] == list(promoted.evidence_ids)
    for record in chain.evidence:
        assert record.subject_ref == promoted.id
        assert record.provenance.implementation_revision == REVISION
        assert record.kind == EvidenceKind.OBSERVATION
    # the steps are convertible verbatim into the W4 records (one algorithm)
    for step, record in zip(chain.steps, chain.evidence):
        assert step_to_w4_evidence(step, traceability=tr()) == record

    # the full explainability chain is preserved on the record (C2/required
    # outcome 10): hypothesis + trigger evidence + payload + gates + decision
    assert promoted.hypothesis.trigger_evidence_ids == (harness.intervention.id,)
    assert promoted.hypothesis.causal_hypothesis_ids == (harness.hypothesis.id,)
    assert promoted.changes[0].path == TARGET_MODULE
    assert promoted.changes[0].payload == PAYLOAD_TEXT
    assert promoted.changes[0].base_revision == REVISION == promoted.target_revision
    assert promoted.origin == ProposalOrigin.MODEL_GENERATED

    # the real engines produced the gates (not stubs)
    assert chain.gates.assurance.id.startswith("assurance-")
    assert chain.gates.gate_decision.promoted is True
    assert chain.act.id.startswith("autonomy-")


def test_identical_runs_produce_byte_identical_records_and_ids(tmp_path):
    chain_a = run_happy(harness_at(tmp_path / "repo-a"))
    chain_b = run_happy(harness_at(tmp_path / "repo-b"))

    # identical inputs -> identical content-addressed ids and byte-identical
    # records, even from independently recovered fixture repositories
    assert chain_a.proposal.id == chain_b.proposal.id
    assert chain_a.proposal == chain_b.proposal
    assert chain_a.steps == chain_b.steps
    assert chain_a.evidence == chain_b.evidence
    assert chain_a.gates.assurance.id == chain_b.gates.assurance.id
    assert chain_a.gates.experiment.id == chain_b.gates.experiment.id
    assert chain_a.act.id == chain_b.act.id


def test_promoted_record_carries_adoption_revision_as_data(tmp_path):
    harness = harness_at(tmp_path / "repo")
    adopted = run_happy(
        harness, adoption_revision="f00dcafe1234567890abcdef1234567890abcdef"
    )
    assert adopted.proposal.adoption_revision == "f00dcafe1234567890abcdef1234567890abcdef"

    # an empty adoption citation is rejected (never fabricated, never blank)
    with pytest.raises(SelfEvolutionContractError, match="adoption_revision"):
        run_happy(harness, adoption_revision="   ")


# ---------------------------------------------------------------------------
# 2. The frozen lifecycle state machine (no free-form transitions)
# ---------------------------------------------------------------------------


def test_lifecycle_state_machine_rejects_free_form_transitions():
    chain = [
        SelfEvolutionState.PROPOSED,
        SelfEvolutionState.UNDER_ASSURANCE,
        SelfEvolutionState.UNDER_EXPERIMENT,
        SelfEvolutionState.UNDER_AUTHORITY,
    ]
    for before, after in zip(chain, chain[1:]):
        validate_self_evolution_transition(before, after)
    # lawful branches
    validate_self_evolution_transition(SelfEvolutionState.PROPOSED, SelfEvolutionState.REJECTED)
    validate_self_evolution_transition(SelfEvolutionState.UNDER_ASSURANCE, SelfEvolutionState.REJECTED)
    validate_self_evolution_transition(SelfEvolutionState.UNDER_EXPERIMENT, SelfEvolutionState.REJECTED)
    validate_self_evolution_transition(SelfEvolutionState.UNDER_EXPERIMENT, SelfEvolutionState.ROLLED_BACK)
    validate_self_evolution_transition(SelfEvolutionState.UNDER_AUTHORITY, SelfEvolutionState.PAUSED_ASKING)
    validate_self_evolution_transition(SelfEvolutionState.UNDER_AUTHORITY, SelfEvolutionState.REJECTED)
    validate_self_evolution_transition(SelfEvolutionState.UNDER_AUTHORITY, SelfEvolutionState.ROLLED_BACK)
    validate_self_evolution_transition(SelfEvolutionState.PAUSED_ASKING, SelfEvolutionState.UNDER_AUTHORITY)
    validate_self_evolution_transition(SelfEvolutionState.PAUSED_ASKING, SelfEvolutionState.REJECTED)
    validate_self_evolution_transition(SelfEvolutionState.PROMOTED, SelfEvolutionState.ROLLED_BACK)

    # every other pair is refused (exhaustive)
    states = list(SelfEvolutionState)
    lawful = {
        (SelfEvolutionState.PROPOSED, SelfEvolutionState.UNDER_ASSURANCE),
        (SelfEvolutionState.PROPOSED, SelfEvolutionState.REJECTED),
        (SelfEvolutionState.UNDER_ASSURANCE, SelfEvolutionState.UNDER_EXPERIMENT),
        (SelfEvolutionState.UNDER_ASSURANCE, SelfEvolutionState.REJECTED),
        (SelfEvolutionState.UNDER_EXPERIMENT, SelfEvolutionState.UNDER_AUTHORITY),
        (SelfEvolutionState.UNDER_EXPERIMENT, SelfEvolutionState.REJECTED),
        (SelfEvolutionState.UNDER_EXPERIMENT, SelfEvolutionState.ROLLED_BACK),
        (SelfEvolutionState.UNDER_AUTHORITY, SelfEvolutionState.PROMOTED),
        (SelfEvolutionState.UNDER_AUTHORITY, SelfEvolutionState.PAUSED_ASKING),
        (SelfEvolutionState.UNDER_AUTHORITY, SelfEvolutionState.REJECTED),
        (SelfEvolutionState.UNDER_AUTHORITY, SelfEvolutionState.ROLLED_BACK),
        (SelfEvolutionState.PAUSED_ASKING, SelfEvolutionState.UNDER_AUTHORITY),
        (SelfEvolutionState.PAUSED_ASKING, SelfEvolutionState.REJECTED),
        (SelfEvolutionState.PROMOTED, SelfEvolutionState.ROLLED_BACK),
    }
    for before in states:
        for after in states:
            if (before, after) in lawful:
                continue
            with pytest.raises(SelfEvolutionContractError, match="invalid self-evolution lifecycle transition"):
                validate_self_evolution_transition(before, after)
    # non-enum states are refused
    with pytest.raises(SelfEvolutionContractError, match="must be a SelfEvolutionState"):
        validate_self_evolution_transition("PROPOSED", SelfEvolutionState.UNDER_ASSURANCE)


def proposal_in_state(
    harness: Harness,
    state: SelfEvolutionState,
) -> tuple[SelfEvolutionProposal, Gates, dict[str, Any]]:
    """Build a proposal record that is actually IN the given lifecycle state
    (advancing through the real gates)."""
    proposal = make_proposal(harness)
    gates = gates_for(harness, proposal)
    registries = registries_for(harness, gates)
    if state == SelfEvolutionState.PROPOSED:
        return proposal, gates, registries
    if state == SelfEvolutionState.REJECTED:
        reject = evaluate_autonomy(
            policy=act_policy(allow_act=False), action=DecisionAction.ACT,
            assurance=None, experiment=None, promotion=None,
            evidence_ids=(harness.intervention.id,), traceability=tr(),
            known_evidence=harness.known_evidence, blast_radius="limited",
            risk=0.1, confidence=0.9, reversible=True,
        )
        registries["known_decisions"][reject.id] = reject
        result = advance(proposal, SelfEvolutionState.REJECTED, registries, autonomy_decision_id=reject.id)
        return result.proposal, gates, registries
    admitted = advance(proposal, SelfEvolutionState.UNDER_ASSURANCE, registries)
    if state == SelfEvolutionState.UNDER_ASSURANCE:
        return admitted.proposal, gates, registries
    under_experiment = advance(
        admitted.proposal, SelfEvolutionState.UNDER_EXPERIMENT, registries,
        assurance_result_id=gates.assurance.id,
    )
    if state == SelfEvolutionState.UNDER_EXPERIMENT:
        return under_experiment.proposal, gates, registries
    if state == SelfEvolutionState.ROLLED_BACK:
        rolled = transition_experiment(gates.experiment, ExperimentState.ROLLED_BACK)
        registries["known_experiments"][rolled.id] = rolled
        result = advance(
            under_experiment.proposal, SelfEvolutionState.ROLLED_BACK, registries,
            experiment_id=rolled.id, rollback_path=gates.rollback_path,
        )
        return result.proposal, gates, registries
    under_authority = advance(
        under_experiment.proposal, SelfEvolutionState.UNDER_AUTHORITY, registries,
        experiment_id=gates.experiment.id, evaluation_id=gates.evaluation.id,
        promotion_id=promotion_ref(gates), rollback_path=gates.rollback_path,
    )
    if state == SelfEvolutionState.UNDER_AUTHORITY:
        return under_authority.proposal, gates, registries
    if state == SelfEvolutionState.PAUSED_ASKING:
        ask = decide(gates, action=DecisionAction.ACT, policy=act_policy(human_approval_for_act=True))
        registries["known_decisions"][ask.id] = ask
        result = advance(
            under_authority.proposal, SelfEvolutionState.PAUSED_ASKING, registries,
            autonomy_decision_id=ask.id,
        )
        return result.proposal, gates, registries
    if state == SelfEvolutionState.PROMOTED:
        act = decide(gates, action=DecisionAction.ACT)
        registries["known_decisions"][act.id] = act
        result = advance(
            under_authority.proposal, SelfEvolutionState.PROMOTED, registries,
            autonomy_decision_id=act.id, rollback_path=gates.rollback_path,
        )
        return result.proposal, gates, registries
    raise AssertionError(f"unsupported builder state {state}")


@pytest.mark.parametrize(
    ("from_state", "to_state"),
    [
        (SelfEvolutionState.PROPOSED, SelfEvolutionState.UNDER_EXPERIMENT),
        (SelfEvolutionState.PROPOSED, SelfEvolutionState.PROMOTED),
        (SelfEvolutionState.PROPOSED, SelfEvolutionState.UNDER_AUTHORITY),
        (SelfEvolutionState.UNDER_ASSURANCE, SelfEvolutionState.UNDER_AUTHORITY),
        (SelfEvolutionState.UNDER_EXPERIMENT, SelfEvolutionState.PROMOTED),
        (SelfEvolutionState.PAUSED_ASKING, SelfEvolutionState.PROMOTED),
        (SelfEvolutionState.REJECTED, SelfEvolutionState.UNDER_ASSURANCE),
        (SelfEvolutionState.ROLLED_BACK, SelfEvolutionState.PROMOTED),
        (SelfEvolutionState.PROMOTED, SelfEvolutionState.UNDER_AUTHORITY),
    ],
)
def test_stage_skip_attempts_are_rejected_at_the_transition_boundary(tmp_path, from_state, to_state):
    harness = harness_at(tmp_path / "repo")
    proposal, gates, registries = proposal_in_state(harness, from_state)
    assert proposal.state == from_state
    with pytest.raises(SelfEvolutionContractError, match="invalid self-evolution lifecycle transition"):
        transition_self_evolution(
            proposal, to_state, **registries,
            assurance_result_id=gates.assurance.id,
            experiment_id=gates.experiment.id,
            evaluation_id=gates.evaluation.id,
            promotion_id=promotion_ref(gates),
            autonomy_decision_id="autonomy-whatever",
            rollback_path=gates.rollback_path,
            timestamp=TS,
        )


# ---------------------------------------------------------------------------
# 3. W7-before-W8 ordering invariant (C3): non-PASS/missing/unbound rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status", [AssuranceStatus.FAIL, AssuranceStatus.UNKNOWN, AssuranceStatus.BLOCKED]
)
def test_under_experiment_requires_w7_pass_bound_to_exact_chain(tmp_path, status):
    harness = harness_at(tmp_path / "repo")
    proposal = make_proposal(harness)
    gates = gates_for(harness, proposal)
    registries = registries_for(harness, gates)
    admitted = advance(proposal, SelfEvolutionState.UNDER_ASSURANCE, registries)

    # a resolved non-PASS result can never unlock the experiment stage
    non_pass = assurance_record(candidate_id=proposal.id, status=status)
    registries["known_assurance"][non_pass.id] = non_pass
    with pytest.raises(SelfEvolutionContractError, match="W7-before-W8 ordering invariant"):
        advance(
            admitted.proposal, SelfEvolutionState.UNDER_EXPERIMENT, registries,
            assurance_result_id=non_pass.id,
        )

    # a PASS result bound to a DIFFERENT candidate: chain mismatch rejected
    foreign = assurance_record(candidate_id="selfevo-someone-else", status=AssuranceStatus.PASS)
    registries["known_assurance"][foreign.id] = foreign
    with pytest.raises(SelfEvolutionContractError, match="not bound to the exact proposal"):
        advance(
            admitted.proposal, SelfEvolutionState.UNDER_EXPERIMENT, registries,
            assurance_result_id=foreign.id,
        )

    # a PASS result bound to a DIFFERENT revision: chain mismatch rejected
    wrong_revision = assurance_record(
        candidate_id=proposal.id, status=AssuranceStatus.PASS, revision=OTHER_REVISION
    )
    registries["known_assurance"][wrong_revision.id] = wrong_revision
    with pytest.raises(SelfEvolutionContractError, match="does not bind to the proposal target revision"):
        advance(
            admitted.proposal, SelfEvolutionState.UNDER_EXPERIMENT, registries,
            assurance_result_id=wrong_revision.id,
        )

    # missing id / unknown id / non-record: rejected
    with pytest.raises(SelfEvolutionContractError, match="requires the W7 assurance result id"):
        advance(admitted.proposal, SelfEvolutionState.UNDER_EXPERIMENT, registries)
    with pytest.raises(SelfEvolutionContractError, match="not present in the caller-supplied"):
        advance(
            admitted.proposal, SelfEvolutionState.UNDER_EXPERIMENT, registries,
            assurance_result_id="assurance-bogus",
        )
    registries["known_assurance"]["assurance-fake"] = {"status": "PASS"}  # type: ignore[assignment]
    with pytest.raises(SelfEvolutionContractError, match="not a real W7 AssuranceResult"):
        advance(
            admitted.proposal, SelfEvolutionState.UNDER_EXPERIMENT, registries,
            assurance_result_id="assurance-fake",
        )

    # the real PASS result unlocks the stage
    result = advance(
        admitted.proposal, SelfEvolutionState.UNDER_EXPERIMENT, registries,
        assurance_result_id=gates.assurance.id,
    )
    assert result.proposal.state == SelfEvolutionState.UNDER_EXPERIMENT
    assert result.proposal.assurance_status == AssuranceStatus.PASS


@pytest.mark.parametrize(
    ("status", "expected_truth"),
    [
        (AssuranceStatus.FAIL, TruthState.FAILED),
        (AssuranceStatus.UNKNOWN, TruthState.UNKNOWN),
        (AssuranceStatus.BLOCKED, TruthState.UNAVAILABLE),
    ],
)
def test_rejection_on_resolved_non_pass_w7_preserves_distinctions(
    tmp_path, status, expected_truth
):
    harness = harness_at(tmp_path / "repo")
    proposal = make_proposal(harness)
    gates = gates_for(harness, proposal)
    registries = registries_for(harness, gates)
    admitted = advance(proposal, SelfEvolutionState.UNDER_ASSURANCE, registries)

    non_pass = assurance_record(candidate_id=proposal.id, status=status)
    registries["known_assurance"][non_pass.id] = non_pass
    result = advance(
        admitted.proposal, SelfEvolutionState.REJECTED, registries,
        assurance_result_id=non_pass.id,
    )
    assert result.proposal.state == SelfEvolutionState.REJECTED
    assert result.proposal.assurance_status == status
    # the distinct W7 status is preserved verbatim in the step + evidence
    assert result.step.outcome.state == expected_truth
    assert result.evidence.result.state == expected_truth
    assert status.value in result.step.outcome.detail

    # a PASS result cannot ground a rejection
    with pytest.raises(SelfEvolutionContractError, match="PASS W7 assurance result cannot ground"):
        advance(
            admitted.proposal, SelfEvolutionState.REJECTED, registries,
            assurance_result_id=gates.assurance.id,
        )


# ---------------------------------------------------------------------------
# 4. W8 promotion gate (C3/C7): PromotionGate/PromotionDecision required
# ---------------------------------------------------------------------------


def test_promotion_requires_the_w8_promotion_gate_decision(tmp_path):
    harness = harness_at(tmp_path / "repo")
    proposal, gates, registries, _, _ = run_to_authority(harness)
    under_experiment = advance(
        dataclasses.replace(proposal, state=SelfEvolutionState.UNDER_EXPERIMENT),
        SelfEvolutionState.UNDER_EXPERIMENT, registries,
    ) if False else None  # (the helper already advanced; rebuild below)
    # rebuild the UNDER_EXPERIMENT record for boundary probing
    admitted = advance(make_proposal(harness), SelfEvolutionState.UNDER_ASSURANCE, registries)
    under_experiment = advance(
        admitted.proposal, SelfEvolutionState.UNDER_EXPERIMENT, registries,
        assurance_result_id=gates.assurance.id,
    ).proposal

    # missing promotion id
    with pytest.raises(SelfEvolutionContractError, match="requires the W8 promotion decision id"):
        advance(
            under_experiment, SelfEvolutionState.UNDER_AUTHORITY, registries,
            experiment_id=gates.experiment.id, evaluation_id=gates.evaluation.id,
            rollback_path=gates.rollback_path,
        )
    # unknown promotion id
    with pytest.raises(SelfEvolutionContractError, match="not present in the caller-supplied"):
        advance(
            under_experiment, SelfEvolutionState.UNDER_AUTHORITY, registries,
            experiment_id=gates.experiment.id, evaluation_id=gates.evaluation.id,
            promotion_id="experiment-x:eval-y", rollback_path=gates.rollback_path,
        )
    # a non-promoted gate decision cannot unlock the authority stage
    refused = PromotionDecision(
        promoted=False, rationale="evaluation not promotion-eligible",
        experiment_id=gates.experiment.id, evaluation_id=gates.evaluation.id,
    )
    registries["known_promotions"][promotion_ref(gates)] = refused
    with pytest.raises(SelfEvolutionContractError, match="did not grant promotion"):
        advance(
            under_experiment, SelfEvolutionState.UNDER_AUTHORITY, registries,
            experiment_id=gates.experiment.id, evaluation_id=gates.evaluation.id,
            promotion_id=promotion_ref(gates), rollback_path=gates.rollback_path,
        )
    # a FORGED promoted decision over a non-eligible chain is refused by the
    # real PromotionGate re-run (the supplied record cannot outrank the engine)
    failing_gates = gates_for(harness, make_proposal(harness), evaluation_success=False)
    assert failing_gates.gate_decision.promoted is False
    forged = PromotionDecision(
        promoted=True, rationale="forged: ignores the failed evaluation",
        experiment_id=failing_gates.experiment.id, evaluation_id=failing_gates.evaluation.id,
    )
    failing_registries = registries_for(
        harness, failing_gates, promotions={promotion_ref(failing_gates): forged}
    )
    failing_admitted = advance(
        make_proposal(harness), SelfEvolutionState.UNDER_ASSURANCE, failing_registries
    )
    failing_under_experiment = advance(
        failing_admitted.proposal, SelfEvolutionState.UNDER_EXPERIMENT, failing_registries,
        assurance_result_id=failing_gates.assurance.id,
    ).proposal
    with pytest.raises(SelfEvolutionContractError, match="real W8 PromotionGate refused"):
        advance(
            failing_under_experiment, SelfEvolutionState.UNDER_AUTHORITY, failing_registries,
            experiment_id=failing_gates.experiment.id,
            evaluation_id=failing_gates.evaluation.id,
            promotion_id=promotion_ref(failing_gates),
            rollback_path=failing_gates.rollback_path,
        )


def test_rejection_at_the_experiment_stage_records_the_refused_gate(tmp_path):
    harness = harness_at(tmp_path / "repo")
    proposal = make_proposal(harness)
    failing_gates = gates_for(harness, proposal, evaluation_success=False)
    assert failing_gates.gate_decision.promoted is False
    registries = registries_for(harness, failing_gates)
    admitted = advance(proposal, SelfEvolutionState.UNDER_ASSURANCE, registries)
    under_experiment = advance(
        admitted.proposal, SelfEvolutionState.UNDER_EXPERIMENT, registries,
        assurance_result_id=failing_gates.assurance.id,
    ).proposal
    result = advance(
        under_experiment, SelfEvolutionState.REJECTED, registries,
        experiment_id=failing_gates.experiment.id,
        evaluation_id=failing_gates.evaluation.id,
        promotion_id=promotion_ref(failing_gates),
    )
    assert result.proposal.state == SelfEvolutionState.REJECTED
    assert result.proposal.promotion_id == promotion_ref(failing_gates)
    assert result.step.gate == SelfEvolutionGate.W8_PROMOTION
    assert result.step.outcome.state == TruthState.FAILED
    # a promoted decision cannot ground a rejection
    ok_gates = gates_for(harness, proposal)
    ok_registries = registries_for(harness, ok_gates)
    ok_admitted = advance(proposal, SelfEvolutionState.UNDER_ASSURANCE, ok_registries)
    ok_under_experiment = advance(
        ok_admitted.proposal, SelfEvolutionState.UNDER_EXPERIMENT, ok_registries,
        assurance_result_id=ok_gates.assurance.id,
    ).proposal
    with pytest.raises(SelfEvolutionContractError, match="cannot ground a rejection"):
        advance(
            ok_under_experiment, SelfEvolutionState.REJECTED, ok_registries,
            experiment_id=ok_gates.experiment.id, evaluation_id=ok_gates.evaluation.id,
            promotion_id=promotion_ref(ok_gates),
        )


def test_promotion_requires_a_bounded_rollback_path_bound_to_the_declared_reference(tmp_path):
    harness = harness_at(tmp_path / "repo")
    proposal = make_proposal(harness)
    gates = gates_for(harness, proposal)
    registries = registries_for(harness, gates)
    admitted = advance(proposal, SelfEvolutionState.UNDER_ASSURANCE, registries)
    under_experiment = advance(
        admitted.proposal, SelfEvolutionState.UNDER_EXPERIMENT, registries,
        assurance_result_id=gates.assurance.id,
    ).proposal

    base = dict(
        experiment_id=gates.experiment.id, evaluation_id=gates.evaluation.id,
        promotion_id=promotion_ref(gates),
    )
    # no rollback path at all
    with pytest.raises(SelfEvolutionContractError, match="requires a bounded W8 RollbackPath"):
        advance(under_experiment, SelfEvolutionState.UNDER_AUTHORITY, registries, **base)
    # a rollback path bound to a DIFFERENT reference
    wrong_ref = RollbackPath(
        reference="rb-someone-else", evidence_ids=(harness.rollback_ev.id,),
        detail="wrong reference",
    )
    with pytest.raises(SelfEvolutionContractError, match="does not bind to the proposal's"):
        advance(under_experiment, SelfEvolutionState.UNDER_AUTHORITY, registries,
                rollback_path=wrong_ref, **base)
    # recovery evidence missing from the registry
    missing_ev = RollbackPath(
        reference=ROLLBACK_REF, evidence_ids=("evidence-not-there",), detail="missing evidence",
    )
    with pytest.raises(SelfEvolutionContractError, match="not present in the caller-supplied"):
        advance(under_experiment, SelfEvolutionState.UNDER_AUTHORITY, registries,
                rollback_path=missing_ev, **base)
    # recovery evidence with a non-SUCCESS observed state
    failed = failed_evidence(harness.graph_id)
    registries["known_evidence"][failed.id] = failed
    failed_path = RollbackPath(
        reference=ROLLBACK_REF, evidence_ids=(failed.id,), detail="failed recovery evidence",
    )
    with pytest.raises(SelfEvolutionContractError, match="requires SUCCESS recovery evidence"):
        advance(under_experiment, SelfEvolutionState.UNDER_AUTHORITY, registries,
                rollback_path=failed_path, **base)
    # recovery evidence provenance-bound to a different revision
    other_rev = rollback_evidence(harness.graph_id)
    other_rev = _build_evidence(
        kind=EvidenceKind.OBSERVATION, source_ref="rollback-verified-other-rev",
        subject_ref=harness.graph_id,
        result=TruthfulValue(TruthState.SUCCESS, "rollback-capable", None),
        provenance=prov(harness.graph_id, revision=OTHER_REVISION), traceability=tr(),
        availability=TruthState.SUCCESS,
    )
    registries["known_evidence"][other_rev.id] = other_rev
    other_path = RollbackPath(
        reference=ROLLBACK_REF, evidence_ids=(other_rev.id,), detail="wrong revision",
    )
    with pytest.raises(SelfEvolutionContractError, match="does not bind to the proposal target revision"):
        advance(under_experiment, SelfEvolutionState.UNDER_AUTHORITY, registries,
                rollback_path=other_path, **base)
    # the bounded, bound rollback path unlocks the authority stage
    result = advance(
        under_experiment, SelfEvolutionState.UNDER_AUTHORITY, registries,
        rollback_path=gates.rollback_path, **base,
    )
    assert result.proposal.state == SelfEvolutionState.UNDER_AUTHORITY


# ---------------------------------------------------------------------------
# 5. W9 authority gate (C4): missing/unresolved ACT rejection
# ---------------------------------------------------------------------------


def test_missing_or_unresolved_w9_reference_is_rejected(tmp_path):
    harness = harness_at(tmp_path / "repo")
    proposal, gates, registries, _, _ = run_to_authority(harness)

    # no decision id supplied: no gate, no promotion
    with pytest.raises(SelfEvolutionContractError, match="requires the W9 autonomy decision id"):
        advance(
            proposal, SelfEvolutionState.PROMOTED, registries,
            rollback_path=gates.rollback_path,
        )
    # unresolved reference
    with pytest.raises(SelfEvolutionContractError, match="unresolved W9 reference|not present"):
        advance(
            proposal, SelfEvolutionState.PROMOTED, registries,
            autonomy_decision_id="autonomy-bogus", rollback_path=gates.rollback_path,
        )
    # a non-record in the registry
    registries["known_decisions"]["autonomy-fake"] = {"state": "ACT"}  # type: ignore[assignment]
    with pytest.raises(SelfEvolutionContractError, match="not a real W9 AutonomyDecision"):
        advance(
            proposal, SelfEvolutionState.PROMOTED, registries,
            autonomy_decision_id="autonomy-fake", rollback_path=gates.rollback_path,
        )
    # a resolved decision in the WRONG state (ASK) cannot promote
    ask = decide(gates, action=DecisionAction.ACT, policy=act_policy(human_approval_for_act=True))
    assert ask.state == AutonomyDecisionState.ASK
    registries["known_decisions"][ask.id] = ask
    with pytest.raises(SelfEvolutionContractError, match="requires a resolved W9 ACT decision"):
        advance(
            proposal, SelfEvolutionState.PROMOTED, registries,
            autonomy_decision_id=ask.id, rollback_path=gates.rollback_path,
        )
    # a GATHER_EVIDENCE decision cannot promote either
    gather = decide(gates, action=DecisionAction.GATHER_EVIDENCE)
    registries["known_decisions"][gather.id] = gather
    with pytest.raises(SelfEvolutionContractError, match="requires a resolved W9 ACT decision"):
        advance(
            proposal, SelfEvolutionState.PROMOTED, registries,
            autonomy_decision_id=gather.id, rollback_path=gates.rollback_path,
        )
    # an ACT decision bound to a DIFFERENT chain is rejected
    act = decide(gates, action=DecisionAction.ACT)
    foreign_chain = AutonomyDecision(
        id="", state=AutonomyDecisionState.ACT, action=DecisionAction.ACT,
        rationale="act bound to someone else's chain",
        reasons=("forged",), evidence_ids=tuple(gates.evaluation.evidence_ids),
        assurance_id="assurance-someone-else", experiment_id=gates.experiment.id,
        promotion_id=promotion_ref(gates), policy_id="policy-selfevo-1", traceability=tr(),
    )
    registries["known_decisions"][foreign_chain.id] = foreign_chain
    with pytest.raises(SelfEvolutionContractError, match="not bound to the exact assurance chain"):
        advance(
            proposal, SelfEvolutionState.PROMOTED, registries,
            autonomy_decision_id=foreign_chain.id, rollback_path=gates.rollback_path,
        )
    # an ACT decision whose evidence set does not match the W8 evaluation
    mismatched = AutonomyDecision(
        id="", state=AutonomyDecisionState.ACT, action=DecisionAction.ACT,
        rationale="act with mismatched evidence",
        reasons=("forged",), evidence_ids=(harness.intervention.id,),
        assurance_id=gates.assurance.id, experiment_id=gates.experiment.id,
        promotion_id=promotion_ref(gates), policy_id="policy-selfevo-1", traceability=tr(),
    )
    registries["known_decisions"][mismatched.id] = mismatched
    with pytest.raises(SelfEvolutionContractError, match="evidence ids do not match the W8 evaluation"):
        advance(
            proposal, SelfEvolutionState.PROMOTED, registries,
            autonomy_decision_id=mismatched.id, rollback_path=gates.rollback_path,
        )
    # promotion also requires the bounded rollback path (C7 at the only
    # promotion point)
    registries["known_decisions"][act.id] = act
    with pytest.raises(SelfEvolutionContractError, match="requires a bounded W8 RollbackPath"):
        advance(proposal, SelfEvolutionState.PROMOTED, registries, autonomy_decision_id=act.id)
    # the resolved ACT decision + bounded rollback promotes
    result = advance(
        proposal, SelfEvolutionState.PROMOTED, registries,
        autonomy_decision_id=act.id, rollback_path=gates.rollback_path,
    )
    assert result.proposal.state == SelfEvolutionState.PROMOTED
    assert result.step.gate == SelfEvolutionGate.W9_AUTHORITY


# ---------------------------------------------------------------------------
# 6. ASK pause mechanics (C5)
# ---------------------------------------------------------------------------


def test_w9_ask_pauses_with_explicit_pending_authorization_record(tmp_path):
    harness = harness_at(tmp_path / "repo")
    proposal, gates, registries, steps, evidence = run_to_authority(harness)
    ask = decide(gates, action=DecisionAction.ACT, policy=act_policy(human_approval_for_act=True))
    assert ask.state == AutonomyDecisionState.ASK
    registries["known_decisions"][ask.id] = ask

    result = advance(proposal, SelfEvolutionState.PAUSED_ASKING, registries, autonomy_decision_id=ask.id)
    paused = result.proposal
    assert paused.state == SelfEvolutionState.PAUSED_ASKING
    assert paused.autonomy_decision_id == ask.id

    pending = paused.pending_authorization
    assert pending is not None
    assert pending.resolution == PendingResolution.PENDING
    assert pending.decision_state == AutonomyDecisionState.ASK
    assert pending.decision_id == ask.id
    assert pending.proposal_id == paused.id
    assert pending.rationale == ask.rationale

    # the pause is itself recorded as truthful UNKNOWN evidence — never silent
    assert result.step.gate == SelfEvolutionGate.W9_ASK
    assert result.step.outcome.state == TruthState.UNKNOWN
    assert result.evidence.result.state == TruthState.UNKNOWN
    assert "pending human authorization" in result.evidence.result.detail

    # a non-ASK decision cannot pause
    gather = decide(gates, action=DecisionAction.GATHER_EVIDENCE)
    registries["known_decisions"][gather.id] = gather
    with pytest.raises(SelfEvolutionContractError, match="requires a resolved W9 ASK decision"):
        advance(proposal, SelfEvolutionState.PAUSED_ASKING, registries, autonomy_decision_id=gather.id)


def test_ask_pause_leaves_only_via_a_new_resolved_act_decision(tmp_path):
    harness = harness_at(tmp_path / "repo")
    proposal, gates, registries, _, _ = run_to_authority(harness)
    ask = decide(gates, action=DecisionAction.ACT, policy=act_policy(human_approval_for_act=True))
    registries["known_decisions"][ask.id] = ask
    paused = advance(
        proposal, SelfEvolutionState.PAUSED_ASKING, registries, autonomy_decision_id=ask.id
    ).proposal

    # leaving the pause without a decision is impossible
    with pytest.raises(SelfEvolutionContractError, match="requires the W9 autonomy decision id"):
        advance(paused, SelfEvolutionState.UNDER_AUTHORITY, registries)
    # the OLD ASK decision cannot leave the pause
    with pytest.raises(SelfEvolutionContractError, match="NEW resolved W9 ACT decision"):
        advance(paused, SelfEvolutionState.UNDER_AUTHORITY, registries, autonomy_decision_id=ask.id)
    # a GATHER_EVIDENCE decision cannot leave the pause either
    gather = decide(gates, action=DecisionAction.GATHER_EVIDENCE)
    registries["known_decisions"][gather.id] = gather
    with pytest.raises(SelfEvolutionContractError, match="NEW resolved W9 ACT decision"):
        advance(paused, SelfEvolutionState.UNDER_AUTHORITY, registries, autonomy_decision_id=gather.id)

    # a NEW resolved ACT decision (human authority) leaves the pause
    act = decide(
        gates, action=DecisionAction.ACT, policy=act_policy(),
        human_authority_present=True,
    )
    assert act.state == AutonomyDecisionState.ACT and act.id != ask.id
    registries["known_decisions"][act.id] = act
    resumed = advance(
        paused, SelfEvolutionState.UNDER_AUTHORITY, registries, autonomy_decision_id=act.id
    )
    assert resumed.proposal.state == SelfEvolutionState.UNDER_AUTHORITY
    assert resumed.proposal.pending_authorization is None
    assert resumed.proposal.autonomy_decision_id == act.id
    assert resumed.step.gate == SelfEvolutionGate.W9_RESUME
    assert resumed.step.outcome.state == TruthState.SUCCESS

    # and the resumed proposal promotes through the ordinary promotion gate
    promoted = advance(
        resumed.proposal, SelfEvolutionState.PROMOTED, registries,
        autonomy_decision_id=act.id, rollback_path=gates.rollback_path,
    )
    assert promoted.proposal.state == SelfEvolutionState.PROMOTED


def test_pending_authorization_can_never_auto_approve(tmp_path):
    harness = harness_at(tmp_path / "repo")
    proposal, gates, registries, _, _ = run_to_authority(harness)
    ask = decide(gates, action=DecisionAction.ACT, policy=act_policy(human_approval_for_act=True))
    registries["known_decisions"][ask.id] = ask
    paused = advance(
        proposal, SelfEvolutionState.PAUSED_ASKING, registries, autonomy_decision_id=ask.id
    ).proposal
    pending = paused.pending_authorization
    assert pending is not None

    # PENDING is the only resolution state; no granting API exists anywhere
    assert [s.name for s in PendingResolution] == ["PENDING"]
    granters = {"approve", "grant", "resolve", "authorize", "with_resolution", "promote"}
    assert not granters & {
        n for n in dir(pending) if not n.startswith("_") and callable(getattr(pending, n))
    }
    # a resolved pending record is unconstructible (PENDING is the only
    # member; a forged non-PENDING resolution is refused by validate)
    forged = PendingProposalAuthorization(
        proposal_id=pending.proposal_id, decision_id=pending.decision_id,
        decision_state=pending.decision_state, requested_action=pending.requested_action,
        rationale=pending.rationale, reasons=pending.reasons, id=pending.id,
    )
    object.__setattr__(forged, "resolution", "approved")
    with pytest.raises(SelfEvolutionContractError, match="resolved state"):
        forged.validate()
    # the paused record itself cannot be promoted directly (frozen table)
    with pytest.raises(SelfEvolutionContractError, match="invalid self-evolution lifecycle transition"):
        transition_self_evolution(
            paused, SelfEvolutionState.PROMOTED, **registries,
            autonomy_decision_id=ask.id, rollback_path=gates.rollback_path, timestamp=TS,
        )
    # a pending record requires a real ASK decision
    act = decide(gates, action=DecisionAction.ACT)
    with pytest.raises(SelfEvolutionContractError, match="ASK decision"):
        PendingProposalAuthorization.from_decision(act, proposal_id=paused.id)
    with pytest.raises(SelfEvolutionContractError, match="AutonomyDecision"):
        PendingProposalAuthorization.from_decision({"state": "ASK"}, proposal_id=paused.id)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 7. Non-resolving W9 states: explicit deferral (C5)
# ---------------------------------------------------------------------------


def test_w9_gather_evidence_defers_with_explicit_pending_record(tmp_path):
    harness = harness_at(tmp_path / "repo")
    proposal, gates, registries, _, _ = run_to_authority(harness)
    gather = decide(gates, action=DecisionAction.GATHER_EVIDENCE)
    assert gather.state == AutonomyDecisionState.GATHER_EVIDENCE
    registries["known_decisions"][gather.id] = gather

    result = defer_self_evolution(
        proposal, gather.id, known_decisions=registries["known_decisions"], timestamp=TS
    )
    deferred = result.proposal
    # no advancement, no refusal: the state is unchanged
    assert deferred.state == SelfEvolutionState.UNDER_AUTHORITY
    assert deferred.pending_evidence is not None
    assert deferred.pending_evidence.decision_state == AutonomyDecisionState.GATHER_EVIDENCE
    assert deferred.pending_evidence.resolution == PendingResolution.PENDING
    # the deferral is recorded as truthful UNKNOWN evidence
    assert result.step.gate == SelfEvolutionGate.W9_DEFERRAL
    assert result.step.from_state == result.step.to_state == SelfEvolutionState.UNDER_AUTHORITY
    assert result.step.outcome.state == TruthState.UNKNOWN
    assert result.evidence.result.state == TruthState.UNKNOWN

    # the deferral did NOT refuse the proposal: promotion still works
    act = decide(gates, action=DecisionAction.ACT)
    registries["known_decisions"][act.id] = act
    promoted = advance(
        deferred, SelfEvolutionState.PROMOTED, registries,
        autonomy_decision_id=act.id, rollback_path=gates.rollback_path,
    )
    assert promoted.proposal.state == SelfEvolutionState.PROMOTED
    assert promoted.proposal.pending_evidence is None


def test_w9_experiment_decision_defers_and_deferral_is_gated(tmp_path):
    harness = harness_at(tmp_path / "repo")
    proposal, gates, registries, _, _ = run_to_authority(harness)
    experiment_action = evaluate_autonomy(
        policy=AutonomyRequest(
            id="policy-selfevo-experiment", version=1,
            allowed_actions=(DecisionAction.EXPERIMENT, DecisionAction.GATHER_EVIDENCE),
            ceilings=PolicyCeiling(
                max_risk=0.3, max_blast_radius="service", require_reversible=True,
                min_confidence=0.8, require_human_approval_for_act=False,
            ),
            traceability=tr(),
        ),
        action=DecisionAction.EXPERIMENT,
        assurance=gates.assurance, experiment=gates.experiment, promotion=None,
        evidence_ids=tuple(gates.evaluation.evidence_ids), traceability=tr(),
        known_evidence=gates.known_evidence, blast_radius="limited",
        risk=0.1, confidence=0.9, reversible=True,
    )
    assert experiment_action.state == AutonomyDecisionState.EXPERIMENT
    registries["known_decisions"][experiment_action.id] = experiment_action

    result = defer_self_evolution(
        proposal, experiment_action.id,
        known_decisions=registries["known_decisions"], timestamp=TS,
    )
    assert result.proposal.state == SelfEvolutionState.UNDER_AUTHORITY
    assert result.proposal.pending_evidence.decision_state == AutonomyDecisionState.EXPERIMENT

    # a deferral requires a NON-RESOLVING decision: ACT/ASK/REJECT/ROLLBACK
    # are refused
    act = decide(gates, action=DecisionAction.ACT)
    registries["known_decisions"][act.id] = act
    with pytest.raises(SelfEvolutionContractError, match="non-resolving W9 decision"):
        defer_self_evolution(
            proposal, act.id, known_decisions=registries["known_decisions"]
        )
    ask = decide(gates, action=DecisionAction.ACT, policy=act_policy(human_approval_for_act=True))
    registries["known_decisions"][ask.id] = ask
    with pytest.raises(SelfEvolutionContractError, match="non-resolving W9 decision"):
        defer_self_evolution(
            proposal, ask.id, known_decisions=registries["known_decisions"]
        )
    # a deferral is only lawful while the proposal awaits W9 authority
    fresh = make_proposal(harness)
    with pytest.raises(SelfEvolutionContractError, match="only lawful while the proposal awaits"):
        defer_self_evolution(
            fresh, experiment_action.id, known_decisions=registries["known_decisions"]
        )
    # an unresolved deferral reference is rejected
    with pytest.raises(SelfEvolutionContractError, match="unresolved W9 reference|not present"):
        defer_self_evolution(
            proposal, "autonomy-bogus", known_decisions=registries["known_decisions"]
        )


def gather_id(registries: dict[str, Any]) -> str:
    for did, decision in registries["known_decisions"].items():
        if decision.state == AutonomyDecisionState.GATHER_EVIDENCE:
            return did
    raise AssertionError("no GATHER_EVIDENCE decision in the registries")


def test_deferral_while_paused_keeps_the_pause_state(tmp_path):
    harness = harness_at(tmp_path / "repo")
    proposal, gates, registries, _, _ = run_to_authority(harness)
    ask = decide(gates, action=DecisionAction.ACT, policy=act_policy(human_approval_for_act=True))
    registries["known_decisions"][ask.id] = ask
    paused = advance(
        proposal, SelfEvolutionState.PAUSED_ASKING, registries, autonomy_decision_id=ask.id
    ).proposal
    gather = decide(gates, action=DecisionAction.GATHER_EVIDENCE)
    registries["known_decisions"][gather.id] = gather

    result = defer_self_evolution(
        paused, gather.id, known_decisions=registries["known_decisions"], timestamp=TS
    )
    # still paused (the deferral neither advances nor refuses), with BOTH the
    # pause record and the pending-evidence record explicit
    assert result.proposal.state == SelfEvolutionState.PAUSED_ASKING
    assert result.proposal.pending_authorization is not None
    assert result.proposal.pending_evidence is not None
    assert result.step.outcome.state == TruthState.UNKNOWN


# ---------------------------------------------------------------------------
# 8. W9 REJECT refusal + W9 ROLLBACK with recovery evidence (C5/C7)
# ---------------------------------------------------------------------------


def test_w9_reject_refuses_the_proposal(tmp_path):
    harness = harness_at(tmp_path / "repo")
    # refusal at the authority stage
    proposal, gates, registries, _, _ = run_to_authority(harness)
    reject = decide(gates, action=DecisionAction.ACT, policy=act_policy(allow_act=False))
    assert reject.state == AutonomyDecisionState.REJECT
    registries["known_decisions"][reject.id] = reject
    result = advance(proposal, SelfEvolutionState.REJECTED, registries, autonomy_decision_id=reject.id)
    assert result.proposal.state == SelfEvolutionState.REJECTED
    assert result.proposal.autonomy_decision_id == reject.id
    assert result.step.gate == SelfEvolutionGate.W9_REJECT
    assert result.step.outcome.state == TruthState.FAILED
    assert reject.rationale in result.step.outcome.detail

    # refusal at intake (PROPOSED): a REJECT decision with an empty chain
    fresh = make_proposal(harness)
    intake_reject = evaluate_autonomy(
        policy=act_policy(allow_act=False), action=DecisionAction.ACT,
        assurance=None, experiment=None, promotion=None,
        evidence_ids=(harness.intervention.id,), traceability=tr(),
        known_evidence=harness.known_evidence, blast_radius="limited",
        risk=0.1, confidence=0.9, reversible=True,
    )
    assert intake_reject.state == AutonomyDecisionState.REJECT
    assert intake_reject.assurance_id == ""
    registries["known_decisions"][intake_reject.id] = intake_reject
    intake_result = advance(
        fresh, SelfEvolutionState.REJECTED, registries,
        autonomy_decision_id=intake_reject.id,
    )
    assert intake_result.proposal.state == SelfEvolutionState.REJECTED
    assert intake_result.proposal.autonomy_decision_id == intake_reject.id
    assert intake_result.proposal.assurance_result_id is None

    # a non-REJECT decision cannot ground an intake rejection
    act = decide(gates, action=DecisionAction.ACT)
    registries["known_decisions"][act.id] = act
    with pytest.raises(SelfEvolutionContractError, match="requires a resolved W9 REJECT decision"):
        advance(fresh, SelfEvolutionState.REJECTED, registries, autonomy_decision_id=act.id)

    # REJECTED is terminal
    with pytest.raises(SelfEvolutionContractError, match="invalid self-evolution lifecycle transition"):
        advance(
            intake_result.proposal, SelfEvolutionState.UNDER_ASSURANCE, registries,
            autonomy_decision_id=intake_reject.id,
        )


def test_w9_rollback_from_authority_rolls_back_with_recovery_evidence(tmp_path):
    harness = harness_at(tmp_path / "repo")
    proposal, gates, registries, _, _ = run_to_authority(harness)
    rollback = decide(gates, action=DecisionAction.ROLLBACK)
    assert rollback.state == AutonomyDecisionState.ROLLBACK
    registries["known_decisions"][rollback.id] = rollback

    # governed recovery evidence is required
    with pytest.raises(SelfEvolutionContractError, match="requires a bounded W8 RollbackPath"):
        advance(proposal, SelfEvolutionState.ROLLED_BACK, registries, autonomy_decision_id=rollback.id)
    wrong = RollbackPath(
        reference="rb-someone-else", evidence_ids=(harness.rollback_ev.id,), detail="wrong ref"
    )
    with pytest.raises(SelfEvolutionContractError, match="does not bind to the proposal's"):
        advance(
            proposal, SelfEvolutionState.ROLLED_BACK, registries,
            autonomy_decision_id=rollback.id, rollback_path=wrong,
        )

    result = advance(
        proposal, SelfEvolutionState.ROLLED_BACK, registries,
        autonomy_decision_id=rollback.id, rollback_path=gates.rollback_path,
    )
    assert result.proposal.state == SelfEvolutionState.ROLLED_BACK
    assert result.step.gate == SelfEvolutionGate.W9_ROLLBACK
    assert result.step.outcome.state == TruthState.SUCCESS
    assert result.step.outcome.value == ROLLBACK_REF
    # the recovery step becomes ROLLBACK-kind W4 evidence
    assert result.evidence.kind == EvidenceKind.ROLLBACK

    # a non-ROLLBACK decision cannot ground a rollback
    act = decide(gates, action=DecisionAction.ACT)
    registries["known_decisions"][act.id] = act
    with pytest.raises(SelfEvolutionContractError, match="requires a resolved W9 ROLLBACK decision"):
        advance(
            proposal, SelfEvolutionState.ROLLED_BACK, registries,
            autonomy_decision_id=act.id, rollback_path=gates.rollback_path,
        )


def test_promoted_record_rolls_back_through_governed_recovery(tmp_path):
    harness = harness_at(tmp_path / "repo")
    chain = run_happy(harness, adoption_revision="f00dcafe1234567890abcdef1234567890abcdef")
    promoted = chain.proposal
    rollback = decide(chain.gates, action=DecisionAction.ROLLBACK)
    chain.registries["known_decisions"][rollback.id] = rollback

    result = advance(
        promoted, SelfEvolutionState.ROLLED_BACK, chain.registries,
        autonomy_decision_id=rollback.id, rollback_path=chain.gates.rollback_path,
    )
    assert result.proposal.state == SelfEvolutionState.ROLLED_BACK
    # the adoption citation is preserved as historical data
    assert result.proposal.adoption_revision == "f00dcafe1234567890abcdef1234567890abcdef"
    assert result.evidence.kind == EvidenceKind.ROLLBACK
    assert result.evidence.result.state == TruthState.SUCCESS

    # ROLLED_BACK is terminal
    with pytest.raises(SelfEvolutionContractError, match="invalid self-evolution lifecycle transition"):
        advance(
            result.proposal, SelfEvolutionState.PROMOTED, chain.registries,
            autonomy_decision_id=rollback.id, rollback_path=chain.gates.rollback_path,
        )


def test_w8_experiment_rollback_from_under_experiment_requires_governed_recovery(tmp_path):
    harness = harness_at(tmp_path / "repo")
    proposal = make_proposal(harness)
    gates = gates_for(harness, proposal)
    registries = registries_for(harness, gates)
    admitted = advance(proposal, SelfEvolutionState.UNDER_ASSURANCE, registries)
    under_experiment = advance(
        admitted.proposal, SelfEvolutionState.UNDER_EXPERIMENT, registries,
        assurance_result_id=gates.assurance.id,
    ).proposal

    # the W8 experiment lifecycle itself must be ROLLED_BACK (W8-governed)
    with pytest.raises(SelfEvolutionContractError, match="must itself be ROLLED_BACK"):
        advance(
            under_experiment, SelfEvolutionState.ROLLED_BACK, registries,
            experiment_id=gates.experiment.id, rollback_path=gates.rollback_path,
        )

    # roll the real W8 experiment back, then the proposal follows under the
    # same recovery binding
    rolled = transition_experiment(gates.experiment, ExperimentState.ROLLED_BACK)
    registries["known_experiments"][rolled.id] = rolled
    with pytest.raises(SelfEvolutionContractError, match="requires a bounded W8 RollbackPath"):
        advance(
            under_experiment, SelfEvolutionState.ROLLED_BACK, registries, experiment_id=rolled.id
        )
    result = advance(
        under_experiment, SelfEvolutionState.ROLLED_BACK, registries,
        experiment_id=rolled.id, rollback_path=gates.rollback_path,
    )
    assert result.proposal.state == SelfEvolutionState.ROLLED_BACK
    assert result.proposal.experiment_id == rolled.id
    assert result.step.gate == SelfEvolutionGate.W8_EXPERIMENT_ROLLBACK
    assert result.evidence.kind == EvidenceKind.ROLLBACK
    assert result.step.outcome.state == TruthState.SUCCESS


# ---------------------------------------------------------------------------
# 9. Intake policy (C6): frozen paths, authority-module DELETE, malformed input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    sorted(FROZEN_AUTHORITY_PATHS | {
        "spec/work-orders/W13-self-evolution.md",
        "spec/work-orders/README.md",
        "spec/work-orders/W99-future.md",
    }),
)
def test_frozen_authority_target_paths_are_rejected_at_intake(path):
    # rejected at SourceChange construction (the innermost boundary)...
    with pytest.raises(SelfEvolutionContractError, match="frozen authority artifact"):
        SourceChange(
            path=path, base_revision=REVISION,
            kind=SourceChangeKind.MODIFY, payload=PAYLOAD_TEXT,
        )
    # ...and at proposal construction (defense in depth, via a forged change
    # that bypasses the change's own __post_init__)
    forged = SourceChange(
        path="src/sos/optimization.py", base_revision=REVISION,
        kind=SourceChangeKind.MODIFY, payload=PAYLOAD_TEXT,
    )
    object.__setattr__(forged, "path", path)
    hypothesis = SelfImprovementHypothesis(
        rationale="r", trigger_evidence_ids=("evidence-x",),
        predicted_effects=("e",),
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
    )
    with pytest.raises(SelfEvolutionContractError, match="frozen authority artifact"):
        SelfEvolutionProposal(
            target_revision=REVISION, target_paths=(path,), changes=(forged,),
            hypothesis=hypothesis, origin=ProposalOrigin.HUMAN_GENERATED,
            rollback_ref=ROLLBACK_REF, meta_depth=0, traceability=tr(),
        )


@pytest.mark.parametrize("path", sorted(AUTHORITY_MODULE_PATHS))
def test_delete_on_authority_implementation_modules_is_rejected_at_intake(path):
    with pytest.raises(SelfEvolutionContractError, match="authority-implementation module"):
        SourceChange(path=path, base_revision=REVISION, kind=SourceChangeKind.DELETE, payload="")


def test_non_authority_delete_and_authority_modify_remain_lawful_proposals(tmp_path):
    # DELETE of a non-authority module is a lawful (still fully gated) proposal
    change = SourceChange(
        path="src/sos/optimization.py", base_revision=REVISION,
        kind=SourceChangeKind.DELETE, payload="",
    )
    assert change.kind == SourceChangeKind.DELETE
    # MODIFY of an authority module is a lawful (still fully gated) proposal —
    # authority deletion is the prohibited class, not authority evolution
    modify = SourceChange(
        path="src/sos/assurance.py", base_revision=REVISION,
        kind=SourceChangeKind.MODIFY, payload=PAYLOAD_TEXT,
    )
    assert modify.kind == SourceChangeKind.MODIFY


@pytest.mark.parametrize(
    ("change_spec", "target_path", "match"),
    [
        # malformed paths
        ("/etc/hosts", "/etc/hosts", "repo-relative POSIX path"),
        ("../outside.py", "../outside.py", "parent-directory components"),
        ("src\\sos\\x.py", "src\\sos\\x.py", "repo-relative POSIX path"),
        ("src/sos/", "src/sos/", "must name a file"),
        # payload rules
        ("src/sos/new.py::CREATE::  ", "src/sos/new.py", "require a diff-shaped payload"),
        (f"src/sos/new.py::DELETE::{PAYLOAD_TEXT}", "src/sos/new.py", "carry no payload"),
        # chain binding of the change's base revision
        (f"src/sos/x.py::MODIFY-WRONG-REV::{PAYLOAD_TEXT}", "src/sos/x.py",
         "does not bind to the proposal target revision"),
    ],
)
def test_proposal_construction_rejects_malformed_changes(change_spec, target_path, match):
    change = None

    def build_change(spec: str) -> SourceChange:
        if "::" not in spec:
            return SourceChange(spec, REVISION, SourceChangeKind.MODIFY, PAYLOAD_TEXT)
        path, rest = spec.split("::", 1)
        if rest == "CREATE":
            return SourceChange(path, REVISION, SourceChangeKind.CREATE, "  ")
        if rest.startswith("DELETE::"):
            return SourceChange(path, REVISION, SourceChangeKind.DELETE, rest.split("::", 1)[1])
        if rest.startswith("MODIFY-WRONG-REV::"):
            return SourceChange(
                path, OTHER_REVISION, SourceChangeKind.MODIFY, rest.split("::", 1)[1]
            )
        return SourceChange(path, REVISION, SourceChangeKind.MODIFY, rest.split("::", 1)[-1])

    hypothesis = SelfImprovementHypothesis(
        rationale="r", trigger_evidence_ids=("evidence-x",),
        predicted_effects=("e",),
        uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
    )
    # the rejection surfaces at the innermost boundary that sees the defect:
    # the SourceChange constructor for path/payload defects, the proposal
    # constructor for chain-binding defects (defense in depth)
    with pytest.raises(SelfEvolutionContractError, match=match):
        change = build_change(change_spec)
        SelfEvolutionProposal(
            target_revision=REVISION, target_paths=(target_path,), changes=(change,),
            hypothesis=hypothesis, origin=ProposalOrigin.HUMAN_GENERATED,
            rollback_ref=ROLLBACK_REF, meta_depth=0, traceability=tr(),
        )


def test_proposal_construction_rejects_malformed_intake(tmp_path):
    harness = harness_at(tmp_path / "repo")
    base = make_proposal(harness)

    def build(**overrides: Any) -> SelfEvolutionProposal:
        return dataclasses.replace(base, **overrides)

    good_change = base.changes[0]
    # empty changes / mismatched or unsorted target paths / duplicate paths
    with pytest.raises(SelfEvolutionContractError, match="changes is required"):
        build(changes=())
    with pytest.raises(SelfEvolutionContractError, match="sorted and deduplicated"):
        build(
            target_paths=("src/sos/zzz.py", "src/sos/optimization.py"),
            changes=(
                SourceChange("src/sos/zzz.py", REVISION, SourceChangeKind.CREATE, "@@ +1 @@\n+new\n"),
                good_change,
            ),
        )
    with pytest.raises(SelfEvolutionContractError, match="exactly match the change paths"):
        build(target_paths=("src/sos/other.py",))
    # revision / rollback / origin / hypothesis shape
    with pytest.raises(SelfEvolutionContractError, match="target_revision is required"):
        build(target_revision="  ")
    with pytest.raises(SelfEvolutionContractError, match="rollback_ref is required"):
        build(rollback_ref="")
    with pytest.raises(SelfEvolutionContractError, match="origin must be a ProposalOrigin"):
        build(origin="MODEL_GENERATED")  # type: ignore[arg-type]
    with pytest.raises(SelfEvolutionContractError, match="rationale is required"):
        build(hypothesis=SelfImprovementHypothesis(
            rationale=" ", trigger_evidence_ids=("evidence-x",), predicted_effects=("e",),
            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
        ))
    with pytest.raises(SelfEvolutionContractError, match="trigger_evidence_ids is required"):
        build(hypothesis=SelfImprovementHypothesis(
            rationale="r", trigger_evidence_ids=(), predicted_effects=("e",),
            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
        ))
    with pytest.raises(SelfEvolutionContractError, match="predicted_effects is required"):
        build(hypothesis=SelfImprovementHypothesis(
            rationale="r", trigger_evidence_ids=("evidence-x",), predicted_effects=(),
            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "u"),
        ))
    with pytest.raises(SelfEvolutionContractError, match="may not be SUCCESS"):
        build(hypothesis=SelfImprovementHypothesis(
            rationale="r", trigger_evidence_ids=("evidence-x",), predicted_effects=("e",),
            uncertainty=TruthfulValue(TruthState.SUCCESS, "proven", None),
        ))
    # a record in an advanced state without its gate binding is
    # unconstructible (the C3 ordering made visible in the record itself)
    with pytest.raises(SelfEvolutionContractError, match="cannot carry"):
        build(assurance_result_id="assurance-x")
    with pytest.raises(SelfEvolutionContractError, match="requires the PASS W7 assurance reference"):
        build(state=SelfEvolutionState.UNDER_EXPERIMENT, evidence_ids=("evidence-x",))


# ---------------------------------------------------------------------------
# 10. Bounded recursion (C10): MAX_META_DEPTH + ancestor chain resolution
# ---------------------------------------------------------------------------


def test_recursion_depth_overflow_is_rejected(tmp_path):
    harness = harness_at(tmp_path / "repo")
    root = make_proposal(harness)

    # a lawful maximal chain: depths 0..MAX_META_DEPTH all constructible
    chain_proposals = [root]
    for depth in range(1, MAX_META_DEPTH + 1):
        child = make_proposal(
            harness, meta_depth=depth,
            ancestor_proposal_id=chain_proposals[-1].id,
        )
        assert child.meta_depth == depth
        chain_proposals.append(child)
    deepest = chain_proposals[-1]
    assert deepest.meta_depth == MAX_META_DEPTH

    known = {p.id: p for p in chain_proposals}
    assert resolve_meta_chain(deepest, known) == tuple(p.id for p in chain_proposals[:-1])

    # depth beyond the fixed bound is rejected at construction
    with pytest.raises(SelfEvolutionContractError, match="within \\[0"):
        make_proposal(harness, meta_depth=MAX_META_DEPTH + 1, ancestor_proposal_id=deepest.id)
    with pytest.raises(SelfEvolutionContractError, match="within \\[0"):
        make_proposal(harness, meta_depth=-1)

    # ancestor/depth pairing is validated at construction
    with pytest.raises(SelfEvolutionContractError, match="carries no ancestor"):
        make_proposal(harness, meta_depth=0, ancestor_proposal_id=root.id)
    with pytest.raises(SelfEvolutionContractError, match="requires ancestor_proposal_id"):
        make_proposal(harness, meta_depth=1, ancestor_proposal_id=None)

    # a hand-forged record whose depth exceeds the bound is refused by the
    # evaluation surface (validate + resolve both check)
    forged = make_proposal(harness, meta_depth=1, ancestor_proposal_id=root.id)
    object.__setattr__(forged, "meta_depth", MAX_META_DEPTH + 1)
    with pytest.raises(SelfEvolutionContractError, match="exceeds the fixed bound"):
        resolve_meta_chain(forged, known)
    with pytest.raises(SelfEvolutionContractError, match="within \\[0"):
        transition_self_evolution(
            forged, SelfEvolutionState.UNDER_ASSURANCE,
            known_assurance={}, known_experiments={}, known_evaluations={},
            known_promotions={}, known_decisions={},
            known_evidence=harness.known_evidence, known_proposals=known,
            known_hypotheses=harness.known_hypotheses,
            known_candidates=harness.known_candidates,
        )


def test_ancestor_chain_must_resolve_completely_from_known_proposals(tmp_path):
    harness = harness_at(tmp_path / "repo")
    root = make_proposal(harness)
    child = make_proposal(harness, meta_depth=1, ancestor_proposal_id=root.id)
    grandchild = make_proposal(harness, meta_depth=2, ancestor_proposal_id=child.id)

    # the full chain resolves and the intake transition passes
    known = {root.id: root, child.id: child, grandchild.id: grandchild}
    assert resolve_meta_chain(grandchild, known) == (root.id, child.id)
    result = transition_self_evolution(
        grandchild, SelfEvolutionState.UNDER_ASSURANCE,
        known_assurance={}, known_experiments={}, known_evaluations={},
        known_promotions={}, known_decisions={},
        known_evidence=harness.known_evidence, known_proposals=known,
        known_hypotheses=harness.known_hypotheses, known_candidates=harness.known_candidates,
        timestamp=TS,
    )
    assert result.proposal.state == SelfEvolutionState.UNDER_ASSURANCE
    # the intake step cites the whole resolved chain + the provenance citations
    assert result.step.gate_record_ids == (
        root.id, child.id, harness.intervention.id, harness.hypothesis.id,
        harness.citation_candidate.id,
    )

    # a missing ancestor link is rejected
    with pytest.raises(SelfEvolutionContractError, match="cannot be resolved|not present"):
        resolve_meta_chain(grandchild, {child.id: child, grandchild.id: grandchild})
    with pytest.raises(SelfEvolutionContractError, match="not present in the caller-supplied"):
        transition_self_evolution(
            grandchild, SelfEvolutionState.UNDER_ASSURANCE,
            known_assurance={}, known_experiments={}, known_evaluations={},
            known_promotions={}, known_decisions={},
            known_evidence=harness.known_evidence,
            known_proposals={child.id: child, grandchild.id: grandchild},
            known_hypotheses=harness.known_hypotheses,
            known_candidates=harness.known_candidates,
        )
    # an inconsistent chain (forged parent depth) is rejected
    forged_child = dataclasses.replace(child)
    object.__setattr__(forged_child, "meta_depth", 0)
    inconsistent = {root.id: root, forged_child.id: forged_child, grandchild.id: grandchild}
    with pytest.raises(SelfEvolutionContractError, match="inconsistent"):
        resolve_meta_chain(grandchild, inconsistent)
    # a non-proposal in the registry is rejected
    with pytest.raises(SelfEvolutionContractError, match="not a real SelfEvolutionProposal"):
        resolve_meta_chain(grandchild, {child.id: {"id": child.id}, grandchild.id: grandchild})  # type: ignore[dict-item]


# ---------------------------------------------------------------------------
# 11. Origin never authorizes (C9)
# ---------------------------------------------------------------------------


def test_origin_never_authorizes_identical_gates_for_every_origin(tmp_path):
    harness = harness_at(tmp_path / "repo")
    outcomes = {}
    for origin in ProposalOrigin:
        chain = run_happy(harness, make_proposal(harness, origin=origin))
        assert chain.proposal.state == SelfEvolutionState.PROMOTED
        outcomes[origin] = (
            [s.gate for s in chain.steps],
            [s.outcome.state for s in chain.steps],
        )
        # identical failure behavior too: the W7 non-PASS gate rejects every
        # origin identically
        proposal = make_proposal(harness, origin=origin)
        gates = gates_for(harness, proposal)
        registries = registries_for(harness, gates)
        admitted = advance(proposal, SelfEvolutionState.UNDER_ASSURANCE, registries)
        non_pass = assurance_record(candidate_id=proposal.id, status=AssuranceStatus.FAIL)
        registries["known_assurance"][non_pass.id] = non_pass
        with pytest.raises(SelfEvolutionContractError, match="W7-before-W8 ordering invariant"):
            advance(
                admitted.proposal, SelfEvolutionState.UNDER_EXPERIMENT, registries,
                assurance_result_id=non_pass.id,
            )
    # every origin produced the identical governed outcome shape
    assert len({repr(v) for v in outcomes.values()}) == 1


def test_no_gate_reads_the_proposal_origin():
    """C9 structural proof: the gate/evaluation code never touches the origin
    field (it is untrusted provenance data only)."""
    import sos.selfevolution as semod

    module_source = inspect.getsource(semod)
    assert "proposal.origin" not in module_source
    for fn in (
        semod.transition_self_evolution,
        semod.defer_self_evolution,
        semod.resolve_meta_chain,
        semod.validate_self_evolution_transition,
        semod._resolve_decision,
        semod._check_decision_chain,
        semod._resolve_w7,
        semod._resolve_w8_chain,
        semod._resolve_promotion,
        semod._validate_recovery,
    ):
        assert "origin" not in inspect.getsource(fn), fn.__name__


# ---------------------------------------------------------------------------
# 12. Truth preservation (C8): distinctions never collapse; predictions and
#     payloads are never evidence
# ---------------------------------------------------------------------------


def test_truth_distinctions_are_preserved_through_the_lifecycle(tmp_path):
    harness = harness_at(tmp_path / "repo")
    chain = run_happy(harness)

    # the hypothesis uncertainty (a prediction) stays UNKNOWN end-to-end
    assert chain.proposal.hypothesis.uncertainty.state == TruthState.UNKNOWN
    # every happy-path step is SUCCESS and every pause/deferral is UNKNOWN —
    # verified in their own tests; here the evidence graph keeps each state
    by_id = {e.id: e for e in chain.evidence}
    assert {by_id[eid].result.state for eid in chain.proposal.evidence_ids} == {
        TruthState.SUCCESS
    }
    # the injective W7-status -> truth-state mapping never collapses
    from sos.selfevolution import _ASSURANCE_TRUTH

    assert _ASSURANCE_TRUTH[AssuranceStatus.PASS] == TruthState.SUCCESS
    assert _ASSURANCE_TRUTH[AssuranceStatus.FAIL] == TruthState.FAILED
    assert _ASSURANCE_TRUTH[AssuranceStatus.UNKNOWN] == TruthState.UNKNOWN
    assert _ASSURANCE_TRUTH[AssuranceStatus.BLOCKED] == TruthState.UNAVAILABLE
    assert len(set(_ASSURANCE_TRUTH.values())) == len(_ASSURANCE_TRUTH)

    # a FAILED observation stays FAILED in the evidence the W8 evaluation saw
    gates = chain.gates
    failed = failed_evidence(harness.graph_id)
    evaluation = evaluate_experiment(
        gates.experiment, known_evidence={**gates.known_evidence, failed.id: failed},
        evidence_refs=(failed.id,), evaluation_success=True,
        known_assurance=gates.assurance, rollback_path=gates.rollback_path,
    )
    assert evaluation.evidence_results[failed.id] == TruthState.FAILED
    assert evaluation.promotion_eligible is False


def test_predictions_and_payloads_are_never_ingested_as_evidence(tmp_path):
    harness = harness_at(tmp_path / "repo")
    chain = run_happy(harness)

    graph = EvidenceGraph(
        id="w13-never-evidence", version=1, records=(), traceability=tr()
    )
    for record in chain.evidence:
        graph = graph.ingest(record)

    serialized = json.dumps(_convert_for_json(graph), sort_keys=True)
    # the predicted effects are DATA and never appear in any evidence record
    assert PREDICTED_EFFECT not in serialized
    # the payload contents are DATA and never appear in any evidence record
    assert "+improved" not in serialized
    assert "+governed" not in serialized
    # only existing evidence kinds are ever produced
    assert {r.kind for r in graph.records} <= {
        EvidenceKind.OBSERVATION, EvidenceKind.ROLLBACK,
    }
    # every appended evidence record is a lifecycle step observation bound to
    # the proposal, never an inferred system fact
    for record in graph.records:
        assert record.subject_ref == chain.proposal.id
        assert record.source_ref.startswith("self-evolution-step:")
        assert record.provenance.source == "sos-self-evolution-lifecycle"


# ---------------------------------------------------------------------------
# 13. W5/W6 provenance citations (outcome 7): validated against registries
# ---------------------------------------------------------------------------


def test_w5_w6_citations_are_validated_against_caller_supplied_registries(tmp_path):
    harness = harness_at(tmp_path / "repo")

    # trigger evidence must resolve in known_evidence
    bad_trigger = make_proposal(harness, trigger_evidence_ids=("evidence-bogus",))
    with pytest.raises(SelfEvolutionContractError, match="trigger evidence 'evidence-bogus'"):
        transition_self_evolution(
            bad_trigger, SelfEvolutionState.UNDER_ASSURANCE,
            known_assurance={}, known_experiments={}, known_evaluations={},
            known_promotions={}, known_decisions={},
            known_evidence=harness.known_evidence, known_proposals={},
            known_hypotheses=harness.known_hypotheses,
            known_candidates=harness.known_candidates,
        )

    # W5 causal priors must resolve when the registry is supplied
    bad_prior = make_proposal(harness, causal_hypothesis_ids=("causal-bogus",))
    with pytest.raises(SelfEvolutionContractError, match="W5 causal prior 'causal-bogus'"):
        transition_self_evolution(
            bad_prior, SelfEvolutionState.UNDER_ASSURANCE,
            known_assurance={}, known_experiments={}, known_evaluations={},
            known_promotions={}, known_decisions={},
            known_evidence=harness.known_evidence, known_proposals={},
            known_hypotheses=harness.known_hypotheses,
            known_candidates=harness.known_candidates,
        )
    # ...and citations without ANY registry are refused (cannot be validated)
    with pytest.raises(SelfEvolutionContractError, match="no known_hypotheses registry"):
        transition_self_evolution(
            bad_prior, SelfEvolutionState.UNDER_ASSURANCE,
            known_assurance={}, known_experiments={}, known_evaluations={},
            known_promotions={}, known_decisions={},
            known_evidence=harness.known_evidence, known_proposals={},
            known_hypotheses=None, known_candidates=None,
        )

    # W6 candidate citations must resolve
    bad_candidate = make_proposal(harness, candidate_ref="candidate-bogus")
    with pytest.raises(SelfEvolutionContractError, match="W6 candidate 'candidate-bogus'"):
        transition_self_evolution(
            bad_candidate, SelfEvolutionState.UNDER_ASSURANCE,
            known_assurance={}, known_experiments={}, known_evaluations={},
            known_promotions={}, known_decisions={},
            known_evidence=harness.known_evidence, known_proposals={},
            known_hypotheses=harness.known_hypotheses,
            known_candidates=harness.known_candidates,
        )
    with pytest.raises(SelfEvolutionContractError, match="no known_candidates registry"):
        transition_self_evolution(
            make_proposal(harness, candidate_ref="candidate-bogus", causal_hypothesis_ids=()),
            SelfEvolutionState.UNDER_ASSURANCE,
            known_assurance={}, known_experiments={}, known_evaluations={},
            known_promotions={}, known_decisions={},
            known_evidence=harness.known_evidence, known_proposals={},
            known_hypotheses=None, known_candidates=None,
        )

    # memory-as-prior: the W5 ArchitectureMemory projection is a lawful source
    # for the hypothesis registry (used as a prior, never as proof)
    memory = ArchitectureMemory(
        id="w13-memory", version=1, graph_ref=harness.graph_id,
        hypotheses=(harness.hypothesis,), traceability=tr(),
    )
    result = transition_self_evolution(
        make_proposal(harness), SelfEvolutionState.UNDER_ASSURANCE,
        known_assurance={}, known_experiments={}, known_evaluations={},
        known_promotions={}, known_decisions={},
        known_evidence=harness.known_evidence, known_proposals={},
        known_hypotheses={h.id: h for h in memory.hypotheses},
        known_candidates=harness.known_candidates,
        timestamp=TS,
    )
    assert result.proposal.state == SelfEvolutionState.UNDER_ASSURANCE


# ---------------------------------------------------------------------------
# 14. Persistence (C12): W1 JsonModelStore round-trip
# ---------------------------------------------------------------------------


def test_records_round_trip_through_w1_json_store(tmp_path):
    harness = harness_at(tmp_path / "repo")
    chain = run_happy(harness, adoption_revision="f00dcafe1234567890abcdef1234567890abcdef")

    store = JsonModelStore(tmp_path / "promoted.json")
    store.save(chain.proposal)
    assert store.load() == _convert_for_json(chain.proposal)

    step_store = JsonModelStore(tmp_path / "step.json")
    step_store.save(chain.steps[-1])
    assert step_store.load() == _convert_for_json(chain.steps[-1])

    # the pending records round-trip too
    proposal, gates, registries, _, _ = run_to_authority(harness)
    ask = decide(gates, action=DecisionAction.ACT, policy=act_policy(human_approval_for_act=True))
    registries["known_decisions"][ask.id] = ask
    paused = advance(
        proposal, SelfEvolutionState.PAUSED_ASKING, registries, autonomy_decision_id=ask.id
    ).proposal
    pending_store = JsonModelStore(tmp_path / "pending.json")
    pending_store.save(paused.pending_authorization)
    assert pending_store.load() == _convert_for_json(paused.pending_authorization)
    paused_store = JsonModelStore(tmp_path / "paused.json")
    paused_store.save(paused)
    assert paused_store.load() == _convert_for_json(paused)


# ---------------------------------------------------------------------------
# 15. Composition identity (C1): the real authorities, referenced by identity
# ---------------------------------------------------------------------------


def test_w13_references_frozen_authorities_without_redefining():
    import sos.assurance as assurance_mod
    import sos.autonomy as autonomy_mod
    import sos.candidates as candidates_mod
    import sos.causal as causal_mod
    import sos.evidence as evidence_mod
    import sos.experimentation as experimentation_mod
    import sos.model as model_mod
    import sos.selfevolution as semod

    assert semod.SelfEvolutionContractError.__bases__[0] is model_mod.ModelValidationError
    assert semod.ModelValidationError is model_mod.ModelValidationError
    assert semod.Traceability is model_mod.Traceability
    assert semod.TruthState is model_mod.TruthState
    assert semod.TruthfulValue is model_mod.TruthfulValue
    assert semod.Evidence is evidence_mod.Evidence
    assert semod.EvidenceKind is evidence_mod.EvidenceKind
    assert semod.EvidenceProvenance is evidence_mod.EvidenceProvenance
    assert semod._build_evidence is evidence_mod._build_evidence  # the single assembly authority
    assert semod.CausalHypothesis is causal_mod.CausalHypothesis
    assert semod.CandidateProposal is candidates_mod.CandidateProposal
    assert semod.AssuranceResult is assurance_mod.AssuranceResult
    assert semod.AssuranceStatus is assurance_mod.AssuranceStatus
    assert semod.Experiment is experimentation_mod.Experiment
    assert semod.ExperimentState is experimentation_mod.ExperimentState
    assert semod.ExperimentEvaluation is experimentation_mod.ExperimentEvaluation
    assert semod.PromotionDecision is experimentation_mod.PromotionDecision
    assert semod.PromotionGate is experimentation_mod.PromotionGate
    assert semod.RollbackPath is experimentation_mod.RollbackPath
    assert semod.AutonomyDecision is autonomy_mod.AutonomyDecision
    assert semod.AutonomyDecisionState is autonomy_mod.AutonomyDecisionState
    # every W13-owned record belongs to this module only
    for name in (
        "SelfEvolutionContractError", "ProposalOrigin", "SourceChangeKind", "SourceChange",
        "SelfImprovementHypothesis", "SelfEvolutionState", "SelfEvolutionGate",
        "PendingResolution", "PendingProposalAuthorization", "PendingProposalEvidence",
        "SelfEvolutionProposal", "SelfEvolutionStep", "SelfEvolutionTransitionResult",
    ):
        assert getattr(semod, name).__module__ == "sos.selfevolution", name
    # the frozen governance constants
    assert semod.MAX_META_DEPTH == 3
    assert isinstance(semod.FROZEN_AUTHORITY_PATHS, frozenset)
    assert isinstance(semod.FROZEN_AUTHORITY_PATH_PREFIXES, frozenset)
    assert isinstance(semod.AUTHORITY_MODULE_PATHS, frozenset)


def test_w13_exports_only_through_the_package_surface():
    import sos
    import sos.selfevolution as semod

    for name in (
        "SelfEvolutionProposal", "SelfEvolutionState", "SelfEvolutionStep",
        "SelfEvolutionGate", "SelfEvolutionContractError", "SelfImprovementHypothesis",
        "SourceChange", "SourceChangeKind", "ProposalOrigin", "PendingResolution",
        "PendingProposalAuthorization", "PendingProposalEvidence",
        "SelfEvolutionTransitionResult", "MAX_META_DEPTH", "FROZEN_AUTHORITY_PATHS",
        "FROZEN_AUTHORITY_PATH_PREFIXES", "AUTHORITY_MODULE_PATHS",
        "SELF_EVOLUTION_TERMINAL_STATES", "transition_self_evolution",
        "defer_self_evolution", "validate_self_evolution_transition",
        "resolve_meta_chain", "step_to_w4_evidence",
    ):
        # exported through the package, and identical to the module object
        assert name in sos.__all__, name
        assert getattr(sos, name) is getattr(semod, name), name
        owner = getattr(semod, name)
        if isinstance(owner, type) or callable(owner):
            assert owner.__module__ == "sos.selfevolution", name


# ---------------------------------------------------------------------------
# 16. Bounded authority surface (C12): source scans, no W14 symbols, no
#     proposal-generation path
# ---------------------------------------------------------------------------


def test_no_self_modification_execution_tokens_anywhere_in_src():
    """C11/C12: source scan of src/sos/ for network/child-process execution
    tokens (mirroring the W11 no-integration-symbol test pattern)."""
    src_dir = Path(__import__("sos").__file__).parent
    sources = sorted(src_dir.glob("*.py"))
    assert len(sources) >= 15  # the full authority tree is present
    for path in sources:
        text = path.read_text(encoding="utf-8").lower()
        for token in (
            "socket", "urllib", "os.system", "popen", "http://", "https://",
            "ftp://", "shutil", "requests.post", "time.time", "datetime.now",
        ):
            assert token not in text, f"forbidden token in {path.name}: {token!r}"


def test_selfevolution_module_scan_is_clean():
    """C11/C12: the W13 module itself is additionally free of every
    file-mutation, randomness, clock, and version-control token."""
    import sos.selfevolution as semod

    src = inspect.getsource(semod).lower()
    for token in (
        "subprocess", "socket", "urllib", "requests.post", "os.system", "popen",
        "http://", "https://", "ftp://", "uuid4", "time.time", "datetime.now",
        "shutil", "write_text", "write_bytes", "mkdir", "open(", ".write(",
        "pathlib", "chmod", "unlink", "git", "w14", "dogfood", "adversarial",
    ):
        assert token not in src, f"forbidden token in src/sos/selfevolution.py: {token!r}"


def test_no_w14_or_successor_symbols():
    import sos.selfevolution as semod

    forbidden = {
        "Dogfood", "AdversarialVerifier", "Adversarial", "W14", "MetaAdaptationLayer",
        "ConstitutionMutation", "LiveSystemAdapter", "ExecutionSubstrate",
        "OptimizationLoop", "run_optimization_loop",
    }
    exported = {n for n in dir(semod) if not n.startswith("_")}
    assert not (forbidden & exported), f"forbidden successor-stage symbols: {forbidden & exported}"


def test_evaluation_surface_exposes_no_proposal_generation_path():
    """C10/P8: the evaluation surface never creates, mutates, or re-generates
    proposals; one call advances exactly one proposal."""
    import sos.selfevolution as semod

    generation_tokens = (
        "generate", "create", "propose", "mutate", "regen", "spawn", "mint",
    )
    for name, obj in vars(semod).items():
        if name.startswith("_") or not callable(obj):
            continue
        if getattr(obj, "__module__", None) != "sos.selfevolution":
            continue  # authority symbols are referenced, not owned
        assert not any(t in name.lower() for t in generation_tokens), name

    # the two evaluation entry points take an EXISTING proposal first and
    # return exactly one advanced proposal record
    for fn in (semod.transition_self_evolution, semod.defer_self_evolution):
        params = list(inspect.signature(fn).parameters.values())
        assert params[0].name == "proposal", fn.__name__
        assert params[0].annotation in (
            "SelfEvolutionProposal", semod.SelfEvolutionProposal,
        ), fn.__name__
        assert fn.__annotations__.get("return") in (
            "SelfEvolutionTransitionResult", semod.SelfEvolutionTransitionResult,
        ), fn.__name__
    # the constructor is the ONLY creation path (a plain dataclass constructor
    # invoked by the caller); no factory function exists on the module
    factories = {
        n for n, o in vars(semod).items()
        if not n.startswith("_") and callable(o)
        and getattr(o, "__module__", "") == "sos.selfevolution"
        and not isinstance(o, type)
        and n not in (
            "transition_self_evolution", "defer_self_evolution",
            "validate_self_evolution_transition", "resolve_meta_chain",
            "step_to_w4_evidence",
        )
    }
    assert not factories, f"unexpected free functions on the evaluation surface: {factories}"


# ---------------------------------------------------------------------------
# 17. The transition result contract
# ---------------------------------------------------------------------------


def test_transition_result_is_chain_bound_and_tamper_evident(tmp_path):
    harness = harness_at(tmp_path / "repo")
    proposal = make_proposal(harness)
    gates = gates_for(harness, proposal)
    registries = registries_for(harness, gates)
    result = advance(proposal, SelfEvolutionState.UNDER_ASSURANCE, registries)

    # the result is internally chain-bound
    result.validate()
    # tampering with any part is detectable (each probe uses a FRESH result —
    # object.__setattr__ mutates the shared frozen record in place)
    fresh_a = advance(proposal, SelfEvolutionState.UNDER_ASSURANCE, registries)
    mismatched_proposal = fresh_a.proposal
    object.__setattr__(mismatched_proposal, "state", SelfEvolutionState.PROPOSED)
    with pytest.raises(SelfEvolutionContractError, match="does not match the advanced proposal"):
        SelfEvolutionTransitionResult(
            proposal=mismatched_proposal, step=fresh_a.step, evidence=fresh_a.evidence
        )
    fresh_b = advance(proposal, SelfEvolutionState.UNDER_ASSURANCE, registries)
    unbound_step = fresh_b.step
    object.__setattr__(unbound_step, "proposal_id", "selfevo-x")
    with pytest.raises(SelfEvolutionContractError, match="not bound to the exact proposal"):
        SelfEvolutionTransitionResult(
            proposal=fresh_b.proposal, step=unbound_step, evidence=fresh_b.evidence
        )
    # step identity is content-addressed and tamper-evident
    with pytest.raises(SelfEvolutionContractError, match="content-addressed material"):
        dataclasses.replace(result.step, detail="tampered").validate()
    # proposal identity is content-addressed and tamper-evident
    with pytest.raises(SelfEvolutionContractError, match="content-addressed intake material"):
        dataclasses.replace(result.proposal, rollback_ref="rb-tampered").validate()
    # a non-proposal is refused by the transition boundary
    with pytest.raises(SelfEvolutionContractError, match="requires a real SelfEvolutionProposal"):
        transition_self_evolution(
            {"state": "PROPOSED"},  # type: ignore[arg-type]
            SelfEvolutionState.UNDER_ASSURANCE,
            known_assurance={}, known_experiments={}, known_evaluations={},
            known_promotions={}, known_decisions={},
            known_evidence=harness.known_evidence, known_proposals={},
        )


def test_step_records_are_table_validated_at_construction():
    outcome = TruthfulValue(TruthState.SUCCESS, "x", None)
    base = dict(
        proposal_id="selfevo-x", target_revision=REVISION,
        gate_record_ids=("record-1",), outcome=outcome, detail="d", traceability=tr(),
    )
    # a lawful step constructs
    SelfEvolutionStep(
        from_state=SelfEvolutionState.PROPOSED,
        to_state=SelfEvolutionState.UNDER_ASSURANCE,
        gate=SelfEvolutionGate.INTAKE, **base,
    )
    # an out-of-table step is unconstructible
    with pytest.raises(SelfEvolutionContractError, match="invalid self-evolution lifecycle transition"):
        SelfEvolutionStep(
            from_state=SelfEvolutionState.PROPOSED,
            to_state=SelfEvolutionState.PROMOTED,
            gate=SelfEvolutionGate.W9_AUTHORITY, **base,
        )
    # a deferral step must keep the state and be at the authority stage
    with pytest.raises(SelfEvolutionContractError, match="keeps the current state"):
        SelfEvolutionStep(
            from_state=SelfEvolutionState.UNDER_AUTHORITY,
            to_state=SelfEvolutionState.PROMOTED,
            gate=SelfEvolutionGate.W9_DEFERRAL, **base,
        )
    with pytest.raises(SelfEvolutionContractError, match="only lawful while"):
        SelfEvolutionStep(
            from_state=SelfEvolutionState.PROPOSED,
            to_state=SelfEvolutionState.PROPOSED,
            gate=SelfEvolutionGate.W9_DEFERRAL, **base,
        )
    # a state-keeping step under a non-deferral gate is unconstructible
    with pytest.raises(SelfEvolutionContractError, match="changes the lifecycle state"):
        SelfEvolutionStep(
            from_state=SelfEvolutionState.UNDER_AUTHORITY,
            to_state=SelfEvolutionState.UNDER_AUTHORITY,
            gate=SelfEvolutionGate.W9_AUTHORITY, **base,
        )
    # the W13 error is a W1 ModelValidationError (no competing error authority)
    assert issubclass(SelfEvolutionContractError, ModelValidationError)
