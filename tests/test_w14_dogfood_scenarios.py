"""W14 — integrated dogfood scenarios (the full Mission-diagram chain).

Work Order: ``spec/work-orders/W14-dogfood-adversarial-verification.md``
(Required outcomes 3, 5, 7, 8; acceptance criteria C1, C5; the roadmap
"Final integrated gate" mapping). Design:
``docs/implementation/W14-DOGFOOD-ADVERSARIAL-DESIGN.md`` §§2, 5.

Two deterministic end-to-end scenarios compose every merged authority
through its public contract on the fixture systems built in
``tests/w14_fixtures.py``:

- **Scenario 1 (brownfield entry)**: the fixture repository is recovered
  through the real W3 ``recover_repository`` (W2 SystemState/Architecture
  Graph with preserved uncertainty) and runs the full chain
  W1 → W2/W3 → W4 → W5 → W6 → W7 → W8 → W9 → W11 → W12 (the loop composes
  the middle of the chain) → W10 → W13 → **governed promotion** (DEPLOY
  class, through the W11 substrate with the stub provider) → W4/W5 closure.
- **Scenario 2 (greenfield-seam entry)**: the directly-constructed W2
  greenfield SystemState's first governed executions go through the W11
  ``ExecutionSubstrate`` (OBSERVE under a W9 GATHER_EVIDENCE decision, then
  DEPLOY under a W9 ACT decision); the DEPLOY partially fails, the chain
  recovers through a governed rollback, and the realized system's seed
  repository converges on the same W12 brownfield loop → **governed
  rollback** → W4/W5 closure.

Both scenarios are fully deterministic and hermetic: fixed revisions, fixed
caller-supplied timestamps, no network, no subprocess, no wall clock.
"""

from __future__ import annotations

import pytest

import w14_fixtures as w14
from sos import (
    AssuranceStatus,
    AutonomyDecisionState,
    DecisionAction,
    EvidenceKind,
    ExperimentState,
    ModelValidationError,
    RevisionStatus,
    TruthState,
)
from sos.optimization import IterationOutcome, LoopStopReason, PromotionClass
from sos.candidates import CandidateEvaluation

# ---------------------------------------------------------------------------
# Scenario 1 — brownfield entry, full chain, governed promotion
# ---------------------------------------------------------------------------


