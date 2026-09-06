"""W10 — contextual personalization boundary for SOS.

Represents explicit context dimensions relevant to policy selection, selects
bounded policies/candidates against context while preserving global constraints,
and preserves W9 authority (context may narrow but never widen).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from .model import ModelValidationError, Traceability, TruthState, TruthfulValue, ContextDimension, ContextValue, DecisionAction
from .autonomy import AutonomyDecisionState

if TYPE_CHECKING:
    from .autonomy import AutonomyRequest, PolicyCeiling


# ---------------------------------------------------------------------------
# Contextual selector
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextualSelector:
    """Explicit context dimensions for policy selection (C1)."""

    dimensions: tuple[ContextValue, ...]

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        # dimensions may be empty — a policy with no context narrowing is valid
        for d in self.dimensions:
            d.validate()


# ---------------------------------------------------------------------------
# Contextual policy (narrowed W9 policy)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextualPolicy:
    """A W9 policy narrowed by context (C2, C3).

    ``narrowed_allowed_actions`` must be a subset of ``source_policy.allowed_actions``.
    ``narrowed_ceilings`` must be stricter than or equal to ``source_policy.ceilings``.
    Context may narrow but never widen.
    """

    id: str
    version: int
    source_policy: "AutonomyRequest"
    selector: ContextualSelector
    narrowed_allowed_actions: tuple[Any, ...]
    narrowed_ceilings: "PolicyCeiling"
    traceability: Traceability

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not self.id.strip():
            raise ModelValidationError("ContextualPolicy.id is required")
        if self.version < 1:
            raise ModelValidationError("ContextualPolicy.version must be >= 1")
        self.source_policy.validate()
        self.selector.validate()
        if not self.narrowed_allowed_actions:
            raise ModelValidationError("ContextualPolicy.narrowed_allowed_actions is required")
        # C3: narrowed_allowed_actions must be a subset of source_policy.allowed_actions
        source_set = set(self.source_policy.allowed_actions)
        for a in self.narrowed_allowed_actions:
            if a not in source_set:
                raise ModelValidationError(
                    f"ContextualPolicy cannot expand allowed_actions: {a} not in source policy"
                )
        # C3: narrowed_ceilings must be stricter (not relaxed)
        sc = self.source_policy.ceilings
        nc = self.narrowed_ceilings
        if nc.max_risk > sc.max_risk:
            raise ModelValidationError(
                f"ContextualPolicy cannot relax max_risk: {nc.max_risk} > {sc.max_risk}"
            )
        if _blast_rank(nc.max_blast_radius) > _blast_rank(sc.max_blast_radius):
            raise ModelValidationError(
                f"ContextualPolicy cannot widen max_blast_radius: {nc.max_blast_radius} > {sc.max_blast_radius}"
            )
        if sc.require_reversible and not nc.require_reversible:
            raise ModelValidationError("ContextualPolicy cannot relax require_reversible")
        if nc.min_confidence < sc.min_confidence:
            raise ModelValidationError(
                f"ContextualPolicy cannot lower min_confidence: {nc.min_confidence} < {sc.min_confidence}"
            )
        if sc.require_human_approval_for_act and not nc.require_human_approval_for_act:
            raise ModelValidationError("ContextualPolicy cannot waive human approval")
        self.traceability.validate(require_value=True, require_context=True)


_BLAST_ORDER: dict[str, int] = {"none": 0, "limited": 1, "service": 2, "system": 3, "organization": 4}


def _blast_rank(level: str) -> int:
    return _BLAST_ORDER.get(level, 0)


# ---------------------------------------------------------------------------
# Personalization decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PersonalizationDecision:
    """A deterministic personalization decision (C8, C9)."""

    id: str
    state: str  # AutonomyDecisionState value
    policy_id: str
    context_refs: tuple[str, ...]
    rationale: str
    reasons: tuple[str, ...]
    traceability: Traceability

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", _decision_id(self))
        self.validate()

    def validate(self) -> None:
        if not self.state.strip():
            raise ModelValidationError("PersonalizationDecision.state is required")
        if not self.policy_id.strip():
            raise ModelValidationError("PersonalizationDecision.policy_id is required")
        if not self.rationale.strip():
            raise ModelValidationError("PersonalizationDecision.rationale is required")
        if not self.reasons:
            raise ModelValidationError("PersonalizationDecision.reasons is required")
        self.traceability.validate(require_value=True, require_context=True)


def _decision_id(d: PersonalizationDecision) -> str:
    material = "|".join([d.state, d.policy_id, ",".join(d.context_refs), d.rationale])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"personalization-{digest}"


# ---------------------------------------------------------------------------
# Personalization evaluation
# ---------------------------------------------------------------------------


def evaluate_personalization(
    *,
    policy: "AutonomyRequest",
    selector: ContextualSelector,
    traceability: Traceability,
    w9_decision_state: AutonomyDecisionState = AutonomyDecisionState.ASK,
) -> PersonalizationDecision:
    """Evaluate a personalization decision deterministically (C3, C4, C9).

    - C3 (SOS-W10-F01): inherits the W9 decision state; resolved context may
      narrow an already-authorized option (ACT) but CANNOT turn ASK/REJECT into
      ACT. The personalization state starts as the W9 decision state and can
      only be narrowed (never widened).
    - C4: unknown/unavailable context routes to ASK.
    - C9: same inputs produce same outputs.
    """
    policy.validate()
    selector.validate()
    reasons: list[str] = []
    context_refs: list[str] = []

    # SOS-W10-F01: inherit W9 decision state. Personalization may only narrow.
    state = w9_decision_state.value
    reasons.append(f"inherited W9 decision state: {state}")

    for d in selector.dimensions:
        context_refs.append(f"{d.dimension.value}:{d.key}")
        if d.value.state in (TruthState.UNKNOWN, TruthState.UNAVAILABLE, TruthState.UNSUPPORTED):
            # C4: unresolved context narrows to ASK (never widens to ACT)
            if state != AutonomyDecisionState.ASK.value:
                state = AutonomyDecisionState.ASK.value
            reasons.append(f"context '{d.key}' state is {d.value.state.value}; narrowed to ASK")

    if state == AutonomyDecisionState.ACT.value:
        reasons.append("all context dimensions resolved; W9 ACT preserved")
    rationale = "personalization authorized within W9 boundary" if state == AutonomyDecisionState.ACT.value else f"personalization narrowed to {state} by W9 boundary or context"

    return PersonalizationDecision(
        id="",
        state=state,
        policy_id=policy.id,
        context_refs=tuple(context_refs),
        rationale=rationale,
        reasons=tuple(reasons),
        traceability=traceability,
    )
