"""W7 trusted assurance boundary for candidate evaluation."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Mapping, Sequence

from .evidence import EvidenceMode, EvidenceRecord, EvidenceKind
from .search import CandidateState
from .model import ModelValidationError, Traceability, TruthState


class CheckKind(str, Enum):
    STATIC_ANALYSIS = "STATIC_ANALYSIS"
    TEST = "TEST"
    REPLAY = "REPLAY"
    SIMULATION = "SIMULATION"
    IMPACT = "IMPACT"
    RISK = "RISK"


class CheckState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_RUN = "NOT_RUN"


class AssuranceVerdict(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class ImpactAssessment:
    blast_radius: float
    affected_nodes: tuple[str, ...]
    user_impact: float
    operational_impact: float

    def validate(self) -> None:
        for name, value in (("blast_radius", self.blast_radius), ("user_impact", self.user_impact), ("operational_impact", self.operational_impact)):
            if not 0 <= value <= 1:
                raise ModelValidationError(f"{name} must be within [0, 1]")
        if not self.affected_nodes:
            raise ModelValidationError("ImpactAssessment requires affected nodes")


@dataclass(frozen=True)
class RiskAssessment:
    risk: float
    safety_constraints: tuple[str, ...]
    rollback_required: bool
    residual_risk: float

    def validate(self) -> None:
        for name, value in (("risk", self.risk), ("residual_risk", self.residual_risk)):
            if not 0 <= value <= 1:
                raise ModelValidationError(f"{name} must be within [0, 1]")
        if self.rollback_required and not self.safety_constraints:
            raise ModelValidationError("Rollback-required risk assessment must name safety constraints")


@dataclass(frozen=True)
class AssuranceCheck:
    id: str
    kind: CheckKind
    state: CheckState
    description: str
    evidence_refs: tuple[str, ...]
    source_revision: str

    def validate(self) -> None:
        if not self.id or not self.description or not self.source_revision:
            raise ModelValidationError("AssuranceCheck requires id, description and source_revision")
        if self.state == CheckState.PASS and not self.evidence_refs:
            raise ModelValidationError("PASS assurance checks require evidence references")


@dataclass(frozen=True)
class AssurancePolicy:
    id: str
    version: int
    required_checks: tuple[CheckKind, ...]
    max_risk: float
    max_blast_radius: float
    max_residual_risk: float
    traceability: Traceability

    def validate(self) -> None:
        if not self.id or self.version < 1:
            raise ModelValidationError("AssurancePolicy requires id and version >= 1")
        for name, value in (("max_risk", self.max_risk), ("max_blast_radius", self.max_blast_radius), ("max_residual_risk", self.max_residual_risk)):
            if not 0 <= value <= 1:
                raise ModelValidationError(f"{name} must be within [0, 1]")
        if not self.required_checks:
            raise ModelValidationError("AssurancePolicy requires at least one required check")
        self.traceability.validate()


@dataclass(frozen=True)
class AssuranceResult:
    candidate_ref: str
    base_system_state_ref: str
    checks: tuple[AssuranceCheck, ...]
    impact: ImpactAssessment
    risk: RiskAssessment
    verdict: AssuranceVerdict
    reasons: tuple[str, ...]
    traceability: Traceability

    def validate(self, policy: AssurancePolicy) -> None:
        policy.validate()
        if not self.candidate_ref or not self.base_system_state_ref:
            raise ModelValidationError("AssuranceResult requires candidate and base system references")
        self.impact.validate()
        self.risk.validate()
        for check in self.checks:
            check.validate()
        if self.verdict == AssuranceVerdict.PASS and self.reasons:
            raise ModelValidationError("Passing assurance must not report blocking reasons")
        self.traceability.validate(require_value=True, require_context=True)


def _evidence_supports_check(check: AssuranceCheck, evidence: Mapping[str, EvidenceRecord]) -> bool:
    if check.state != CheckState.PASS:
        return False
    if not check.evidence_refs:
        return False
    records = [evidence.get(ref) for ref in check.evidence_refs]
    return all(record is not None and record.result.state == TruthState.SUCCESS for record in records)


def assure_candidate(
    *,
    candidate: CandidateState,
    checks: Sequence[AssuranceCheck],
    impact: ImpactAssessment,
    risk: RiskAssessment,
    policy: AssurancePolicy,
    evidence: Mapping[str, EvidenceRecord],
) -> AssuranceResult:
    """Evaluate assurance gates without mutating or promoting the candidate."""
    candidate.validate(candidate.replacement_graph if hasattr(candidate, "replacement_graph") else _candidate_graph(candidate))
    policy.validate()
    impact.validate()
    risk.validate()
    reasons: list[str] = []
    by_kind: dict[CheckKind, list[AssuranceCheck]] = {}
    for check in checks:
        check.validate()
        by_kind.setdefault(check.kind, []).append(check)
        if check.state == CheckState.PASS and not _evidence_supports_check(check, evidence):
            reasons.append(f"check {check.id} is PASS without successful evidence")
    for required in policy.required_checks:
        available = by_kind.get(required, [])
        if not any(check.state == CheckState.PASS and _evidence_supports_check(check, evidence) for check in available):
            reasons.append(f"required check {required.value} is not successfully evidenced")
    if risk.risk > policy.max_risk:
        reasons.append("risk exceeds assurance policy")
    if impact.blast_radius > policy.max_blast_radius:
        reasons.append("blast radius exceeds assurance policy")
    if risk.residual_risk > policy.max_residual_risk:
        reasons.append("residual risk exceeds assurance policy")
    verdict = AssuranceVerdict.PASS if not reasons else AssuranceVerdict.BLOCK
    result = AssuranceResult(candidate.id, candidate.base_system_state_ref, tuple(checks), impact, risk, verdict, tuple(reasons), candidate.traceability)
    result.validate(policy)
    return result


def _candidate_graph(candidate: CandidateState):
    """W6 replacement validation is normally performed before assurance."""
    class _GraphProxy:
        id = candidate.replacement.base_graph_ref
        nodes = ()
    # A real ArchitectureGraph is supplied by callers in normal use. This proxy
    # is intentionally not used for graph semantics; W6 validation remains the gate.
    return _GraphProxy()


def export_assurance(result: AssuranceResult, path: str | Path) -> None:
    payload = {
        "candidate_ref": result.candidate_ref,
        "base_system_state_ref": result.base_system_state_ref,
        "checks": [
            {"id": check.id, "kind": check.kind.value, "state": check.state.value, "description": check.description, "evidence_refs": list(check.evidence_refs), "source_revision": check.source_revision}
            for check in result.checks
        ],
        "impact": {"blast_radius": result.impact.blast_radius, "affected_nodes": list(result.impact.affected_nodes), "user_impact": result.impact.user_impact, "operational_impact": result.impact.operational_impact},
        "risk": {"risk": result.risk.risk, "safety_constraints": list(result.risk.safety_constraints), "rollback_required": result.risk.rollback_required, "residual_risk": result.risk.residual_risk},
        "verdict": result.verdict.value,
        "reasons": list(result.reasons),
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
