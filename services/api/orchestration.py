"""Domain orchestration + domain↔wire mapping (PUB-01 thin-route seam).

THE RULE (contract §C.4): every route is ``authenticate → tenant-authorize →
validate → call a domain orchestration function (importing ``sos.*``) →
persist → return a typed DTO``. This module IS that domain-orchestration
function layer: it imports ``sos.*`` (never edits it), constructs and drives
the frozen domain objects, and maps rows ↔ domain objects ↔ wire payloads.

Mapping ONLY — no second authority: truth states pass through verbatim
(``sos.model.TruthState``); no decision logic is invented here; every
governed transition (experiment lifecycle, promotion, autonomy, execution
authorization) runs through the ``src/sos`` services that own it.

The demo seed (``db/seeds/demo_seed.py``) uses the SAME mapping functions,
so persisted rows and runtime flows cannot drift apart.
"""
from __future__ import annotations

import hashlib
from typing import Any

from sos.assurance import (
    AssuranceGate,
    AssuranceResult,
    AssuranceStatus,
    BlastRadius,
    ImpactAnalysis,
    ReversibilityAssessment,
    RiskAssessment,
    RiskItem,
)
from sos.autonomy import AutonomyDecision, AutonomyDecisionState
from sos.causal import EvidenceSupport, InterventionMetadata, SupportKind
from sos.evidence import Evidence, EvidenceKind, EvidenceProvenance
from sos.execution import (
    ExecutionReceipt,
    ExecutionRequest,
    ExecutionSubstrate,
    RollbackReference,
    receipt_to_w4_evidence,
)
from sos.experimentation import Experiment, ExperimentState
from sos.model import (
    AskPayload,
    DecisionAction,
    Traceability,
    TruthState,
    TruthfulValue,
)

# ---------------------------------------------------------------------------
# Wire evidence kinds (the public 7-kind vocabulary, directive §5) and the
# documented domain mapping (mapping only — semantics stay in src/sos).
# ---------------------------------------------------------------------------

WIRE_EVIDENCE_KINDS: tuple[str, ...] = (
    "source_revision",
    "runtime_observation",
    "test_result",
    "telemetry",
    "environment",
    "experiment",
    "business_outcome",
)

DOMAIN_TO_WIRE_EVIDENCE_KIND: dict[str, str] = {
    "static-analysis": "source_revision",
    "observation": "runtime_observation",
    "test": "test_result",
    "experiment": "experiment",
    "simulation": "experiment",
    "replay": "experiment",
    "shadow": "experiment",
    "canary": "experiment",
    "deployment": "runtime_observation",
    "rollback": "runtime_observation",
    "incident": "runtime_observation",
    "business-outcome": "business_outcome",
    "user-outcome": "business_outcome",
}

WIRE_TO_DOMAIN_EVIDENCE_KIND: dict[str, EvidenceKind] = {
    "source_revision": EvidenceKind.STATIC_ANALYSIS,
    "runtime_observation": EvidenceKind.OBSERVATION,
    "test_result": EvidenceKind.TEST,
    "telemetry": EvidenceKind.OBSERVATION,
    "environment": EvidenceKind.OBSERVATION,
    "experiment": EvidenceKind.EXPERIMENT,
    "business_outcome": EvidenceKind.BUSINESS_OUTCOME,
}


def truth_state_of(value: Any) -> str:
    """A truth state rendered verbatim (six-state; never converted)."""
    if isinstance(value, TruthState):
        return value.value
    return str(value)


# ---------------------------------------------------------------------------
# Traceability helper (constitution/mission refs recorded on domain objects)
# ---------------------------------------------------------------------------

DEMO_TRACEABILITY = Traceability(
    constitution_ref="spec/constitution.md",
    mission_ref="mission:demo",
    value_model_ref="value-model:demo",
    context_ref="context:demo",
)


def traceability_from_payload(payload: dict[str, Any]) -> Traceability:
    return Traceability(
        constitution_ref=payload.get("constitutionRef", "spec/constitution.md"),
        mission_ref=payload.get("missionRef", ""),
        value_model_ref=payload.get("valueModelRef"),
        context_ref=payload.get("contextRef"),
    )


