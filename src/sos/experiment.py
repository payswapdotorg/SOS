"""W8 experiment, promotion and rollback lifecycle boundary.

This module governs lifecycle state only. It does not deploy software, start
experiments, or execute rollback operations against a live environment.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path

from .assurance import AssuranceResult, AssuranceVerdict
from .model import ModelValidationError, Traceability


class ExperimentStage(str, Enum):
    PROPOSED = "PROPOSED"
    ANALYZED = "ANALYZED"
    ASSURED = "ASSURED"
    TESTED = "TESTED"
    SIMULATED = "SIMULATED"
    REPLAYED = "REPLAYED"
    SHADOW = "SHADOW"
    CANARY = "CANARY"
    EXPERIMENTAL = "EXPERIMENTAL"
    PROMOTED = "PROMOTED"
    ROLLBACK = "ROLLBACK"


LIVE_STAGES = {
    ExperimentStage.SHADOW,
    ExperimentStage.CANARY,
    ExperimentStage.EXPERIMENTAL,
    ExperimentStage.PROMOTED,
}


@dataclass(frozen=True)
class ExperimentDesign:
    population: str
    context: str
    allocation: str
    success_metrics: tuple[str, ...]
    guardrails: tuple[str, ...]

    def validate(self) -> None:
        if not all((self.population, self.context, self.allocation)):
            raise ModelValidationError("ExperimentDesign requires population, context and allocation")
        if not self.success_metrics:
            raise ModelValidationError("ExperimentDesign requires success metrics")
        if not self.guardrails:
            raise ModelValidationError("ExperimentDesign requires guardrails")


@dataclass(frozen=True)
class GuardrailTrigger:
    id: str
    metric: str
    condition: str
    observed_value: str
    evidence_ref: str

    def validate(self) -> None:
        if not all((self.id, self.metric, self.condition, self.observed_value, self.evidence_ref)):
            raise ModelValidationError("GuardrailTrigger requires metric, condition, observed value and evidence reference")


@dataclass(frozen=True)
class RollbackRecord:
    recovery_target_ref: str
    trigger: GuardrailTrigger
    recorded_revision: str

    def validate(self) -> None:
        if not self.recovery_target_ref or not self.recorded_revision:
            raise ModelValidationError("RollbackRecord requires recovery target and revision")
        self.trigger.validate()


@dataclass(frozen=True)
class PromotionDecision:
    authority_ref: str
    authority_evidence_ref: str
    assurance_ref: str
    decision_revision: str

    def validate(self) -> None:
        if not all((self.authority_ref, self.authority_evidence_ref, self.assurance_ref, self.decision_revision)):
            raise ModelValidationError("PromotionDecision requires authority and assurance evidence")


@dataclass(frozen=True)
class Experiment:
    id: str
    candidate_ref: str
    base_system_state_ref: str
    design: ExperimentDesign
    current_stage: ExperimentStage
    assurance_ref: str | None
    promotion: PromotionDecision | None
    rollback: RollbackRecord | None
    traceability: Traceability
    transition_revision: str

    def validate(self) -> None:
        if not self.id or not self.candidate_ref or not self.base_system_state_ref or not self.transition_revision:
            raise ModelValidationError("Experiment requires identity, candidate, base state and transition revision")
        self.design.validate()
        self.traceability.validate(require_value=True, require_context=True)
        if self.current_stage == ExperimentStage.ASSURED and not self.assurance_ref:
            raise ModelValidationError("ASSURED stage requires explicit assurance reference")
        if self.current_stage == ExperimentStage.PROMOTED and self.promotion is None:
            raise ModelValidationError("PROMOTED stage requires promotion decision")
        if self.current_stage == ExperimentStage.ROLLBACK and self.rollback is None:
            raise ModelValidationError("ROLLBACK stage requires rollback record")
        if self.promotion:
            self.promotion.validate()
        if self.rollback:
            self.rollback.validate()

    @classmethod
    def propose(
        cls,
        *,
        identifier: str,
        candidate_ref: str,
        base_system_state_ref: str,
        design: ExperimentDesign,
        traceability: Traceability,
        transition_revision: str,
    ) -> "Experiment":
        experiment = cls(identifier, candidate_ref, base_system_state_ref, design, ExperimentStage.PROPOSED, None, None, None, traceability, transition_revision)
        experiment.validate()
        return experiment


_ALLOWED_NEXT = {
    ExperimentStage.PROPOSED: {ExperimentStage.ANALYZED},
    ExperimentStage.ANALYZED: {ExperimentStage.ASSURED},
    ExperimentStage.ASSURED: {ExperimentStage.TESTED},
    ExperimentStage.TESTED: {ExperimentStage.SIMULATED, ExperimentStage.REPLAYED},
    ExperimentStage.SIMULATED: {ExperimentStage.SHADOW},
    ExperimentStage.REPLAYED: {ExperimentStage.SHADOW},
    ExperimentStage.SHADOW: {ExperimentStage.CANARY, ExperimentStage.EXPERIMENTAL},
    ExperimentStage.CANARY: {ExperimentStage.EXPERIMENTAL},
    ExperimentStage.EXPERIMENTAL: {ExperimentStage.PROMOTED},
    ExperimentStage.PROMOTED: set(),
    ExperimentStage.ROLLBACK: set(),
}


def advance(
    experiment: Experiment,
    *,
    target: ExperimentStage,
    transition_revision: str,
    assurance: AssuranceResult | None = None,
    assurance_ref: str | None = None,
    promotion: PromotionDecision | None = None,
) -> Experiment:
    """Advance one legal lifecycle step; execution side effects are absent."""
    experiment.validate()
    if target == ExperimentStage.ROLLBACK:
        raise ModelValidationError("Use rollback() with a guardrail trigger for rollback transitions")
    if target not in _ALLOWED_NEXT[experiment.current_stage]:
        raise ModelValidationError(f"Illegal experiment transition: {experiment.current_stage.value} -> {target.value}")

    next_assurance_ref = experiment.assurance_ref
    if target == ExperimentStage.ASSURED:
        if assurance is None or assurance.verdict != AssuranceVerdict.PASS:
            raise ModelValidationError("ASSURED requires a passing W7 AssuranceResult")
        if not assurance_ref:
            raise ModelValidationError("ASSURED requires an explicit assurance reference")
        next_assurance_ref = assurance_ref

    if target == ExperimentStage.PROMOTED:
        if promotion is None:
            raise ModelValidationError("PROMOTED requires explicit PromotionDecision")
        if promotion.assurance_ref != experiment.assurance_ref:
            raise ModelValidationError("Promotion assurance reference must match the experiment assurance reference")
        if not experiment.assurance_ref:
            raise ModelValidationError("Promotion requires an assurance reference")

    updated = Experiment(
        experiment.id, experiment.candidate_ref, experiment.base_system_state_ref, experiment.design,
        target, next_assurance_ref, promotion if target == ExperimentStage.PROMOTED else experiment.promotion,
        experiment.rollback, experiment.traceability, transition_revision,
    )
    updated.validate()
    return updated


def rollback(
    experiment: Experiment,
    *,
    trigger: GuardrailTrigger,
    recovery_target_ref: str,
    transition_revision: str,
) -> Experiment:
    """Record a bounded rollback requirement from any live stage."""
    experiment.validate()
    if experiment.current_stage not in LIVE_STAGES:
        raise ModelValidationError("Rollback is only legal from a live experiment stage")
    record = RollbackRecord(recovery_target_ref, trigger, transition_revision)
    record.validate()
    updated = Experiment(
        experiment.id, experiment.candidate_ref, experiment.base_system_state_ref, experiment.design,
        ExperimentStage.ROLLBACK, experiment.assurance_ref, experiment.promotion, record,
        experiment.traceability, transition_revision,
    )
    updated.validate()
    return updated


def promotion_from_assurance(
    assurance: AssuranceResult,
    *,
    assurance_ref: str,
    authority_ref: str,
    authority_evidence_ref: str,
    decision_revision: str,
) -> PromotionDecision:
    if assurance.verdict != AssuranceVerdict.PASS:
        raise ModelValidationError("PromotionDecision requires passing assurance")
    if not assurance_ref:
        raise ModelValidationError("assurance_ref is required")
    decision = PromotionDecision(authority_ref, authority_evidence_ref, assurance_ref, decision_revision)
    decision.validate()
    return decision


def export_experiment(experiment: Experiment, path: str | Path) -> None:
    payload = {
        "id": experiment.id,
        "candidate_ref": experiment.candidate_ref,
        "base_system_state_ref": experiment.base_system_state_ref,
        "design": {
            "population": experiment.design.population,
            "context": experiment.design.context,
            "allocation": experiment.design.allocation,
            "success_metrics": list(experiment.design.success_metrics),
            "guardrails": list(experiment.design.guardrails),
        },
        "current_stage": experiment.current_stage.value,
        "assurance_ref": experiment.assurance_ref,
        "promotion": None if experiment.promotion is None else {
            "authority_ref": experiment.promotion.authority_ref,
            "authority_evidence_ref": experiment.promotion.authority_evidence_ref,
            "assurance_ref": experiment.promotion.assurance_ref,
            "decision_revision": experiment.promotion.decision_revision,
        },
        "rollback": None if experiment.rollback is None else {
            "recovery_target_ref": experiment.rollback.recovery_target_ref,
            "trigger": {
                "id": experiment.rollback.trigger.id,
                "metric": experiment.rollback.trigger.metric,
                "condition": experiment.rollback.trigger.condition,
                "observed_value": experiment.rollback.trigger.observed_value,
                "evidence_ref": experiment.rollback.trigger.evidence_ref,
            },
            "recorded_revision": experiment.rollback.recorded_revision,
        },
        "transition_revision": experiment.transition_revision,
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