def test_scenario_01_brownfield_full_chain_ends_in_governed_promotion(tmp_path):
    scenario = w14.run_brownfield_scenario(tmp_path / "repo")
    harness = scenario.harness
    graph = scenario.graph

    # --- W1: mission formalization + explicit, evidence-proposed revision ---
    scenario.mission_v1.validate()
    assert scenario.mission_v1.status.value == "ACTIVE"
    # R2: the mission carries the full formalization vocabulary
    assert scenario.mission_v1.goals and scenario.mission_v1.desired_outcomes
    assert scenario.mission_v1.stakeholders and scenario.mission_v1.measures
    assert scenario.mission_v1.assumptions and scenario.mission_v1.ambiguities
    # R3: revision is versioned, evidence-proposed, owner-authorized
    assert scenario.mission_v2.version == 2
    assert scenario.mission_v2.parent_version == 1
    assert scenario.mission_v2.status.value == "ACTIVE"
    last_revision = scenario.mission_v2.history[-1]
    assert last_revision.status is RevisionStatus.APPROVED
    assert last_revision.decided_by == "owner-1"
    assert harness.intervention.id in last_revision.reason  # evidence-proposed
    scenario.mission_v2.validate()

    # --- W2/W3: reconstruction with preserved uncertainty (R6/R7) ---
    recovery = harness.recovery
    assert recovery.revision == w14.BROWN_REVISION
    assert recovery.system_state.architecture_ref == graph.id
    assert recovery.system_state.implementation_ref.ref.state is TruthState.SUCCESS
    # runtime gaps stay UNAVAILABLE — never converted into successful facts
    assert recovery.system_state.deployment_ref.ref.state is TruthState.UNAVAILABLE
    assert recovery.system_state.environment_ref.ref.state is TruthState.UNAVAILABLE
    assert any(
        f.truth.state is TruthState.UNKNOWN for f in recovery.unresolved_facts
    )  # the unparsed setup.py manifest
    assert any(
        f.truth.state is TruthState.UNAVAILABLE for f in recovery.unresolved_facts
    )
    assert len(graph.nodes) >= 8  # multi-component service/data-store graph

    # --- W4: the evidence cycle, recorded verbatim (R9/R21) ---
    final_records = {r.id: r for r in scenario.evidence_graph.records}
    for record in scenario.evidence_graph.records:
        record.validate()
        # exact-revision provenance on every fixture evidence record
        assert record.provenance.implementation_revision == w14.BROWN_REVISION
    assert harness.otel_span.result.state is TruthState.SUCCESS
    assert harness.otel_span.availability is TruthState.SUCCESS
    assert harness.unavailable_ev.result.state is TruthState.UNAVAILABLE
    assert harness.unavailable_ev.availability is TruthState.UNAVAILABLE
    # idempotent dedup: re-ingesting an identical record is a no-op
    assert scenario.evidence_graph.ingest(harness.intervention) is scenario.evidence_graph

    # --- W5: causal hypotheses distinct from evidence (R10) ---
    assert harness.observation_hyp.status == "proposed"
    assert harness.observation_hyp.uncertainty.state is TruthState.UNKNOWN
    assert harness.confirmed_hyp.status == "confirmed"
    evidence_ids = set(final_records)
    assert harness.observation_hyp.id not in evidence_ids  # hypotheses are not evidence
    assert harness.confirmed_hyp.id not in evidence_ids
    # every hypothesis support id resolves in the evidence graph
    for hypothesis in (harness.observation_hyp, harness.confirmed_hyp):
        for support in hypothesis.supporting_evidence:
            assert support.evidence_id in evidence_ids

    # --- W6: bounded subgraph replacement + multi-objective Pareto (R8/R11/R12) ---
    harness.subgraph_replacement.validate(graph)  # the W2 boundary contract
    assert len(harness.pareto.candidates) >= 2  # a Pareto set, not a scalar winner
    evaluation = CandidateEvaluation(harness.pareto.candidates[0].objectives)
    assert len(evaluation.objectives) == 3  # multi-objective, no scalar score

    # --- W7/W8/W9/W11/W12: the governed loop over the recovered system ---
    run = scenario.run
    run.validate()  # every cross-authority reference chain-checks
    assert run.loop.stop.reason == LoopStopReason.COMPLETED
    assert run.loop.recovered_state_ref == recovery.system_state.id
    assert run.loop.recovered_revision == w14.BROWN_REVISION
    outcomes = [it.outcome for it in run.loop.iterations]
    # the value-model hard constraint filtered the violating candidate (R4)
    assert IterationOutcome.ASSURANCE_NOT_PASSED in outcomes
    # ...and the lawful frontier candidate was promoted
    assert IterationOutcome.PROMOTED in outcomes

    refused = next(
        it for it in run.loop.iterations
        if it.outcome == IterationOutcome.ASSURANCE_NOT_PASSED
    )
    assert refused.assurance_status is AssuranceStatus.FAIL
    assert refused.experiment_id is None  # no experiment may be constructed
    assert refused.promotion is None
    # the FAIL status was preserved verbatim as W4 evidence
    refused_assurance_ev = final_records[refused.evidence_ids[-1]]
    assert refused_assurance_ev.result.state is TruthState.FAILED

    promoted = next(
        it for it in run.loop.iterations if it.outcome == IterationOutcome.PROMOTED
    )
    assert promoted.assurance_status is AssuranceStatus.PASS
    assert promoted.decision_state is AutonomyDecisionState.ACT
    assert promoted.promotion is not None
    assert promoted.promotion.promotion_class == PromotionClass.DEPLOY
    assert promoted.promotion.receipt_id is not None
    assert promoted.promotion.rollback is not None  # bounded rollback mandatory
    assert promoted.promotion.experiment_rollback_ref == w14.ROLLBACK_REF_BROWN
    # the W7-before-W8 ordering is visible in the record
    assert promoted.assurance_id is not None and promoted.experiment_id is not None

    # the governed execution went through the W11 substrate (stub provider)
    assert len(run.receipts) == 1
    receipt = run.receipts[0]
    assert receipt.lifecycle.value == "succeeded"
    assert receipt.outcome.state is TruthState.SUCCESS
    assert receipt.w9_decision_id == promoted.promotion.decision_id
    assert receipt.provenance_revision == w14.BROWN_REVISION
    assert receipt.changed_revisions == (w14.DEPLOY_CHANGED_REVISION,)
    # exactly ONE provider engagement: the pre-gate rejection never dispatched
    assert scenario.provider.execute_calls == 1

    # the W9 chain: launch (EXPERIMENT) then the authorizing ACT decision
    decisions_by_id = {d.id: d for d in run.decisions}
    assert promoted.decision_ids[-1] == promoted.promotion.decision_id
    assert decisions_by_id[promoted.decision_ids[-1]].state is AutonomyDecisionState.ACT

    # --- W10: contextual/platform narrowing subordinate to W9 (R17/R18) ---
    assert scenario.w10.selection.state == "ACT"  # inherited ACT preserved
    assert scenario.w10.adapter_plan.compatible is True
    assert DecisionAction.ACT in scenario.w10.constraint.narrowed_allowed_actions
    assert scenario.w10.personalization.state == "ACT"
    assert scenario.w10.personalization.w9_decision_id == scenario.act_decision.id

    # --- W13: the self-evolution boundary check (R20) ---
    assert isinstance(scenario.selfevo.refusal_error, w14.SelfEvolutionContractError)
    assert "frozen authority" in str(scenario.selfevo.refusal_error)
    assert scenario.selfevo.refusal_evidence.id in final_records
    assert final_records[scenario.selfevo.refusal_evidence.id].result.state is TruthState.FAILED
    # the lawful proposal passed the SAME gates and is PROMOTED as data only
    assert scenario.selfevo.promoted.state.value == "PROMOTED"
    assert scenario.selfevo.promoted.adoption_revision is None  # never applied here

    # --- closure: learning record + resolvable evidence graph (R19/C5) ---
    assert scenario.learning_hypothesis.status == "confirmed"
    assert scenario.memory_v2.version == 2
    assert scenario.memory_v2.graph_ref == graph.id
    for support in scenario.learning_hypothesis.supporting_evidence:
        assert support.evidence_id in evidence_ids
    # every W13 step's evidence joined the closed cycle
    for record in scenario.selfevo.evidence:
        assert record.id in final_records


