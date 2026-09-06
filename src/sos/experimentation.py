"""W8 — experimentation + promotion / rollback lifecycle for SOS.

Consumes non-authorizing W7 assurance results and defines deterministic
experiment, evaluation, promotion-gating, containment, and rollback state
semantics without becoming a platform-specific deployment adapter or an autonomy
authority (frozen W8 Work Order; architecture §§4.7–4.9, 9, 13).

Design invariants:

- only a W7 assurance result with status PASS can enter an executable experiment
  state (READY/RUNNING); FAIL/UNKNOWN/BLOCKED remain distinguishable and cannot
  become execution-ready (C2);
- experiments are bounded: explicit mode (SHADOW/CANARY/CONTROLLED), scope,
  observation window, success criteria, stop conditions, rollback reference —
  no hidden unbounded execution (C3);
- evidence evaluation is truthful: W4 evidence truth states are preserved;
  UNKNOWN/FAILED/UNAVAILABLE evidence cannot produce a promotion PASS (C4);
- hard stop conditions cannot be offset by favorable objectives (C5);
- promotion is an explicit gated transition requiring successful experiment
  evaluation + rollback/containment; no implicit promotion from completion, no
  confidence-only shortcut (C6);
- rollback/containment is explicit and required for promotion eligibility unless
  a documented governed containment exception is referenced (C7);
- lifecycle state transitions are validated; rollback cannot bypass required
  intermediate semantics (C8);
- multi-objective integrity: W6 objectives + W7 impact/risk/uncertainty are
  preserved; no single scalar becomes authoritative (C9);
- W8 owns experimentation/promotion/rollback lifecycle only — no W9 autonomy/
  ASK, no W10 platform/personalization, no W7 authority re-export (C12).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING

from .model import ModelValidationError, Traceability, TruthState, TruthfulValue

if TYPE_CHECKING:
    from .assurance import AssuranceResult


# ---------------------------------------------------------------------------
# Frozen vocabulary
# ---------------------------------------------------------------------------


class ExperimentMode(str, Enum):
    """Bounded experiment modes (architecture §9)."""

    SHADOW = "shadow"
    CANARY = "canary"
    CONTROLLED = "controlled"


class ExperimentState(str, Enum):
    """Experiment lifecycle states (architecture §9)."""

    PLANNED = "planned"
    READY = "ready"
    RUNNING = "running"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


# ---------------------------------------------------------------------------
# Stop condition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StopCondition:
    """An explicit hard-stop condition that cannot be optimized away (C5)."""

    name: str
    threshold: float
    metric: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ModelValidationError("StopCondition.name is required")
        if not self.metric.strip():
            raise ModelValidationError("StopCondition.metric is required")


# ---------------------------------------------------------------------------
# Rollback path
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RollbackPath:
    """A governed rollback/recovery reference backed by evidence (C7).

    ``recovered`` is False on construction — it is set True only by an explicit
    recovery state transition. W8 models rollback lifecycle; it does not invent
    or silently downgrade recovery guarantees.
    """

    reference: str
    evidence_ids: tuple[str, ...]
    detail: str
    recovered: bool = False

    def __post_init__(self) -> None:
        if not self.reference.strip():
            raise ModelValidationError("RollbackPath.reference is required")
        if not self.evidence_ids:
            raise ModelValidationError("RollbackPath.evidence_ids is required")
        if not self.detail.strip():
            raise ModelValidationError("RollbackPath.detail is required")

    def validate(self, known_evidence: dict[str, Any] | None = None) -> None:
        if known_evidence is not None:
            for eid in self.evidence_ids:
                if eid not in known_evidence:
                    raise ModelValidationError(
                        f"RollbackPath references unknown evidence id '{eid}'"
                    )

    def with_recovered(self, recovered: bool) -> "RollbackPath":
        return RollbackPath(
            reference=self.reference, evidence_ids=self.evidence_ids,
            detail=self.detail, recovered=recovered,
        )


# ---------------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Experiment:
    """A bounded experiment consuming a W7 assurance result for a candidate.

    Binds to the exact candidate id, assurance result id, base graph id/revision,
    provenance revision, and W1 traceability (C1). Only a PASS assurance result
    can transition to executable states (READY/RUNNING) (C2).
    """

    id: str
    candidate_id: str
    assurance_result_id: str
    base_graph_id: str
    base_graph_revision: str
    provenance_revision: str
    mode: ExperimentMode
    scope: tuple[str, ...]
    observation_window: tuple[str, str]
    success_criteria: tuple[str, ...]
    stop_conditions: tuple[StopCondition, ...]
    rollback_ref: str
    traceability: Traceability
    state: ExperimentState = ExperimentState.PLANNED
    containment_policy_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", _experiment_id(self))
        self.validate()

    def validate(self, *, known_assurance: "AssuranceResult | None" = None) -> None:
        if not self.candidate_id.strip():
            raise ModelValidationError("Experiment.candidate_id is required")
        if not self.assurance_result_id.strip():
            raise ModelValidationError("Experiment.assurance_result_id is required")
        if not self.base_graph_id.strip():
            raise ModelValidationError("Experiment.base_graph_id is required")
        if not self.base_graph_revision.strip():
            raise ModelValidationError("Experiment.base_graph_revision is required")
        if not self.provenance_revision.strip():
            raise ModelValidationError("Experiment.provenance_revision is required")
        if not isinstance(self.mode, ExperimentMode):
            raise ModelValidationError("Experiment.mode must be an ExperimentMode")
        if not self.scope:
            raise ModelValidationError("Experiment.scope is required")
        if len(self.observation_window) != 2:
            raise ModelValidationError("Experiment.observation_window must be a (start, end) pair")
        if not self.success_criteria:
            raise ModelValidationError("Experiment.success_criteria is required")
        if not self.stop_conditions:
            raise ModelValidationError("Experiment.stop_conditions is required (C5)")
        self.traceability.validate(require_value=True, require_context=True)
        # C1: if known_assurance supplied, candidate/assurance/graph must match.
        if known_assurance is not None:
            if self.candidate_id != known_assurance.candidate_id:
                raise ModelValidationError(
                    f"Experiment.candidate_id '{self.candidate_id}' does not match assurance result's candidate '{known_assurance.candidate_id}'"
                )
            if self.assurance_result_id != known_assurance.id:
                raise ModelValidationError(
                    f"Experiment.assurance_result_id '{self.assurance_result_id}' does not match assurance result id '{known_assurance.id}'"
                )
            if self.base_graph_id != known_assurance.base_graph_id:
                raise ModelValidationError(
                    f"Experiment.base_graph_id '{self.base_graph_id}' does not match assurance result's graph '{known_assurance.base_graph_id}'"
                )


def _experiment_id(e: Experiment) -> str:
    """Content-addressed identity for the experiment."""
    material = "|".join([
        e.candidate_id, e.assurance_result_id, e.base_graph_id, e.base_graph_revision,
        e.provenance_revision, e.mode.value, ",".join(e.scope),
        ",".join(e.success_criteria), e.rollback_ref or "", e.containment_policy_ref or "",
    ])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"experiment-{digest}"


# ---------------------------------------------------------------------------
# Validated lifecycle transitions (C8)
# ---------------------------------------------------------------------------


# Valid direct transitions FROM -> {allowed TO states}
_VALID_TRANSITIONS: dict[ExperimentState, frozenset[ExperimentState]] = {
    ExperimentState.PLANNED: frozenset({ExperimentState.READY, ExperimentState.FAILED}),
    ExperimentState.READY: frozenset({ExperimentState.RUNNING, ExperimentState.STOPPED, ExperimentState.FAILED}),
    ExperimentState.RUNNING: frozenset({ExperimentState.STOPPED, ExperimentState.COMPLETED, ExperimentState.FAILED, ExperimentState.ROLLED_BACK}),
    ExperimentState.STOPPED: frozenset({ExperimentState.ROLLED_BACK, ExperimentState.FAILED}),
    ExperimentState.COMPLETED: frozenset({ExperimentState.ROLLED_BACK}),
    ExperimentState.FAILED: frozenset({ExperimentState.ROLLED_BACK}),
    ExperimentState.ROLLED_BACK: frozenset(),
}


def transition_experiment(
    experiment: Experiment,
    new_state: ExperimentState,
    *,
    known_assurance: "AssuranceResult | None" = None,
) -> Experiment:
    """Transition an experiment to a new lifecycle state with validation (C8).

    C2: only a PASS assurance result can enter an executable state (READY/RUNNING).
    C8: invalid transitions are rejected; rollback cannot bypass intermediate
    semantics (PLANNED -> ROLLED_BACK is not valid).
    """
    experiment.validate(known_assurance=known_assurance)
    if new_state not in _VALID_TRANSITIONS.get(experiment.state, frozenset()):
        raise ModelValidationError(
            f"invalid experiment transition: {experiment.state.value} -> {new_state.value}"
        )
    # C2: entry assurance gate — executable states require PASS assurance.
    if new_state in (ExperimentState.READY, ExperimentState.RUNNING):
        if known_assurance is None:
            raise ModelValidationError(
                f"transition to {new_state.value} requires known_assurance to verify PASS status"
            )
        if known_assurance.status.value != "PASS":
            raise ModelValidationError(
                f"only a PASS assurance result can enter {new_state.value}; "
                f"assurance status is {known_assurance.status.value}"
            )
    return Experiment(
        id=experiment.id, candidate_id=experiment.candidate_id,
        assurance_result_id=experiment.assurance_result_id,
        base_graph_id=experiment.base_graph_id,
        base_graph_revision=experiment.base_graph_revision,
        provenance_revision=experiment.provenance_revision,
        mode=experiment.mode, scope=experiment.scope,
        observation_window=experiment.observation_window,
        success_criteria=experiment.success_criteria,
        stop_conditions=experiment.stop_conditions, rollback_ref=experiment.rollback_ref,
        traceability=experiment.traceability, state=new_state,
        containment_policy_ref=experiment.containment_policy_ref,
    )


# ---------------------------------------------------------------------------
# Experiment evaluation (truthful, bounded, multi-objective)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExperimentEvaluation:
    """A truthful, bounded evaluation of an experiment's observed evidence.

    ``promotion_eligible`` is True only when: (a) evaluation_success was supplied,
    (b) no hard stop fired, (c) all referenced evidence is SUCCESS, and (d)
    rollback or a documented containment exception is present. Promotion is an
    explicit gate decision, not implicit (C6).
    """

    id: str
    experiment_id: str
    evidence_ids: tuple[str, ...]
    evidence_results: dict[str, TruthState]
    objectives: tuple[Any, ...]
    promotion_eligible: bool
    stopped: bool
    detail: str
    traceability: Traceability

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", _evaluation_id(self))
        self.validate()

    def validate(self) -> None:
        if not self.experiment_id.strip():
            raise ModelValidationError("ExperimentEvaluation.experiment_id is required")
        self.traceability.validate(require_value=True, require_context=True)


def _evaluation_id(ev: ExperimentEvaluation) -> str:
    material = "|".join([
        ev.experiment_id, ",".join(ev.evidence_ids),
        str(ev.promotion_eligible), str(ev.stopped),
    ])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"eval-{digest}"


def evaluate_experiment(
    experiment: Experiment,
    *,
    known_evidence: dict[str, Any],
    evaluation_success: bool = False,
    stop_trigger: tuple[str, ...] = (),
    known_assurance: "AssuranceResult | None" = None,
) -> ExperimentEvaluation:
    """Evaluate an experiment's observed evidence truthfully (C4, C5, C9).

    - C4: evidence truth states are preserved; UNKNOWN/FAILED/UNAVAILABLE
      evidence cannot produce promotion eligibility.
    - C5: a fired stop condition stops the experiment and cannot be offset by
      favorable objectives.
    - C7: promotion eligibility requires rollback or a documented containment
      exception.
    - C9: objectives are preserved (no scalar).
    """
    experiment.validate()
    evidence_ids: list[str] = []
    evidence_results: dict[str, TruthState] = {}
    all_success = True
    for eid, ev in known_evidence.items():
        evidence_ids.append(eid)
        state = ev.result.state if hasattr(ev, "result") else TruthState.UNKNOWN
        evidence_results[eid] = state
        if state != TruthState.SUCCESS:
            all_success = False

    # C5: hard stop conditions fire — cannot be offset by objectives.
    stopped = len(stop_trigger) > 0

    # C7: rollback or documented containment exception required for eligibility.
    has_rollback = bool(experiment.rollback_ref and experiment.rollback_ref.strip())
    has_containment = experiment.containment_policy_ref is not None and experiment.containment_policy_ref.strip() != ""
    recovery_satisfied = has_rollback or has_containment

    # C4 + C6: promotion eligibility requires: evaluation_success + all evidence
    # SUCCESS + no hard stop + recovery satisfied.
    promotion_eligible = (
        evaluation_success
        and all_success
        and not stopped
        and recovery_satisfied
    )

    detail_parts: list[str] = []
    if stopped:
        detail_parts.append(f"hard stop fired: {', '.join(stop_trigger)}")
    if not all_success:
        detail_parts.append("non-SUCCESS evidence present")
    if not recovery_satisfied:
        detail_parts.append("no rollback or documented containment exception")
    if evaluation_success and all_success and not stopped and recovery_satisfied:
        detail_parts.append("promotion eligible")
    elif evaluation_success and all_success and not stopped and not recovery_satisfied:
        detail_parts.append("evaluation succeeded but recovery not satisfied")
    detail = "; ".join(detail_parts) if detail_parts else "evaluation complete"

    return ExperimentEvaluation(
        id="",
        experiment_id=experiment.id,
        evidence_ids=tuple(evidence_ids),
        evidence_results=evidence_results,
        objectives=known_assurance.objectives if known_assurance is not None else (),  # C9: preserve W6 objectives
        promotion_eligible=promotion_eligible,
        stopped=stopped,
        detail=detail,
        traceability=experiment.traceability,
    )


# ---------------------------------------------------------------------------
# Promotion gate (explicit, non-implicit, non-confidence-only)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PromotionDecision:
    """An explicit promotion decision with a rationale (C6)."""

    promoted: bool
    rationale: str
    experiment_id: str
    evaluation_id: str

    def __post_init__(self) -> None:
        if not self.rationale.strip():
            raise ModelValidationError("PromotionDecision.rationale is required")


@dataclass(frozen=True)
class PromotionGate:
    """An explicit promotion gate (C6).

    Promotion requires: a W7 PASS assurance result, a promotion-eligible
    experiment evaluation, and (transitively) rollback/containment. There is no
    implicit promotion from experiment completion and no confidence-only
    shortcut.
    """

    def evaluate(
        self,
        experiment: Experiment,
        evaluation: ExperimentEvaluation,
        *,
        known_assurance: "AssuranceResult",
    ) -> PromotionDecision:
        experiment.validate(known_assurance=known_assurance)
        # C2: assurance must be PASS.
        if known_assurance.status.value != "PASS":
            return PromotionDecision(
                promoted=False,
                rationale=f"assurance status is {known_assurance.status.value}, not PASS",
                experiment_id=experiment.id, evaluation_id=evaluation.id,
            )
        # C6: promotion requires promotion-eligible evaluation.
        if not evaluation.promotion_eligible:
            return PromotionDecision(
                promoted=False,
                rationale=f"evaluation not promotion-eligible: {evaluation.detail}",
                experiment_id=experiment.id, evaluation_id=evaluation.id,
            )
        return PromotionDecision(
            promoted=True,
            rationale="assurance PASS + promotion-eligible evaluation + recovery satisfied",
            experiment_id=experiment.id, evaluation_id=evaluation.id,
        )
