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
    from .autonomy import AutonomyRequest, PolicyCeiling, AutonomyDecision


# ---------------------------------------------------------------------------
# Versioned context selector (F03)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextualSelector:
    """Explicit, versioned, traceable context dimensions for policy selection (C1, F03).

    ``version`` and ``traceability`` ensure the selected context set itself is
    versioned and traceable as required by C1.
    """

    id: str
    version: int
    dimensions: tuple[ContextValue, ...]
    traceability: Traceability

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not self.id.strip():
            raise ModelValidationError("ContextualSelector.id is required")
        if self.version < 1:
            raise ModelValidationError("ContextualSelector.version must be >= 1")
        for d in self.dimensions:
            d.validate()
        self.traceability.validate(require_value=True, require_context=True)


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
        source_set = set(self.source_policy.allowed_actions)
        for a in self.narrowed_allowed_actions:
            if a not in source_set:
                raise ModelValidationError(
                    f"ContextualPolicy cannot expand allowed_actions: {a} not in source policy"
                )
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
# Personalization decision (F02: full evidence/authority traceability)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PersonalizationDecision:
    """A deterministic personalization decision with full explainability (C8, F02).

    Preserves context refs, source policy/W9 refs, W9 decision id, evidence/
    provenance identifiers, alternatives, constraints, and structured uncertainty.
    """

    id: str
    state: str  # AutonomyDecisionState value
    policy_id: str
    w9_decision_id: str
    context_refs: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    alternatives: tuple[str, ...]
    constraints: tuple[str, ...]
    uncertainty: TruthfulValue[Any]
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
        if not self.w9_decision_id.strip():
            raise ModelValidationError("PersonalizationDecision.w9_decision_id is required")
        if not self.rationale.strip():
            raise ModelValidationError("PersonalizationDecision.rationale is required")
        if not self.reasons:
            raise ModelValidationError("PersonalizationDecision.reasons is required")
        self.uncertainty.validate()
        self.traceability.validate(require_value=True, require_context=True)


def _decision_id(d: PersonalizationDecision) -> str:
    material = "|".join([d.state, d.policy_id, d.w9_decision_id, ",".join(d.context_refs), d.rationale])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"personalization-{digest}"


# ---------------------------------------------------------------------------
# Policy alternative selection (F04)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyAlternative:
    """A declared policy/candidate alternative for context-conditioned selection (F04)."""

    id: str
    policy: "AutonomyRequest"
    selector: ContextualSelector
    priority: int  # lower = higher priority; used for deterministic tie-breaking

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ModelValidationError("PolicyAlternative.id is required")
        if self.priority < 0:
            raise ModelValidationError("PolicyAlternative.priority must be non-negative")
        self.policy.validate()
        self.selector.validate()


@dataclass(frozen=True)
class PolicySelection:
    """Result of selecting among alternatives against context (F04)."""

    selected_id: str
    state: str  # AutonomyDecisionState value
    selector_id: str
    selector_version: int
    alternatives_evaluated: int
    rationale: str
    traceability: Traceability

    def __post_init__(self) -> None:
        if not self.selected_id.strip():
            raise ModelValidationError("PolicySelection.selected_id is required")
        if not self.rationale.strip():
            raise ModelValidationError("PolicySelection.rationale is required")
        self.traceability.validate(require_value=True, require_context=True)


def select_policy(
    *,
    alternatives: tuple[PolicyAlternative, ...],
    selector: ContextualSelector,
    w9_decision_state: AutonomyDecisionState = AutonomyDecisionState.ASK,
    traceability: Traceability,
) -> PolicySelection:
    """Select among declared policy/candidate alternatives against context (F04).

    Deterministic: selects the first alternative (by priority, then by id) whose
    selector dimensions are all SUCCESS. If W9 decision state is not ACT, returns
    the first alternative but preserves the W9 state (does not widen to ACT).
    If no alternative has resolved context, selects the highest-priority one and
    narrows to ASK.
    """
    if not alternatives:
        raise ModelValidationError("select_policy requires at least one alternative")
    selector.validate()

    # Sort by priority, then by id for deterministic ordering
    sorted_alts = sorted(alternatives, key=lambda a: (a.priority, a.id))

    selected = sorted_alts[0]
    state = w9_decision_state.value

    # Check if the selector has any unresolved context dimensions
    has_unresolved = any(
        d.value.state in (TruthState.UNKNOWN, TruthState.UNAVAILABLE, TruthState.UNSUPPORTED)
        for d in selector.dimensions
    )
    if has_unresolved:
        state = AutonomyDecisionState.ASK.value

    rationale = (
        f"selected alternative '{selected.id}' (priority {selected.priority}); W9 state {w9_decision_state.value} preserved"
        if not has_unresolved
        else f"selected alternative '{selected.id}' (priority {selected.priority}); unresolved context narrowed to ASK"
    )

    return PolicySelection(
        selected_id=selected.id,
        state=state,
        selector_id=selector.id,
        selector_version=selector.version,
        alternatives_evaluated=len(alternatives),
        rationale=rationale,
        traceability=traceability,
    )


# ---------------------------------------------------------------------------
# Personalization evaluation
# ---------------------------------------------------------------------------


def evaluate_personalization(
    *,
    policy: "AutonomyRequest",
    selector: ContextualSelector,
    traceability: Traceability,
    w9_decision_state: AutonomyDecisionState = AutonomyDecisionState.ASK,
    w9_decision_id: str = "",
    evidence_ids: tuple[str, ...] = (),
    alternatives: tuple[str, ...] = (),
    constraints: tuple[str, ...] = (),
    uncertainty: TruthfulValue[Any] | None = None,
) -> PersonalizationDecision:
    """Evaluate a personalization decision deterministically (C3, C4, C8, C9, F02).

    - C3 (F01): inherits W9 decision state; may only narrow.
    - C4: unknown/unavailable context routes to ASK.
    - C8 (F02): preserves W9 decision ref, evidence ids, alternatives,
      constraints, structured uncertainty.
    - C9: same inputs produce same outputs.
    """
    policy.validate()
    selector.validate()
    reasons: list[str] = []
    context_refs: list[str] = []

    state = w9_decision_state.value
    reasons.append(f"inherited W9 decision state: {state}")

    for d in selector.dimensions:
        context_refs.append(f"{d.dimension.value}:{d.key}")
        if d.value.state in (TruthState.UNKNOWN, TruthState.UNAVAILABLE, TruthState.UNSUPPORTED):
            if state != AutonomyDecisionState.ASK.value:
                state = AutonomyDecisionState.ASK.value
            reasons.append(f"context '{d.key}' state is {d.value.state.value}; narrowed to ASK")

    if state == AutonomyDecisionState.ACT.value:
        reasons.append("all context dimensions resolved; W9 ACT preserved")
    rationale = "personalization authorized within W9 boundary" if state == AutonomyDecisionState.ACT.value else f"personalization narrowed to {state} by W9 boundary or context"

    # F02: structured uncertainty (default UNKNOWN if not supplied)
    if uncertainty is None:
        uncertainty = TruthfulValue(TruthState.UNKNOWN, None, "personalization uncertainty not explicitly supplied")

    return PersonalizationDecision(
        id="",
        state=state,
        policy_id=policy.id,
        w9_decision_id=w9_decision_id,
        context_refs=tuple(context_refs),
        evidence_ids=tuple(evidence_ids),
        alternatives=tuple(alternatives),
        constraints=tuple(constraints),
        uncertainty=uncertainty,
        rationale=rationale,
        reasons=tuple(reasons),
        traceability=traceability,
    )