def test_scenario_01_mission_and_state_records_round_trip_through_w1_store(tmp_path):
    """R24-adjacent fixture integrity: the scenario's W1/W2 records persist
    through the W1 JsonModelStore without any new persistence authority."""
    import json

    from sos.model import _convert_for_json

    scenario = w14.run_brownfield_scenario(tmp_path / "repo")
    store = w14.JsonModelStore(tmp_path / "store" / "mission.json")
    store.save(scenario.mission_v2)
    loaded = json.loads((tmp_path / "store" / "mission.json").read_text(encoding="utf-8"))
    assert loaded == _convert_for_json(scenario.mission_v2)


# ---------------------------------------------------------------------------
# Scenario 2 — greenfield-seam entry, full chain, governed rollback
# ---------------------------------------------------------------------------


def test_scenario_02_greenfield_seam_full_chain_ends_in_governed_rollback(tmp_path):
    scenario = w14.run_greenfield_scenario(tmp_path / "greenfield")
    harness = scenario.harness
    graph = scenario.graph

    # --- W1: the same authorities govern the greenfield entry ---
    scenario.mission.validate()
    scenario.value_model.validate()
    scenario.context.validate()

    # --- W2: greenfield SystemState as an explicit versioned hypothesis ---
    state = harness.system_state
    assert state.id == "w14-gf-state-1"  # deterministic (no uuid factory)
    assert state.version == 1
    assert state.parent_revision_id is None
    assert state.architecture_ref == graph.id
    assert state.implementation_ref.ref.value == w14.GREEN_REVISION
    # truthful greenfield gaps: not yet deployed, no runtime environment
    assert state.deployment_ref.ref.state is TruthState.UNAVAILABLE
    assert state.environment_ref.ref.state is TruthState.UNAVAILABLE
    assert graph.uncertainty.state is TruthState.UNKNOWN  # unvalidated hypothesis
    state.validate()

    # --- W4: the evidence cycle, verbatim ---
    for record in scenario.evidence_graph.records:
        record.validate()
    assert harness.unavailable_ev.result.state is TruthState.UNAVAILABLE

    # --- W5: causal knowledge as priors ---
    assert harness.observation_hyp.status == "proposed"
    assert harness.confirmed_hyp.status == "confirmed"

    # --- W6: bounded search through the REAL SearchEngine + Pareto ---
    assert len(harness.generated_frontier.candidates) >= 1
    assert len(harness.pareto.candidates) >= 2
    generated = harness.generated_frontier.candidates[0]
    generated.validate(
        known_graph=graph,
        known_evidence_ids=set(harness.known_evidence),
        known_hypothesis_ids=set(harness.known_hypotheses),
    )

    # --- W7/W8: assurance PASS + the governed experiment ---
    assert harness.assurance.status is AssuranceStatus.PASS
    assert harness.assurance.candidate_id == harness.selected_candidate.id
    assert scenario.experiment.state is ExperimentState.ROLLED_BACK
    assert harness.evaluation.promotion_eligible is True
    assert harness.gate_decision.promoted is True

    # --- W9 → W11: the first governed execution is a read-only observation ---
    assert scenario.gather_decision.state is AutonomyDecisionState.GATHER_EVIDENCE
    assert scenario.observe_receipt.lifecycle.value == "succeeded"
    assert scenario.observe_receipt.outcome.state is TruthState.SUCCESS
    assert scenario.observe_receipt.action_scope.value == "observe"
    assert scenario.observe_provider.execute_calls == 1

    # --- W9 ACT → W10 narrowing preserved ACT ---
    assert scenario.act_decision.state is AutonomyDecisionState.ACT
    assert scenario.w10.selection.state == "ACT"
    assert scenario.w10.personalization.state == "ACT"
    assert DecisionAction.ACT in scenario.w10.constraint.narrowed_allowed_actions

    # --- W11 DEPLOY: the partial failure, recorded verbatim (ADV-16 shape) ---
    assert scenario.deploy_receipt.lifecycle.value == "failed"
    assert scenario.deploy_receipt.outcome.state is TruthState.FAILED
    assert scenario.deploy_receipt.started_at == w14.TS_DEPLOY_START
    assert scenario.deploy_receipt.finished_at == w14.TS_DEPLOY_END
    assert scenario.deploy_receipt.rollback_reference is not None
    final_records = {r.id: r for r in scenario.evidence_graph.records}
    deploy_ev = final_records[scenario.deploy_evidence.id]
    assert deploy_ev.result.state is TruthState.FAILED  # never rendered as success
    assert deploy_ev.kind is EvidenceKind.DEPLOYMENT

    # --- governed rollback: W9 ROLLBACK → W11 ROLLBACK → typed ROLLED_BACK ---
    assert scenario.rollback_decision.state is AutonomyDecisionState.ROLLBACK
    assert scenario.rollback_receipt.lifecycle.value == "rolled-back"
    assert scenario.rollback_receipt.outcome.state is TruthState.SUCCESS
    assert scenario.rollback_receipt.rollback_reference.evidence_ids == (
        harness.rollback_ev.id,
    )
    rollback_ev = final_records[scenario.rollback_evidence.id]
    assert rollback_ev.result.state is TruthState.SUCCESS
    assert rollback_ev.kind is EvidenceKind.ROLLBACK
    assert scenario.experiment.state is ExperimentState.ROLLED_BACK

    # --- W12: convergence on the same brownfield loop (architecture §10) ---
    seed_run = scenario.seed_run
    seed_run.validate()
    assert seed_run.loop.recovered_revision == w14.SEED_REVISION
    assert seed_run.loop.stop.reason == LoopStopReason.COMPLETED
    seed_iteration = seed_run.loop.iterations[0]
    assert seed_iteration.outcome == IterationOutcome.ROLLED_BACK
    assert seed_iteration.decision_state is AutonomyDecisionState.ROLLBACK
    assert seed_iteration.promotion is None  # no partial record as success
    # the failed experiment evidence stayed verbatim FAILED
    seed_failed_ev = [
        r for r in seed_run.evidence_graph.records
        if r.kind is EvidenceKind.EXPERIMENT
    ]
    assert any(r.result.state is TruthState.FAILED for r in seed_failed_ev)
    # the governed rollback evidence is SUCCESS and present
    assert any(
        r.kind is EvidenceKind.ROLLBACK and r.result.state is TruthState.SUCCESS
        for r in seed_run.evidence_graph.records
    )

    # --- W13: boundary check ---
    assert isinstance(scenario.selfevo.refusal_error, w14.SelfEvolutionContractError)
    assert scenario.selfevo.promoted.state.value == "PROMOTED"

    # --- closure: failure-informed learning record ---
    assert scenario.learning_hypothesis.status == "proposed"
    assert scenario.learning_hypothesis.uncertainty.state is TruthState.UNKNOWN
    assert scenario.memory_v2.version == 2
    for support in scenario.learning_hypothesis.supporting_evidence:
        assert support.evidence_id in final_records


