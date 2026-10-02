"""The deterministic demo seed (see ``db/seeds/__init__.py``)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (str(_REPO_ROOT / "src"), str(_REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from sos.assurance import assure_candidate  # noqa: E402
from sos.autonomy import (  # noqa: E402
    AutonomyDecisionState,
    AutonomyRequest,
    PolicyCeiling,
    evaluate_autonomy,
)
from sos.candidates import (  # noqa: E402
    CandidateObjective,
    CandidateProposal,
    MutationKind,
    ObjectiveDirection,
    SubgraphMutation,
)
from sos.causal import (  # noqa: E402
    CausalHypothesis,
    CausalRelationType,
    EvidenceSupport,
    InterventionMetadata,
    SupportKind,
)
from sos.evidence import EvidenceProvenance  # noqa: E402
from sos.experimentation import (  # noqa: E402
    Experiment,
    ExperimentMode,
    ExperimentState,
    PromotionGate,
    RollbackPath,
    StopCondition,
    evaluate_experiment,
    transition_experiment,
)
from sos.model import (  # noqa: E402
    AskPayload,
    DecisionAction,
    Traceability,
    TruthState,
    TruthfulValue,
)
from sos.recovery import recover_repository  # noqa: E402

from execution.adapters.demo import DemoProvider  # noqa: E402
from providers.github.local import LocalFixtureGitHubSource  # noqa: E402
from services.api.orchestration import (  # noqa: E402
    DEMO_TRACEABILITY,
    ask_payload_domain_to_wire,
    build_evidence_record,
    content_hash,
    evidence_domain_to_wire,
    receipt_to_payload,
    traceability_to_payload,
)

# -- fixed identities / times (deterministic) -------------------------------

DEMO_WORKSPACE_ID = "ws-demo"
ALICE_WORKSPACE_ID = "ws-alice"
BOB_WORKSPACE_ID = "ws-bob"
DEMO_SYSTEM_ID = "sys-demo-example-api"
DEMO_MISSION_ID = "mission-demo-1"
DEMO_EXPERIMENT_ID = "exp-demo-cache"
# Decision/assurance ids are DOMAIN-computed (content-addressed by the W7/W9
# authorities); the seed discovers them at construction time and threads them
# through every reference (persisted rows, experiment chain, execution
# request, authorizations, jobs) so the recorded chain is exactly the chain
# the src/sos services validated.
DEMO_EXECUTION_ID = "exec-demo-1"
DEMO_CANDIDATE_CACHE_ID = "cand-demo-cache"
DEMO_CANDIDATE_REPLICA_ID = "cand-demo-replica"

_T0 = "2026-05-01T09:00:00Z"
_T1 = "2026-05-02T10:00:00Z"
_T2 = "2026-05-10T11:30:00Z"
_T3 = "2026-05-15T08:00:00Z"
_T4 = "2026-05-20T09:30:00Z"
_T5 = "2026-05-21T10:00:00Z"
_T6 = "2026-05-22T15:00:00Z"
_T7 = "2026-05-23T16:00:00Z"

_FIXTURE_COMMITS = tuple(c.sha for c in LocalFixtureGitHubSource.fixture_commits())
_C1, _C2, _C3 = _FIXTURE_COMMITS


def seed_demo(persistence: Any) -> dict[str, Any]:
    """Load the deterministic demo dataset through the persistence seam."""
    if persistence.is_seeded():
        return {"seeded": False, "reason": "demo workspace already present"}

    created: list[str] = []

    # -- 1. users ---------------------------------------------------------
    persistence.upsert_user(
        user_id="user-demo-owner", github_id="900001", login="demo-owner",
        display_name="Demo Owner", created_at=_T0,
    )
    persistence.upsert_user(
        user_id="user-alice", github_id="900002", login="alice",
        display_name="Alice (tenant isolation fixture)", created_at=_T0,
    )
    persistence.upsert_user(
        user_id="user-bob", github_id="900003", login="bob",
        display_name="Bob (tenant isolation fixture)", created_at=_T0,
    )

    # -- 2. workspaces ----------------------------------------------------
    persistence.create_workspace(
        workspace_id=DEMO_WORKSPACE_ID, name="SOS Demo Workspace",
        slug="demo", owner_user_id="user-demo-owner", is_demo=True,
        created_at=_T0,
    )
    persistence.create_workspace(
        workspace_id=ALICE_WORKSPACE_ID, name="Alice's Lab", slug="alice-lab",
        owner_user_id="user-alice", is_demo=False, created_at=_T0,
    )
    persistence.create_workspace(
        workspace_id=BOB_WORKSPACE_ID, name="Bob's Lab", slug="bob-lab",
        owner_user_id="user-bob", is_demo=False, created_at=_T0,
    )
    created += ["workspaces"]

    # -- 3. mission + revisions (journey fields per §C.3) ------------------
    persistence.insert_mission(
        workspace_id=DEMO_WORKSPACE_ID, mission_id=DEMO_MISSION_ID,
        title="Continuously improve the example-api realization",
        status="ACTIVE", current_revision_id="mission-demo-1-r2",
        created_at=_T1,
    )
    persistence.insert_mission_revision(
        mission_id=DEMO_MISSION_ID, revision_id="mission-demo-1-r1", revision=1,
        payload={
            "goals": [
                "Keep example-api reliable for its read-heavy users",
                "Reduce perceived latency on the query path",
            ],
            "outcomes": [
                "p95 latency below 250ms at current traffic",
                "zero unplanned downtime windows",
            ],
            "stakeholders": ["api users", "on-call engineers", "product owner"],
            "measures": [
                "p95 latency (ms) from telemetry",
                "error rate (%) from runtime observations",
            ],
            "constraints": [
                "hard: no data loss (store is the source of truth)",
                "hard: rollback must stay possible at every change",
            ],
            "preferences": [
                "prefer reversible changes over big-bang rewrites",
                "prefer evidence-backed candidates over opinion",
            ],
            "approval": {
                "state": "approved",
                "requestedBy": "user-demo-owner",
                "decidedBy": "user-demo-owner",
                "decidedAt": _T1,
            },
        },
        created_at=_T1, set_current=False,
    )
    persistence.insert_mission_revision(
        mission_id=DEMO_MISSION_ID, revision_id="mission-demo-1-r2", revision=2,
        payload={
            "goals": [
                "Keep example-api reliable for its read-heavy users",
                "Reduce perceived latency on the query path",
                "Contain infrastructure cost growth",
            ],
            "outcomes": [
                "p95 latency below 200ms at current traffic",
                "zero unplanned downtime windows",
                "monthly infra cost stable or lower",
            ],
            "stakeholders": ["api users", "on-call engineers", "product owner"],
            "measures": [
                "p95 latency (ms) from telemetry",
                "error rate (%) from runtime observations",
                "monthly provider cost (USD) from business outcome records",
            ],
            "constraints": [
                "hard: no data loss (store is the source of truth)",
                "hard: rollback must stay possible at every change",
                "hard: cache staleness window bounded to 60s",
            ],
            "preferences": [
                "prefer reversible changes over big-bang rewrites",
                "prefer evidence-backed candidates over opinion",
                "prefer multi-objective tradeoff visibility over a single score",
            ],
            "approval": {
                "state": "approved",
                "requestedBy": "user-demo-owner",
                "decidedBy": "user-demo-owner",
                "decidedAt": _T2,
            },
        },
        created_at=_T2, set_current=True,
    )
    created += ["mission"]

    # -- 4. brownfield system via the REAL recovery pipeline ---------------
    fixture_root = (
        Path(__file__).resolve().parents[2]
        / "providers" / "github" / "fixtures" / "demo-repo"
    )
    recovery_c1 = recover_repository(
        root=fixture_root, revision=_C1, traceability=DEMO_TRACEABILITY
    )
    recovery_c2 = recover_repository(
        root=fixture_root, revision=_C2, traceability=DEMO_TRACEABILITY
    )
    state1 = recovery_c1.system_state
    state2 = recovery_c2.system_state
    graph2 = state2.architecture

    persistence.insert_system(
        workspace_id=DEMO_WORKSPACE_ID, system_id=DEMO_SYSTEM_ID,
        name="example-api", mode="brownfield",
        current_revision_id="sysrev-demo-2", created_at=_T1,
    )
    persistence.insert_system_revision(
        system_id=DEMO_SYSTEM_ID, revision_id="sysrev-demo-1", revision=1,
        payload={
            "stateSummary": (
                "Recovered from the fixture repository at commit 1: an API "
                "layer, a SQLite store and a background worker, with no "
                "caching layer."
            ),
            "uncertainty": {
                "state": "UNKNOWN",
                "reason": (
                    "runtime deployment/configuration facts are unavailable "
                    "from static recovery (source-only inventory)"
                ),
                "confidence": None,
            },
            "sourceRef": {
                "kind": "github",
                "url": "https://github.com/sos-demo/example-api",
                "revision": _C1,
                "immutable": True,
                "fixture": True,
            },
            "recovery": {
                "jobId": "job-demo-recovery-1",
                "status": "succeeded",
            },
            "graph": _graph_wire(state1.architecture),
        },
        created_at=_T1, set_current=False,
    )
    persistence.insert_system_revision(
        system_id=DEMO_SYSTEM_ID, revision_id="sysrev-demo-2", revision=2,
        payload={
            "stateSummary": (
                "Recovered at commit 2 (adds the caching-layer commit on the "
                "query path): stable; read-heavy load concentrated on the "
                "query path; runtime deployment facts still unavailable from "
                "static recovery."
            ),
            "uncertainty": {
                "state": "UNKNOWN",
                "reason": (
                    "runtime deployment/configuration facts remain "
                    "unavailable from static recovery"
                ),
                "confidence": None,
            },
            "sourceRef": {
                "kind": "github",
                "url": "https://github.com/sos-demo/example-api",
                "revision": _C2,
                "immutable": True,
                "fixture": True,
            },
            "recovery": {
                "jobId": "job-demo-recovery-2",
                "status": "succeeded",
            },
            "graph": _graph_wire(graph2),
        },
        created_at=_T2, set_current=True,
    )
    created += ["system"]

    api_node_id = next(
        n.id for n in graph2.nodes if n.name.endswith("api.py")
    )
    api_cached_node_id = next(
        n.id for n in graph2.nodes if n.name.endswith("api_cached.py")
    )
    store_node_id = next(
        n.id for n in graph2.nodes if n.name.endswith("store.py")
    )
    store_replica_node_id = next(
        n.id for n in graph2.nodes if n.name.endswith("store_replica.py")
    )

    # -- 5. evidence: every wire kind, every truth state --------------------
    evidence_specs = [
        # (id, wire kind, result state, provenance rev, environment, source, subject, detail, value)
        ("ev-demo-01", "source_revision", "SUCCESS", _C2, None,
         "architecture-recovery", DEMO_SYSTEM_ID,
         "system state recovered from the fixture repository at the pinned "
         "commit; inventory and graph recorded",
         {"filesClassified": len(recovery_c2.inventory.files),
          "nodesRecovered": len(graph2.nodes)}),
        ("ev-demo-02", "runtime_observation", "SUCCESS", _C2, "production",
         "otel:example-api", graph2.id,
         "request traces captured for the query path over the last window",
         {"requests": 48213, "errorRate": 0.0021}),
        ("ev-demo-03", "runtime_observation", "UNAVAILABLE", None, "production",
         "otel:worker-traces", DEMO_SYSTEM_ID,
         "the worker trace receiver was unreachable during the capture "
         "window; no worker runtime observation exists for this period "
         "(missing data is NOT success)",
         None),
        ("ev-demo-04", "runtime_observation", "EMPTY", _C2, "production",
         "otel:example-api/off-peak", graph2.id,
         "the capture window recorded zero samples (off-peak probe); an "
         "empty capture, not a zero-valued measurement",
         None),
        ("ev-demo-05", "test_result", "SUCCESS", _C2, "ci",
         "ci:pytest", DEMO_SYSTEM_ID,
         "full suite green at the pinned commit",
         {"passed": 64, "failed": 0}),
        ("ev-demo-06", "test_result", "FAILED", _C1, "ci",
         "ci:pytest", DEMO_SYSTEM_ID,
         "2 tests failed at the earlier commit (store race under load; "
         "61 passed); kept as an honest failure record",
         None),
        ("ev-demo-07", "telemetry", "SUCCESS", _C2, "production",
         "telemetry:p95", graph2.id,
         "p95 latency measured on the query path",
         {"p95Ms": 312.0}),
        ("ev-demo-08", "telemetry", "UNKNOWN", _C2, "production",
         "telemetry:cache-hit-ratio", graph2.id,
         "cache-hit-ratio metric absent for this window; the true value is "
         "unknown (not zero, not success)",
         None),
        ("ev-demo-09", "telemetry", "UNSUPPORTED", _C2, "production",
         "telemetry:gc-pause", graph2.id,
         "gc-pause metric is not emitted by this runtime; the measurement is "
         "unsupported for this system",
         None),
        ("ev-demo-10", "environment", "SUCCESS", _C2, None,
         "environment:repo-pins", DEMO_SYSTEM_ID,
         "repository-level environment facts recovered from the manifest",
         {"python": ">=3.10",
          "dependencies": ["fastapi", "pydantic", "httpx"]}),
        ("ev-demo-11", "environment", "UNAVAILABLE", None, None,
         "environment:runtime", DEMO_SYSTEM_ID,
         "runtime environment facts (deployment/configuration/policy) are "
         "unavailable from static recovery; recorded truthfully as "
         "unavailable, not invented",
         None),
        ("ev-demo-12", "experiment", "SUCCESS", _C2, "staging",
         "experiment:cache-warming", graph2.id,
         "staged cache-warming intervention on staging: p95 dropped during "
         "the intervention window (intervention-grade evidence)",
         {"p95BeforeMs": 312.0, "p95AfterMs": 208.0, "window": "72h"}),
        ("ev-demo-13", "business_outcome", "SUCCESS", None, None,
         "analytics:funnel", DEMO_SYSTEM_ID,
         "business funnel outcome over the same period (externally measured; "
         "no implementation revision applies)",
         {"conversion": 0.034, "signups": 1210}),
    ]
    domain_evidence: dict[str, Any] = {}
    for i, spec in enumerate(evidence_specs):
        (
            eid, wire_kind, result_state, prov_rev, env, source, subject,
            detail, value,
        ) = spec
        domain_kind = wire_kind  # domain construction via the wire mapping
        ev = build_evidence_record(
            kind=domain_kind,
            source_ref=source,
            subject_ref=subject,
            result=TruthfulValue(TruthState(result_state), value, detail),
            provenance=EvidenceProvenance(
                source=source,
                observed_subject=subject,
                timestamp=_T2,
                environment=env,
                implementation_revision=prov_rev,
            ),
            traceability=DEMO_TRACEABILITY,
            evidence_id=eid,
            timestamp=_T2,
            environment=env,
            confidence=0.9 if result_state == "SUCCESS" else None,
        )
        domain_evidence[eid] = ev
        persistence.insert_evidence(
            workspace_id=DEMO_WORKSPACE_ID, evidence_id=eid,
            payload=evidence_domain_to_wire(
                ev, evidence_id=eid, workspace_id=DEMO_WORKSPACE_ID,
                system_id=DEMO_SYSTEM_ID,
                created_at=_stamp(10 + i),
                wire_kind=wire_kind,  # the PUBLIC classification is binding
            ),
        )
    created += [f"evidence:{len(evidence_specs)}"]

    # rollback-rehearsal evidence (domain kind ROLLBACK; the governed
    # rollback path for the cache candidate)
    ev_rollback = build_evidence_record(
        kind="runtime_observation",
        source_ref="rollback-rehearsal:staging",
        subject_ref=graph2.id,
        result=TruthfulValue(
            TruthState.SUCCESS,
            {"rehearsedAt": _T3, "restoredWithinSeconds": 96},
            "rollback rehearsal on staging restored the pre-change state "
            "within the bounded window",
        ),
        provenance=EvidenceProvenance(
            source="rollback-rehearsal:staging",
            observed_subject=graph2.id,
            timestamp=_T3,
            environment="staging",
            implementation_revision=_C2,
        ),
        traceability=DEMO_TRACEABILITY,
        evidence_id="ev-demo-rollback",
        timestamp=_T3,
        environment="staging",
        confidence=0.85,
    )
    domain_evidence["ev-demo-rollback"] = ev_rollback
    persistence.insert_evidence(
        workspace_id=DEMO_WORKSPACE_ID, evidence_id="ev-demo-rollback",
        payload=evidence_domain_to_wire(
            ev_rollback, evidence_id="ev-demo-rollback",
            workspace_id=DEMO_WORKSPACE_ID, system_id=DEMO_SYSTEM_ID,
            created_at=_T3, wire_kind="runtime_observation",
        ),
    )

    # -- 6. hypotheses (W5 semantics via the real types) --------------------
    hyp_cache = CausalHypothesis(
        cause_subject="query-path cache",
        effect_subject="p95 latency",
        relation_type=CausalRelationType.INFLUENCES,
        direction="decreases",
        rationale=(
            "The staged cache-warming intervention on staging reduced p95 "
            "during the intervention window; observational telemetry alone "
            "would not establish this"
        ),
        status="confirmed",
        uncertainty=TruthfulValue(
            TruthState.SUCCESS,
            {"stagingToProductionExtrapolation": "moderate"},
            "intervention-grade evidence supports the causal direction; "
            "magnitude carries extrapolation uncertainty",
        ),
        supporting_evidence=(
            EvidenceSupport(
                evidence_id="ev-demo-12",
                support_kind=SupportKind.INTERVENTION,
                intervention=InterventionMetadata(
                    intervention_id="int-cache-warming-staging-1",
                    intervention_kind="config-change",
                    applied_at=_T2,
                    revision=_C2,
                    environment="staging",
                ),
            ),
        ),
        traceability=DEMO_TRACEABILITY,
        provenance_revision=_C2,
        id="hyp-demo-1",
    )
    hyp_replica = CausalHypothesis(
        cause_subject="read replica",
        effect_subject="read throughput",
        relation_type=CausalRelationType.INFLUENCES,
        direction="increases",
        rationale=(
            "Read traffic diversion to a replica should raise read "
            "throughput, but only observational telemetry exists so far; no "
            "intervention has run"
        ),
        status="proposed",
        uncertainty=TruthfulValue(
            TruthState.UNKNOWN, None,
            "no intervention-grade evidence; the causal direction is "
            "plausible but unestablished",
        ),
        supporting_evidence=(
            EvidenceSupport(
                evidence_id="ev-demo-07",
                support_kind=SupportKind.OBSERVATIONAL,
            ),
        ),
        traceability=DEMO_TRACEABILITY,
        provenance_revision=_C2,
        id="hyp-demo-2",
    )
    for hyp, eid_list in ((hyp_cache, ["ev-demo-12"]), (hyp_replica, ["ev-demo-07"])):
        persistence.insert_hypothesis(
            workspace_id=DEMO_WORKSPACE_ID,
            hypothesis_id=hyp.id,
            payload={
                "statement": (
                    f"{hyp.cause_subject} {hyp.relation_type.value} "
                    f"{hyp.effect_subject} ({hyp.direction})"
                ),
                "causal": {
                    "causeSubject": hyp.cause_subject,
                    "effectSubject": hyp.effect_subject,
                    "relationType": hyp.relation_type.value,
                    "direction": hyp.direction,
                    "rationale": hyp.rationale,
                    "status": hyp.status,
                    "uncertainty": {
                        "state": hyp.uncertainty.state.value,
                        "value": hyp.uncertainty.value,
                        "detail": hyp.uncertainty.detail,
                    },
                    "supportingEvidence": [
                        {
                            "evidenceId": s.evidence_id,
                            "supportKind": s.support_kind.value,
                        }
                        for s in hyp.supporting_evidence
                    ],
                },
                "evidenceRefs": eid_list,
                "status": (
                    "SUCCESS" if hyp.status == "confirmed" else "UNKNOWN"
                ),
                "createdAt": _T3,
            },
        )
    created += ["hypotheses"]

    # -- 7. candidates with multi-objective evaluations ----------------------
    cache_objectives = (
        CandidateObjective(
            name="p95-latency-ms", direction=ObjectiveDirection.MINIMIZE,
            predicted_value=205.0,
            uncertainty=TruthfulValue(
                TruthState.UNKNOWN, None,
                "prediction from staging extrapolation; magnitude uncertain",
            ),
        ),
        CandidateObjective(
            name="infra-cost-usd", direction=ObjectiveDirection.MINIMIZE,
            predicted_value=41.0,
            uncertainty=TruthfulValue(
                TruthState.UNKNOWN, None, "estimated monthly delta",
            ),
        ),
        CandidateObjective(
            name="reliability", direction=ObjectiveDirection.MAXIMIZE,
            predicted_value=0.995,
            uncertainty=TruthfulValue(
                TruthState.UNKNOWN, None, "post-change error budget estimate",
            ),
        ),
    )
    replica_objectives = (
        CandidateObjective(
            name="read-throughput-qps", direction=ObjectiveDirection.MAXIMIZE,
            predicted_value=2100.0,
            uncertainty=TruthfulValue(
                TruthState.UNKNOWN, None,
                "no intervention-grade evidence; extrapolated",
            ),
        ),
        CandidateObjective(
            name="infra-cost-usd", direction=ObjectiveDirection.MINIMIZE,
            predicted_value=118.0,
            uncertainty=TruthfulValue(
                TruthState.UNKNOWN, None,
                "replica + storage duplication; estimate only",
            ),
        ),
        CandidateObjective(
            name="reliability", direction=ObjectiveDirection.MAXIMIZE,
            predicted_value=0.994,
            uncertainty=TruthfulValue(
                TruthState.UNKNOWN, None, "replication-lag risk unquantified",
            ),
        ),
    )
    cand_cache = CandidateProposal(
        id=DEMO_CANDIDATE_CACHE_ID,
        base_graph_ref=graph2.id,
        base_graph_revision=state2.revision_id,
        mutation=SubgraphMutation(
            kind=MutationKind.SUBGRAPH_REPLACE,
            base_graph_ref=graph2.id,
            target_node_ids=(api_node_id,),
            replacement_node_ids=(api_cached_node_id,),
            boundary_interface_ids=(store_node_id,),
            invariants=(
                "cache staleness window bounded to 60s (mission hard constraint)",
                "store remains the source of truth (no data loss)",
                "rollback path preserved (rehearsed on staging)",
            ),
        ),
        objectives=cache_objectives,
        rationale=(
            "Switch the query-path entrypoint onto the cached variant "
            "already present (but unwired) in the repository. "
            "Intervention-grade staging evidence supports the latency "
            "direction; costs are bounded and the change is reversible."
        ),
        uncertainty=TruthfulValue(
            TruthState.UNKNOWN, None,
            "predicted effects are extrapolations from staging, not facts",
        ),
        reasoning_evidence_ids=("ev-demo-01", "ev-demo-02", "ev-demo-12"),
        reasoning_hypothesis_ids=("hyp-demo-1",),
        risks=(
            "cache staleness serving stale data within the bounded window",
            "memory pressure on the API process",
            "cache invalidation bugs on write paths",
        ),
        traceability=DEMO_TRACEABILITY,
        provenance_revision=_C2,
    )
    cand_replica = CandidateProposal(
        id=DEMO_CANDIDATE_REPLICA_ID,
        base_graph_ref=graph2.id,
        base_graph_revision=state2.revision_id,
        mutation=SubgraphMutation(
            kind=MutationKind.SUBGRAPH_REPLACE,
            base_graph_ref=graph2.id,
            target_node_ids=(store_node_id,),
            replacement_node_ids=(store_replica_node_id,),
            boundary_interface_ids=(api_node_id,),
            invariants=(
                "replication lag bounded and observable",
                "store remains the source of truth (no data loss)",
                "rollback path preserved",
            ),
        ),
        objectives=replica_objectives,
        rationale=(
            "Swap the store implementation onto the replica-capable variant "
            "already present (but unwired) in the repository and divert read "
            "traffic. Only observational evidence exists; cost roughly "
            "triples the storage footprint."
        ),
        uncertainty=TruthfulValue(
            TruthState.UNKNOWN, None,
            "no intervention-grade evidence for the causal direction",
        ),
        reasoning_evidence_ids=("ev-demo-07", "ev-demo-08"),
        reasoning_hypothesis_ids=("hyp-demo-2",),
        risks=(
            "replication lag serving stale reads",
            "significant infrastructure cost growth",
            "operational complexity of a second data store",
        ),
        traceability=DEMO_TRACEABILITY,
        provenance_revision=_C2,
    )
    known_hypotheses = {hyp_cache.id: hyp_cache, hyp_replica.id: hyp_replica}

    def candidate_wire_payload(cand: CandidateProposal) -> dict[str, Any]:
        return {
            "name": (
                "Switch the query path onto the cached API variant"
                if cand.id == DEMO_CANDIDATE_CACHE_ID
                else "Swap the store onto the replica-capable variant"
            ),
            "subgraphReplacement": {
                "kind": cand.mutation.kind.value,
                "targetNodeIds": list(cand.mutation.target_node_ids),
                "replacementNodeIds": list(cand.mutation.replacement_node_ids),
                "boundaryInterfaceIds": list(
                    cand.mutation.boundary_interface_ids
                ),
                "invariants": list(cand.mutation.invariants),
            },
            "effects": [
                {
                    "objective": o.name,
                    "direction": o.direction.value,
                    "predictedValue": o.predicted_value,
                }
                for o in cand.objectives
            ],
            "costs": [
                {"kind": "infra", "amount": (
                    12.0 if cand.id == DEMO_CANDIDATE_CACHE_ID else 89.0
                ), "unit": "USD/month"},
            ],
            "risks": list(cand.risks),
            "constraints": list(cand.mutation.invariants),
            "evidenceRefs": list(cand.reasoning_evidence_ids),
            "reversibility": {
                "rollbackAvailable": True,
                "detail": (
                    "rollback rehearsed on staging (ev-demo-rollback); "
                    "bounded restore within the governed window"
                ),
            },
            "evaluation": {
                "objectives": [
                    {
                        "name": o.name,
                        "direction": o.direction.value,
                        "predictedValue": o.predicted_value,
                        "uncertainty": {
                            "state": o.uncertainty.state.value,
                            "detail": o.uncertainty.detail,
                        },
                    }
                    for o in cand.objectives
                ],
                "paretoFront": [
                    {
                        "candidateId": DEMO_CANDIDATE_CACHE_ID,
                        "values": {
                            "p95-latency-ms": 205.0,
                            "infra-cost-usd": 41.0,
                            "reliability": 0.995,
                            "read-throughput-qps": 1650.0,
                        },
                    },
                    {
                        "candidateId": DEMO_CANDIDATE_REPLICA_ID,
                        "values": {
                            "p95-latency-ms": 251.0,
                            "infra-cost-usd": 118.0,
                            "reliability": 0.994,
                            "read-throughput-qps": 2100.0,
                        },
                    },
                ],
            },
            "createdAt": _T3,
        }

    persistence.insert_candidate(
        workspace_id=DEMO_WORKSPACE_ID, candidate_id=cand_cache.id,
        payload=candidate_wire_payload(cand_cache),
    )
    persistence.insert_candidate(
        workspace_id=DEMO_WORKSPACE_ID, candidate_id=cand_replica.id,
        payload=candidate_wire_payload(cand_replica),
    )
    created += ["candidates"]

    # -- 8. assurance runs through the REAL W7 engine ------------------------
    assurance_cache = assure_candidate(
        candidate=cand_cache,
        base_graph=graph2,
        known_evidence=domain_evidence,
        known_hypotheses=known_hypotheses,
        hard_constraints=(),
        rollback_evidence_ids=("ev-demo-rollback",),
    )
    assurance_replica = assure_candidate(
        candidate=cand_replica,
        base_graph=graph2,
        known_evidence=domain_evidence,
        known_hypotheses=known_hypotheses,
        hard_constraints=(),
        rollback_evidence_ids=("ev-demo-rollback",),
    )

    def assurance_wire_payload(result: Any) -> dict[str, Any]:
        return {
            "candidateId": result.candidate_id,
            "checks": [
                {
                    "name": g.name,
                    "status": g.status.value,
                    "evidenceIds": list(g.evidence_ids),
                    "detail": g.detail,
                }
                for g in result.gates
            ],
            "verdict": result.status.value,
            "domain": {
                "baseGraphId": result.base_graph_id,
                "baseGraphRevision": result.base_graph_revision,
                "provenanceRevision": result.provenance_revision,
                "gates": [
                    {
                        "name": g.name,
                        "status": g.status.value,
                        "evidenceIds": list(g.evidence_ids),
                        "detail": g.detail,
                    }
                    for g in result.gates
                ],
                "impact": {
                    "affectedNodeIds": list(result.impact.affected_node_ids),
                    "affectedEdgeIds": list(result.impact.affected_edge_ids),
                    "boundaryInterfaceIds": list(
                        result.impact.boundary_interface_ids
                    ),
                    "dependencyReach": list(result.impact.dependency_reach),
                    "blastRadius": {
                        "level": result.impact.blast_radius.level,
                        "affectedCount": result.impact.blast_radius.affected_count,
                        "detail": result.impact.blast_radius.detail,
                    },
                },
                "risk": {
                    "items": [
                        {
                            "name": r.name,
                            "severity": r.severity,
                            "uncertainty": {
                                "state": r.uncertainty.state.value,
                                "value": r.uncertainty.value,
                                "detail": r.uncertainty.detail,
                            },
                            "mitigation": r.mitigation,
                            "residual": r.residual,
                        }
                        for r in result.risk.items
                    ]
                },
                "reversibility": {
                    "rollbackAvailable": result.reversibility.rollback_available,
                    "detail": result.reversibility.detail,
                    "rollbackEvidenceIds": list(
                        result.reversibility.rollback_evidence_ids
                    ),
                    "containmentPolicyRef": (
                        result.reversibility.containment_policy_ref
                    ),
                },
                "objectives": [
                    {
                        "name": o.name,
                        "direction": o.direction.value,
                        "predictedValue": o.predicted_value,
                    }
                    for o in result.objectives
                ],
                "traceability": traceability_to_payload(result.traceability),
            },
        }

    persistence.insert_assurance(
        workspace_id=DEMO_WORKSPACE_ID, assurance_id=assurance_cache.id,
        payload={**assurance_wire_payload(assurance_cache),
                 "createdAt": _T4},
    )
    persistence.insert_assurance(
        workspace_id=DEMO_WORKSPACE_ID, assurance_id=assurance_replica.id,
        payload={**assurance_wire_payload(assurance_replica),
                 "createdAt": _T4},
    )
    created += [
        f"assurance:{assurance_cache.status.value}/{assurance_replica.status.value}"
    ]

    # -- 9. experiment + lifecycle + evaluation + promotion ------------------
    rollback_ref = "rollback://demo/example-api/cache-v1"
    experiment = Experiment(
        id=DEMO_EXPERIMENT_ID,
        candidate_id=cand_cache.id,
        assurance_result_id=assurance_cache.id,
        base_graph_id=graph2.id,
        base_graph_revision=state2.revision_id,
        provenance_revision=_C2,
        mode=ExperimentMode.CANARY,
        scope=("query-path",),
        observation_window=(_T4, _T6),
        success_criteria=(
            "p95 latency below 250ms during the window",
            "error rate below 0.5% during the window",
        ),
        stop_conditions=(
            StopCondition(
                name="error-rate", threshold=0.01, metric="error-rate"
            ),
            StopCondition(name="p95-latency", threshold=450.0, metric="p95-ms"),
        ),
        rollback_ref=rollback_ref,
        traceability=DEMO_TRACEABILITY,
        state=ExperimentState.PLANNED,
    )
    experiment = transition_experiment(
        experiment, ExperimentState.READY,
        known_assurance=assurance_cache,
    )
    experiment = transition_experiment(
        experiment, ExperimentState.RUNNING,
        known_assurance=assurance_cache,
    )
    experiment = transition_experiment(
        experiment, ExperimentState.COMPLETED,
        known_assurance=assurance_cache,
    )
    evaluation = evaluate_experiment(
        experiment,
        known_evidence=domain_evidence,
        evidence_refs=("ev-demo-02", "ev-demo-12"),
        evaluation_success=True,
        known_assurance=assurance_cache,
        rollback_path=RollbackPath(
            reference=rollback_ref,
            evidence_ids=("ev-demo-rollback",),
            detail=(
                "staging rollback rehearsal bound to the experiment's "
                "governed rollback reference"
            ),
            recovered=False,
        ),
    )
    promotion = PromotionGate().evaluate(
        experiment, evaluation, known_assurance=assurance_cache
    )
    persistence.insert_experiment(
        workspace_id=DEMO_WORKSPACE_ID, experiment_id=experiment.id,
        payload={
            "candidateId": experiment.candidate_id,
            "status": experiment.state.value,
            "events": [
                {"at": _T4, "type": "created",
                 "detail": "experiment created for the cache candidate"},
                {"at": _T4, "type": "assurance-bound",
                 "detail": f"bound to assurance-demo-cache "
                           f"({assurance_cache.status.value})"},
                {"at": _T5, "type": "started",
                 "detail": "canary window opened on the query path"},
                {"at": _T6, "type": "completed",
                 "detail": "observation window closed; evaluation recorded"},
            ],
            "domain": {
                "assuranceResultId": experiment.assurance_result_id,
                "baseGraphId": experiment.base_graph_id,
                "baseGraphRevision": experiment.base_graph_revision,
                "provenanceRevision": experiment.provenance_revision,
                "mode": experiment.mode.value,
                "scope": list(experiment.scope),
                "observationWindow": list(experiment.observation_window),
                "successCriteria": list(experiment.success_criteria),
                "stopConditions": [
                    {"name": s.name, "threshold": s.threshold,
                     "metric": s.metric}
                    for s in experiment.stop_conditions
                ],
                "rollbackRef": experiment.rollback_ref,
                "containmentPolicyRef": experiment.containment_policy_ref,
                "traceability": traceability_to_payload(experiment.traceability),
            },
            "createdAt": _T4,
        },
    )
    created += [f"experiment:{experiment.state.value}",
                f"promotion:{promotion.promoted}"]

    # -- 10. autonomy decisions through the REAL W9 engine -------------------
    policy = AutonomyRequest(
        id="policy-demo-default",
        version=1,
        allowed_actions=(
            DecisionAction.GATHER_EVIDENCE, DecisionAction.EXPERIMENT,
            DecisionAction.ACT,
        ),
        ceilings=PolicyCeiling(
            max_risk=0.4,
            max_blast_radius="limited",
            require_reversible=True,
            min_confidence=0.75,
            require_human_approval_for_act=False,
        ),
        traceability=DEMO_TRACEABILITY,
    )

    decision_act = evaluate_autonomy(
        policy=policy,
        action=DecisionAction.ACT,
        assurance=assurance_cache,
        experiment=experiment,
        promotion=promotion,
        evaluation=evaluation,
        evidence_ids=("ev-demo-02", "ev-demo-12"),
        traceability=DEMO_TRACEABILITY,
        known_evidence=domain_evidence,
        human_authority_present=True,
        blast_radius="limited",
        rollback_path=RollbackPath(
            reference=rollback_ref,
            evidence_ids=("ev-demo-rollback",),
            detail="staging rollback rehearsal",
            recovered=False,
        ),
        risk=0.3,
        confidence=0.82,
        reversible=True,
    )
    decision_ask = evaluate_autonomy(
        policy=policy,
        action=DecisionAction.ACT,
        assurance=assurance_replica,
        experiment=None,
        promotion=None,
        evaluation=None,
        evidence_ids=("ev-demo-07", "ev-demo-08"),
        traceability=DEMO_TRACEABILITY,
        known_evidence=domain_evidence,
        human_authority_present=False,
        blast_radius="organization",
        rollback_path=None,
        risk=0.75,
        confidence=0.55,
        reversible=True,
    )
    ask = AskPayload(
        exact_decision=(
            "Approve the read-replica candidate (EXPERIMENT first on a "
            "staging slice, then re-evaluate) or REJECT it"
        ),
        alternatives=(
            "EXPERIMENT: run a bounded replica experiment on staging first",
            "GATHER_EVIDENCE: instrument replication-lag telemetry before "
            "deciding",
            "REJECT: keep the single-store design",
        ),
        evidence_quality=(
            "observational only; no intervention-grade evidence for the "
            "causal direction"
        ),
        uncertainty=(
            "cost estimate is a wide extrapolation; replication lag is "
            "unquantified"
        ),
        trade_offs=(
            "read throughput vs. infra cost growth",
            "throughput vs. operational complexity",
        ),
    )

    persistence.insert_decision(
        workspace_id=DEMO_WORKSPACE_ID, decision_id=decision_act.id,
        payload=_decision_wire_payload(
            decision=decision_act,
            requested_action=DecisionAction.ACT,
            policy=policy,
            risk=0.3,
            blast_radius="limited",
            reversibility={
                "rollbackAvailable": True,
                "detail": "governed rollback path bound to the experiment",
            },
            required_approvals=[],
            expected_impact={
                "objectives": [
                    {"name": o.name,
                     "direction": o.direction.value,
                     "predictedValue": o.predicted_value}
                    for o in cand_cache.objectives
                ]
            },
            ask_payload=None,
            created_at=_T6,
        ),
    )
    persistence.insert_decision(
        workspace_id=DEMO_WORKSPACE_ID, decision_id=decision_ask.id,
        payload=_decision_wire_payload(
            decision=decision_ask,
            requested_action=DecisionAction.ACT,
            policy=policy,
            risk=0.75,
            blast_radius="organization",
            reversibility={
                "rollbackAvailable": True,
                "detail": "rollback possible but cost-heavy (storage removal)",
            },
            required_approvals=["user-demo-owner"],
            expected_impact={
                "objectives": [
                    {"name": o.name,
                     "direction": o.direction.value,
                     "predictedValue": o.predicted_value}
                    for o in cand_replica.objectives
                ]
            },
            ask_payload=ask_payload_domain_to_wire(ask),
            created_at=_T6,
        ),
    )
    created += [
        f"decision:{decision_act.state.value}/{decision_ask.state.value}"
    ]

    # -- 11. authorizations ---------------------------------------------------
    persistence.insert_authorization(
        workspace_id=DEMO_WORKSPACE_ID, authorization_id="auth-demo-1",
        payload={
            "decisionId": decision_act.id,
            "principal": "user:demo-owner",
            "scope": "deploy:example-api",
            "decision": "granted",
            "createdAt": _T6,
        },
    )
    persistence.insert_authorization(
        workspace_id=DEMO_WORKSPACE_ID, authorization_id="auth-demo-2",
        payload={
            "decisionId": None,
            "principal": "role:anonymous",
            "scope": "mutate:demo",
            "decision": "denied",
            "createdAt": _T6,
        },
    )
    created += ["authorizations"]

    # -- 12. governed execution through the REAL W11 substrate ----------------
    from sos.execution import RollbackReference as _RR

    exec_request = _build_seed_execution_request(
        graph_id=graph2.id,
        graph_revision=state2.revision_id,
        rollback_ref=rollback_ref,
        decision_id=decision_act.id,
        assurance_id=assurance_cache.id,
    )
    substrate_registry = {"demo": DemoProvider()}
    from sos.execution import ExecutionSubstrate

    substrate = ExecutionSubstrate(
        providers=substrate_registry,
        known_decisions={decision_act.id: decision_act},
        known_assurance={assurance_cache.id: assurance_cache},
        known_experiments={experiment.id: experiment},
    )
    receipt = substrate.submit(exec_request)
    receipt_payload = receipt_to_payload(receipt)
    artifact_key = (
        f"tenants/{DEMO_WORKSPACE_ID}/systems/{DEMO_SYSTEM_ID}/executions/"
        f"{DEMO_EXECUTION_ID}/receipts/{content_hash((receipt.id,))}.json"
    )
    persistence.insert_execution(
        workspace_id=DEMO_WORKSPACE_ID, execution_id=DEMO_EXECUTION_ID,
        payload={
            "experimentId": experiment.id,
            "provider": "demo",
            "requestHash": exec_request.id,
            "receipt": receipt_payload,
            "artifactRefs": [artifact_key],
            "status": receipt_payload["outcome"]["state"],
            "createdAt": _T7,
        },
    )
    # receipt → evidence (observed, not inferred) via the W4 binding
    from services.api.orchestration import receipt_evidence_wire

    receipt_ev, receipt_wire_kind = receipt_evidence_wire(
        receipt, traceability=DEMO_TRACEABILITY
    )
    persistence.insert_evidence(
        workspace_id=DEMO_WORKSPACE_ID, evidence_id="ev-demo-exec-receipt",
        payload=evidence_domain_to_wire(
            receipt_ev, evidence_id="ev-demo-exec-receipt",
            workspace_id=DEMO_WORKSPACE_ID, system_id=DEMO_SYSTEM_ID,
            created_at=_T7, wire_kind=receipt_wire_kind,
            artifact_ref=artifact_key,
        ),
    )
    created += [f"execution:{receipt.lifecycle.value}"]

    # -- 13. learning + memory --------------------------------------------------
    persistence.insert_learning(
        workspace_id=DEMO_WORKSPACE_ID, record_id="learn-demo-1",
        payload={
            "context": {
                "missionRef": "mission-demo-1",
                "graphRef": graph2.id,
                "environment": "staging+production",
            },
            "candidate": cand_cache.id,
            "predictedEffects": [
                {"objective": "p95-latency-ms", "predicted": 205.0},
                {"objective": "infra-cost-usd", "predicted": 41.0},
            ],
            "actualEffects": [
                {"objective": "p95-latency-ms", "observed": 208.0,
                 "state": "SUCCESS"},
                {"objective": "infra-cost-usd", "observed": None,
                 "state": "UNKNOWN"},
            ],
            "uncertainty": {
                "state": "UNKNOWN",
                "reason": "one window of observation; cost not yet invoiced",
            },
            "verdict": "partially-confirmed",
            "lessons": [
                "staging extrapolation tracked production latency within 2%",
                "cost effects need invoiced data before confirmation",
                "keep the cache-staleness invariant visible in the next cycle",
            ],
            "createdAt": _T7,
        },
    )
    persistence.insert_memory(
        workspace_id=DEMO_WORKSPACE_ID, entry_id="mem-demo-1",
        payload={
            "context": {"graphRef": graph2.id, "scope": "query-path"},
            "candidate": cand_cache.id,
            "predictedEffects": [
                {"objective": "p95-latency-ms", "predicted": 205.0}
            ],
            "actualEffects": [
                {"objective": "p95-latency-ms", "observed": 208.0}
            ],
            "uncertainty": {
                "state": "UNKNOWN", "reason": "single-cycle evidence",
            },
            "verdict": "direction-confirmed",
            "lessons": [
                "cache-before-query-path reduced p95 in both staging and "
                "production windows",
            ],
            "createdAt": _T7,
        },
    )
    persistence.insert_memory(
        workspace_id=DEMO_WORKSPACE_ID, entry_id="mem-demo-2",
        payload={
            "context": {"graphRef": graph2.id, "scope": "worker"},
            "candidate": "none (observation)",
            "predictedEffects": [],
            "actualEffects": [
                {"objective": "worker-health", "observed": None,
                 "state": "UNAVAILABLE"}
            ],
            "uncertainty": {
                "state": "UNAVAILABLE",
                "reason": "worker trace receiver unreachable (ev-demo-03)",
            },
            "verdict": "not-observable",
            "lessons": [
                "worker runtime facts stay UNAVAILABLE until the trace "
                "receiver is repaired; do not treat as healthy",
            ],
            "createdAt": _T7,
        },
    )
    created += ["learning", "memory"]

    # -- 14. jobs ------------------------------------------------------------------
    persistence.insert_job(
        workspace_id=DEMO_WORKSPACE_ID, job_id="job-demo-recovery-1",
        payload={
            "type": "system_recovery",
            "requestedBy": "user-demo-owner",
            "authoritySnapshot": {
                "principal": "user:demo-owner",
                "workspaceRole": "owner",
            },
            "inputHash": content_hash((_C1, DEMO_SYSTEM_ID)),
            "sourceRevision": _C1,
            "provider": "local",
            "status": "succeeded",
            "startedAt": _T1,
            "completedAt": _T1,
            "receipt": {
                "performedBy": "sos.recovery.recover_repository",
                "fixture": True,
                "source": "providers/github/fixtures/demo-repo",
                "revision": _C1,
                "systemRevisionId": "sysrev-demo-1",
            },
            "artifactRefs": [],
            "errorState": None,
            "idempotencyKey": "seed-recovery-1",
            "createdAt": _T1,
        },
    )
    persistence.insert_job(
        workspace_id=DEMO_WORKSPACE_ID, job_id="job-demo-recovery-2",
        payload={
            "type": "system_recovery",
            "requestedBy": "user-demo-owner",
            "authoritySnapshot": {
                "principal": "user:demo-owner",
                "workspaceRole": "owner",
            },
            "inputHash": content_hash((_C2, DEMO_SYSTEM_ID)),
            "sourceRevision": _C2,
            "provider": "local",
            "status": "succeeded",
            "startedAt": _T2,
            "completedAt": _T2,
            "receipt": {
                "performedBy": "sos.recovery.recover_repository",
                "fixture": True,
                "source": "providers/github/fixtures/demo-repo",
                "revision": _C2,
                "systemRevisionId": "sysrev-demo-2",
            },
            "artifactRefs": [],
            "errorState": None,
            "idempotencyKey": "seed-recovery-2",
            "createdAt": _T2,
        },
    )
    persistence.insert_job(
        workspace_id=DEMO_WORKSPACE_ID, job_id="job-demo-exec-1",
        payload={
            "type": "experiment_execution",
            "requestedBy": "user-demo-owner",
            "authoritySnapshot": {
                "principal": "user:demo-owner",
                "policyId": policy.id,
                "decisionId": decision_act.id,
                "assuranceId": assurance_cache.id,
                "workspaceRole": "owner",
            },
            "inputHash": exec_request.id,
            "sourceRevision": _C2,
            "provider": "demo",
            "status": "succeeded",
            "startedAt": receipt_payload["startedAt"],
            "completedAt": receipt_payload["finishedAt"],
            "receipt": receipt_payload,
            "artifactRefs": [artifact_key],
            "errorState": None,
            "idempotencyKey": "seed-exec-1",
            "createdAt": _T7,
        },
    )
    created += ["jobs"]

    # -- 15. activity (audit) trail ---------------------------------------------
    audit_specs = [
        ("audit-demo-01", _T1, "user-demo-owner", "workspace.seeded",
         f"workspace/{DEMO_WORKSPACE_ID}", {"demo": True}),
        ("audit-demo-02", _T1, "user-demo-owner", "mission.created",
         f"mission/{DEMO_MISSION_ID}", {"revision": 1}),
        ("audit-demo-03", _T2, "user-demo-owner", "mission.revision.approved",
         "mission-revision/mission-demo-1-r2", {"revision": 2}),
        ("audit-demo-04", _T1, "user-demo-owner", "system.onboarded",
         f"system/{DEMO_SYSTEM_ID}", {"mode": "brownfield",
                                      "sourceRevision": _C1}),
        ("audit-demo-05", _T2, "user-demo-owner", "system.recovered",
         "system-revision/sysrev-demo-2", {"sourceRevision": _C2}),
        ("audit-demo-06", _T4, "user-demo-owner", "assurance.evaluated",
         "assurance/assurance-demo-cache",
         {"verdict": assurance_cache.status.value}),
        ("audit-demo-07", _T6, "user-demo-owner", "decision.recorded",
         f"decision/{decision_act.id}",
         {"action": decision_act.state.value}),
        ("audit-demo-08", _T6, "user-demo-owner", "decision.recorded",
         f"decision/{decision_ask.id}",
         {"action": decision_ask.state.value}),
        ("audit-demo-09", _T7, "user-demo-owner", "execution.dispatched",
         f"execution/{DEMO_EXECUTION_ID}",
         {"provider": "demo", "demo": True}),
        ("audit-demo-10", _T7, "user-demo-owner", "job.completed",
         "job/job-demo-exec-1", {"status": "succeeded"}),
    ]
    for audit_id, ts, actor, action, target, meta in audit_specs:
        persistence.append_audit(
            tenant_id=DEMO_WORKSPACE_ID, actor=actor, action=action,
            target=target, meta=meta, ts=ts, audit_id=audit_id,
        )
    created += [f"audit:{len(audit_specs)}"]

    return {"seeded": True, "created": created}


# -- helpers -------------------------------------------------------------------


def _stamp(day_offset: int) -> str:
    return f"2026-05-{day_offset:02d}T12:00:00Z"


def _graph_wire(graph: Any) -> dict[str, Any]:
    return {
        "id": graph.id,
        "version": graph.version,
        "nodes": [
            {
                "id": n.id,
                "type": n.type.value,
                "name": n.name,
                "attributes": dict(n.attributes),
                "uncertainty": {
                    "state": n.uncertainty.state.value,
                    "reason": n.uncertainty.reason,
                    "confidence": n.uncertainty.confidence,
                },
            }
            for n in graph.nodes
        ],
        "edges": [
            {
                "id": e.id,
                "type": e.type.value,
                "sourceId": e.source_id,
                "targetId": e.target_id,
                "attributes": dict(e.attributes),
                "uncertainty": {
                    "state": e.uncertainty.state.value,
                    "reason": e.uncertainty.reason,
                    "confidence": e.uncertainty.confidence,
                },
            }
            for e in graph.edges
        ],
        "boundaryContracts": [
            {
                "id": b.id,
                "interfaceNodeId": b.interface_node_id,
                "contract": b.contract,
                "invariants": list(b.invariants),
            }
            for b in graph.boundary_contracts
        ],
    }


def _decision_wire_payload(
    *,
    decision: Any,
    requested_action: DecisionAction,
    policy: AutonomyRequest,
    risk: float,
    blast_radius: str,
    reversibility: dict[str, Any],
    required_approvals: list[str],
    expected_impact: dict[str, Any],
    ask_payload: dict[str, Any] | None,
    created_at: str,
) -> dict[str, Any]:
    return {
        "action": decision.state.value,  # the OUTCOME (ASK stays ASK)
        "rationale": decision.rationale,
        "evidenceRefs": list(decision.evidence_ids),
        "authoritySnapshot": {
            "policyId": decision.policy_id,
            "policyVersion": policy.version,
            "requestedAction": requested_action.value,
            "autonomyState": decision.state.value,
            "assuranceId": decision.assurance_id,
            "experimentId": decision.experiment_id,
            "promotionId": decision.promotion_id,
            "humanAuthorityPresent": True,
            "reasons": list(decision.reasons),
            "traceability": traceability_to_payload(decision.traceability),
        },
        "expectedImpact": expected_impact,
        "risk": risk,
        "blastRadius": blast_radius,
        "reversibility": reversibility,
        "requiredApprovals": required_approvals,
        "askPayload": ask_payload,
        "createdAt": created_at,
    }


def _build_seed_execution_request(
    *,
    graph_id: str,
    graph_revision: str,
    rollback_ref: str,
    decision_id: str,
    assurance_id: str,
):
    from sos.execution import RollbackReference

    from services.api.orchestration import build_execution_request

    return build_execution_request(
        intent=(
            "Demo execution of the governed cache candidate for the example-api "
            "query path (simulated; demo:true)"
        ),
        provider_id="demo",
        source_revision=_C2,
        provenance_revision=_C2,
        base_graph_id=graph_id,
        base_graph_revision=graph_revision,
        environment="demo",
        w9_decision_id=decision_id,
        w7_assurance_id=assurance_id,
        w8_experiment_id=DEMO_EXPERIMENT_ID,
        rollback_reference={
            "reference": rollback_ref,
            "evidenceIds": ["ev-demo-rollback"],
            "detail": "staging rollback rehearsal bound to the experiment",
        },
        traceability=DEMO_TRACEABILITY,
        workspace_ref=DEMO_WORKSPACE_ID,
    )
