"""W9 — autonomy + ASK + human authority boundary for SOS.

Makes autonomy explicit, policy-governed, reversible, explainable, and
subordinate to human authority (frozen W9 Work Order; architecture §§4.8–4.9,
5, 12–13).

Design invariants:

- autonomy is **policy-governed**: actions may only be considered within the
  policy's declared ``allowed_actions`` and bounded by ``PolicyCeiling`` scope/
  risk/blast-radius/reversibility constraints (C1, C6);
- the decision state machine distinguishes ``GATHER_EVIDENCE``, ``EXPERIMENT``,
  ``ACT``, ``ASK``, ``REJECT``, ``ROLLBACK`` — no implicit action from candidate
  generation, assurance, or experiment completion (C2);
- ``ASK`` is mandatory when authority is ambiguous, scope is unsafe, or a policy
  boundary is unresolved; no silent inference of user authorization (C3);
- ACT requires W7 PASS assurance + W8 promotion + W9 policy authorization;
  W7 PASS is **non-authorizing** — it cannot be treated as an authorization token
  (C4);
- UNKNOWN/FAILED/UNAVAILABLE/UNSUPPORTED truth states remain distinct and can
  force GATHER_EVIDENCE, ASK, REJECT, or ROLLBACK; confidence alone cannot
  authorize (C5);
- every decision records rationale, traceability, policy refs, upstream assurance/
  experiment references, evidence ids, and uncertainty outcomes (C7, C9);
- rollback decisions consume W8 governed recovery and cannot claim success
  without evidence (C8);
- W9 is non-authority: no W10 platform/personalization, no W7/W8 re-export (C12).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any, TYPE_CHECKING

from .model import ModelValidationError, Traceability, TruthState, TruthfulValue, DecisionAction

if TYPE_CHECKING:
    from .assurance import AssuranceResult
    from .experimentation import Experiment, ExperimentEvaluation, PromotionDecision, RollbackPath
    from .evidence import Evidence


# ---------------------------------------------------------------------------
# Frozen vocabulary
# ---------------------------------------------------------------------------


class AutonomyDecisionState(str, Enum):
    """Decision states (architecture §4.8 + W9 Work Order C2)."""

    GATHER_EVIDENCE = "GATHER_EVIDENCE"
    EXPERIMENT = "EXPERIMENT"
    ACT = "ACT"
    ASK = "ASK"
    REJECT = "REJECT"
    ROLLBACK = "ROLLBACK"


# ---------------------------------------------------------------------------
# Policy ceiling + autonomy request (policy)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyCeiling:
    """Bounded policy ceilings: scope, risk, blast radius, reversibility, confidence."""

    max_risk: float
    max_blast_radius: str
    require_reversible: bool
    min_confidence: float
    require_human_approval_for_act: bool

    def __post_init__(self) -> None:
        if not 0.0 <= self.max_risk <= 1.0:
            raise ModelValidationError("PolicyCeiling.max_risk must be within [0, 1]")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ModelValidationError("PolicyCeiling.min_confidence must be within [0, 1]")
        if self.max_blast_radius not in ("none", "limited", "service", "system", "organization"):
            raise ModelValidationError(f"PolicyCeiling.max_blast_radius '{self.max_blast_radius}' is not a known level")


_BLAST_ORDER: dict[str, int] = {"none": 0, "limited": 1, "service": 2, "system": 3, "organization": 4}


def _blast_rank(level: str) -> int | None:
    """Return the blast-radius rank, or None for unknown levels (SOS-W9-F10)."""
    return _BLAST_ORDER.get(level)


@dataclass(frozen=True)
class AutonomyRequest:
    """A structured, bounded, traceable autonomy policy (C1).

    ``allowed_actions`` declares which DecisionActions this policy may consider.
    ``ceilings`` bound the scope. The policy cannot authorize beyond its declared
    scope/ceilings.
    """

    id: str
    version: int
    allowed_actions: tuple[Any, ...]  # tuple of DecisionAction
    ceilings: PolicyCeiling
    traceability: Traceability

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not self.id.strip():
            raise ModelValidationError("AutonomyRequest.id is required")
        if self.version < 1:
            raise ModelValidationError("AutonomyRequest.version must be >= 1")
        if not self.allowed_actions:
            raise ModelValidationError("AutonomyRequest.allowed_actions is required")
        # SOS-W9-F07: every allowed action must be a real DecisionAction enum member.
        for a in self.allowed_actions:
            if not isinstance(a, DecisionAction):
                raise ModelValidationError(
                    f"AutonomyRequest.allowed_actions contains a non-DecisionAction value: {a!r}"
                )
        self.ceilings.__post_init__()
        self.traceability.validate(require_value=True, require_context=True)

    def is_action_allowed(self, action: Any) -> bool:
        """Check if a DecisionAction is within the policy's declared allowed_actions."""
        return action in self.allowed_actions