# ---------------------------------------------------------------------------
# Focused roadmap-gate assertions (the "Final integrated gate" items)
# ---------------------------------------------------------------------------


def test_w14_mission_revision_is_explicit_evidence_proposed_and_owner_authorized(tmp_path):
    """Roadmap gate: mission formalization and revision — never silent."""
    harness = w14.brownfield_harness(tmp_path / "repo")
    mission = harness.mission

    # telemetry/evidence may only PROPOSE: the proposed record is not ACTIVE
    proposed = mission.propose_revision(
        statement="revised statement from telemetry pressure",
        proposed_by="telemetry-evidence-cycle",
        reason=f"evidence-proposed from {harness.intervention.id}",
        created_at=w14.TS_MISSION_V2,
    )
    assert proposed.status.value == "PROPOSED_REVISION"
    assert proposed.version == 2
    assert proposed.history[-1].decided_by is None  # not yet authorized

    # only the mission authority may approve
    with pytest.raises(ModelValidationError, match="mission authority"):
        proposed.approve_revision(approver="someone-else")

    # an empty proposed statement is rejected (no silent no-op revision)
    with pytest.raises(ModelValidationError, match="cannot be empty"):
        mission.propose_revision(
            statement="   ", proposed_by="telemetry", reason="x", created_at=w14.TS,
        )

    approved = proposed.approve_revision(approver="owner-1")
    assert approved.status.value == "ACTIVE"
    assert approved.history[-1].status is RevisionStatus.APPROVED
    # the parent chain is explicit and versioned
    assert approved.parent_version == 1


