"""W1 mission/value/context domain model for SOS.

The module deliberately contains only W1 semantics. It has no runtime
architecture, telemetry, search, experimentation, or promotion behavior.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any, Generic, Mapping, Sequence, TypeVar
from uuid import uuid4


class ModelValidationError(ValueError):
    """Raised when a W1 model violates an invariant."""


class MissionStatus(str, Enum):
    DRAFT = "DRAFT"
    PROPOSED_REVISION = "PROPOSED_REVISION"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class RevisionStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ConstraintClass(str, Enum):
    HARD = "HARD"
    SOFT = "SOFT"
    RISK = "RISK"
    PREFERENCE = "PREFERENCE"


class DecisionAction(str, Enum):
    ACT = "ACT"
    EXPERIMENT = "EXPERIMENT"
    GATHER_EVIDENCE = "GATHER_EVIDENCE"
    ASK = "ASK"
    REJECT = "REJECT"
    ROLLBACK = "ROLLBACK"


class TruthState(str, Enum):
    SUCCESS = "SUCCESS"
    EMPTY = "EMPTY"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"
    UNAVAILABLE = "UNAVAILABLE"


class ContextDimension(str, Enum):
    USER = "USER"
    COHORT = "COHORT"
    DEVICE = "DEVICE"
    PLATFORM = "PLATFORM"
    ENVIRONMENT = "ENVIRONMENT"
    WORKLOAD = "WORKLOAD"
    GEOGRAPHY = "GEOGRAPHY"
    TIME = "TIME"
    REGULATORY = "REGULATORY"
    CUSTOM = "CUSTOM"


T = TypeVar("T")


@dataclass(frozen=True)
class Traceability:
    """Authority and semantic ownership references for a W1 artifact."""

    constitution_ref: str
    mission_ref: str
    value_model_ref: str | None = None
    context_ref: str | None = None

    def validate(self, *, require_value: bool = False, require_context: bool = False) -> None:
        for name, value in (("constitution_ref", self.constitution_ref), ("mission_ref", self.mission_ref)):
            if not value:
                raise ModelValidationError(f"{name} is required")
        if require_value and not self.value_model_ref:
            raise ModelValidationError("value_model_ref is required")
        if require_context and not self.context_ref:
            raise ModelValidationError("context_ref is required")


@dataclass(frozen=True)
class MissionRevision:
    version: int
    statement: str
    status: RevisionStatus
    proposed_by: str
    decided_by: str | None
    reason: str
    created_at: str


@dataclass(frozen=True)
class Mission:
    id: str
    version: int
    authority: str
    statement: str
    goals: tuple[str, ...]
    desired_outcomes: tuple[str, ...]
    stakeholders: tuple[str, ...]
    measures: tuple[str, ...]
    assumptions: tuple[str, ...]
    ambiguities: tuple[str, ...]
    status: MissionStatus
    parent_version: int | None
    history: tuple[MissionRevision, ...]
    traceability: Traceability

    def validate(self) -> None:
        if not self.id or not self.authority or not self.statement.strip():
            raise ModelValidationError("Mission requires id, authority and statement")
        if self.version < 1:
            raise ModelValidationError("Mission version must be >= 1")
        if self.parent_version is not None and self.parent_version >= self.version:
            raise ModelValidationError("Mission parent_version must be lower than version")
        if any(rev.version > self.version for rev in self.history):
            raise ModelValidationError("Mission history cannot contain a future revision")
        self.traceability.validate()

    def propose_revision(self, *, statement: str, proposed_by: str, reason: str, created_at: str) -> "Mission":
        self.validate()
        if not statement.strip():
            raise ModelValidationError("Proposed mission statement cannot be empty")
        revision = MissionRevision(
            version=self.version + 1,
            statement=statement,
            status=RevisionStatus.PROPOSED,
            proposed_by=proposed_by,
            decided_by=None,
            reason=reason,
            created_at=created_at,
        )
        return Mission(
            id=self.id,
            version=self.version + 1,
            authority=self.authority,
            statement=statement,
            goals=self.goals,
            desired_outcomes=self.desired_outcomes,
            stakeholders=self.stakeholders,
            measures=self.measures,
            assumptions=self.assumptions,
            ambiguities=self.ambiguities,
            status=MissionStatus.PROPOSED_REVISION,
            parent_version=self.version,
            history=self.history + (revision,),
            traceability=self.traceability,
        )

    def approve_revision(self, *, approver: str) -> "Mission":
        self.validate()
        if self.status != MissionStatus.PROPOSED_REVISION or not self.history:
            raise ModelValidationError("Only an explicit proposed mission revision can be approved")
        if not approver or approver != self.authority:
            raise ModelValidationError("Mission revision requires the mission authority")
        last = self.history[-1]
        approved = MissionRevision(
            version=last.version,
            statement=last.statement,
            status=RevisionStatus.APPROVED,
            proposed_by=last.proposed_by,
            decided_by=approver,
            reason=last.reason,
            created_at=last.created_at,
        )
        data = asdict(self)
        data["status"] = MissionStatus.ACTIVE
        data["history"] = self.history[:-1] + (approved,)
        return Mission(**data)


@dataclass(frozen=True)
class Constraint:
    id: str
    name: str
    class_: ConstraintClass
    description: str
    hard: bool
    traceability: Traceability

    def validate(self) -> None:
        if not self.id or not self.name or not self.description.strip():
            raise ModelValidationError("Constraint requires id, name and description")
        if self.hard != (self.class_ == ConstraintClass.HARD):
            raise ModelValidationError("hard flag must agree with constraint class")
        self.traceability.validate(require_value=True)


@dataclass(frozen=True)
class Objective:
    id: str
    description: str
    priority: int
    traceability: Traceability

    def validate(self) -> None:
        if not self.id or not self.description.strip() or self.priority < 0:
            raise ModelValidationError("Objective requires id, description and non-negative priority")
        self.traceability.validate(require_value=True)


@dataclass(frozen=True)
class Incentive:
    id: str
    description: str
    traceability: Traceability

    def validate(self) -> None:
        if not self.id or not self.description.strip():
            raise ModelValidationError("Incentive requires id and description")
        self.traceability.validate(require_value=True)


@dataclass(frozen=True)
class Opportunity:
    id: str
    description: str
    traceability: Traceability

    def validate(self) -> None:
        if not self.id or not self.description.strip():
            raise ModelValidationError("Opportunity requires id and description")
        self.traceability.validate(require_value=True)


@dataclass(frozen=True)
class ValueModel:
    id: str
    version: int
    business_model: Mapping[str, Any]
    economic_objectives: tuple[Objective, ...]
    budgets: Mapping[str, float]
    incentives: tuple[Incentive, ...]
    opportunities: tuple[Opportunity, ...]
    constraints: tuple[Constraint, ...]
    traceability: Traceability

    def validate(self) -> None:
        if not self.id or self.version < 1:
            raise ModelValidationError("ValueModel requires id and version >= 1")
        self.traceability.validate(require_value=True)
        for item in (*self.economic_objectives, *self.incentives, *self.opportunities, *self.constraints):
            item.validate()
        if any(value < 0 for value in self.budgets.values()):
            raise ModelValidationError("Budgets cannot be negative")


@dataclass(frozen=True)
class TruthfulValue(Generic[T]):
    state: TruthState
    value: T | None = None
    detail: str | None = None

    def validate(self) -> None:
        if self.state == TruthState.SUCCESS and self.value is None:
            raise ModelValidationError("SUCCESS requires a value")
        if self.state != TruthState.SUCCESS and self.value is not None:
            raise ModelValidationError("Non-success truth states must not masquerade as a value")
        if self.state in (TruthState.FAILED, TruthState.UNKNOWN, TruthState.UNAVAILABLE, TruthState.UNSUPPORTED) and not self.detail:
            raise ModelValidationError(f"{self.state.value} requires an explanatory detail")


@dataclass(frozen=True)
class ContextValue:
    dimension: ContextDimension
    key: str
    value: TruthfulValue[Any]

    def validate(self) -> None:
        if not self.key:
            raise ModelValidationError("Context value key is required")
        self.value.validate()


@dataclass(frozen=True)
class Context:
    id: str
    version: int
    values: tuple[ContextValue, ...]
    traceability: Traceability

    def validate(self) -> None:
        if not self.id or self.version < 1:
            raise ModelValidationError("Context requires id and version >= 1")
        self.traceability.validate(require_context=True)
        for item in self.values:
            item.validate()


@dataclass(frozen=True)
class AutonomyRule:
    action: DecisionAction
    environment: str
    min_confidence: float
    max_risk: float
    require_reversible: bool
    max_blast_radius: float
    require_human_approval: bool

    def validate(self) -> None:
        if not self.environment:
            raise ModelValidationError("Autonomy rule requires environment")
        for field_name, value in (("min_confidence", self.min_confidence), ("max_risk", self.max_risk), ("max_blast_radius", self.max_blast_radius)):
            if not 0 <= value <= 1:
                raise ModelValidationError(f"{field_name} must be within [0, 1]")
        if self.action == DecisionAction.ASK and not self.require_human_approval:
            raise ModelValidationError("ASK rules require human approval")


@dataclass(frozen=True)
class AutonomyPolicy:
    id: str
    version: int
    rules: tuple[AutonomyRule, ...]
    traceability: Traceability

    def validate(self) -> None:
        if not self.id or self.version < 1:
            raise ModelValidationError("AutonomyPolicy requires id and version >= 1")
        self.traceability.validate()
        for rule in self.rules:
            rule.validate()

    def authorize(
        self,
        *,
        action: DecisionAction,
        environment: str,
        confidence: float,
        risk: float,
        reversible: bool,
        blast_radius: float,
    ) -> bool:
        self.validate()
        matches = [r for r in self.rules if r.action == action and r.environment == environment]
        if not matches:
            return False
        return any(
            confidence >= r.min_confidence
            and risk <= r.max_risk
            and blast_radius <= r.max_blast_radius
            and (reversible or not r.require_reversible)
            and not r.require_human_approval
            for r in matches
        )


@dataclass(frozen=True)
class AskPayload:
    exact_decision: str
    alternatives: tuple[str, ...]
    evidence_quality: str
    uncertainty: str
    trade_offs: tuple[str, ...]

    def validate(self) -> None:
        if not self.exact_decision.strip() or not self.alternatives:
            raise ModelValidationError("ASK requires an exact decision and alternatives")
        if not self.evidence_quality.strip() or not self.uncertainty.strip():
            raise ModelValidationError("ASK requires evidence quality and uncertainty")
        if not self.trade_offs:
            raise ModelValidationError("ASK requires trade-offs")


@dataclass(frozen=True)
class Decision:
    id: str
    action: DecisionAction
    authority_ref: str
    confidence: float
    calibration: str
    risk: float
    evidence_refs: tuple[str, ...]
    ask: AskPayload | None
    mission_ref: str
    value_model_ref: str | None
    context_ref: str | None

    def validate(self) -> None:
        if not self.id or not self.authority_ref or not self.mission_ref:
            raise ModelValidationError("Decision requires id, authority_ref and mission_ref")
        if not 0 <= self.confidence <= 1 or not 0 <= self.risk <= 1:
            raise ModelValidationError("Decision confidence and risk must be within [0, 1]")
        if self.action == DecisionAction.ASK:
            if self.ask is None:
                raise ModelValidationError("ASK requires an ask payload")
            self.ask.validate()
        elif self.ask is not None:
            raise ModelValidationError("Only ASK decisions may contain an ask payload")


def decide(
    *,
    requested_action: DecisionAction,
    environment: str,
    confidence: float,
    calibration: str,
    risk: float,
    reversible: bool,
    blast_radius: float,
    policy: AutonomyPolicy,
    authority_ref: str,
    mission_ref: str,
    value_model_ref: str | None = None,
    context_ref: str | None = None,
    evidence_refs: Sequence[str] = (),
    ask: AskPayload | None = None,
) -> Decision:
    """Apply the W1 authority boundary: insufficient authority becomes ASK."""
    permitted = requested_action != DecisionAction.ASK and policy.authorize(
        action=requested_action,
        environment=environment,
        confidence=confidence,
        risk=risk,
        reversible=reversible,
        blast_radius=blast_radius,
    )
    action = requested_action if permitted else DecisionAction.ASK
    if action == DecisionAction.ASK and ask is None:
        raise ModelValidationError("Insufficient authority requires a complete ASK payload")
    decision = Decision(
        id=str(uuid4()),
        action=action,
        authority_ref=authority_ref,
        confidence=confidence,
        calibration=calibration,
        risk=risk,
        evidence_refs=tuple(evidence_refs),
        ask=ask if action == DecisionAction.ASK else None,
        mission_ref=mission_ref,
        value_model_ref=value_model_ref,
        context_ref=context_ref,
    )
    decision.validate()
    return decision


def _convert_for_json(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(k): _convert_for_json(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_convert_for_json(v) for v in value]
    if hasattr(value, "__dataclass_fields__"):
        return {k: _convert_for_json(v) for k, v in asdict(value).items()}
    return value


class JsonModelStore:
    """Small deterministic JSON persistence boundary for W1 artifacts."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def save(self, artifact: Any) -> None:
        payload = _convert_for_json(artifact)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def load(self) -> Any:
        return json.loads(self.path.read_text(encoding="utf-8"))