def traceability_to_payload(t: Traceability) -> dict[str, str | None]:
    return {
        "constitutionRef": t.constitution_ref,
        "missionRef": t.mission_ref,
        "valueModelRef": t.value_model_ref,
        "contextRef": t.context_ref,
    }


# ---------------------------------------------------------------------------
# Domain → wire: evidence
# ---------------------------------------------------------------------------


def evidence_domain_to_wire(
    ev: Evidence,
    *,
    evidence_id: str,
    workspace_id: str,
    system_id: str | None,
    created_at: str,
    wire_kind: str | None = None,
    artifact_ref: str | None = None,
) -> dict[str, Any]:
    """Map one ``sos.evidence.Evidence`` to the wire payload (§C.3 minimums).

    The wire ``status`` is the evidence's observed RESULT truth state — the
    six-state vocabulary, verbatim. ``relatedSystemState`` carries the
    evidence's ``subject_ref``. Availability (capture state) is preserved in
    provenance detail.
    """
    wire = DOMAIN_TO_WIRE_EVIDENCE_KIND[ev.kind.value]
    return {
        "id": evidence_id,
        "workspaceId": workspace_id,
        "systemId": system_id,
        "kind": wire_kind or wire,
        "status": truth_state_of(ev.result.state),
        "provenance": {
            "source": ev.provenance.source,
            "observedSubject": ev.provenance.observed_subject,
            "timestamp": ev.provenance.timestamp,
            "environment": ev.provenance.environment,
            "implementationRevision": ev.provenance.implementation_revision,
            "availability": truth_state_of(ev.availability),
        },
        "timestamp": ev.timestamp,
        "sourceRevision": ev.provenance.implementation_revision,
        "relatedSystemState": ev.subject_ref,
        "confidence": ev.confidence,
        "artifactRef": artifact_ref,
        "result": {
            "state": truth_state_of(ev.result.state),
            "value": _jsonable(ev.result.value),
            "detail": ev.result.detail,
        },
        "createdAt": created_at,
    }


def build_evidence_record(
    *,
    kind: str,
    source_ref: str,
    subject_ref: str,
    result: TruthfulValue[Any],
    provenance: EvidenceProvenance,
    traceability: Traceability,
    evidence_id: str,
    timestamp: str | None = None,
    environment: str | None = None,
    confidence: float | None = None,
    availability: TruthState = TruthState.SUCCESS,
) -> Evidence:
    """Construct a domain ``Evidence`` with an explicit deterministic id.

    Public ``Evidence`` dataclass construction — validation runs at the
    boundary exactly as in the W4 module (no semantic invention here).
    """
    return Evidence(
        id=evidence_id,
        kind=WIRE_TO_DOMAIN_EVIDENCE_KIND[kind],
        source_ref=source_ref,
        subject_ref=subject_ref,
        timestamp=timestamp,
        environment=environment,
        result=result,
        provenance=provenance,
        confidence=confidence,
        availability=availability,
        traceability=traceability,
    )