def test_w14_value_model_hard_constraints_filter_candidates(tmp_path):
    """Roadmap gate: value-model constraints — hard constraints outrank
    objective improvements (architecture §13.3)."""
    harness = w14.brownfield_harness(tmp_path / "repo")
    constraint_text = harness.value_model.constraints[0].description
    assert harness.value_model.constraints[0].hard is True

    clean = assure(harness, harness.selected_candidate, constraint_text)
    violating = assure(harness, harness.violating_candidate, constraint_text)

    assert clean.status is AssuranceStatus.PASS
    assert violating.status is AssuranceStatus.FAIL
    hard_gate = next(g for g in violating.gates if g.name == "hard-constraint")
    assert hard_gate.status is AssuranceStatus.FAIL
    # the violating candidate has strictly BETTER objectives — and still FAILs
    better_latency = violating.objectives[0].predicted_value < clean.objectives[0].predicted_value
    assert better_latency
    # FAIL cannot be offset (overall status is FAIL, not UNKNOWN/PASS)


def assure(harness, candidate, constraint_text):
    from sos import assure_candidate

    return assure_candidate(
        candidate=candidate, base_graph=harness.graph,
        known_evidence=dict(harness.known_evidence),
        known_hypotheses=dict(harness.known_hypotheses),
        hard_constraints=(constraint_text,),
        rollback_evidence_ids=(harness.rollback_ev.id,),
    )