# ---------------------------------------------------------------------------
# Autonomy decision (explainable, deterministic, traceable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AutonomyDecision:
    """A deterministic, explainable autonomy decision (C9).

    Records rationale, reasons, evidence ids, assurance/experiment references,
    policy reference, and W1 traceability. Carries no authorization flag beyond
    its state — the state IS the authorization outcome (ACT = authorized to act;
    ASK = human authority required; etc.).
    """

    id: str
    state: AutonomyDecisionState
    action: Any  # the DecisionAction that was evaluated
    rationale: str
    reasons: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    assurance_id: str
    experiment_id: str | None
    promotion_id: str | None
    policy_id: str
    traceability: Traceability

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", _decision_id(self))
        self.validate()

    def validate(self) -> None:
        if not isinstance(self.state, AutonomyDecisionState):
            raise ModelValidationError("AutonomyDecision.state must be an AutonomyDecisionState")
        if not self.rationale.strip():
            raise ModelValidationError("AutonomyDecision.rationale is required")
        if not self.reasons:
            raise ModelValidationError("AutonomyDecision.reasons is required")
        if not self.policy_id.strip():
            raise ModelValidationError("AutonomyDecision.policy_id is required")
        self.traceability.validate(require_value=True, require_context=True)


def _decision_id(d: AutonomyDecision) -> str:
    """Content-addressed identity for the autonomy decision."""
    material = "|".join([
        d.state.value, str(d.action), d.assurance_id,
        d.experiment_id or "", d.promotion_id or "", d.policy_id,
        ",".join(d.evidence_ids), d.rationale,
    ])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"autonomy-{digest}"


# ---------------------------------------------------------------------------
# Autonomy evaluation engine (deterministic, bounded, non-authorizing beyond scope)
# ---------------------------------------------------------------------------


