"""W10 — contextual personalization boundary for SOS.

Represents explicit context dimensions relevant to policy selection, selects
bounded policies/candidates against context while preserving global constraints,
and preserves W9 authority (context may narrow but never widen).

Architect review iteration 4 corrections (findings A1–A4):

- A1: alternative selection is a TRUE predicate over the SUPPLIED context —
  for every dimension an alternative declares, the supplied selector must
  contain a corresponding resolvable value equal to the alternative's declared
  constraint; a SUCCESS flag on the alternative's own declaration alone never
  implies compatibility;
- A2: every non-SUCCESS supplied truth state (FAILED and EMPTY included)
  narrows the decision — no non-SUCCESS state is collapsed into success, so a
  FAILED context can never silently preserve ACT;
- A3: all state adjustment is monotonic in the W9 decision-state lattice
  (``narrow_decision_state``): inherited REJECT/ROLLBACK survive, ACT may
  narrow to ASK, and nothing ever moves to a less restrictive state;
- A4: selection results carry per-alternative evaluation evidence, the
  inherited W9 state, and the narrowing chain (inherited → final, with
  reasons), JSON-round-trippable and strictly additive to the existing
  dataclass contract.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, TYPE_CHECKING

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
# Monotonic narrowing in the W9 decision-state lattice (A3, C3)
# ---------------------------------------------------------------------------


# Restriction ranks over the W9 ``AutonomyDecisionState`` lattice, derived from
# the frozen W9 transition contract (``src/sos/autonomy.py``, SOS-W9-F19):
# ACT is the only authorizing state (least restrictive); EXPERIMENT and
# GATHER_EVIDENCE are non-authorizing forward-lifecycle states; ASK gates on
# human authority; REJECT and ROLLBACK are terminal non-authorization (most
# restrictive). W10 narrowing may only move to a state at least as restrictive
# as the inherited W9 state — it may never widen authority (C3).
_RESTRICTION_RANK: dict[AutonomyDecisionState, int] = {
    AutonomyDecisionState.ACT: 0,
    AutonomyDecisionState.EXPERIMENT: 1,
    AutonomyDecisionState.GATHER_EVIDENCE: 1,
    AutonomyDecisionState.ASK: 2,
    AutonomyDecisionState.REJECT: 3,
    AutonomyDecisionState.ROLLBACK: 3,
}


def narrow_decision_state(
    inherited: AutonomyDecisionState,
    candidate: AutonomyDecisionState,
) -> AutonomyDecisionState:
    """Monotonic narrowing in the W9 decision-state lattice (A3, C3).

    Returns ``candidate`` only when it is strictly MORE restrictive than
    ``inherited``; otherwise returns ``inherited``. Consequently:

    - inherited ``REJECT`` stays ``REJECT`` (an ASK candidate is less
      restrictive and is refused);
    - inherited ``ROLLBACK`` stays ``ROLLBACK``;
    - ``ACT`` may narrow to ``ASK``;
    - nothing ever moves to a LESS restrictive state than inherited, so W10
      can never upgrade W9 authority (C3).
    """
    if not isinstance(inherited, AutonomyDecisionState):
        raise ModelValidationError(
            f"inherited state must be an AutonomyDecisionState, got {inherited!r}"
        )
    if not isinstance(candidate, AutonomyDecisionState):
        raise ModelValidationError(
            f"candidate state must be an AutonomyDecisionState, got {candidate!r}"
        )
    if _RESTRICTION_RANK[candidate] > _RESTRICTION_RANK[inherited]:
        return candidate
    return inherited


# ---------------------------------------------------------------------------
# Alternative selection as a predicate over the SUPPLIED context (A1, F04)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyAlternative:
    """A declared policy/candidate alternative for context-conditioned selection (F04).

    ``selector`` declares the alternative's context constraints: for every
    declared dimension the SUPPLIED selector must carry a corresponding
    resolvable (SUCCESS) value equal to the declared value for the alternative
    to be context-compatible (A1).
    """

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


# Per-dimension supplied-context outcomes for one declared alternative (A4).
_OUTCOME_MATCHED = "matched"
_OUTCOME_MISMATCHED = "mismatched"
_OUTCOME_UNRESOLVED = "unresolved"
# Recorded as the supplied truth state when the declared dimension is entirely
# absent from the supplied selector (A1: absent dimensions are unresolved).
_SUPPLIED_ABSENT = "ABSENT"


@dataclass(frozen=True)
class AlternativeDimensionEvaluation:
    """A4: the supplied-context outcome for ONE declared dimension of an alternative.

    ``outcome`` is ``matched`` (dimension identity + resolvable supplied value
    + value equality with the declared constraint), ``mismatched`` (both sides
    resolvable but the values differ), or ``unresolved`` (the dimension is
    absent from the supplied selector — ``supplied_state`` is ``ABSENT`` — or
    either side carries a non-SUCCESS truth state, recorded verbatim).
    """

    dimension: str  # ContextDimension value declared by the alternative
    key: str
    outcome: str
    declared_state: str  # TruthState value declared by the alternative
    supplied_state: str  # TruthState value in the supplied selector, or ABSENT
    declared_value: Any = None
    supplied_value: Any = None

    def __post_init__(self) -> None:
        if not self.dimension.strip():
            raise ModelValidationError("AlternativeDimensionEvaluation.dimension is required")
        if not self.key.strip():
            raise ModelValidationError("AlternativeDimensionEvaluation.key is required")
        if self.outcome not in (_OUTCOME_MATCHED, _OUTCOME_MISMATCHED, _OUTCOME_UNRESOLVED):
            raise ModelValidationError(
                f"AlternativeDimensionEvaluation.outcome '{self.outcome}' is not one of "
                f"{_OUTCOME_MATCHED}/{_OUTCOME_MISMATCHED}/{_OUTCOME_UNRESOLVED}"
            )
        known_states = {s.value for s in TruthState}
        if self.declared_state not in known_states:
            raise ModelValidationError(
                f"AlternativeDimensionEvaluation.declared_state '{self.declared_state}' is not a TruthState value"
            )
        if self.supplied_state not in known_states | {_SUPPLIED_ABSENT}:
            raise ModelValidationError(
                f"AlternativeDimensionEvaluation.supplied_state '{self.supplied_state}' is not a TruthState value or ABSENT"
            )


@dataclass(frozen=True)
class AlternativeEvaluation:
    """A4: per-alternative evaluation evidence — id, context-compatibility, and
    the supplied-context outcome for every declared dimension."""

    alternative_id: str
    compatible: bool
    dimension_evaluations: tuple[AlternativeDimensionEvaluation, ...] = ()

    def __post_init__(self) -> None:
        if not self.alternative_id.strip():
            raise ModelValidationError("AlternativeEvaluation.alternative_id is required")
        if not isinstance(self.compatible, bool):
            raise ModelValidationError("AlternativeEvaluation.compatible must be a bool")
        for e in self.dimension_evaluations:
            e.__post_init__()


@dataclass(frozen=True)
class StateNarrowingStep:
    """A4: one monotonic narrowing step of the W9 decision state (from → to, with reason)."""

    from_state: str  # AutonomyDecisionState value before the step
    to_state: str  # AutonomyDecisionState value after the step
    reason: str

    def __post_init__(self) -> None:
        known_states = {s.value for s in AutonomyDecisionState}
        if self.from_state not in known_states:
            raise ModelValidationError(
                f"StateNarrowingStep.from_state '{self.from_state}' is not an AutonomyDecisionState value"
            )
        if self.to_state not in known_states:
            raise ModelValidationError(
                f"StateNarrowingStep.to_state '{self.to_state}' is not an AutonomyDecisionState value"
            )
        if not self.reason.strip():
            raise ModelValidationError("StateNarrowingStep.reason is required")


@dataclass(frozen=True)
class PolicySelection:
    """Result of selecting among alternatives against context (F04).

    A4 (strictly additive fields, safe defaults so previously persisted records
    remain loadable): ``alternative_evaluations`` carries the per-alternative
    evaluation evidence; ``inherited_state`` records the inherited W9 decision
    state; ``narrowing_chain`` records the monotonic steps (from → to, with
    reason) that produced the final ``state`` from ``inherited_state``.
    """

    selected_id: str
    state: str  # AutonomyDecisionState value
    selector_id: str
    selector_version: int
    alternatives_evaluated: int
    rationale: str
    traceability: Traceability
    alternative_evaluations: tuple[AlternativeEvaluation, ...] = ()
    inherited_state: str = ""  # AutonomyDecisionState value
    narrowing_chain: tuple[StateNarrowingStep, ...] = ()

    def __post_init__(self) -> None:
        if not self.selected_id.strip():
            raise ModelValidationError("PolicySelection.selected_id is required")
        if not self.rationale.strip():
            raise ModelValidationError("PolicySelection.rationale is required")
        known_states = {s.value for s in AutonomyDecisionState}
        if self.inherited_state and self.inherited_state not in known_states:
            raise ModelValidationError(
                f"PolicySelection.inherited_state '{self.inherited_state}' is not an AutonomyDecisionState value"
            )
        for evaluation in self.alternative_evaluations:
            evaluation.__post_init__()
        for step in self.narrowing_chain:
            step.__post_init__()
        self.traceability.validate(require_value=True, require_context=True)


def _evaluate_alternative_dimensions(
    alt: PolicyAlternative,
    supplied: Mapping[tuple[str, str], ContextValue],
) -> tuple[AlternativeDimensionEvaluation, ...]:
    """A1: evaluate every dimension an alternative DECLARES against the SUPPLIED context.

    The alternative's selector is a predicate, not a self-declaration: for each
    declared dimension (dimension identity + key) the supplied selector must
    contain a corresponding resolvable (SUCCESS) value equal to the declared
    constraint value. Absent, non-SUCCESS (on either side), or value-mismatched
    supplied context makes the dimension — and therefore the alternative — not
    context-compatible. A SUCCESS flag on the alternative's own declaration
    alone never implies compatibility.
    """
    results: list[AlternativeDimensionEvaluation] = []
    for declared in alt.selector.dimensions:
        supplied_value = supplied.get((declared.dimension.value, declared.key))
        if supplied_value is None:
            results.append(
                AlternativeDimensionEvaluation(
                    dimension=declared.dimension.value,
                    key=declared.key,
                    outcome=_OUTCOME_UNRESOLVED,
                    declared_state=declared.value.state.value,
                    supplied_state=_SUPPLIED_ABSENT,
                    declared_value=declared.value.value,
                    supplied_value=None,
                )
            )
            continue
        if (
            supplied_value.value.state != TruthState.SUCCESS
            or declared.value.state != TruthState.SUCCESS
        ):
            results.append(
                AlternativeDimensionEvaluation(
                    dimension=declared.dimension.value,
                    key=declared.key,
                    outcome=_OUTCOME_UNRESOLVED,
                    declared_state=declared.value.state.value,
                    supplied_state=supplied_value.value.state.value,
                    declared_value=declared.value.value,
                    supplied_value=supplied_value.value.value,
                )
            )
            continue
        if supplied_value.value.value != declared.value.value:
            results.append(
                AlternativeDimensionEvaluation(
                    dimension=declared.dimension.value,
                    key=declared.key,
                    outcome=_OUTCOME_MISMATCHED,
                    declared_state=declared.value.state.value,
                    supplied_state=supplied_value.value.state.value,
                    declared_value=declared.value.value,
                    supplied_value=supplied_value.value.value,
                )
            )
            continue
        results.append(
            AlternativeDimensionEvaluation(
                dimension=declared.dimension.value,
                key=declared.key,
                outcome=_OUTCOME_MATCHED,
                declared_state=declared.value.state.value,
                supplied_state=supplied_value.value.state.value,
                declared_value=declared.value.value,
                supplied_value=supplied_value.value.value,
            )
        )
    return tuple(results)


def select_policy(
    *,
    alternatives: tuple[PolicyAlternative, ...],
    selector: ContextualSelector,
    w9_decision_state: AutonomyDecisionState = AutonomyDecisionState.ASK,
    traceability: Traceability,
) -> PolicySelection:
    """Select among declared policy/candidate alternatives against the SUPPLIED context (F04).

    SOS-W10-F04 / A1: deterministically evaluates each declared alternative as
    a predicate over the SUPPLIED ``selector``: an alternative is
    context-compatible only when every dimension it declares is matched by the
    supplied context — same dimension identity (dimension + key), a resolvable
    (SUCCESS) supplied value, and value equality with the alternative's
    declared constraint. A SUCCESS flag on the alternative's own declaration
    alone never implies compatibility. Among context-compatible alternatives
    the selection order is (priority, id). If no alternative is
    context-compatible, the highest-priority alternative is carried as the
    proposal and the state is narrowed.

    A2: every non-SUCCESS truth state in the supplied selector (FAILED and
    EMPTY included) narrows the decision; no non-SUCCESS state is collapsed
    into success.

    A3: W9 state is inherited and may only narrow — monotonically
    (``narrow_decision_state``): inherited REJECT/ROLLBACK survive, ACT may
    narrow to ASK, nothing ever widens.

    A4: the result records per-alternative evaluation evidence, the inherited
    W9 state, and the narrowing chain (inherited → final, with reasons).
    """
    if not alternatives:
        raise ModelValidationError("select_policy requires at least one alternative")
    selector.validate()

    # A1: index the SUPPLIED context by (dimension, key); the first occurrence
    # wins so duplicate supplied entries are resolved deterministically.
    supplied: dict[tuple[str, str], ContextValue] = {}
    for d in selector.dimensions:
        supplied.setdefault((d.dimension.value, d.key), d)

    evaluations: list[AlternativeEvaluation] = []
    for alt in alternatives:
        dimension_evaluations = _evaluate_alternative_dimensions(alt, supplied)
        evaluations.append(
            AlternativeEvaluation(
                alternative_id=alt.id,
                compatible=all(e.outcome == _OUTCOME_MATCHED for e in dimension_evaluations),
                dimension_evaluations=dimension_evaluations,
            )
        )

    compatible = [alt for alt, evaluation in zip(alternatives, evaluations) if evaluation.compatible]

    state = w9_decision_state
    narrowing: list[StateNarrowingStep] = []

    if compatible:
        # Sort compatible alternatives by (priority, id) for deterministic selection
        ordered = sorted(compatible, key=lambda a: (a.priority, a.id))
        selected = ordered[0]
        rationale = (
            f"selected alternative '{selected.id}' (priority {selected.priority}); "
            f"context-compatible with supplied selector '{selector.id}' v{selector.version}; "
            f"{len(compatible)} compatible of {len(alternatives)} evaluated; "
            f"W9 state {w9_decision_state.value} inherited"
        )
    else:
        # No context-compatible alternative — carry the highest-priority
        # alternative as the proposal and narrow monotonically (A3).
        ordered = sorted(alternatives, key=lambda a: (a.priority, a.id))
        selected = ordered[0]
        narrowed = narrow_decision_state(state, AutonomyDecisionState.ASK)
        if narrowed != state:
            narrowing.append(
                StateNarrowingStep(
                    from_state=state.value,
                    to_state=narrowed.value,
                    reason=(
                        "no context-compatible alternative; "
                        f"narrowed {state.value} -> {narrowed.value} per C4"
                    ),
                )
            )
        state = narrowed
        rationale = (
            f"selected alternative '{selected.id}' (priority {selected.priority}); "
            f"no alternative context-compatible with supplied selector '{selector.id}' v{selector.version}; "
            f"monotonic narrowing {w9_decision_state.value} -> {state.value} per C4; "
            f"{len(alternatives)} evaluated"
        )

    # A2: EVERY non-SUCCESS supplied truth state narrows the decision
    # (FAILED and EMPTY included); A3: monotonically, never widening.
    unresolved = [
        (d.dimension.value, d.key, d.value.state)
        for d in selector.dimensions
        if d.value.state != TruthState.SUCCESS
    ]
    if unresolved:
        detail = "; ".join(f"{dim}:{key} is {st.value}" for dim, key, st in unresolved)
        narrowed = narrow_decision_state(state, AutonomyDecisionState.ASK)
        if narrowed != state:
            narrowing.append(
                StateNarrowingStep(
                    from_state=state.value,
                    to_state=narrowed.value,
                    reason=(
                        f"supplied context unresolved ({detail}); "
                        f"narrowed {state.value} -> {narrowed.value} per C4"
                    ),
                )
            )
            state = narrowed
        rationale += f"; supplied selector has non-SUCCESS truth state(s): {detail}; final state {state.value}"

    return PolicySelection(
        selected_id=selected.id,
        state=state.value,
        selector_id=selector.id,
        selector_version=selector.version,
        alternatives_evaluated=len(alternatives),
        rationale=rationale,
        traceability=traceability,
        alternative_evaluations=tuple(evaluations),
        inherited_state=w9_decision_state.value,
        narrowing_chain=tuple(narrowing),
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

    - C3 (F01/A3): inherits the W9 decision state and may only narrow —
      monotonically in the W9 lattice (``narrow_decision_state``), so an
      inherited REJECT/ROLLBACK is never widened to ASK;
    - C4 (A2): EVERY non-SUCCESS supplied truth state (FAILED and EMPTY
      included) narrows the decision — no non-SUCCESS state is collapsed into
      success, so a FAILED context can never silently preserve ACT;
    - C8 (F02): preserves W9 decision ref, evidence ids, alternatives,
      constraints, structured uncertainty.
    - C9: same inputs produce same outputs.
    """
    policy.validate()
    selector.validate()
    reasons: list[str] = []
    context_refs: list[str] = []

    state = w9_decision_state
    reasons.append(f"inherited W9 decision state: {state.value}")

    for d in selector.dimensions:
        context_refs.append(f"{d.dimension.value}:{d.key}")
        # A2: every non-SUCCESS truth state narrows (FAILED/EMPTY included);
        # A3: monotonically — an inherited REJECT/ROLLBACK is preserved.
        if d.value.state != TruthState.SUCCESS:
            narrowed = narrow_decision_state(state, AutonomyDecisionState.ASK)
            if narrowed != state:
                reasons.append(
                    f"context '{d.key}' state is {d.value.state.value}; "
                    f"narrowed {state.value} -> {narrowed.value}"
                )
                state = narrowed
            else:
                reasons.append(
                    f"context '{d.key}' state is {d.value.state.value}; "
                    f"inherited {state.value} preserved by monotonic narrowing"
                )

    if state == AutonomyDecisionState.ACT:
        reasons.append("all supplied context dimensions resolved; W9 ACT preserved")
    rationale = "personalization authorized within W9 boundary" if state == AutonomyDecisionState.ACT else f"personalization narrowed to {state.value} by W9 boundary or context"

    # F02: structured uncertainty (default UNKNOWN if not supplied)
    if uncertainty is None:
        uncertainty = TruthfulValue(TruthState.UNKNOWN, None, "personalization uncertainty not explicitly supplied")

    return PersonalizationDecision(
        id="",
        state=state.value,
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