def test_w14_pareto_non_dominated_candidate_output(tmp_path):
    """Roadmap gate: multi-objective trade-offs — a non-dominated set, not a
    scalar winner (R12)."""
    harness = w14.brownfield_harness(tmp_path / "repo")
    frontier = harness.pareto.candidates
    assert len(frontier) == 2
    # the frontier members do not dominate each other
    evaluations = [CandidateEvaluation(c.objectives) for c in frontier]
    assert not evaluations[0].dominates(evaluations[1])
    assert not evaluations[1].dominates(evaluations[0])
    # a genuine trade-off exists: one is better on latency, the other on cost
    by_latency = sorted(frontier, key=lambda c: c.objectives[0].predicted_value)
    assert by_latency[0].objectives[0].predicted_value < by_latency[1].objectives[0].predicted_value
    assert by_latency[0].objectives[1].predicted_value > by_latency[1].objectives[1].predicted_value
    # the frontier is deterministically ordered by id
    assert [c.id for c in frontier] == sorted(c.id for c in frontier)
    # no scalar score exists anywhere on the evaluation surface
    assert not hasattr(evaluations[0], "score")
    # every candidate keeps its full multi-objective profile
    assert all(len(c.objectives) == 3 for c in frontier)


def test_w14_causal_hypothesis_evidence_distinction(tmp_path):
    """Roadmap gate: causal hypothesis/evidence distinction — correlation is
    never re-typed as intervention evidence (R10, architecture §13.4-5)."""
    harness = w14.brownfield_harness(tmp_path / "repo")

    # an observation-only hypothesis cannot reach "confirmed"
    with pytest.raises(ModelValidationError, match="intervention-grade"):
        harness.observation_hyp.with_status(
            "confirmed",
            known_evidence_ids={harness.otel_span.id},
            known_evidence_records={harness.otel_span.id: harness.otel_span},
        )

    # OBSERVATIONAL support must not carry fabricated intervention metadata
    from sos import EvidenceSupport, InterventionMetadata, SupportKind

    with pytest.raises(ModelValidationError, match="must not carry InterventionMetadata"):
        EvidenceSupport(
            evidence_id=harness.otel_span.id, support_kind=SupportKind.OBSERVATIONAL,
            intervention=InterventionMetadata(
                intervention_id="fabricated", intervention_kind="experiment",
                applied_at=w14.TS, revision=w14.BROWN_REVISION, environment="simulation",
            ),
        )

    # the confirmed hypothesis's intervention support binds to the exact
    # intervention evidence provenance (a mismatched revision is rejected)
    with pytest.raises(ModelValidationError, match="does not match"):
        EvidenceSupport(
            evidence_id=harness.intervention.id,
            support_kind=SupportKind.INTERVENTION,
            intervention=InterventionMetadata(
                intervention_id="experiment-w14-77", intervention_kind="experiment",
                applied_at=w14.TS, revision=w14.STALE_REVISION,
                environment="simulation",
            ),
        ).validate(
            known_evidence_records={harness.intervention.id: harness.intervention}
        )

    # hypotheses stay hypotheses: uncertainty is non-SUCCESS unless
    # intervention-backed, and a hypothesis id is never an evidence id
    assert harness.observation_hyp.uncertainty.state is TruthState.UNKNOWN
    assert harness.confirmed_hyp.uncertainty.state is TruthState.SUCCESS
    assert harness.observation_hyp.id != harness.otel_span.id


def test_w14_subgraph_replacement_boundary_invariants(tmp_path):
    """Roadmap gate: candidate subgraph replacement — A' = A - S + S' with
    boundary invariants (R8, architecture §3.6)."""
    harness = w14.brownfield_harness(tmp_path / "repo")
    graph = harness.graph
    replacement = harness.subgraph_replacement
    node_ids = set(harness.node_ids.values())

    # the W2 record validates against the recovered graph
    replacement.validate(graph)
    assert replacement.base_graph_ref == graph.id
    assert set(replacement.target_node_ids) <= node_ids
    assert set(replacement.boundary_interface_ids) <= node_ids
    assert set(replacement.replacement_node_ids) <= node_ids
    # replacement and target are disjoint (A - S + S')
    assert not set(replacement.replacement_node_ids) & set(replacement.target_node_ids)

    # the W6 mutation mirrors the same boundary contract
    mutation = harness.selected_candidate.mutation
    mutation.validate(graph)

    from sos import SubgraphReplacement, SubgraphMutation, ModelValidationError

    # a boundary referencing an unknown node is rejected at the W2 authority
    with pytest.raises(ModelValidationError, match="unknown nodes"):
        SubgraphReplacement(
            id="bad-1", base_graph_ref=graph.id,
            target_node_ids=replacement.target_node_ids,
            replacement_node_ids=replacement.replacement_node_ids,
            boundary_interface_ids=("node-does-not-exist",),
            invariants=("preserve-boundary",), traceability=w14.tr(),
        ).validate(graph)

    # a mutation whose replacement is not a real node is rejected at W6
    with pytest.raises(ModelValidationError, match="replacement references unknown nodes"):
        SubgraphMutation(
            kind=mutation.kind, base_graph_ref=graph.id,
            target_node_ids=mutation.target_node_ids,
            replacement_node_ids=("node-does-not-exist",),
            boundary_interface_ids=mutation.boundary_interface_ids,
            invariants=("preserve-boundary",),
        ).validate(graph)


