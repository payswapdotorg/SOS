"""W9 explicit authority and autonomous decision policy boundary."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Sequence

from .model import ModelValidationError, Traceability


class AuthorityAction(str, Enum):
    ACT = "ACT"
    EXPERIMENT = "EXPERIMENT"
    GATHER_EVIDENCE = "GATHER_EVIDENCE"
    ASK = "ASK"


class EvidenceQuality(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class AuthorityGrant:
    id: str
    owner: str
    action: AuthorityAction
    environment: str
    min_confidence: float
    max_risk: float
    max_impact: float
    max_blast_radius: float
    require_reversible: bool
    allow_gather_evidence: bool
    gather_min_confidence: float
    gather_max_risk: float
    gather_max_blast_radius: float
    require_human_approval: bool
    valid_from: str
    valid_until: str | None
    traceability: Traceability

    def validate(self) -> None:
        if not all((self.id, self.owner, self.environment, self.valid_from)):
            raise ModelValidationError("AuthorityGrant requires identity, owner, environment and validity start")
        for name, value in (
            ("min_confidence", self.min_confidence),
            ("max_risk", self.max_risk),
            ("max_impact", self.max_impact),
            ("max_blast_radius", self.max_blast_radius),
            ("gather_min_confidence", self.gather_min_confidence),
            ("gather_max_risk", self.gather_max_risk),
            ("gather_max_blast_radius", self.gather_max_blast_radius),
        ):
            if not 0 <= value <= 1:
                raise ModelValidationError(f"{name} must be within [0, 1]")
        if self.valid_until is not None and self.valid_until < self.valid_from:
            raise ModelValidationError("valid_until must not precede valid_from")
        self.traceability.validate()


@dataclass(frozen=True)
class DecisionRequest:
    action: AuthorityAction
    environment: str
    confidence: float
    calibration: str
    evidence_quality: EvidenceQuality
    risk: float
    impact: float
    reversible: bool
    blast_radius: float
    decision_ref: str
    traceability: Traceability

    def validate(self) -> None:
        if not self.environment or not self.calibration or not self.decision_ref:
            raise ModelValidationError("DecisionRequest requires environment, calibration and decision_ref")
        for name, value in (("confidence", self.confidence), ("risk", self.risk), ("impact", self.impact), ("blast_radius", self.blast_radius)):
            if not 0 <= value <= 1:
                raise ModelValidationError(f"{name} must be within [0, 1]")
        self.traceability.validate()


@dataclass(frozen=True)
class AskPayload:
    exact_decision: str
    alternatives: tuple[str, ...]
    evidence_quality: EvidenceQuality
    uncertainty: str
    trade_offs: tuple[str, ...]

    def validate(self) -> None:
        if not self.exact_decision or not self.alternatives or not self.uncertainty or not self.trade_offs:
            raise ModelValidationError("ASK requires decision, alternatives, uncertainty and trade-offs")


@dataclass(frozen=True)
class AuthorityDecision:
    id: str
    request_ref: str
    requested_action: AuthorityAction
    outcome: AuthorityAction
    grant_ref: str | None
    rationale: str
    calibration: str
    evidence_quality: EvidenceQuality
    ask: AskPayload | None
    traceability: Traceability

    def validate(self) -> None:
        if not self.id or not self.request_ref or not self.rationale:
            raise ModelValidationError("AuthorityDecision requires identity, request and rationale")
        if self.outcome == AuthorityAction.ASK:
            if self.ask is None:
                raise ModelValidationError("ASK outcome requires AskPayload")
            self.ask.validate()
        elif self.ask is not None:
            raise ModelValidationError("Only ASK decisions may contain AskPayload")
        self.traceability.validate()


class AuthorityLedger:
    """Append-only authority decision history."""

    def __init__(self) -> None:
        self._records: list[AuthorityDecision] = []

    def append(self, decision: AuthorityDecision) -> None:
        decision.validate()
        if any(record.id == decision.id for record in self._records):
            raise ModelValidationError(f"AuthorityDecision id already exists: {decision.id}")
        self._records.append(decision)

    def records(self) -> tuple[AuthorityDecision, ...]:
        return tuple(self._records)

    def export_json(self, path: str | Path) -> None:
        payload = [
            {
                "id": record.id,
                "request_ref": record.request_ref,
                "requested_action": record.requested_action.value,
                "outcome": record.outcome.value,
                "grant_ref": record.grant_ref,
                "rationale": record.rationale,
                "calibration": record.calibration,
                "evidence_quality": record.evidence_quality.value,
                "ask": None if record.ask is None else {
                    "exact_decision": record.ask.exact_decision,
                    "alternatives": list(record.ask.alternatives),
                    "evidence_quality": record.ask.evidence_quality.value,
                    "uncertainty": record.ask.uncertainty,
                    "trade_offs": list(record.ask.trade_offs),
                },
            }
            for record in sorted(self._records, key=lambda value: value.id)
        ]
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _quality_score(quality: EvidenceQuality) -> float:
    return {
        EvidenceQuality.HIGH: 1.0,
        EvidenceQuality.MEDIUM: 0.67,
        EvidenceQuality.LOW: 0.33,
        EvidenceQuality.UNKNOWN: 0.0,
        EvidenceQuality.UNAVAILABLE: 0.0,
    }[quality]


def _ask(request: DecisionRequest, grant: AuthorityGrant | None, reason: str, alternatives: Sequence[str]) -> AuthorityDecision:
    payload = AskPayload(
        exact_decision=request.decision_ref,
        alternatives=tuple(alternatives),
        evidence_quality=request.evidence_quality,
        uncertainty=reason,
        trade_offs=("autonomy versus risk", "evidence sufficiency versus delay"),
    )
    return AuthorityDecision(
        id=f"decision:{request.decision_ref}",
        request_ref=request.decision_ref,
        requested_action=request.action,
        outcome=AuthorityAction.ASK,
        grant_ref=None if grant is None else grant.id,
        rationale=reason,
        calibration=request.calibration,
        evidence_quality=request.evidence_quality,
        ask=payload,
        traceability=request.traceability,
    )


def evaluate(request: DecisionRequest, grants: Sequence[AuthorityGrant]) -> AuthorityDecision:
    """Evaluate explicit grants; insufficient authority always escalates to ASK."""
    request.validate()
    for grant in grants:
        grant.validate()
    matches = [g for g in grants if g.action == request.action and g.environment == request.environment]
    grant = matches[0] if matches else None
    if grant is None:
        return _ask(request, None, "no authority grant covers this action/environment", ("authorize", "do not authorize"))
    if grant.require_human_approval:
        return _ask(request, grant, "grant requires human approval", ("approve", "reject"))
    if request.risk > grant.max_risk or request.impact > grant.max_impact or request.blast_radius > grant.max_blast_radius:
        return _ask(request, grant, "requested action exceeds granted risk, impact, or blast-radius boundary", ("accept risk", "choose safer alternative"))
    if grant.require_reversible and not request.reversible:
        return _ask(request, grant, "granted action requires reversibility", ("approve exception", "choose reversible alternative"))
    evidence_ok = _quality_score(request.evidence_quality) >= grant.min_confidence
    confidence_ok = request.confidence >= grant.min_confidence
    if not (evidence_ok and confidence_ok):
        if grant.allow_gather_evidence and request.risk <= grant.gather_max_risk and request.blast_radius <= grant.gather_max_blast_radius and request.confidence >= grant.gather_min_confidence:
            return AuthorityDecision(
                id=f"decision:{request.decision_ref}", request_ref=request.decision_ref, requested_action=request.action,
                outcome=AuthorityAction.GATHER_EVIDENCE, grant_ref=grant.id,
                rationale="confidence or evidence quality is below the action threshold; gather more evidence",
                calibration=request.calibration, evidence_quality=request.evidence_quality, ask=None, traceability=request.traceability,
            )
        return _ask(request, grant, "confidence/evidence quality is insufficient for autonomous action", ("gather evidence", "approve manually"))
    return AuthorityDecision(
        id=f"decision:{request.decision_ref}", request_ref=request.decision_ref, requested_action=request.action,
        outcome=request.action, grant_ref=grant.id, rationale="explicit authority and policy bounds satisfied",
        calibration=request.calibration, evidence_quality=request.evidence_quality, ask=None, traceability=request.traceability,
    )