def causal_support_domain_to_wire(support: EvidenceSupport) -> dict[str, Any]:
    return {
        "evidenceId": support.evidence_id,
        "supportKind": support.support_kind.value,
        "intervention": (
            {
                "interventionId": support.intervention.intervention_id,
                "interventionKind": support.intervention.intervention_kind,
                "appliedAt": support.intervention.applied_at,
                "revision": support.intervention.revision,
                "environment": support.intervention.environment,
            }
            if support.intervention is not None
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Domain → wire: execution receipts
# ---------------------------------------------------------------------------


def receipt_to_payload(receipt: ExecutionReceipt) -> dict[str, Any]:
    """Serialize a receipt verbatim (truth states, provenance, demo flag)."""
    return {
        "id": receipt.id,
        "requestId": receipt.request_id,
        "providerId": receipt.provider_id,
        "actionScope": receipt.action_scope.value,
        "lifecycle": receipt.lifecycle.value,
        "outcome": {
            "state": truth_state_of(receipt.outcome.state),
            "value": _jsonable(receipt.outcome.value),
            "detail": receipt.outcome.detail,
        },
        "w9DecisionId": receipt.w9_decision_id,
        "w7AssuranceId": receipt.w7_assurance_id,
        "sourceRevision": receipt.source_revision,
        "provenanceRevision": receipt.provenance_revision,
        "baseGraphId": receipt.base_graph_id,
        "baseGraphRevision": receipt.base_graph_revision,
        "environment": receipt.environment,
        "startedAt": receipt.started_at,
        "finishedAt": receipt.finished_at,
        "sideEffects": [
            {
                "kind": s.kind.value,
                "target": s.target,
                "detail": s.detail,
            }
            for s in receipt.side_effects
        ],
        "stdoutRef": receipt.stdout_ref,
        "stderrRef": receipt.stderr_ref,
        "logRef": receipt.log_ref,
        "changedRevisions": list(receipt.changed_revisions),
        "rollbackReference": (
            {
                "reference": receipt.rollback_reference.reference,
                "evidenceIds": list(receipt.rollback_reference.evidence_ids),
                "detail": receipt.rollback_reference.detail,
            }
            if receipt.rollback_reference is not None
            else None
        ),
        "demo": receipt.provider_id == "demo",
    }


def execution_status_from_receipt(receipt: ExecutionReceipt) -> str:
    """The wire ``status`` of an execution: the receipt's outcome truth state
    (terminal lifecycle states map 1:1 onto the six-state vocabulary)."""
    return truth_state_of(receipt.outcome.state)


def receipt_from_payload(payload: dict[str, Any]) -> ExecutionReceipt:
    """Reconstruct a domain receipt from its serialized payload (used by the
    execution registries when re-driving the substrate)."""
    from sos.execution import (
        ExecutionActionScope,
        ExecutionLifecycleState,
        RollbackReference,
        SideEffect,
        SideEffectKind,
    )

    rollback = payload.get("rollbackReference")
    return ExecutionReceipt(
        request_id=payload["requestId"],
        provider_id=payload["providerId"],
        action_scope=ExecutionActionScope(payload["actionScope"]),
        lifecycle=ExecutionLifecycleState(payload["lifecycle"]),
        outcome=TruthfulValue(
            TruthState(payload["outcome"]["state"]),
            _dejsonable(payload["outcome"].get("value")),
            payload["outcome"].get("detail"),
        ),
        w9_decision_id=payload["w9DecisionId"],
        source_revision=payload["sourceRevision"],
        provenance_revision=payload["provenanceRevision"],
        base_graph_id=payload["baseGraphId"],
        base_graph_revision=payload["baseGraphRevision"],
        environment=payload["environment"],
        started_at=payload.get("startedAt"),
        finished_at=payload.get("finishedAt"),
        side_effects=tuple(
            SideEffect(
                kind=SideEffectKind(s["kind"]),
                target=s["target"],
                detail=s["detail"],
            )
            for s in payload.get("sideEffects", ())
        ),
        stdout_ref=payload.get("stdoutRef"),
        stderr_ref=payload.get("stderrRef"),
        log_ref=payload.get("logRef"),
        changed_revisions=tuple(payload.get("changedRevisions", ())),
        rollback_reference=(
            RollbackReference(
                reference=rollback["reference"],
                evidence_ids=tuple(rollback["evidenceIds"]),
                detail=rollback["detail"],
            )
            if rollback
            else None
        ),
        w7_assurance_id=payload.get("w7AssuranceId"),
    )


# ---------------------------------------------------------------------------
# Wire rows → domain registries (for the W11 substrate dispatch)
# ---------------------------------------------------------------------------


def decision_row_to_autonomy(row: dict[str, Any]) -> AutonomyDecision:
    """Map a persisted decision row → ``sos.autonomy.AutonomyDecision``.

    The row's ``authority_snapshot`` is the authoritative recorded snapshot
    (policy id, promotion binding, reasons) — mapped verbatim.
    """
    snap = row["authority_snapshot"]
    return AutonomyDecision(
        id=row["id"],
        state=AutonomyDecisionState(snap.get("autonomyState", row["action"])),
        action=DecisionAction(snap.get("requestedAction", row["action"])),
        rationale=row["rationale"],
        reasons=tuple(snap.get("reasons", ())),
        evidence_ids=tuple(row["evidence_refs"]),
        assurance_id=snap.get("assuranceId", ""),
        experiment_id=snap.get("experimentId"),
        promotion_id=snap.get("promotionId"),
        policy_id=snap["policyId"],
        traceability=traceability_from_payload(snap.get("traceability", {})),
    )


def assurance_row_to_result(row: dict[str, Any]) -> AssuranceResult:
    """Map a persisted assurance row → ``sos.assurance.AssuranceResult``."""
    dom = row["checks"].get("domain", {}) if isinstance(
        row.get("checks"), dict
    ) else {}
    gate_rows = row["checks"].get("gates", row["checks"]) if isinstance(
        row.get("checks"), dict
    ) else row.get("checks", ())
    gates = tuple(
        AssuranceGate(
            name=g["name"],
            status=AssuranceStatus(g["status"]),
            evidence_ids=tuple(g.get("evidenceIds", ())),
            detail=g["detail"],
        )
        for g in gate_rows
    )
    impact_data = dom.get("impact", {})
    impact = ImpactAnalysis(
        affected_node_ids=tuple(impact_data.get("affectedNodeIds", ())),
        affected_edge_ids=tuple(impact_data.get("affectedEdgeIds", ())),
        boundary_interface_ids=tuple(impact_data.get("boundaryInterfaceIds", ())),
        dependency_reach=tuple(impact_data.get("dependencyReach", ())),
        blast_radius=BlastRadius(
            level=impact_data.get("blastRadius", {}).get("level", "limited"),
            affected_count=impact_data.get("blastRadius", {}).get(
                "affectedCount", 0
            ),
            detail=impact_data.get("blastRadius", {}).get("detail", ""),
        ),
    )
    risk_data = dom.get("risk", {})
    risk = RiskAssessment(
        items=tuple(
            RiskItem(
                name=r["name"],
                severity=r.get("severity", "medium"),
                uncertainty=TruthfulValue(
                    TruthState(r.get("uncertainty", {}).get("state", "UNKNOWN")),
                    _dejsonable(r.get("uncertainty", {}).get("value")),
                    r.get("uncertainty", {}).get("detail"),
                ),
                mitigation=r.get("mitigation"),
                residual=r.get("residual"),
            )
            for r in risk_data.get("items", ())
        )
    )
    rev_data = dom.get("reversibility", {})
    reversibility = ReversibilityAssessment(
        rollback_available=rev_data.get("rollbackAvailable", False),
        detail=rev_data.get("detail", ""),
        rollback_evidence_ids=tuple(rev_data.get("rollbackEvidenceIds", ())),
        containment_policy_ref=rev_data.get("containmentPolicyRef"),
    )
    return AssuranceResult(
        id=row["id"],
        candidate_id=row["candidate_id"],
        base_graph_id=dom.get("baseGraphId", ""),
        base_graph_revision=dom.get("baseGraphRevision", ""),
        provenance_revision=dom.get("provenanceRevision", ""),
        status=AssuranceStatus(row["verdict"]),
        gates=gates,
        impact=impact,
        risk=risk,
        reversibility=reversibility,
        objectives=tuple(dom.get("objectives", ())),
        traceability=traceability_from_payload(
            dom.get("traceability", {}) or {}
        ),
    )


def experiment_row_to_domain(row: dict[str, Any]) -> Experiment:
    """Map a persisted experiment row → ``sos.experimentation.Experiment``."""
    dom = row["events"]["domain"]
    from sos.experimentation import ExperimentMode, StopCondition

    return Experiment(
        id=row["id"],
        candidate_id=row["candidate_id"],
        assurance_result_id=dom["assuranceResultId"],
        base_graph_id=dom["baseGraphId"],
        base_graph_revision=dom["baseGraphRevision"],
        provenance_revision=dom["provenanceRevision"],
        mode=ExperimentMode(dom.get("mode", "canary")),
        scope=tuple(dom.get("scope", ())),
        observation_window=tuple(dom.get("observationWindow", ("", ""))),
        success_criteria=tuple(dom.get("successCriteria", ())),
        stop_conditions=tuple(
            StopCondition(
                name=s["name"],
                threshold=s["threshold"],
                metric=s["metric"],
            )
            for s in dom.get("stopConditions", ())
        ),
        rollback_ref=dom["rollbackRef"],
        traceability=traceability_from_payload(dom.get("traceability", {})),
        state=ExperimentState(row["status"]),
        containment_policy_ref=dom.get("containmentPolicyRef"),
    )


# ---------------------------------------------------------------------------
# The governed execution dispatch (the W11 substrate through the API)
# ---------------------------------------------------------------------------


def build_execution_request(
    *,
    intent: str,
    provider_id: str,
    source_revision: str,
    provenance_revision: str,
    base_graph_id: str,
    base_graph_revision: str,
    environment: str,
    w9_decision_id: str,
    w7_assurance_id: str,
    w8_experiment_id: str,
    rollback_reference: dict[str, Any] | None,
    traceability: Traceability,
    workspace_ref: str | None = None,
) -> ExecutionRequest:
    rollback = (
        RollbackReference(
            reference=rollback_reference["reference"],
            evidence_ids=tuple(rollback_reference["evidenceIds"]),
            detail=rollback_reference["detail"],
        )
        if rollback_reference
        else None
    )
    return ExecutionRequest(
        intent=intent,
        action_scope=_scope_for_intent(intent),
        provider_id=provider_id,
        source_revision=source_revision,
        provenance_revision=provenance_revision,
        base_graph_id=base_graph_id,
        base_graph_revision=base_graph_revision,
        environment=environment,
        w9_decision_id=w9_decision_id,
        traceability=traceability,
        w7_assurance_id=w7_assurance_id,
        w8_experiment_id=w8_experiment_id,
        workspace_ref=workspace_ref,
        rollback_reference=rollback,
    )


def _scope_for_intent(intent: str) -> Any:
    from sos.execution import ExecutionActionScope

    if intent.startswith("rollback"):
        return ExecutionActionScope.ROLLBACK
    if intent.startswith("observe"):
        return ExecutionActionScope.OBSERVE
    return ExecutionActionScope.DEPLOY


def submit_governed_execution(
    *,
    providers: dict[str, Any],
    known_decisions: dict[str, AutonomyDecision],
    known_assurance: dict[str, AssuranceResult],
    known_experiments: dict[str, Experiment],
    request: ExecutionRequest,
) -> ExecutionReceipt:
    """Submit through the W11 substrate: authority gates (W9 resolution,
    scope state, provider-not-authorizer, chain equality, W7 PASS, W8 chain,
    rollback binding) reject BEFORE any provider call."""
    substrate = ExecutionSubstrate(
        providers=providers,
        known_decisions=known_decisions,
        known_assurance=known_assurance,
        known_experiments=known_experiments,
    )
    return substrate.submit(request)


def receipt_evidence_wire(
    receipt: ExecutionReceipt,
    *,
    traceability: Traceability,
) -> tuple[Evidence, str]:
    """Convert a receipt → W4 evidence (observed, not inferred) and report
    the WIRE kind the evidence record classifies under."""
    ev = receipt_to_w4_evidence(receipt, traceability=traceability)
    wire_kind = DOMAIN_TO_WIRE_EVIDENCE_KIND[ev.kind.value]
    return ev, wire_kind


def ask_payload_domain_to_wire(ask: AskPayload) -> dict[str, Any]:
    return {
        "decision": ask.exact_decision,
        "alternatives": list(ask.alternatives),
        "evidenceQuality": ask.evidence_quality,
        "uncertainty": ask.uncertainty,
        "tradeoffs": list(ask.trade_offs),
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return str(value)


def _dejsonable(value: Any) -> Any:
    return value


def content_hash(parts: tuple[str, ...]) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