def test_w14_full_exact_revision_traceability_no_dangling_references(tmp_path):
    """Roadmap gate: full exact-revision traceability — every record cites its
    producing revision and every cross-authority reference resolves (C5)."""
    brown = w14.run_brownfield_scenario(tmp_path / "brown")
    green = w14.run_greenfield_scenario(tmp_path / "green")

    for scenario, revision in ((brown, w14.BROWN_REVISION), (green, w14.GREEN_REVISION)):
        # the resolvable id universe: every record the scenario produced
        run = scenario.run if hasattr(scenario, "run") else scenario.seed_run
        known_ids: set[str] = {
            r.id for r in scenario.evidence_graph.records
        } | {r.id for r in run.evidence_graph.records}
        known_ids.update(c.id for c in run.candidates)
        known_ids.update(a.id for a in run.assurance_results)
        known_ids.update(e.id for e in run.experiments)
        known_ids.update(e.id for e in run.evaluations)
        known_ids.update(d.id for d in run.decisions)
        known_ids.update(r.id for r in run.receipts)
        known_ids.update(it.id for it in run.loop.iterations)
        known_ids.add(run.loop.id)
        for it in run.loop.iterations:
            if it.promotion is not None:
                known_ids.add(it.promotion.id)
        known_ids.update(s.id for s in scenario.selfevo.steps)
        known_ids.add(scenario.selfevo.proposal.id)
        known_ids.add(scenario.graph.id)

        # every referenced id resolves — no dangling references anywhere
        for it in run.loop.iterations:
            for eid in it.evidence_ids:
                assert eid in known_ids, f"iteration {it.index} dangling evidence {eid}"
            for did in it.decision_ids:
                assert did in known_ids, f"iteration {it.index} dangling decision {did}"
            if it.assurance_id is not None:
                assert it.assurance_id in known_ids
            if it.experiment_id is not None:
                assert it.experiment_id in known_ids
            if it.evaluation_id is not None:
                assert it.evaluation_id in known_ids
        # every evidence subject resolves to a known record or artifact
        for record in scenario.evidence_graph.records:
            assert record.subject_ref in known_ids

        # exact-revision provenance: fixture evidence cites the fixture revision
        for record in scenario.evidence_graph.records:
            assert record.provenance.implementation_revision in (
                revision, w14.SEED_REVISION, w14.GREEN_REVISION, w14.BROWN_REVISION,
                w14.DEPLOY_CHANGED_REVISION,
            ) or record.provenance.implementation_revision is None

        # the cross-authority chain agrees on candidate/revision/decision
        for it in run.loop.iterations:
            if it.experiment_id is None:
                continue
            experiment = next(e for e in run.experiments if e.id == it.experiment_id)
            assurance = next(
                a for a in run.assurance_results if a.id == it.assurance_id
            )
            assert experiment.candidate_id == it.candidate_id
            assert experiment.assurance_result_id == assurance.id
            assert assurance.candidate_id == it.candidate_id
            assert experiment.base_graph_revision == assurance.base_graph_revision
            assert experiment.provenance_revision == assurance.provenance_revision

        # every produced id is content-addressed (the repo-wide shape)
        for record in scenario.evidence_graph.records:
            assert record.id.startswith("evidence-")
        for candidate in run.candidates:
            assert candidate.id.startswith("candidate-")
        for decision in run.decisions:
            assert decision.id.startswith("autonomy-")
        for receipt in run.receipts:
            assert receipt.id.startswith("exec-receipt-")
