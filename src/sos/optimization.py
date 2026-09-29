"""W12 — brownfield optimization loop orchestrator for SOS (first bounded slice).

Composes the already-merged authorities into one deterministic, bounded,
fully-traceable governed cycle over a RECOVERED EXTERNAL system:

    recovered system state (W3)
      -> candidate proposal (W6, W5-informed)
      -> assurance gate (W7)
      -> governed experiment (W8)
      -> autonomy decision gate (W9: ACT / ASK / REJECT)
      -> promotion or governed rollback (W8)
      -> evidence recording at every consequential step (W4, verbatim)

The loop is a simulation-level composition in this slice: it operates on
models and injected port objects (deterministic stub evaluators), never on
running production systems. SOS remains every authority; the loop only
orchestrates.

Design invariants (frozen W12 Work Order `spec/work-orders/W12-optimization-loop.md`):

- composition only: the loop orchestrates the real W3/W4/W5/W6/W7/W8/W9(/W11)
  types and never redefines an authority (C1). Every cross-authority reference
  is chain-checked at the record boundary (``OptimizationRun.validate``);
- W9 gates every consequential step: experiment launch, promotion, and
  rollback each consume a resolved W9 decision; an ASK decision PAUSES the
  loop with an explicit pending-authorization record (never a silent default,
  never an auto-approve — a pending record has no resolution-granting code
  path); REJECT terminates the iteration as refused (C2);
- W7-before-W8 ordering: an experiment is unconstructible through the loop
  boundary (``governed_experiment``) without a PASS assurance result bound to
  the exact candidate/graph/revision/provenance chain (C3);
- promotion requires the W8 ``PromotionGate`` decision plus a W9 ACT decision;
  every DEPLOY-class promotion carries a bounded W8 ``RollbackPath`` bound to
  the experiment's rollback reference; stop conditions are W8
  ``StopCondition``-typed and a fired hard stop terminates the loop; rollback
  is itself W9-governed (C4);
- verbatim W4 evidence: every consequential step appends evidence through the
  existing W4 vocabulary and ingestion path — observed artifacts only, no new
  evidence kinds, nothing inferred recorded as observed (C5);
- deterministic and bounded: a fixed caller-supplied max-iteration bound,
  candidates ordered by content-addressed id (stable, deduplicated), a
  clock-free core (timestamps are caller-supplied data), and identical inputs
  produce identical content-addressed loop records (C6);
- FAILED / UNKNOWN / UNAVAILABLE / UNSUPPORTED stay distinct end-to-end: the
  appended W4 evidence records and the iteration records preserve the exact
  truth states; none collapses to a favorable value (C7);
- model-only safety: no running system, no side effects outside the model;
  the optional W11 seam dispatches governed DEPLOY steps through the real
  ``ExecutionSubstrate`` port against injected stub providers (C8);
- loop records round-trip through the W1 ``JsonModelStore``; no new
  persistence authority (C9);
- bounded authority surface: no successor-stage symbols, no self-modification
  of SOS's own sources (the loop targets recovered EXTERNAL systems only), no
  duplicate authority; W12 exports only through ``sos`` (C10).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .model import ModelValidationError, Traceability, TruthState, TruthfulValue, DecisionAction
from .recovery import RecoveryResult
from .evidence import Evidence, EvidenceGraph, EvidenceKind, EvidenceProvenance, _build_evidence
from .causal import CausalHypothesis, CausalKnowledgeGraph
from .candidates import CandidateProposal, MutationKind
from .assurance import AssuranceResult, AssuranceStatus, assure_candidate
from .experimentation import (
    Experiment,
    ExperimentEvaluation,
    ExperimentMode,
    ExperimentState,
    PromotionDecision,
    PromotionGate,
    RollbackPath,
    StopCondition,
    evaluate_experiment,
    transition_experiment,
)
from .autonomy import AutonomyDecision, AutonomyDecisionState, AutonomyRequest, evaluate_autonomy
from .execution import (
    ExecutionActionScope,
    ExecutionProviderPort,
    ExecutionReceipt,
    ExecutionRequest,
    ExecutionSubstrate,
    RollbackReference,
    receipt_to_w4_evidence,
)


# ---------------------------------------------------------------------------
# Error authority (anchored in the W1 validation-error family — no new error
# authority is introduced)
# ---------------------------------------------------------------------------


class OptimizationContractError(ModelValidationError):
    """Raised when the W12 loop contract is violated at a boundary."""


# ---------------------------------------------------------------------------
# Governed iteration lifecycle (deterministic state machine; no free-form
# narrative transitions — Work Order required outcome 2)
# ---------------------------------------------------------------------------


class IterationOutcome(str, Enum):
    """Iteration lifecycle states; terminal members are the iteration outcomes.

    Non-terminal members (PROPOSED .. DECIDED) are the deterministic phases an
    iteration advances through; terminal members are the recorded outcomes of
    a finished loop's iterations.
    """

    PROPOSED = "proposed"
    ASSURED = "assured"
    EXPERIMENTED = "experimented"
    EVALUATED = "evaluated"
    DECIDED = "decided"
    # terminal outcomes
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled-back"
    PAUSED_PENDING_AUTHORIZATION = "paused-pending-authorization"
    REFUSED = "refused"
    STOPPED_BY_CONDITION = "stopped-by-condition"
    GATHER_EVIDENCE = "gather-evidence"
    ASSURANCE_NOT_PASSED = "assurance-not-passed"


#: Terminal iteration outcomes (the only ones lawful in a finished loop record).
ITERATION_TERMINAL_OUTCOMES: frozenset[IterationOutcome] = frozenset({
    IterationOutcome.PROMOTED,
    IterationOutcome.ROLLED_BACK,
    IterationOutcome.PAUSED_PENDING_AUTHORIZATION,
    IterationOutcome.REFUSED,
    IterationOutcome.STOPPED_BY_CONDITION,
    IterationOutcome.GATHER_EVIDENCE,
    IterationOutcome.ASSURANCE_NOT_PASSED,
})

# Valid direct transitions FROM -> {allowed TO states}. Terminal outcomes have
# no outgoing transitions: an iteration never leaves its terminal outcome.
_VALID_ITERATION_TRANSITIONS: dict[IterationOutcome, frozenset[IterationOutcome]] = {
    IterationOutcome.PROPOSED: frozenset({
        IterationOutcome.ASSURED, IterationOutcome.ASSURANCE_NOT_PASSED,
    }),
    IterationOutcome.ASSURED: frozenset({
        IterationOutcome.EXPERIMENTED, IterationOutcome.REFUSED,
        IterationOutcome.PAUSED_PENDING_AUTHORIZATION,
    }),
    IterationOutcome.EXPERIMENTED: frozenset({
        IterationOutcome.EVALUATED,
    }),
    IterationOutcome.EVALUATED: frozenset({
        IterationOutcome.DECIDED, IterationOutcome.STOPPED_BY_CONDITION,
    }),
    IterationOutcome.DECIDED: frozenset({
        IterationOutcome.PROMOTED, IterationOutcome.ROLLED_BACK,
        IterationOutcome.PAUSED_PENDING_AUTHORIZATION, IterationOutcome.REFUSED,
        IterationOutcome.GATHER_EVIDENCE,
    }),
}


def validate_iteration_transition(
    from_outcome: IterationOutcome,
    to_outcome: IterationOutcome,
) -> None:
    """Validate an iteration lifecycle transition against the frozen machine.

    Raises ``OptimizationContractError`` for invalid transitions.
    """
    if not isinstance(from_outcome, IterationOutcome):
        raise OptimizationContractError(
            f"from_outcome must be an IterationOutcome, got {from_outcome!r}"
        )
    if not isinstance(to_outcome, IterationOutcome):
        raise OptimizationContractError(
            f"to_outcome must be an IterationOutcome, got {to_outcome!r}"
        )
    allowed = _VALID_ITERATION_TRANSITIONS.get(from_outcome, frozenset())
    if to_outcome not in allowed:
        raise OptimizationContractError(
            f"invalid iteration transition: {from_outcome.value} -> {to_outcome.value}"
        )


# ---------------------------------------------------------------------------
# Pending authorization (the explicit ASK pause record — never auto-approved)
# ---------------------------------------------------------------------------


class AuthorizationResolution(str, Enum):
    """The resolution state of a pending authorization. PENDING is the only
    member: this slice provides no code path that resolves a pending record —
    approval would require a fresh W9 decision under human authority."""

    PENDING = "pending"


@dataclass(frozen=True)
class PendingAuthorization:
    """An explicit pending-authorization pause record (W9 ASK).

    Constructed only from a real W9 ``AutonomyDecision`` whose state is ASK.
    The record is frozen with ``resolution == PENDING`` and exposes no method
    that grants, mints, or upgrades authorization: the loop can never
    auto-approve its own pause.
    """

    iteration_index: int
    decision_id: str
    decision_state: AutonomyDecisionState
    requested_action: str
    rationale: str
    reasons: tuple[str, ...]
    resolution: AuthorizationResolution = AuthorizationResolution.PENDING
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", _pending_id(self))
        self.validate()

    def validate(self) -> None:
        if not isinstance(self.iteration_index, int) or self.iteration_index < 1:
            raise OptimizationContractError("PendingAuthorization.iteration_index must be a positive integer")
        if not self.decision_id.strip():
            raise OptimizationContractError("PendingAuthorization.decision_id is required")
        if not isinstance(self.decision_state, AutonomyDecisionState):
            raise OptimizationContractError("PendingAuthorization.decision_state must be an AutonomyDecisionState")
        if self.decision_state != AutonomyDecisionState.ASK:
            raise OptimizationContractError(
                "PendingAuthorization may only arise from an ASK decision "
                f"(got {self.decision_state.value})"
            )
        if not self.requested_action.strip():
            raise OptimizationContractError("PendingAuthorization.requested_action is required")
        if not self.rationale.strip():
            raise OptimizationContractError("PendingAuthorization.rationale is required")
        if not self.reasons:
            raise OptimizationContractError("PendingAuthorization.reasons are required")
        if self.resolution != AuthorizationResolution.PENDING:
            raise OptimizationContractError(
                "a pending authorization cannot be constructed in a resolved state "
                "(approval requires a fresh W9 decision under human authority)"
            )

    @classmethod
    def from_decision(
        cls, decision: AutonomyDecision, *, iteration_index: int
    ) -> "PendingAuthorization":
        """Build the pause record from a real W9 ASK decision."""
        if not isinstance(decision, AutonomyDecision):
            raise OptimizationContractError(
                "PendingAuthorization.from_decision requires a real W9 AutonomyDecision"
            )
        if decision.state != AutonomyDecisionState.ASK:
            raise OptimizationContractError(
                f"PendingAuthorization.from_decision requires an ASK decision (got {decision.state.value})"
            )
        return cls(
            iteration_index=iteration_index,
            decision_id=decision.id,
            decision_state=decision.state,
            requested_action=str(decision.action.value),
            rationale=decision.rationale,
            reasons=tuple(decision.reasons),
        )


def _pending_id(p: PendingAuthorization) -> str:
    material = "|".join([
        str(p.iteration_index), p.decision_id, p.decision_state.value,
        p.requested_action, p.rationale,
    ])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"pending-{digest}"


# ---------------------------------------------------------------------------
# Governed promotion record (PromotionGate required; bounded rollback for
# DEPLOY-class)
# ---------------------------------------------------------------------------


class PromotionClass(str, Enum):
    """The class of a loop promotion.

    MODEL_ONLY promotions are recorded in the model (nothing dispatched);
    DEPLOY promotions dispatched a governed execution step through the W11
    substrate and carry the resulting receipt reference.
    """

    MODEL_ONLY = "model-only"
    DEPLOY = "deploy"


@dataclass(frozen=True)
class LoopPromotion:
    """A governed promotion record (Work Order required outcome 5).

    Constructed through ``apply_promotion`` (which requires the W8
    ``PromotionGate`` decision and the W9 ACT decision). Every DEPLOY-class
    promotion mechanically carries a bounded W8 ``RollbackPath`` bound to the
    experiment's rollback reference.
    """

    candidate_id: str
    assurance_id: str
    experiment_id: str
    evaluation_id: str
    decision_id: str
    promotion_ref: str
    promotion_class: PromotionClass
    experiment_rollback_ref: str
    rollback: RollbackPath | None = None
    receipt_id: str | None = None
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", _promotion_id(self))
        self.validate()

    def validate(self) -> None:
        if not isinstance(self.promotion_class, PromotionClass):
            raise OptimizationContractError("LoopPromotion.promotion_class must be a PromotionClass")
        for name, value in (
            ("candidate_id", self.candidate_id),
            ("assurance_id", self.assurance_id),
            ("experiment_id", self.experiment_id),
            ("evaluation_id", self.evaluation_id),
            ("decision_id", self.decision_id),
            ("promotion_ref", self.promotion_ref),
            ("experiment_rollback_ref", self.experiment_rollback_ref),
        ):
            if not value or not value.strip():
                raise OptimizationContractError(f"LoopPromotion.{name} is required")
        expected_ref = f"{self.experiment_id}:{self.evaluation_id}"
        if self.promotion_ref != expected_ref:
            raise OptimizationContractError(
                f"LoopPromotion.promotion_ref '{self.promotion_ref}' must bind the gate decision "
                f"('{expected_ref}')"
            )
        if self.promotion_class == PromotionClass.DEPLOY:
            # C4: every DEPLOY-class promotion carries a bounded rollback path
            # bound to the experiment's rollback reference.
            if self.rollback is None:
                raise OptimizationContractError(
                    "DEPLOY-class promotion requires a bounded W8 RollbackPath"
                )
            if not self.rollback.evidence_ids:
                raise OptimizationContractError(
                    "DEPLOY-class promotion rollback path must carry recovery evidence"
                )
            if self.rollback.reference != self.experiment_rollback_ref:
                raise OptimizationContractError(
                    f"DEPLOY-class rollback reference '{self.rollback.reference}' does not match "
                    f"the experiment rollback reference '{self.experiment_rollback_ref}'"
                )
            if not (self.receipt_id or "").strip():
                raise OptimizationContractError(
                    "DEPLOY-class promotion requires the W11 execution receipt reference"
                )
        else:
            if self.receipt_id is not None:
                raise OptimizationContractError(
                    "MODEL_ONLY promotion must not carry an execution receipt reference"
                )


def _promotion_id(p: LoopPromotion) -> str:
    rollback_material = "" if p.rollback is None else "|".join([
        p.rollback.reference, ",".join(p.rollback.evidence_ids), p.rollback.detail,
    ])
    material = "|".join([
        p.candidate_id, p.assurance_id, p.experiment_id, p.evaluation_id,
        p.decision_id, p.promotion_ref, p.promotion_class.value,
        p.experiment_rollback_ref, rollback_material, p.receipt_id or "",
    ])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"loop-promotion-{digest}"


# ---------------------------------------------------------------------------
# Iteration record (typed refs + outcome; construction-validated)
# ---------------------------------------------------------------------------


def _require(value: str | None, name: str) -> None:
    if value is None or not value.strip():
        raise OptimizationContractError(f"{name} is required")


@dataclass(frozen=True)
class LoopIteration:
    """One governed loop iteration (Work Order required outcome 2).

    Carries the candidate/assurance/experiment/evaluation/decision references,
    the W4 evidence ids appended during the iteration, the terminal outcome,
    and — where applicable — the promotion, pending-authorization, and fired
    stop-condition records. Field presence is validated against the outcome:
    an experiment reference is impossible without an assurance reference
    (the W7-before-W8 ordering made visible in the record itself).
    """

    index: int
    candidate_id: str
    candidate_mutation_kind: str
    candidate_hypothesis_ids: tuple[str, ...] = ()
    candidate_evidence_ids: tuple[str, ...] = ()
    outcome: IterationOutcome = IterationOutcome.PROPOSED
    assurance_id: str | None = None
    assurance_status: AssuranceStatus | None = None
    experiment_id: str | None = None
    evaluation_id: str | None = None
    decision_ids: tuple[str, ...] = ()
    decision_state: AutonomyDecisionState | None = None
    promotion: LoopPromotion | None = None
    pending_authorization: PendingAuthorization | None = None
    stop_condition_name: str | None = None
    evidence_ids: tuple[str, ...] = ()
    detail: str = ""
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", _iteration_id(self))
        self.validate()

    def validate(self) -> None:
        if not isinstance(self.index, int) or self.index < 1:
            raise OptimizationContractError("LoopIteration.index must be a positive integer")
        _require(self.candidate_id, "LoopIteration.candidate_id")
        _require(self.candidate_mutation_kind, "LoopIteration.candidate_mutation_kind")
        try:
            MutationKind(self.candidate_mutation_kind)
        except ValueError:
            raise OptimizationContractError(
                f"LoopIteration.candidate_mutation_kind '{self.candidate_mutation_kind}' "
                "is not a W6 MutationKind value"
            ) from None
        if not isinstance(self.outcome, IterationOutcome):
            raise OptimizationContractError("LoopIteration.outcome must be an IterationOutcome")
        passed_assurance = self.outcome in (
            IterationOutcome.ASSURED, IterationOutcome.EXPERIMENTED,
            IterationOutcome.EVALUATED, IterationOutcome.DECIDED,
            IterationOutcome.PROMOTED, IterationOutcome.ROLLED_BACK,
            IterationOutcome.PAUSED_PENDING_AUTHORIZATION, IterationOutcome.REFUSED,
            IterationOutcome.GATHER_EVIDENCE, IterationOutcome.STOPPED_BY_CONDITION,
        )
        has_experiment = self.outcome in (
            IterationOutcome.EXPERIMENTED, IterationOutcome.EVALUATED,
            IterationOutcome.DECIDED, IterationOutcome.PROMOTED,
            IterationOutcome.ROLLED_BACK, IterationOutcome.PAUSED_PENDING_AUTHORIZATION,
            IterationOutcome.REFUSED, IterationOutcome.GATHER_EVIDENCE,
            IterationOutcome.STOPPED_BY_CONDITION,
        )
        has_evaluation = self.outcome in (
            IterationOutcome.EVALUATED, IterationOutcome.DECIDED,
            IterationOutcome.PROMOTED, IterationOutcome.ROLLED_BACK,
            IterationOutcome.GATHER_EVIDENCE, IterationOutcome.STOPPED_BY_CONDITION,
        )
        has_decision = self.outcome in (
            IterationOutcome.PROMOTED, IterationOutcome.ROLLED_BACK,
            IterationOutcome.PAUSED_PENDING_AUTHORIZATION, IterationOutcome.REFUSED,
            IterationOutcome.GATHER_EVIDENCE,
        )
        if passed_assurance:
            _require(self.assurance_id, "LoopIteration.assurance_id")
            if self.assurance_status != AssuranceStatus.PASS:
                raise OptimizationContractError(
                    "iterations beyond the assurance phase require a PASS W7 assurance status"
                )
        if self.outcome == IterationOutcome.ASSURANCE_NOT_PASSED:
            _require(self.assurance_id, "LoopIteration.assurance_id")
            if self.assurance_status is None or self.assurance_status == AssuranceStatus.PASS:
                raise OptimizationContractError(
                    "ASSURANCE_NOT_PASSED requires a non-PASS W7 assurance status"
                )
        # C3 made visible: an experiment reference requires the assurance
        # reference that preceded it.
        if self.experiment_id is not None:
            _require(self.experiment_id, "LoopIteration.experiment_id")
            if self.assurance_id is None:
                raise OptimizationContractError(
                    "an iteration experiment reference requires the W7 assurance reference "
                    "(W7-before-W8 ordering)"
                )
        if has_experiment and self.experiment_id is None:
            raise OptimizationContractError(
                f"outcome {self.outcome.value} requires the W8 experiment reference"
            )
        if self.evaluation_id is not None and self.experiment_id is None:
            raise OptimizationContractError(
                "an iteration evaluation reference requires the W8 experiment reference"
            )
        if has_evaluation and self.evaluation_id is None:
            raise OptimizationContractError(
                f"outcome {self.outcome.value} requires the W8 evaluation reference"
            )
        if bool(self.decision_ids) != (self.decision_state is not None):
            raise OptimizationContractError(
                "decision references and the governing decision state must be supplied together"
            )
        if has_decision and not self.decision_ids:
            raise OptimizationContractError(
                f"outcome {self.outcome.value} requires the W9 decision references"
            )
        if self.outcome == IterationOutcome.PROMOTED:
            if self.promotion is None:
                raise OptimizationContractError("PROMOTED requires the promotion record")
            if self.decision_state != AutonomyDecisionState.ACT:
                raise OptimizationContractError("PROMOTED requires an ACT W9 decision")
        if self.outcome == IterationOutcome.ROLLED_BACK:
            if self.decision_state != AutonomyDecisionState.ROLLBACK:
                raise OptimizationContractError("ROLLED_BACK requires a ROLLBACK W9 decision")
        if self.outcome == IterationOutcome.PAUSED_PENDING_AUTHORIZATION:
            if self.pending_authorization is None:
                raise OptimizationContractError(
                    "PAUSED_PENDING_AUTHORIZATION requires the pending-authorization record"
                )
            if self.decision_state != AutonomyDecisionState.ASK:
                raise OptimizationContractError("PAUSED_PENDING_AUTHORIZATION requires an ASK W9 decision")
        if self.outcome == IterationOutcome.REFUSED:
            if self.decision_state != AutonomyDecisionState.REJECT:
                raise OptimizationContractError("REFUSED requires a REJECT W9 decision")
        if self.outcome == IterationOutcome.GATHER_EVIDENCE:
            if self.decision_state != AutonomyDecisionState.GATHER_EVIDENCE:
                raise OptimizationContractError("GATHER_EVIDENCE requires a GATHER_EVIDENCE W9 decision")
        if self.outcome == IterationOutcome.STOPPED_BY_CONDITION:
            _require(self.stop_condition_name, "LoopIteration.stop_condition_name")
        if self.promotion is not None and self.outcome != IterationOutcome.PROMOTED:
            raise OptimizationContractError(
                "a promotion record is only lawful on a PROMOTED iteration"
            )
        if self.pending_authorization is not None and self.outcome != IterationOutcome.PAUSED_PENDING_AUTHORIZATION:
            raise OptimizationContractError(
                "a pending-authorization record is only lawful on a PAUSED_PENDING_AUTHORIZATION iteration"
            )


def _iteration_id(it: LoopIteration) -> str:
    material = "|".join([
        str(it.index), it.candidate_id, it.candidate_mutation_kind,
        ",".join(it.candidate_hypothesis_ids), ",".join(it.candidate_evidence_ids),
        it.outcome.value, it.assurance_id or "", it.experiment_id or "",
        it.evaluation_id or "", ",".join(it.decision_ids),
        it.decision_state.value if it.decision_state is not None else "",
        it.promotion.id if it.promotion is not None else "",
        it.pending_authorization.id if it.pending_authorization is not None else "",
        it.stop_condition_name or "", ",".join(it.evidence_ids), it.detail,
    ])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"iteration-{digest}"


# ---------------------------------------------------------------------------
# Loop stop record (typed reasons; W8 StopCondition-typed hard stops)
# ---------------------------------------------------------------------------


class LoopStopReason(str, Enum):
    """Why the loop stopped."""

    COMPLETED = "completed"
    MAX_ITERATIONS = "max-iterations"
    STOP_CONDITION = "stop-condition"
    PAUSED_FOR_AUTHORIZATION = "paused-for-authorization"


@dataclass(frozen=True)
class LoopStop:
    """The terminal stop record of a loop run."""

    reason: LoopStopReason
    iterations_executed: int
    detail: str
    stop_condition: StopCondition | None = None
    pending_authorization: PendingAuthorization | None = None

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not isinstance(self.reason, LoopStopReason):
            raise OptimizationContractError("LoopStop.reason must be a LoopStopReason")
        if not isinstance(self.iterations_executed, int) or self.iterations_executed < 0:
            raise OptimizationContractError("LoopStop.iterations_executed must be a non-negative integer")
        _require(self.detail, "LoopStop.detail")
        if self.reason == LoopStopReason.STOP_CONDITION and self.stop_condition is None:
            raise OptimizationContractError(
                "STOP_CONDITION requires the fired W8 StopCondition (typed stop conditions)"
            )
        if self.reason != LoopStopReason.STOP_CONDITION and self.stop_condition is not None:
            raise OptimizationContractError(
                "a stop condition is only lawful on a STOP_CONDITION stop"
            )
        if self.reason == LoopStopReason.PAUSED_FOR_AUTHORIZATION and self.pending_authorization is None:
            raise OptimizationContractError(
                "PAUSED_FOR_AUTHORIZATION requires the pending-authorization record"
            )
        if self.reason != LoopStopReason.PAUSED_FOR_AUTHORIZATION and self.pending_authorization is not None:
            raise OptimizationContractError(
                "a pending-authorization record is only lawful on a paused stop"
            )


# ---------------------------------------------------------------------------
# The loop record (typed, construction-validated, content-addressed)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OptimizationLoop:
    """The governed optimization loop record (Work Order required outcome 1).

    Carries the recovered-system reference (W3 SystemState id + exact
    revision), the bounded iteration entries, the stop outcome, and W1
    traceability. Identical runs produce identical content-addressed ids.
    """

    recovered_state_ref: str
    recovered_revision: str
    base_graph_id: str
    base_graph_revision: str
    provenance_revision: str
    max_iterations: int
    iterations: tuple[LoopIteration, ...]
    stop: LoopStop
    traceability: Traceability
    version: int = 1
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", _loop_id(self))
        self.validate()

    def validate(self) -> None:
        if not isinstance(self.version, int) or self.version < 1:
            raise OptimizationContractError("OptimizationLoop.version must be >= 1")
        for name, value in (
            ("recovered_state_ref", self.recovered_state_ref),
            ("recovered_revision", self.recovered_revision),
            ("base_graph_id", self.base_graph_id),
            ("base_graph_revision", self.base_graph_revision),
            ("provenance_revision", self.provenance_revision),
        ):
            _require(value, f"OptimizationLoop.{name}")
        if not isinstance(self.max_iterations, int) or isinstance(self.max_iterations, bool) or self.max_iterations < 1:
            raise OptimizationContractError("OptimizationLoop.max_iterations must be a positive integer")
        # C6: the record itself is bounded — more iterations than the declared
        # bound are unconstructible.
        if len(self.iterations) > self.max_iterations:
            raise OptimizationContractError(
                f"loop record carries {len(self.iterations)} iterations, exceeding the fixed "
                f"bound of {self.max_iterations}"
            )
        indices = [it.index for it in self.iterations]
        if indices != list(range(1, len(self.iterations) + 1)):
            raise OptimizationContractError(
                "iteration indices must be exactly 1..n in execution order"
            )
        for it in self.iterations:
            it.validate()
            if it.outcome not in ITERATION_TERMINAL_OUTCOMES:
                raise OptimizationContractError(
                    f"iteration {it.index} outcome {it.outcome.value} is not terminal; "
                    "a finished loop records only terminal outcomes"
                )
        self.stop.validate()
        if self.stop.iterations_executed != len(self.iterations):
            raise OptimizationContractError(
                "LoopStop.iterations_executed must equal the number of recorded iterations"
            )
        last = self.iterations[-1] if self.iterations else None
        if self.stop.reason == LoopStopReason.PAUSED_FOR_AUTHORIZATION:
            if last is None or last.outcome != IterationOutcome.PAUSED_PENDING_AUTHORIZATION:
                raise OptimizationContractError(
                    "a paused stop requires the last iteration to be paused pending authorization"
                )
        if self.stop.reason == LoopStopReason.MAX_ITERATIONS and len(self.iterations) != self.max_iterations:
            raise OptimizationContractError(
                "a max-iterations stop requires the iteration bound to have been reached"
            )
        if self.stop.reason == LoopStopReason.STOP_CONDITION:
            if last is None or last.outcome != IterationOutcome.STOPPED_BY_CONDITION:
                raise OptimizationContractError(
                    "a stop-condition stop requires the last iteration to be stopped by condition"
                )
        if self.stop.reason == LoopStopReason.COMPLETED:
            if self.stop.stop_condition is not None or self.stop.pending_authorization is not None:
                raise OptimizationContractError("a completed stop carries neither a stop condition nor a pause")
        self.traceability.validate(require_value=True, require_context=True)


def _loop_id(loop: OptimizationLoop) -> str:
    material = "|".join([
        loop.recovered_state_ref, loop.recovered_revision, loop.base_graph_id,
        loop.base_graph_revision, loop.provenance_revision,
        str(loop.max_iterations), str(loop.version),
        ",".join(it.id for it in loop.iterations),
        loop.stop.reason.value, str(loop.stop.iterations_executed), loop.stop.detail,
    ])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"loop-{digest}"


# ---------------------------------------------------------------------------
# Model-only experiment simulation port (injected deterministic evaluator)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SimulatedObservation:
    """A deterministic simulated outcome for one governed experiment.

    The truth state is a W1 ``TruthState`` and is preserved verbatim into the
    appended W4 experiment evidence: FAILED / UNKNOWN / UNAVAILABLE /
    UNSUPPORTED never collapse.
    """

    outcome_state: TruthState
    detail: str
    value: Any = None
    stop_triggered: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not isinstance(self.outcome_state, TruthState):
            raise OptimizationContractError("SimulatedObservation.outcome_state must be a TruthState")
        if self.outcome_state == TruthState.EMPTY:
            raise OptimizationContractError(
                "EMPTY is not a lawful simulated experiment outcome (observation-capture state)"
            )
        # Delegate the truth-state/value/detail contract to the W1 authority.
        TruthfulValue(self.outcome_state, self.value, self.detail).validate()
        for name in self.stop_triggered:
            if not name or not name.strip():
                raise OptimizationContractError("SimulatedObservation.stop_triggered names must be non-empty")


@runtime_checkable
class ExperimentSimulatorPort(Protocol):
    """The injected, deterministic, model-only experiment simulator port.

    The simulator is an injected port object (a deterministic stub evaluator in
    tests) — it simulates governed experiment outcomes and never touches a
    running system. It grants no authority: its output is only ever a truth
    state that flows through the W4/W7/W8/W9 gates unchanged.
    """

    simulator_id: str

    def simulate(self, experiment: Experiment) -> SimulatedObservation: ...


# ---------------------------------------------------------------------------
# W7-before-W8 construction gate (mechanically enforced ordering invariant)
# ---------------------------------------------------------------------------


def governed_experiment(
    *,
    assurance: AssuranceResult,
    candidate: CandidateProposal,
    rollback_ref: str,
    traceability: Traceability,
    stop_conditions: tuple[StopCondition, ...],
    mode: ExperimentMode = ExperimentMode.SHADOW,
    scope: tuple[str, ...] = (),
    observation_window: tuple[str, str] = ("2030-01-01T00:00:00Z", "2030-01-02T00:00:00Z"),
    success_criteria: tuple[str, ...] = ("objectives-not-dominated",),
) -> Experiment:
    """Construct a W8 experiment bound to a PASS W7 assurance result (C3).

    The loop's only experiment construction path. A non-PASS assurance, or an
    assurance not bound to the exact candidate/graph/revision/provenance
    chain, is rejected before any experiment exists — the W7-before-W8
    ordering invariant is mechanically enforced.
    """
    if not isinstance(assurance, AssuranceResult):
        raise OptimizationContractError("governed_experiment requires a real W7 AssuranceResult")
    if not isinstance(candidate, CandidateProposal):
        raise OptimizationContractError("governed_experiment requires a real W6 CandidateProposal")
    if assurance.status != AssuranceStatus.PASS:
        raise OptimizationContractError(
            f"W7-before-W8 ordering invariant: an experiment cannot be constructed on a "
            f"{assurance.status.value} assurance result (only PASS)"
        )
    if candidate.id != assurance.candidate_id:
        raise OptimizationContractError(
            f"candidate '{candidate.id}' is not the candidate the assurance result bound "
            f"('{assurance.candidate_id}')"
        )
    if candidate.base_graph_ref != assurance.base_graph_id:
        raise OptimizationContractError(
            "candidate base graph does not match the assurance base graph"
        )
    if candidate.base_graph_revision != assurance.base_graph_revision:
        raise OptimizationContractError(
            "candidate base graph revision does not match the assurance revision"
        )
    if candidate.provenance_revision != assurance.provenance_revision:
        raise OptimizationContractError(
            "candidate provenance revision does not match the assurance provenance revision"
        )
    if not rollback_ref.strip():
        raise OptimizationContractError("governed_experiment requires a rollback reference")
    if not stop_conditions:
        raise OptimizationContractError(
            "governed_experiment requires W8-typed stop conditions (C5 hard stops)"
        )
    experiment_scope = tuple(scope) if scope else tuple(candidate.mutation.target_node_ids)
    experiment = Experiment(
        id="",
        candidate_id=candidate.id,
        assurance_result_id=assurance.id,
        base_graph_id=assurance.base_graph_id,
        base_graph_revision=assurance.base_graph_revision,
        provenance_revision=assurance.provenance_revision,
        mode=mode,
        scope=experiment_scope,
        observation_window=tuple(observation_window),
        success_criteria=tuple(success_criteria),
        stop_conditions=tuple(stop_conditions),
        rollback_ref=rollback_ref,
        traceability=traceability,
        state=ExperimentState.PLANNED,
    )
    # The W8 authority re-validates the full candidate/assurance/graph/
    # revision/provenance binding (SOS-W8-F01).
    experiment.validate(known_assurance=assurance)
    return experiment


# ---------------------------------------------------------------------------
# Promotion application (PromotionGate + W9 ACT required)
# ---------------------------------------------------------------------------


def apply_promotion(
    *,
    gate_decision: PromotionDecision,
    experiment: Experiment,
    evaluation: ExperimentEvaluation,
    assurance: AssuranceResult,
    autonomy_decision: AutonomyDecision,
    rollback_path: RollbackPath | None,
    promotion_class: PromotionClass,
    receipt: ExecutionReceipt | None = None,
) -> LoopPromotion:
    """Apply a governed promotion (C4: the W8 PromotionGate result is required).

    Promotion without a granted PromotionGate decision, without a W9 ACT
    decision, or (for the DEPLOY class) without a bounded rollback path is
    rejected — there is no implicit promotion path.
    """
    if not isinstance(gate_decision, PromotionDecision):
        raise OptimizationContractError(
            "apply_promotion requires the W8 PromotionGate decision (a PromotionDecision)"
        )
    if not gate_decision.promoted:
        raise OptimizationContractError(
            f"promotion requires the W8 PromotionGate to have granted promotion: {gate_decision.rationale}"
        )
    if not isinstance(experiment, Experiment) or not isinstance(evaluation, ExperimentEvaluation):
        raise OptimizationContractError("apply_promotion requires the W8 experiment and evaluation records")
    if not isinstance(assurance, AssuranceResult):
        raise OptimizationContractError("apply_promotion requires the W7 assurance result")
    if not isinstance(autonomy_decision, AutonomyDecision):
        raise OptimizationContractError("apply_promotion requires a real W9 AutonomyDecision")
    if autonomy_decision.state != AutonomyDecisionState.ACT:
        raise OptimizationContractError(
            f"promotion requires a resolved W9 ACT decision (got {autonomy_decision.state.value}); "
            "no auto-promotion without ACT"
        )
    if gate_decision.experiment_id != experiment.id:
        raise OptimizationContractError(
            "the gate decision is not bound to the exact experiment"
        )
    if gate_decision.evaluation_id != evaluation.id:
        raise OptimizationContractError(
            "the gate decision is not bound to the exact evaluation"
        )
    if evaluation.experiment_id != experiment.id:
        raise OptimizationContractError(
            "the evaluation is not bound to the exact experiment"
        )
    if experiment.assurance_result_id != assurance.id:
        raise OptimizationContractError(
            "the experiment is not bound to the exact assurance result"
        )
    if autonomy_decision.experiment_id != experiment.id:
        raise OptimizationContractError(
            "the authorizing W9 decision is not bound to the exact experiment"
        )
    if autonomy_decision.assurance_id != assurance.id:
        raise OptimizationContractError(
            "the authorizing W9 decision is not bound to the exact assurance result"
        )
    if promotion_class == PromotionClass.DEPLOY:
        if receipt is None:
            raise OptimizationContractError(
                "DEPLOY-class promotion requires the W11 execution receipt"
            )
        if receipt.outcome.state != TruthState.SUCCESS:
            raise OptimizationContractError(
                f"DEPLOY-class promotion requires a successful receipt (got {receipt.outcome.state.value})"
            )
        if receipt.w9_decision_id != autonomy_decision.id:
            raise OptimizationContractError(
                "the execution receipt is not bound to the authorizing W9 decision"
            )
    return LoopPromotion(
        candidate_id=experiment.candidate_id,
        assurance_id=assurance.id,
        experiment_id=experiment.id,
        evaluation_id=evaluation.id,
        decision_id=autonomy_decision.id,
        promotion_ref=f"{gate_decision.experiment_id}:{gate_decision.evaluation_id}",
        promotion_class=promotion_class,
        experiment_rollback_ref=experiment.rollback_ref,
        rollback=rollback_path,
        receipt_id=receipt.id if receipt is not None else None,
    )


# ---------------------------------------------------------------------------
# W11 execution seam (governed DEPLOY dispatch; model-only when absent)
# ---------------------------------------------------------------------------


def dispatch_deployment(
    *,
    providers: Mapping[str, ExecutionProviderPort],
    provider_id: str,
    intent: str,
    decision: AutonomyDecision,
    assurance: AssuranceResult,
    experiment: Experiment,
    rollback_path: RollbackPath,
    source_revision: str,
    environment: str,
    traceability: Traceability,
    workspace_ref: str | None = None,
) -> ExecutionReceipt:
    """Dispatch one governed DEPLOY step through the real W11 substrate.

    The loop resolves the W9 ACT decision into the substrate's decision
    registry before dispatch: an unresolved W9 authorization reference is
    rejected by the substrate's own authority gate before any provider call.
    All other gates (scope state, provider-not-authorizer, W7 PASS + exact
    chain, W8 experiment chain, rollback binding) are the W11 substrate's.
    """
    if not isinstance(decision, AutonomyDecision):
        raise OptimizationContractError("dispatch_deployment requires a real W9 AutonomyDecision")
    if decision.state != AutonomyDecisionState.ACT:
        raise OptimizationContractError(
            f"deployment requires a resolved W9 ACT decision (got {decision.state.value})"
        )
    if assurance.status != AssuranceStatus.PASS:
        raise OptimizationContractError(
            f"deployment requires a PASS W7 assurance result (got {assurance.status.value})"
        )
    if experiment.assurance_result_id != assurance.id:
        raise OptimizationContractError(
            "the experiment is not bound to the exact assurance result"
        )
    if rollback_path.reference != experiment.rollback_ref:
        raise OptimizationContractError(
            f"rollback reference '{rollback_path.reference}' does not match the experiment "
            f"rollback reference '{experiment.rollback_ref}'"
        )
    request = ExecutionRequest(
        intent=intent,
        action_scope=ExecutionActionScope.DEPLOY,
        provider_id=provider_id,
        source_revision=source_revision,
        provenance_revision=experiment.provenance_revision,
        base_graph_id=experiment.base_graph_id,
        base_graph_revision=experiment.base_graph_revision,
        environment=environment,
        w9_decision_id=decision.id,
        traceability=traceability,
        w7_assurance_id=assurance.id,
        w8_experiment_id=experiment.id,
        w8_promotion_ref=decision.promotion_id,
        workspace_ref=workspace_ref,
        rollback_reference=RollbackReference(
            reference=rollback_path.reference,
            evidence_ids=tuple(rollback_path.evidence_ids),
            detail=rollback_path.detail,
        ),
    )
    substrate = ExecutionSubstrate(
        providers=dict(providers),
        known_decisions={decision.id: decision},
        known_assurance={assurance.id: assurance},
        known_experiments={experiment.id: experiment},
    )
    return substrate.submit(request)


# ---------------------------------------------------------------------------
# W4 evidence helper (verbatim assembly through the W4 authority)
# ---------------------------------------------------------------------------


def _loop_evidence(
    *,
    kind: EvidenceKind,
    source_ref: str,
    subject_ref: str,
    result: TruthfulValue[Any],
    traceability: Traceability,
    source: str,
    timestamp: str | None,
    environment: str,
    implementation_revision: str,
) -> Evidence:
    """Assemble one loop evidence record through the W4 authority.

    Uses the W4 module's own content-addressed assembly so the evidence-id
    algorithm exists exactly once. Only existing evidence kinds are used; the
    result states are observed artifacts, never inferred system facts.
    """
    provenance = EvidenceProvenance(
        source=source,
        observed_subject=subject_ref,
        timestamp=timestamp,
        environment=environment,
        implementation_revision=implementation_revision,
    )
    return _build_evidence(
        kind=kind,
        source_ref=source_ref,
        subject_ref=subject_ref,
        result=result,
        provenance=provenance,
        traceability=traceability,
        timestamp=timestamp,
        environment=environment,
        confidence=None,
        availability=TruthState.SUCCESS,
    )


_ASSURANCE_TRUTH: dict[AssuranceStatus, TruthState] = {
    # Distinct W7 statuses map to distinct W1 truth states (C7): none collapses.
    AssuranceStatus.PASS: TruthState.SUCCESS,
    AssuranceStatus.FAIL: TruthState.FAILED,
    AssuranceStatus.UNKNOWN: TruthState.UNKNOWN,
    AssuranceStatus.BLOCKED: TruthState.UNAVAILABLE,
}


def _assurance_evidence_result(assurance: AssuranceResult) -> TruthfulValue[Any]:
    state = _ASSURANCE_TRUTH[assurance.status]
    if state == TruthState.SUCCESS:
        return TruthfulValue(TruthState.SUCCESS, assurance.id, None)
    return TruthfulValue(state, None, f"W7 assurance status {assurance.status.value}")


# ---------------------------------------------------------------------------
# The run result (the full explainability chain, chain-validated)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OptimizationRun:
    """A completed loop run: the loop record plus the full authority chain.

    Preserves the whole chain for explainability (Work Order required outcome
    10): all candidate alternatives, assurance results, experiments,
    evaluations, promotion-gate decisions, W9 decisions, W11 receipts, and the
    final W4 evidence graph. ``validate`` chain-checks every cross-authority
    reference (C1): an unresolved W9 reference, a mismatched
    candidate/assurance/experiment chain, or a dangling evidence id makes the
    run unconstructible.
    """

    loop: OptimizationLoop
    evidence_graph: EvidenceGraph
    candidates: tuple[CandidateProposal, ...]
    assurance_results: tuple[AssuranceResult, ...]
    experiments: tuple[Experiment, ...]
    evaluations: tuple[ExperimentEvaluation, ...]
    promotion_decisions: tuple[PromotionDecision, ...]
    decisions: tuple[AutonomyDecision, ...]
    receipts: tuple[ExecutionReceipt, ...]

    def validate(self) -> None:
        self.loop.validate()
        self.evidence_graph.validate()
        candidate_ids = [c.id for c in self.candidates]
        if len(set(candidate_ids)) != len(candidate_ids):
            raise OptimizationContractError("OptimizationRun.candidates must have unique ids")
        candidates_by_id = {c.id: c for c in self.candidates}
        assurance_by_id = {a.id: a for a in self.assurance_results}
        experiments_by_id = {e.id: e for e in self.experiments}
        evaluations_by_id = {ev.id: ev for ev in self.evaluations}
        decisions_by_id = {d.id: d for d in self.decisions}
        receipts_by_id = {r.id: r for r in self.receipts}
        evidence_ids = {r.id for r in self.evidence_graph.records}
        for it in self.loop.iterations:
            if it.candidate_id not in candidates_by_id:
                raise OptimizationContractError(
                    f"iteration {it.index} references unknown candidate '{it.candidate_id}'"
                )
            if it.assurance_id is not None and it.assurance_id not in assurance_by_id:
                raise OptimizationContractError(
                    f"iteration {it.index} references unknown assurance result '{it.assurance_id}'"
                )
            if it.experiment_id is not None and it.experiment_id not in experiments_by_id:
                raise OptimizationContractError(
                    f"iteration {it.index} references unknown experiment '{it.experiment_id}'"
                )
            if it.evaluation_id is not None and it.evaluation_id not in evaluations_by_id:
                raise OptimizationContractError(
                    f"iteration {it.index} references unknown evaluation '{it.evaluation_id}'"
                )
            for did in it.decision_ids:
                if did not in decisions_by_id:
                    raise OptimizationContractError(
                        f"iteration {it.index} references unresolved W9 decision '{did}'"
                    )
            for eid in it.evidence_ids:
                if eid not in evidence_ids:
                    raise OptimizationContractError(
                        f"iteration {it.index} references evidence '{eid}' not present in the run graph"
                    )
            if it.assurance_id is not None:
                ar = assurance_by_id[it.assurance_id]
                if ar.candidate_id != it.candidate_id:
                    raise OptimizationContractError(
                        f"iteration {it.index} assurance is not bound to the iteration candidate"
                    )
            if it.experiment_id is not None:
                exp = experiments_by_id[it.experiment_id]
                if exp.candidate_id != it.candidate_id:
                    raise OptimizationContractError(
                        f"iteration {it.index} experiment is not bound to the iteration candidate"
                    )
                if it.assurance_id is not None and exp.assurance_result_id != it.assurance_id:
                    raise OptimizationContractError(
                        f"iteration {it.index} experiment is not bound to the iteration assurance"
                    )
            if it.evaluation_id is not None:
                ev = evaluations_by_id[it.evaluation_id]
                if ev.experiment_id != it.experiment_id:
                    raise OptimizationContractError(
                        f"iteration {it.evaluation_id} evaluation is not bound to the iteration experiment"
                    )
                if ev.candidate_id != it.candidate_id:
                    raise OptimizationContractError(
                        f"iteration {it.index} evaluation is not bound to the iteration candidate"
                    )
            if it.decision_ids:
                last = decisions_by_id[it.decision_ids[-1]]
                if last.state != it.decision_state:
                    raise OptimizationContractError(
                        f"iteration {it.index} governing decision state "
                        f"{last.state.value} does not match the recorded {it.decision_state.value}"
                    )
            if it.promotion is not None:
                p = it.promotion
                if p.decision_id not in decisions_by_id:
                    raise OptimizationContractError(
                        f"iteration {it.index} promotion references unresolved W9 decision '{p.decision_id}'"
                    )
                d = decisions_by_id[p.decision_id]
                if d.state != AutonomyDecisionState.ACT:
                    raise OptimizationContractError(
                        "a promotion must be authorized by an ACT W9 decision"
                    )
                if d.experiment_id != it.experiment_id:
                    raise OptimizationContractError(
                        "the authorizing W9 decision is not bound to the promoted experiment"
                    )
                if d.assurance_id != it.assurance_id:
                    raise OptimizationContractError(
                        "the authorizing W9 decision is not bound to the promoted assurance"
                    )
                if p.experiment_id not in experiments_by_id:
                    raise OptimizationContractError(
                        f"promotion references unknown experiment '{p.experiment_id}'"
                    )
                if p.evaluation_id not in evaluations_by_id:
                    raise OptimizationContractError(
                        f"promotion references unknown evaluation '{p.evaluation_id}'"
                    )
                if p.receipt_id is not None and p.receipt_id not in receipts_by_id:
                    raise OptimizationContractError(
                        f"promotion references unknown receipt '{p.receipt_id}'"
                    )
            if it.pending_authorization is not None:
                pa = it.pending_authorization
                if pa.decision_id not in decisions_by_id:
                    raise OptimizationContractError(
                        f"pending authorization references unresolved W9 decision '{pa.decision_id}'"
                    )
                if decisions_by_id[pa.decision_id].state != AutonomyDecisionState.ASK:
                    raise OptimizationContractError(
                        "a pending authorization must reference an ASK W9 decision"
                    )
        for gd in self.promotion_decisions:
            if gd.experiment_id not in experiments_by_id:
                raise OptimizationContractError(
                    f"promotion-gate decision references unknown experiment '{gd.experiment_id}'"
                )
            if gd.evaluation_id not in evaluations_by_id:
                raise OptimizationContractError(
                    f"promotion-gate decision references unknown evaluation '{gd.evaluation_id}'"
                )


# ---------------------------------------------------------------------------
# The orchestrator
# ---------------------------------------------------------------------------


def run_optimization_loop(
    *,
    recovery: RecoveryResult,
    candidates: Sequence[CandidateProposal],
    policy: AutonomyRequest,
    simulator: ExperimentSimulatorPort,
    traceability: Traceability,
    max_iterations: int,
    stop_conditions: tuple[StopCondition, ...],
    evidence_graph: EvidenceGraph | None = None,
    causal_graph: CausalKnowledgeGraph | None = None,
    hard_constraints: tuple[str, ...] = (),
    rollback_ref: str = "loop-rollback-ref-1",
    rollback_evidence_ids: tuple[str, ...] = (),
    experiment_mode: ExperimentMode = ExperimentMode.CANARY,
    observation_window: tuple[str, str] = ("2030-01-01T00:00:00Z", "2030-01-02T00:00:00Z"),
    success_criteria: tuple[str, ...] = ("objectives-not-dominated",),
    confidence: float = 0.9,
    risk: float = 0.1,
    reversible: bool = True,
    blast_radius: str = "limited",
    human_authority_present: bool = False,
    timestamp: str | None = None,
    environment: str = "simulation",
    execution_providers: Mapping[str, ExecutionProviderPort] | None = None,
    execution_provider_id: str | None = None,
    execution_environment: str = "simulation-stub",
    execution_workspace_ref: str | None = None,
) -> OptimizationRun:
    """Run the governed brownfield optimization loop (first bounded slice).

    Deterministic, bounded, model-only composition of the real authorities:
    identical inputs produce identical content-addressed loop records. All
    registries (evidence, hypotheses, providers) are caller-supplied; all
    timestamps are caller-supplied data (the core consults no clock). Without
    ``execution_providers`` the loop runs in model-only mode; with them,
    promotions dispatch governed DEPLOY steps through the real W11 substrate.
    """
    # --- caller-supplied data validation (deterministic, before any step) ---
    if not isinstance(recovery, RecoveryResult):
        raise OptimizationContractError("run_optimization_loop requires a real W3 RecoveryResult")
    if not isinstance(policy, AutonomyRequest):
        raise OptimizationContractError("run_optimization_loop requires a real W9 AutonomyRequest")
    if not isinstance(max_iterations, int) or isinstance(max_iterations, bool) or max_iterations < 1:
        raise OptimizationContractError("max_iterations must be a positive integer")
    if not stop_conditions:
        raise OptimizationContractError("stop_conditions are required (W8-typed hard stops)")
    for sc in stop_conditions:
        if not isinstance(sc, StopCondition):
            raise OptimizationContractError("stop_conditions must be W8 StopCondition records")
    if isinstance(risk, bool) or not isinstance(risk, (int, float)) or not 0.0 <= risk <= 1.0:
        raise OptimizationContractError(f"risk must be a number within [0, 1], got {risk!r}")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
        raise OptimizationContractError(f"confidence must be a number within [0, 1], got {confidence!r}")
    if not isinstance(simulator, ExperimentSimulatorPort):
        raise OptimizationContractError(
            "run_optimization_loop requires an ExperimentSimulatorPort (injected deterministic evaluator)"
        )
    if (execution_providers is None) != (execution_provider_id is None):
        raise OptimizationContractError(
            "the W11 seam requires both execution_providers and execution_provider_id "
            "(omit both for model-only mode)"
        )
    traceability.validate(require_value=True, require_context=True)
    policy.validate()

    system_state = recovery.system_state
    graph = system_state.architecture
    revision = recovery.revision

    # C1: candidates must target the recovered system.
    for c in candidates:
        if not isinstance(c, CandidateProposal):
            raise OptimizationContractError("candidates must be W6 CandidateProposal records")
        if c.base_graph_ref != graph.id:
            raise OptimizationContractError(
                f"candidate '{c.id}' targets graph '{c.base_graph_ref}', not the recovered "
                f"system graph '{graph.id}'"
            )
        if c.base_graph_revision != revision or c.provenance_revision != revision:
            raise OptimizationContractError(
                f"candidate '{c.id}' is not bound to the recovered revision '{revision}'"
            )

    # Deterministic candidate ordering: deduplicate, then sort by the
    # content-addressed id (stable tie-break — equal ids are identical
    # candidates and cannot both remain).
    ordered: list[CandidateProposal] = []
    seen_candidate_ids: set[str] = set()
    for c in sorted(candidates, key=lambda cand: cand.id):
        if c.id in seen_candidate_ids:
            continue
        seen_candidate_ids.add(c.id)
        ordered.append(c)

    if evidence_graph is None:
        evidence_graph = EvidenceGraph(
            id="w12-loop-evidence", version=1, records=(), traceability=traceability,
        )
    known_evidence: dict[str, Evidence] = {r.id: r for r in evidence_graph.records}
    known_hypotheses: dict[str, CausalHypothesis] = (
        {h.id: h for h in causal_graph.hypotheses} if causal_graph is not None else {}
    )
    for eid in rollback_evidence_ids:
        if eid not in known_evidence:
            raise OptimizationContractError(
                f"rollback evidence '{eid}' is not present in the evidence graph"
            )

    iterations: list[LoopIteration] = []
    assurance_results: list[AssuranceResult] = []
    experiments: list[Experiment] = []
    evaluations: list[ExperimentEvaluation] = []
    promotion_decisions: list[PromotionDecision] = []
    decisions: list[AutonomyDecision] = []
    receipts: list[ExecutionReceipt] = []
    stop: LoopStop | None = None

    def ingest(record: Evidence) -> str:
        nonlocal evidence_graph
        evidence_graph = evidence_graph.ingest(record)
        known_evidence[record.id] = record
        return record.id

    for index, candidate in enumerate(ordered, start=1):
        if len(iterations) >= max_iterations:
            stop = LoopStop(
                reason=LoopStopReason.MAX_ITERATIONS,
                iterations_executed=len(iterations),
                detail=f"fixed iteration bound of {max_iterations} reached",
            )
            break

        phase: IterationOutcome = IterationOutcome.PROPOSED

        def advance(to: IterationOutcome) -> None:
            nonlocal phase
            validate_iteration_transition(phase, to)
            phase = to

        iteration_evidence: list[str] = []
        decision_ids: list[str] = []

        def evidence_kwargs(kind: EvidenceKind, source_ref: str, result: TruthfulValue[Any], source: str) -> dict[str, Any]:
            return dict(
                kind=kind, source_ref=source_ref, subject_ref=graph.id, result=result,
                traceability=traceability, source=source, timestamp=timestamp,
                environment=environment, implementation_revision=revision,
            )

        def finish(**overrides: Any) -> None:
            iterations.append(LoopIteration(
                index=index,
                candidate_id=candidate.id,
                candidate_mutation_kind=candidate.mutation.kind.value,
                candidate_hypothesis_ids=tuple(candidate.reasoning_hypothesis_ids),
                candidate_evidence_ids=tuple(candidate.reasoning_evidence_ids),
                evidence_ids=tuple(iteration_evidence),
                decision_ids=tuple(decision_ids),
                **overrides,
            ))

        def pause(decision: AutonomyDecision, detail: str, *, evaluation_id: str | None) -> None:
            """Record the explicit pending-authorization pause and stop the loop."""
            pending = PendingAuthorization.from_decision(decision, iteration_index=index)
            ev = _loop_evidence(
                **evidence_kwargs(
                    EvidenceKind.OBSERVATION,
                    f"pending-authorization:{pending.id}",
                    TruthfulValue(
                        TruthState.UNKNOWN, None,
                        f"loop paused pending human authorization (W9 ASK): {pending.rationale}",
                    ),
                    "w12-optimization-loop",
                )
            )
            eid = ingest(ev)
            if eid not in iteration_evidence:
                iteration_evidence.append(eid)
            experiments.append(experiment)
            finish(
                outcome=IterationOutcome.PAUSED_PENDING_AUTHORIZATION,
                assurance_id=assurance.id,
                assurance_status=assurance.status,
                experiment_id=experiment.id,
                evaluation_id=evaluation_id,
                decision_state=decision.state,
                pending_authorization=pending,
                detail=detail,
            )
            stop_record = LoopStop(
                reason=LoopStopReason.PAUSED_FOR_AUTHORIZATION,
                iterations_executed=len(iterations),
                detail=detail,
                pending_authorization=pending,
            )
            nonlocal stop
            stop = stop_record

        # -- consequential step 1: deterministic candidate selection ----------
        selection_evidence = _loop_evidence(
            **evidence_kwargs(
                EvidenceKind.OBSERVATION,
                f"candidate-selected:{candidate.id}",
                TruthfulValue(TruthState.SUCCESS, candidate.id, None),
                "w12-optimization-loop",
            )
        )
        eid = ingest(selection_evidence)
        iteration_evidence.append(eid)

        # -- consequential step 2: W7 assurance gate (real authority) ----------
        assurance = assure_candidate(
            candidate=candidate,
            base_graph=graph,
            known_evidence=known_evidence,
            known_hypotheses=known_hypotheses,
            hard_constraints=tuple(hard_constraints),
            rollback_evidence_ids=tuple(rollback_evidence_ids),
        )
        assurance_results.append(assurance)
        assurance_evidence = _loop_evidence(
            **evidence_kwargs(
                EvidenceKind.TEST,
                f"assurance:{assurance.id}",
                _assurance_evidence_result(assurance),
                "w12-optimization-loop",
            )
        )
        eid = ingest(assurance_evidence)
        if eid not in iteration_evidence:
            iteration_evidence.append(eid)

        if assurance.status != AssuranceStatus.PASS:
            advance(IterationOutcome.ASSURANCE_NOT_PASSED)
            finish(
                outcome=IterationOutcome.ASSURANCE_NOT_PASSED,
                assurance_id=assurance.id,
                assurance_status=assurance.status,
                detail=f"W7 assurance status {assurance.status.value}: no experiment may be constructed",
            )
            continue
        advance(IterationOutcome.ASSURED)

        # -- consequential step 3: governed experiment construction (C3) ------
        rollback_path = RollbackPath(
            reference=rollback_ref,
            evidence_ids=tuple(assurance.reversibility.rollback_evidence_ids),
            detail=f"governed rollback path bound to experiment rollback reference '{rollback_ref}'",
        )
        experiment = governed_experiment(
            assurance=assurance,
            candidate=candidate,
            rollback_ref=rollback_ref,
            traceability=traceability,
            stop_conditions=tuple(stop_conditions),
            mode=experiment_mode,
            observation_window=tuple(observation_window),
            success_criteria=tuple(success_criteria),
        )

        # -- consequential step 4: W9 gate on experiment launch ----------------
        launch_decision = evaluate_autonomy(
            policy=policy,
            action=DecisionAction.EXPERIMENT,
            assurance=assurance,
            experiment=experiment,
            promotion=None,
            evidence_ids=(),
            traceability=traceability,
            known_evidence=known_evidence,
            human_authority_present=human_authority_present,
            blast_radius=blast_radius,
            risk=risk,
            confidence=confidence,
            reversible=reversible,
        )
        decisions.append(launch_decision)
        decision_ids.append(launch_decision.id)
        if launch_decision.state == AutonomyDecisionState.REJECT:
            advance(IterationOutcome.REFUSED)
            experiments.append(experiment)
            finish(
                outcome=IterationOutcome.REFUSED,
                assurance_id=assurance.id,
                assurance_status=assurance.status,
                experiment_id=experiment.id,
                decision_state=launch_decision.state,
                detail=f"W9 refused the experiment launch: {launch_decision.rationale}",
            )
            continue
        if launch_decision.state == AutonomyDecisionState.ASK:
            advance(IterationOutcome.PAUSED_PENDING_AUTHORIZATION)
            pause(
                launch_decision,
                f"W9 ASK paused the loop before experiment launch: {launch_decision.rationale}",
                evaluation_id=None,
            )
            break
        advance(IterationOutcome.EXPERIMENTED)

        # -- consequential step 5: governed W8 lifecycle -----------------------
        experiment = transition_experiment(experiment, ExperimentState.READY, known_assurance=assurance)
        experiment = transition_experiment(experiment, ExperimentState.RUNNING, known_assurance=assurance)
        observation = simulator.simulate(experiment)
        if not isinstance(observation, SimulatedObservation):
            raise OptimizationContractError(
                "the simulator must return a SimulatedObservation"
            )
        observation.validate()
        declared_stops = {sc.name for sc in experiment.stop_conditions}
        for fired in observation.stop_triggered:
            if fired not in declared_stops:
                raise OptimizationContractError(
                    f"simulator fired undeclared stop condition '{fired}' "
                    f"(declared: {sorted(declared_stops)})"
                )
        if observation.outcome_state == TruthState.SUCCESS:
            terminal_state = ExperimentState.COMPLETED
        elif observation.stop_triggered:
            terminal_state = ExperimentState.STOPPED
        else:
            terminal_state = ExperimentState.FAILED
        experiment = transition_experiment(experiment, terminal_state, known_assurance=assurance)

        # -- consequential step 6: experiment evidence (verbatim simulation) ---
        experiment_evidence = _loop_evidence(
            **evidence_kwargs(
                EvidenceKind.EXPERIMENT,
                f"{simulator.simulator_id}:{experiment.id}",
                TruthfulValue(observation.outcome_state, observation.value, observation.detail),
                simulator.simulator_id,
            )
        )
        eid = ingest(experiment_evidence)
        iteration_evidence.append(eid)

        # -- consequential step 7: W8 truthful evaluation ----------------------
        evaluation = evaluate_experiment(
            experiment,
            known_evidence=known_evidence,
            evidence_refs=(experiment_evidence.id,),
            evaluation_success=(observation.outcome_state == TruthState.SUCCESS),
            stop_trigger=tuple(observation.stop_triggered),
            known_assurance=assurance,
            rollback_path=rollback_path,
        )
        evaluations.append(evaluation)
        advance(IterationOutcome.EVALUATED)

        if evaluation.stopped:
            fired_name = observation.stop_triggered[0]
            fired_condition = next(
                sc for sc in experiment.stop_conditions if sc.name == fired_name
            )
            experiments.append(experiment)
            finish(
                outcome=IterationOutcome.STOPPED_BY_CONDITION,
                assurance_id=assurance.id,
                assurance_status=assurance.status,
                experiment_id=experiment.id,
                evaluation_id=evaluation.id,
                decision_state=launch_decision.state,
                stop_condition_name=fired_name,
                detail=f"W8 hard stop condition '{fired_name}' fired; the loop terminated",
            )
            stop = LoopStop(
                reason=LoopStopReason.STOP_CONDITION,
                iterations_executed=len(iterations),
                detail=f"W8 hard stop condition '{fired_name}' fired; the loop terminated",
                stop_condition=fired_condition,
            )
            break

        # -- consequential step 8: W8 promotion gate ---------------------------
        gate = PromotionGate()
        gate_decision = gate.evaluate(experiment, evaluation, known_assurance=assurance)
        promotion_decisions.append(gate_decision)

        if gate_decision.promoted:
            act_decision = evaluate_autonomy(
                policy=policy,
                action=DecisionAction.ACT,
                assurance=assurance,
                experiment=experiment,
                promotion=gate_decision,
                evaluation=evaluation,
                evidence_ids=tuple(evaluation.evidence_ids),
                traceability=traceability,
                known_evidence=known_evidence,
                human_authority_present=human_authority_present,
                blast_radius=blast_radius,
                risk=risk,
                confidence=confidence,
                reversible=reversible,
            )
            decisions.append(act_decision)
            decision_ids.append(act_decision.id)
            advance(IterationOutcome.DECIDED)

            if act_decision.state == AutonomyDecisionState.ACT:
                if execution_providers is not None and execution_provider_id is not None:
                    receipt = dispatch_deployment(
                        providers=execution_providers,
                        provider_id=execution_provider_id,
                        intent=(
                            f"promote candidate {candidate.id} for iteration {index} of the "
                            "governed optimization loop"
                        ),
                        decision=act_decision,
                        assurance=assurance,
                        experiment=experiment,
                        rollback_path=rollback_path,
                        source_revision=revision,
                        environment=execution_environment,
                        traceability=traceability,
                        workspace_ref=execution_workspace_ref,
                    )
                    receipts.append(receipt)
                    deployment_evidence = receipt_to_w4_evidence(receipt, traceability=traceability)
                    eid = ingest(deployment_evidence)
                    if eid not in iteration_evidence:
                        iteration_evidence.append(eid)
                    if receipt.outcome.state == TruthState.SUCCESS:
                        promotion = apply_promotion(
                            gate_decision=gate_decision,
                            experiment=experiment,
                            evaluation=evaluation,
                            assurance=assurance,
                            autonomy_decision=act_decision,
                            rollback_path=rollback_path,
                            promotion_class=PromotionClass.DEPLOY,
                            receipt=receipt,
                        )
                        advance(IterationOutcome.PROMOTED)
                        experiments.append(experiment)
                        finish(
                            outcome=IterationOutcome.PROMOTED,
                            assurance_id=assurance.id,
                            assurance_status=assurance.status,
                            experiment_id=experiment.id,
                            evaluation_id=evaluation.id,
                            decision_state=act_decision.state,
                            promotion=promotion,
                            detail="promoted via governed W11 deployment",
                        )
                        continue
                    # The governed deployment did not succeed: no promotion is
                    # recorded; the failure evidence is preserved verbatim and
                    # the governed rollback path decides the outcome below.
                else:
                    promotion = apply_promotion(
                        gate_decision=gate_decision,
                        experiment=experiment,
                        evaluation=evaluation,
                        assurance=assurance,
                        autonomy_decision=act_decision,
                        rollback_path=rollback_path,
                        promotion_class=PromotionClass.MODEL_ONLY,
                        receipt=None,
                    )
                    promotion_evidence = _loop_evidence(
                        **evidence_kwargs(
                            EvidenceKind.OBSERVATION,
                            f"promotion:{promotion.id}",
                            TruthfulValue(
                                TruthState.SUCCESS, promotion.promotion_ref,
                                "model-only promotion recorded; no execution dispatched",
                            ),
                            "w12-optimization-loop",
                        )
                    )
                    eid = ingest(promotion_evidence)
                    if eid not in iteration_evidence:
                        iteration_evidence.append(eid)
                    advance(IterationOutcome.PROMOTED)
                    experiments.append(experiment)
                    finish(
                        outcome=IterationOutcome.PROMOTED,
                        assurance_id=assurance.id,
                        assurance_status=assurance.status,
                        experiment_id=experiment.id,
                        evaluation_id=evaluation.id,
                        decision_state=act_decision.state,
                        promotion=promotion,
                        detail="promoted in model-only mode (no execution dispatched)",
                    )
                    continue
            elif act_decision.state == AutonomyDecisionState.ASK:
                advance(IterationOutcome.PAUSED_PENDING_AUTHORIZATION)
                pause(
                    act_decision,
                    f"W9 ASK paused the loop at the promotion gate: {act_decision.rationale}",
                    evaluation_id=evaluation.id,
                )
                break
            elif act_decision.state == AutonomyDecisionState.REJECT:
                advance(IterationOutcome.REFUSED)
                experiments.append(experiment)
                finish(
                    outcome=IterationOutcome.REFUSED,
                    assurance_id=assurance.id,
                    assurance_status=assurance.status,
                    experiment_id=experiment.id,
                    evaluation_id=evaluation.id,
                    decision_state=act_decision.state,
                    detail=f"W9 refused the promotion: {act_decision.rationale}",
                )
                continue
            elif act_decision.state == AutonomyDecisionState.GATHER_EVIDENCE:
                advance(IterationOutcome.GATHER_EVIDENCE)
                experiments.append(experiment)
                finish(
                    outcome=IterationOutcome.GATHER_EVIDENCE,
                    assurance_id=assurance.id,
                    assurance_status=assurance.status,
                    experiment_id=experiment.id,
                    evaluation_id=evaluation.id,
                    decision_state=act_decision.state,
                    detail=f"W9 requires more evidence: {act_decision.rationale}",
                )
                continue
            else:
                raise OptimizationContractError(
                    f"unhandled W9 ACT-gate state {act_decision.state.value}"
                )

        # -- not promoted: governed rollback (W8 + W9) --------------------------
        rollback_decision = evaluate_autonomy(
            policy=policy,
            action=DecisionAction.ROLLBACK,
            assurance=assurance,
            experiment=experiment,
            promotion=None,
            evaluation=evaluation,
            evidence_ids=tuple(evaluation.evidence_ids),
            traceability=traceability,
            known_evidence=known_evidence,
            human_authority_present=human_authority_present,
            blast_radius=blast_radius,
            risk=risk,
            confidence=confidence,
            reversible=reversible,
            rollback_path=rollback_path,
        )
        decisions.append(rollback_decision)
        decision_ids.append(rollback_decision.id)
        if phase == IterationOutcome.EVALUATED:
            # The deploy-failure path already advanced past the ACT decision.
            advance(IterationOutcome.DECIDED)

        if rollback_decision.state == AutonomyDecisionState.ROLLBACK:
            experiment = transition_experiment(experiment, ExperimentState.ROLLED_BACK)
            rollback_evidence_record = _loop_evidence(
                **evidence_kwargs(
                    EvidenceKind.ROLLBACK,
                    f"rollback:{rollback_path.reference}",
                    TruthfulValue(
                        TruthState.SUCCESS, rollback_path.reference,
                        "governed rollback applied (model-only experiment lifecycle transition)",
                    ),
                    "w12-optimization-loop",
                )
            )
            eid = ingest(rollback_evidence_record)
            if eid not in iteration_evidence:
                iteration_evidence.append(eid)
            advance(IterationOutcome.ROLLED_BACK)
            experiments.append(experiment)
            finish(
                outcome=IterationOutcome.ROLLED_BACK,
                assurance_id=assurance.id,
                assurance_status=assurance.status,
                experiment_id=experiment.id,
                evaluation_id=evaluation.id,
                decision_state=rollback_decision.state,
                detail=f"governed rollback applied: {rollback_decision.rationale}",
            )
            continue
        if rollback_decision.state == AutonomyDecisionState.ASK:
            advance(IterationOutcome.PAUSED_PENDING_AUTHORIZATION)
            pause(
                rollback_decision,
                f"W9 ASK paused the loop at the governed rollback: {rollback_decision.rationale}",
                evaluation_id=evaluation.id,
            )
            break
        if rollback_decision.state == AutonomyDecisionState.REJECT:
            advance(IterationOutcome.REFUSED)
            experiments.append(experiment)
            finish(
                outcome=IterationOutcome.REFUSED,
                assurance_id=assurance.id,
                assurance_status=assurance.status,
                experiment_id=experiment.id,
                evaluation_id=evaluation.id,
                decision_state=rollback_decision.state,
                detail=f"W9 refused the governed rollback: {rollback_decision.rationale}",
            )
            continue
        raise OptimizationContractError(
            f"unhandled W9 rollback-gate state {rollback_decision.state.value}"
        )

    if stop is None:
        stop = LoopStop(
            reason=LoopStopReason.COMPLETED,
            iterations_executed=len(iterations),
            detail=(
                f"all {len(ordered)} candidate(s) processed within the bound of {max_iterations}"
                if ordered
                else "no candidates supplied"
            ),
        )

    loop = OptimizationLoop(
        recovered_state_ref=system_state.id,
        recovered_revision=revision,
        base_graph_id=graph.id,
        base_graph_revision=revision,
        provenance_revision=revision,
        max_iterations=max_iterations,
        iterations=tuple(iterations),
        stop=stop,
        traceability=traceability,
    )
    run = OptimizationRun(
        loop=loop,
        evidence_graph=evidence_graph,
        candidates=tuple(ordered),
        assurance_results=tuple(assurance_results),
        experiments=tuple(experiments),
        evaluations=tuple(evaluations),
        promotion_decisions=tuple(promotion_decisions),
        decisions=tuple(decisions),
        receipts=tuple(receipts),
    )
    run.validate()
    return run