def evaluate_autonomy(
    *,
    policy: AutonomyRequest,
    action: Any,  # DecisionAction
    assurance: "AssuranceResult | None",
    experiment: "Experiment | None",
    promotion: "PromotionDecision | None",
    evaluation: "ExperimentEvaluation | None" = None,
    evidence_ids: tuple[str, ...],
    traceability: Traceability,
    known_evidence: dict[str, "Evidence"] | None = None,
    human_authority_present: bool = False,
    blast_radius: str = "limited",
    rollback_path: "RollbackPath | None" = None,
    risk: float = 0.0,
    confidence: float = 0.0,
    reversible: bool = True,
) -> AutonomyDecision:
    """Evaluate an autonomy decision deterministically (C2–C10).

    Returns an ``AutonomyDecision`` with the appropriate state:
    - ``ACT``: all gates passed (policy allows, assurance PASS, promotion promoted,
      evidence SUCCESS, ceilings satisfied, human authority present if required);
    - ``ASK``: authority ambiguous, scope unsafe, or policy boundary unresolved;
    - ``REJECT``: explicit policy rejection (action not allowed, hard violation);
    - ``ROLLBACK``: rollback action with governed recovery evidence;
    - ``GATHER_EVIDENCE``: evidence insufficient (UNKNOWN/missing);
    - ``EXPERIMENT``: action is EXPERIMENT (deferred to W8 lifecycle).

    W7 assurance is **non-authorizing**: PASS alone does not authorize ACT.
    """
    policy.validate()
    reasons: list[str] = []
    state = AutonomyDecisionState.ASK  # default: ask

    # SOS-W9-F11/F16: validate numeric domains for risk and confidence (bool rejected explicitly).
    if isinstance(risk, bool) or not isinstance(risk, (int, float)) or not 0.0 <= risk <= 1.0:
        raise ModelValidationError(f"risk must be a number within [0, 1], got {risk!r}")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
        raise ModelValidationError(f"confidence must be a number within [0, 1], got {confidence!r}")

    # C1: is the action within the policy's declared allowed_actions?
    if not policy.is_action_allowed(action):
        state = AutonomyDecisionState.REJECT
        reasons.append(f"action {action.value} is not in policy.allowed_actions")
        return AutonomyDecision(
            id="", state=state, action=action,
            rationale=f"action {action.value} not authorized by policy {policy.id}",
            reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
            assurance_id=assurance.id if assurance else "",
            experiment_id=experiment.id if experiment else None,
            promotion_id=None, policy_id=policy.id,
            traceability=traceability,
        )

    # C3: if human approval is required for ACT and not present -> ASK
    if action.value == "ACT" and policy.ceilings.require_human_approval_for_act and not human_authority_present:
        state = AutonomyDecisionState.ASK
        reasons.append("policy requires human approval for ACT; no human authority present")
        return AutonomyDecision(
            id="", state=state, action=action,
            rationale="human authority required for ACT; ASK",
            reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
            assurance_id=assurance.id if assurance else "",
            experiment_id=experiment.id if experiment else None,
            promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
            policy_id=policy.id, traceability=traceability,
        )

    # C6: blast radius exceeding ceiling -> ASK (SOS-W9-F10: unknown values route to ASK)
    br_rank = _blast_rank(blast_radius)
    ceiling_rank = _blast_rank(policy.ceilings.max_blast_radius)
    if br_rank is None or ceiling_rank is None:
        state = AutonomyDecisionState.ASK
        reasons.append(f"blast radius '{blast_radius}' is not a known level; ASK")
        return AutonomyDecision(
            id="", state=state, action=action,
            rationale="unknown blast radius level; ASK for human scope resolution",
            reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
            assurance_id=assurance.id if assurance else "",
            experiment_id=experiment.id if experiment else None,
            promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
            policy_id=policy.id, traceability=traceability,
        )
    if br_rank > ceiling_rank:
        state = AutonomyDecisionState.ASK
        reasons.append(f"blast radius '{blast_radius}' exceeds policy ceiling '{policy.ceilings.max_blast_radius}'")
        return AutonomyDecision(
            id="", state=state, action=action,
            rationale="blast radius exceeds policy ceiling; ASK for human scope resolution",
            reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
            assurance_id=assurance.id if assurance else "",
            experiment_id=experiment.id if experiment else None,
            promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
            policy_id=policy.id, traceability=traceability,
        )

    # SOS-W9-F01: enforce policy ceilings (risk, reversibility, confidence).
    if risk > policy.ceilings.max_risk:
        state = AutonomyDecisionState.ASK
        reasons.append(f"risk {risk} exceeds policy ceiling {policy.ceilings.max_risk}")
        return AutonomyDecision(
            id="", state=state, action=action,
            rationale="risk exceeds policy ceiling; ASK for human authority",
            reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
            assurance_id=assurance.id if assurance else "",
            experiment_id=experiment.id if experiment else None,
            promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
            policy_id=policy.id, traceability=traceability,
        )
    if policy.ceilings.require_reversible and not reversible:
        state = AutonomyDecisionState.ASK
        reasons.append("policy requires reversibility; action is not reversible")
        return AutonomyDecision(
            id="", state=state, action=action,
            rationale="action not reversible; policy requires reversibility; ASK",
            reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
            assurance_id=assurance.id if assurance else "",
            experiment_id=experiment.id if experiment else None,
            promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
            policy_id=policy.id, traceability=traceability,
        )
    if confidence < policy.ceilings.min_confidence:
        state = AutonomyDecisionState.ASK
        reasons.append(f"confidence {confidence} below policy floor {policy.ceilings.min_confidence}")
        return AutonomyDecision(
            id="", state=state, action=action,
            rationale="confidence below policy floor; ASK",
            reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
            assurance_id=assurance.id if assurance else "",
            experiment_id=experiment.id if experiment else None,
            promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
            policy_id=policy.id, traceability=traceability,
        )

    # Handle ROLLBACK specifically (C8) — SOS-W9-F03: require verifiable evidence + ref binding
    if action.value == "ROLLBACK":
        if rollback_path is None:
            state = AutonomyDecisionState.ASK
            reasons.append("rollback action without governed rollback path; ASK")
            return AutonomyDecision(
                id="", state=state, action=action,
                rationale="rollback requires governed recovery evidence; ASK",
                reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                assurance_id=assurance.id if assurance else "",
                experiment_id=experiment.id if experiment else None,
                promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
                policy_id=policy.id, traceability=traceability,
            )
        # SOS-W9-F12: ROLLBACK requires a governed experiment context.
        if experiment is None:
            state = AutonomyDecisionState.ASK
            reasons.append("ROLLBACK requires a governed experiment context; no experiment supplied")
            return AutonomyDecision(
                id="", state=state, action=action,
                rationale="ROLLBACK without experiment context; ASK",
                reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                assurance_id=assurance.id if assurance else "",
                experiment_id=None,
                promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
                policy_id=policy.id, traceability=traceability,
            )
        # SOS-W9-F12: rollback_path.reference must match experiment.rollback_ref.
        if experiment.rollback_ref and rollback_path.reference != experiment.rollback_ref:
            state = AutonomyDecisionState.ASK
            reasons.append(f"rollback_path.reference '{rollback_path.reference}' does not match experiment.rollback_ref '{experiment.rollback_ref}'")
            return AutonomyDecision(
                id="", state=state, action=action,
                rationale="rollback reference mismatch; ASK",
                reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                assurance_id=assurance.id if assurance else "",
                experiment_id=experiment.id if experiment else None,
                promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
                policy_id=policy.id, traceability=traceability,
            )
        # SOS-W9-F03: known_evidence is REQUIRED (not optional) for rollback validation.
        if known_evidence is None:
            state = AutonomyDecisionState.ASK
            reasons.append("rollback requires a verifiable evidence store; no known_evidence supplied")
            return AutonomyDecision(
                id="", state=state, action=action,
                rationale="rollback requires verifiable evidence store; ASK",
                reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                assurance_id=assurance.id if assurance else "",
                experiment_id=experiment.id if experiment else None,
                promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
                policy_id=policy.id, traceability=traceability,
            )
        # Validate all rollback evidence is SUCCESS
        for eid in rollback_path.evidence_ids:
            ev = known_evidence.get(eid)
            if ev is None:
                state = AutonomyDecisionState.ASK
                reasons.append(f"rollback evidence '{eid}' not found in known_evidence; ASK")
                return AutonomyDecision(
                    id="", state=state, action=action,
                    rationale="rollback evidence not found; ASK",
                    reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                    assurance_id=assurance.id if assurance else "",
                    experiment_id=experiment.id if experiment else None,
                    promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
                    policy_id=policy.id, traceability=traceability,
                )
            if ev.result.state != TruthState.SUCCESS:
                state = AutonomyDecisionState.ASK
                reasons.append(f"rollback evidence '{eid}' state is {ev.result.state.value}; ASK")
                return AutonomyDecision(
                    id="", state=state, action=action,
                    rationale=f"rollback evidence {ev.result.state.value}; ASK",
                    reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                    assurance_id=assurance.id if assurance else "",
                    experiment_id=experiment.id if experiment else None,
                    promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
                    policy_id=policy.id, traceability=traceability,
                )
        state = AutonomyDecisionState.ROLLBACK
        reasons.append("rollback action with governed recovery evidence")
        return AutonomyDecision(
            id="", state=state, action=action,
            rationale="rollback authorized by policy with governed recovery evidence",
            reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
            assurance_id=assurance.id if assurance else "",
            experiment_id=experiment.id if experiment else None,
            promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
            policy_id=policy.id, traceability=traceability,
        )

    # Handle EXPERIMENT — deferred to W8 lifecycle
    if action.value == "EXPERIMENT":
        state = AutonomyDecisionState.EXPERIMENT
        reasons.append("experiment action deferred to W8 lifecycle")
        return AutonomyDecision(
            id="", state=state, action=action,
            rationale="experiment lifecycle governed by W8",
            reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
            assurance_id=assurance.id if assurance else "",
            experiment_id=experiment.id if experiment else None,
            promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
            policy_id=policy.id, traceability=traceability,
        )

    # Handle GATHER_EVIDENCE
    if action.value == "GATHER_EVIDENCE":
        state = AutonomyDecisionState.GATHER_EVIDENCE
        reasons.append("gather evidence action")
        return AutonomyDecision(
            id="", state=state, action=action,
            rationale="evidence gathering authorized by policy",
            reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
            assurance_id=assurance.id if assurance else "",
            experiment_id=experiment.id if experiment else None,
            promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
            policy_id=policy.id, traceability=traceability,
        )

    # For ACT: C4 — require W7 PASS assurance + W8 experiment/promotion/evaluation + full chain
    if action.value == "ACT":
        # SOS-W9-F08: ACT requires a supplied Experiment (W8 lifecycle subordinate).
        if experiment is None:
            state = AutonomyDecisionState.ASK
            reasons.append("ACT requires a governed experiment context; no experiment supplied")
            return AutonomyDecision(
                id="", state=state, action=action,
                rationale="ACT without experiment context; ASK",
                reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                assurance_id=assurance.id if assurance else "",
                experiment_id=None,
                promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
                policy_id=policy.id, traceability=traceability,
            )
        # SOS-W9-F13: ACT requires an ExperimentEvaluation (not optional).
        if evaluation is None:
            state = AutonomyDecisionState.ASK
            reasons.append("ACT requires an ExperimentEvaluation; no evaluation supplied")
            return AutonomyDecision(
                id="", state=state, action=action,
                rationale="ACT without evaluation; ASK",
                reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                assurance_id=assurance.id if assurance else "",
                experiment_id=experiment.id,
                promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
                policy_id=policy.id, traceability=traceability,
            )
        # SOS-W9-F14: ACT requires the experiment to be in COMPLETED lifecycle state.
        if experiment.state.value != "completed":
            state = AutonomyDecisionState.REJECT
            reasons.append(f"experiment state is {experiment.state.value}, not COMPLETED; ACT requires lifecycle completion")
            return AutonomyDecision(
                id="", state=state, action=action,
                rationale=f"experiment not COMPLETED ({experiment.state.value}); REJECT",
                reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                assurance_id=assurance.id if assurance else "",
                experiment_id=experiment.id,
                promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
                policy_id=policy.id, traceability=traceability,
            )
        # SOS-W9-F13: validate promotion.evaluation_id == evaluation.id.
        if promotion is not None and promotion.evaluation_id != evaluation.id:
            state = AutonomyDecisionState.REJECT
            reasons.append(f"promotion.evaluation_id '{promotion.evaluation_id}' does not match evaluation.id '{evaluation.id}'")
            return AutonomyDecision(
                id="", state=state, action=action,
                rationale="promotion not bound to the exact evaluation; REJECT",
                reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                assurance_id=assurance.id if assurance else "",
                experiment_id=experiment.id,
                promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
                policy_id=policy.id, traceability=traceability,
            )
        if assurance is None:
            state = AutonomyDecisionState.ASK
            reasons.append("no assurance result supplied for ACT; ASK")
            return AutonomyDecision(
                id="", state=state, action=action,
                rationale="ACT requires assurance; ASK",
                reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                assurance_id="", experiment_id=experiment.id if experiment else None,
                promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
                policy_id=policy.id, traceability=traceability,
            )
        # C4: W7 PASS is non-authorizing — PASS alone is not an authorization token.
        if assurance.status.value != "PASS":
            state = AutonomyDecisionState.REJECT
            reasons.append(f"assurance status is {assurance.status.value}, not PASS; REJECT")
            return AutonomyDecision(
                id="", state=state, action=action,
                rationale=f"assurance {assurance.status.value} cannot authorize ACT; REJECT",
                reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                assurance_id=assurance.id,
                experiment_id=experiment.id if experiment else None,
                promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
                policy_id=policy.id, traceability=traceability,
            )
        # C4: W8 promotion required
        if promotion is None or not promotion.promoted:
            state = AutonomyDecisionState.ASK
            reasons.append("ACT requires a promoted W8 PromotionDecision; not promoted")
            return AutonomyDecision(
                id="", state=state, action=action,
                rationale="promotion not granted; ASK for human authority",
                reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                assurance_id=assurance.id,
                experiment_id=experiment.id if experiment else None,
                promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
                policy_id=policy.id, traceability=traceability,
            )
        # SOS-W9-F02: validate the complete W7→W8 authorization chain.
        # promotion must belong to the exact experiment and assurance/candidate/graph/revision/provenance.
        if experiment is not None and promotion.experiment_id != experiment.id:
            state = AutonomyDecisionState.REJECT
            reasons.append(f"promotion.experiment_id '{promotion.experiment_id}' does not match experiment '{experiment.id}'")
            return AutonomyDecision(
                id="", state=state, action=action,
                rationale="promotion not bound to the exact experiment; REJECT",
                reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                assurance_id=assurance.id,
                experiment_id=experiment.id,
                promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id),
                policy_id=policy.id, traceability=traceability,
            )
        # experiment is guaranteed non-None (F08 check above)
        # Validate experiment ↔ assurance chain
        if experiment.assurance_result_id != assurance.id:
                state = AutonomyDecisionState.REJECT
                reasons.append(f"experiment.assurance_result_id '{experiment.assurance_result_id}' does not match assurance '{assurance.id}'")
                return AutonomyDecision(
                    id="", state=state, action=action,
                    rationale="experiment not bound to the exact assurance; REJECT",
                    reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                    assurance_id=assurance.id, experiment_id=experiment.id,
                    promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id),
                    policy_id=policy.id, traceability=traceability,
                )
        if experiment.candidate_id != assurance.candidate_id:
                state = AutonomyDecisionState.REJECT
                reasons.append("experiment.candidate_id does not match assurance.candidate_id")
                return AutonomyDecision(
                    id="", state=state, action=action,
                    rationale="experiment/assurance candidate chain mismatch; REJECT",
                    reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                    assurance_id=assurance.id, experiment_id=experiment.id,
                    promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id),
                    policy_id=policy.id, traceability=traceability,
                )
        if experiment.base_graph_id != assurance.base_graph_id:
                state = AutonomyDecisionState.REJECT
                reasons.append("experiment.base_graph_id does not match assurance.base_graph_id")
                return AutonomyDecision(
                    id="", state=state, action=action,
                    rationale="experiment/assurance graph chain mismatch; REJECT",
                    reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                    assurance_id=assurance.id, experiment_id=experiment.id,
                    promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id),
                    policy_id=policy.id, traceability=traceability,
                )
        if experiment.base_graph_revision != assurance.base_graph_revision:
                state = AutonomyDecisionState.REJECT
                reasons.append("experiment.base_graph_revision does not match assurance.base_graph_revision")
                return AutonomyDecision(
                    id="", state=state, action=action,
                    rationale="experiment/assurance revision chain mismatch; REJECT",
                    reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                    assurance_id=assurance.id, experiment_id=experiment.id,
                    promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id),
                    policy_id=policy.id, traceability=traceability,
                )
        if experiment.provenance_revision != assurance.provenance_revision:
                state = AutonomyDecisionState.REJECT
                reasons.append("experiment.provenance_revision does not match assurance.provenance_revision")
                return AutonomyDecision(
                    id="", state=state, action=action,
                    rationale="experiment/assurance provenance chain mismatch; REJECT",
                    reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                    assurance_id=assurance.id, experiment_id=experiment.id,
                    promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id),
                    policy_id=policy.id, traceability=traceability,
                )

        # SOS-W9-F09: validate the ExperimentEvaluation against the exact experiment/assurance chain.
        if evaluation is not None:
            if evaluation.experiment_id != experiment.id:
                state = AutonomyDecisionState.REJECT
                reasons.append(f"evaluation.experiment_id '{evaluation.experiment_id}' does not match experiment '{experiment.id}'")
                return AutonomyDecision(
                    id="", state=state, action=action,
                    rationale="evaluation not bound to the exact experiment; REJECT",
                    reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                    assurance_id=assurance.id, experiment_id=experiment.id,
                    promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id),
                    policy_id=policy.id, traceability=traceability,
                )
            if evaluation.assurance_result_id != assurance.id:
                state = AutonomyDecisionState.REJECT
                reasons.append("evaluation.assurance_result_id does not match assurance.id")
                return AutonomyDecision(
                    id="", state=state, action=action,
                    rationale="evaluation/assurance chain mismatch; REJECT",
                    reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                    assurance_id=assurance.id, experiment_id=experiment.id,
                    promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id),
                    policy_id=policy.id, traceability=traceability,
                )
            if evaluation.candidate_id != experiment.candidate_id:
                state = AutonomyDecisionState.REJECT
                reasons.append("evaluation.candidate_id does not match experiment.candidate_id")
                return AutonomyDecision(
                    id="", state=state, action=action,
                    rationale="evaluation/experiment candidate chain mismatch; REJECT",
                    reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                    assurance_id=assurance.id, experiment_id=experiment.id,
                    promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id),
                    policy_id=policy.id, traceability=traceability,
                )
            if evaluation.base_graph_id != experiment.base_graph_id or evaluation.base_graph_revision != experiment.base_graph_revision:
                state = AutonomyDecisionState.REJECT
                reasons.append("evaluation graph/revision does not match experiment")
                return AutonomyDecision(
                    id="", state=state, action=action,
                    rationale="evaluation/experiment graph chain mismatch; REJECT",
                    reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                    assurance_id=assurance.id, experiment_id=experiment.id,
                    promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id),
                    policy_id=policy.id, traceability=traceability,
                )
            if evaluation.provenance_revision != experiment.provenance_revision:
                state = AutonomyDecisionState.REJECT
                reasons.append("evaluation.provenance_revision does not match experiment.provenance_revision")
                return AutonomyDecision(
                    id="", state=state, action=action,
                    rationale="evaluation/experiment provenance chain mismatch; REJECT",
                    reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                    assurance_id=assurance.id, experiment_id=experiment.id,
                    promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id),
                    policy_id=policy.id, traceability=traceability,
                )

        # SOS-W9-F04: ACT requires a non-empty evidence set.
        if not evidence_ids:
            state = AutonomyDecisionState.GATHER_EVIDENCE
            reasons.append("ACT requires non-empty evidence; no evidence_ids supplied")
            return AutonomyDecision(
                id="", state=state, action=action,
                rationale="no evidence supplied; GATHER_EVIDENCE",
                reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                assurance_id=assurance.id,
                experiment_id=experiment.id if experiment else None,
                promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id),
                policy_id=policy.id, traceability=traceability,
            )
        # SOS-W9-F15: ACT evidence_ids must match the evaluation's evidence_ids exactly.
        if set(evidence_ids) != set(evaluation.evidence_ids):
            state = AutonomyDecisionState.REJECT
            reasons.append("ACT evidence_ids do not match evaluation.evidence_ids")
            return AutonomyDecision(
                id="", state=state, action=action,
                rationale="evidence set mismatch with W8 evaluation; REJECT",
                reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                assurance_id=assurance.id,
                experiment_id=experiment.id if experiment else None,
                promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id),
                policy_id=policy.id, traceability=traceability,
            )
        # SOS-W9-F04/F05: known_evidence is REQUIRED; every referenced record must resolve to SUCCESS.
        if known_evidence is None:
            state = AutonomyDecisionState.GATHER_EVIDENCE
            reasons.append("ACT requires a verifiable evidence store; no known_evidence supplied")
            return AutonomyDecision(
                id="", state=state, action=action,
                rationale="no evidence store supplied; GATHER_EVIDENCE",
                reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                assurance_id=assurance.id,
                experiment_id=experiment.id if experiment else None,
                promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id),
                policy_id=policy.id, traceability=traceability,
            )
        for eid in evidence_ids:
            ev = known_evidence.get(eid)
            if ev is None:
                state = AutonomyDecisionState.GATHER_EVIDENCE
                reasons.append(f"evidence '{eid}' not found in known_evidence; GATHER_EVIDENCE")
                return AutonomyDecision(
                    id="", state=state, action=action,
                    rationale=f"missing evidence '{eid}'; GATHER_EVIDENCE",
                    reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                    assurance_id=assurance.id,
                    experiment_id=experiment.id if experiment else None,
                    promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id),
                    policy_id=policy.id, traceability=traceability,
                )
            # SOS-W9-F05: preserve the specific W4 truth state in the reason.
            if ev.result.state != TruthState.SUCCESS:
                state = AutonomyDecisionState.GATHER_EVIDENCE
                reasons.append(f"evidence '{eid}' state is {ev.result.state.value}; GATHER_EVIDENCE")
                return AutonomyDecision(
                    id="", state=state, action=action,
                    rationale=f"evidence state {ev.result.state.value}; GATHER_EVIDENCE",
                    reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
                    assurance_id=assurance.id,
                    experiment_id=experiment.id if experiment else None,
                    promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id),
                    policy_id=policy.id, traceability=traceability,
                )

        # All gates passed: ACT
        state = AutonomyDecisionState.ACT
        reasons.append("policy allows action")
        reasons.append("assurance PASS")
        reasons.append("promotion granted")
        reasons.append("ceilings satisfied")
        return AutonomyDecision(
            id="", state=state, action=action,
            rationale="ACT authorized: policy + assurance PASS + promotion + ceilings + evidence",
            reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
            assurance_id=assurance.id,
            experiment_id=experiment.id if experiment else None,
            promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
            policy_id=policy.id, traceability=traceability,
        )

    # Fallback: unknown action
    state = AutonomyDecisionState.ASK
    reasons.append(f"unhandled action {action.value}; ASK")
    return AutonomyDecision(
        id="", state=state, action=action,
        rationale=f"unhandled action {action.value}; ASK",
        reasons=tuple(reasons), evidence_ids=tuple(evidence_ids),
        assurance_id=assurance.id if assurance else "",
        experiment_id=experiment.id if experiment else None,
        promotion_id=(promotion.experiment_id + ":" + promotion.evaluation_id) if promotion else None,
        policy_id=policy.id, traceability=traceability,
    )
