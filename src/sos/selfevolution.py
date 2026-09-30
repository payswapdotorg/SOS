"""W13 — SOS self-evolution / meta-adaptation boundary (first bounded slice).

Implements the governed SELF-EVOLUTION PROPOSAL lifecycle: typed, inert,
content-addressed proposal records carrying diff-shaped source-change payloads
(DATA, never applied) plus a frozen deterministic lifecycle state machine that
COMPOSES the already-merged authorities over proposals that target SOS's own
sources (frozen W13 Work Order; architecture §§2, 4, 9, 11–13):

    SOS current System State (the exact ``target_revision`` citation)
      -> self-improvement hypothesis (``SelfImprovementHypothesis``)
      -> candidate change to SOS (``SelfEvolutionProposal`` + ``SourceChange``)
      -> W7 assurance (a PASS ``AssuranceResult`` bound to the exact chain)
      -> W8 experiment (``Experiment``/``ExperimentEvaluation``/
         ``PromotionGate``/``PromotionDecision`` + bounded ``RollbackPath``)
      -> W9 authority (a resolved ``AutonomyDecision``: ACT / ASK / REJECT /
         ROLLBACK; GATHER_EVIDENCE / EXPERIMENT defer)
      -> promotion / rollback (governed decision records, never execution)
      -> evidence (verbatim W4 records at every consequential step)
      -> new SOS state (``adoption_revision`` cited as data when it exists)

Design invariants (frozen W13 Work Order, acceptance criteria C1–C12):

- composition only: the lifecycle composes the real W1/W4/W5/W6/W7/W8/W9
  types and never redefines an authority (no fifth authority class —
  architecture §12). Every cross-authority reference is chain-checked against
  the exact proposal-id / target-revision / decision chain, and the real W8
  ``PromotionGate`` engine is re-run at every promotion-carrying transition;
- proposal-as-data: the candidate change to SOS sources is inert DATA —
  exact ``target_revision`` citation, typed ``SourceChange`` payloads
  (path / base revision / kind / payload text), untrusted origin, W1
  traceability, content-addressed identity, W1 ``JsonModelStore`` round-trip.
  No code path applies a payload (C2);
- W7-before-W8-before-W9 ordering (mechanically enforced): ``UNDER_EXPERIMENT``
  is unconstructible without a W7 PASS result bound to the exact chain;
  ``UNDER_AUTHORITY`` requires a promoted W8 ``PromotionDecision`` plus a
  bounded ``RollbackPath`` bound to the proposal's declared rollback
  reference; ``PROMOTED`` requires a resolved W9 ACT decision from
  caller-supplied ``known_decisions`` (C3);
- no self-authorization: the module cannot construct authority — it never
  mints a W9 decision, no record field is an authorization token, and
  promotion consumes an external resolved ACT decision only (C4);
- ASK pause mechanics: an ASK decision yields ``PAUSED_ASKING`` with an
  explicit pending-authorization record; leaving the pause requires a NEW
  resolved decision; non-resolving W9 states defer with an explicit pending
  record (no advancement, no refusal, never an auto-approve) (C5);
- Constitution and authority protection: proposals targeting frozen
  authority paths are rejected at construction; DELETE-class changes on
  authority-implementation modules are rejected at construction; gate
  requirements are frozen code, never data-configurable (C6);
- governed promotion/rollback: every promotion-carrying transition binds a
  bounded W8 ``RollbackPath`` matching the proposal's declared rollback
  reference; ``ROLLED_BACK`` requires governed recovery evidence (C7);
- truth preservation: W1 truth distinctions and W4 verbatim evidence
  recording are preserved end-to-end; hypothesis predictions and payload
  contents are DATA and are never ingested as evidence; FAILED / UNKNOWN /
  UNAVAILABLE / UNSUPPORTED never collapse to a favorable value (C8);
- origin never authorizes: the proposal origin is untrusted provenance data
  that no gate reads; MODEL_GENERATED proposals pass and fail exactly the
  same gates as any other origin (C9);
- bounded recursion: a fixed ``MAX_META_DEPTH``; the ancestor chain is
  resolved from caller-supplied ``known_proposals`` and rejected on
  inconsistency/overflow; the evaluation surface exposes no
  proposal-generation path; one call advances exactly one proposal (C10);
- determinism and bounds: single-threaded, clock-free core (timestamps are
  caller-supplied data), deterministic ordering, identical inputs produce
  byte-identical content-addressed records, zero network, zero child
  processes, zero file mutation, zero version-control invocation (C11);
- persistence and bounded surface: records round-trip through the W1
  ``JsonModelStore`` (no new persistence authority); no successor-stage
  symbols; W13 exports only through the ``sos`` package (C12).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Mapping

from .model import ModelValidationError, Traceability, TruthState, TruthfulValue
from .evidence import Evidence, EvidenceKind, EvidenceProvenance, _build_evidence
from .causal import CausalHypothesis
from .candidates import CandidateProposal
from .assurance import AssuranceResult, AssuranceStatus
from .experimentation import (
    Experiment,
    ExperimentEvaluation,
    ExperimentState,
    PromotionDecision,
    PromotionGate,
    RollbackPath,
)
from .autonomy import AutonomyDecision, AutonomyDecisionState


# ---------------------------------------------------------------------------
# Error authority (anchored in the W1 validation-error family — no new error
# authority is introduced)
# ---------------------------------------------------------------------------


class SelfEvolutionContractError(ModelValidationError):
    """Raised when the W13 self-evolution contract is violated at a boundary."""


# ---------------------------------------------------------------------------
# Frozen governance constants (named, never data-configurable)
# ---------------------------------------------------------------------------

#: Fixed recursion bound for meta-proposals (C10). A named constant, not a
#: magic number; changing it is a governed contract change.
MAX_META_DEPTH: int = 3

#: Frozen authority artifacts whose paths may NEVER be targeted by a
#: self-evolution proposal (C6 / P3). Changes to these belong to the governed
#: architecture change process, which this machinery never replaces.
FROZEN_AUTHORITY_PATHS: frozenset[str] = frozenset({
    "spec/constitution.md",
    "spec/architecture.md",
    "spec/architecture-lock.md",
    "spec/architecture-change-process.md",
    "spec/implementation-roadmap.md",
    "spec/requirements.md",
    "spec/sos-meta-model.md",
    "spec/development-state/implementation-state.json",
})

#: Directory prefixes that are frozen authority artifacts in their entirety
#: (every frozen Work Order).
FROZEN_AUTHORITY_PATH_PREFIXES: frozenset[str] = frozenset({
    "spec/work-orders/",
})

#: The ``src/sos/`` modules implementing the W1/W4/W5/W6/W7/W8/W9 authorities
#: (C6 / P4): no payload may DELETE an authority-implementation module. The
#: set is extended with the lifecycle machine's own module and the package
#: export boundary — deleting those would strip the lifecycle machine's own
#: gates, which no code path may weaken.
AUTHORITY_MODULE_PATHS: frozenset[str] = frozenset({
    "src/sos/model.py",             # W1 truth/model/persistence
    "src/sos/evidence.py",          # W4 evidence/observability
    "src/sos/causal.py",            # W5 causal knowledge/memory
    "src/sos/candidates.py",        # W6 candidate generation/search
    "src/sos/assurance.py",         # W7 assurance/impact
    "src/sos/experimentation.py",   # W8 experiment/promotion/rollback
    "src/sos/autonomy.py",          # W9 autonomy/ASK
    "src/sos/selfevolution.py",     # the W13 lifecycle machine itself
    "src/sos/__init__.py",          # the package export boundary
})


# ---------------------------------------------------------------------------
# Frozen proposal vocabulary
# ---------------------------------------------------------------------------


class ProposalOrigin(str, Enum):
    """Untrusted provenance for a proposal (C9): no gate ever reads it."""

    MODEL_GENERATED = "MODEL_GENERATED"
    HUMAN_GENERATED = "HUMAN_GENERATED"
    EVIDENCE_TRIGGERED = "EVIDENCE_TRIGGERED"


class SourceChangeKind(str, Enum):
    """The bounded change kinds a proposal may carry."""

    CREATE = "CREATE"
    MODIFY = "MODIFY"
    DELETE = "DELETE"


def _validate_repo_path(path: str) -> None:
    """Validate a repo-relative POSIX path and enforce the frozen-path policy."""
    if not isinstance(path, str) or not path.strip():
        raise SelfEvolutionContractError("a repo-relative path is required")
    if path != path.strip():
        raise SelfEvolutionContractError(
            f"path '{path}' must not carry surrounding whitespace"
        )
    if path.startswith("/") or "\\" in path:
        raise SelfEvolutionContractError(
            f"path '{path}' must be a repo-relative POSIX path (no absolute paths)"
        )
    if path.endswith("/"):
        raise SelfEvolutionContractError(f"path '{path}' must name a file, not a directory")
    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise SelfEvolutionContractError(
            f"path '{path}' must not contain empty, dot, or parent-directory components"
        )
    if path in FROZEN_AUTHORITY_PATHS or any(
        path.startswith(prefix) for prefix in FROZEN_AUTHORITY_PATH_PREFIXES
    ):
        raise SelfEvolutionContractError(
            f"target path '{path}' is a frozen authority artifact; such changes require "
            "the governed architecture change process, not a self-evolution proposal"
        )


@dataclass(frozen=True)
class SourceChange:
    """One diff-shaped payload entry, carried AS DATA (C2).

    ``path`` is repo-relative; ``base_revision`` is the exact revision the
    change applies against (it must equal the proposal's ``target_revision``);
    ``payload`` is diff-shaped text for CREATE/MODIFY and empty for DELETE.
    The payload is inert data: no code path in this module applies it.
    """

    path: str
    base_revision: str
    kind: SourceChangeKind
    payload: str

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        _validate_repo_path(self.path)
        if not isinstance(self.kind, SourceChangeKind):
            raise SelfEvolutionContractError("SourceChange.kind must be a SourceChangeKind")
        if not self.base_revision or not self.base_revision.strip():
            raise SelfEvolutionContractError("SourceChange.base_revision is required")
        if self.kind == SourceChangeKind.DELETE:
            if self.path in AUTHORITY_MODULE_PATHS:
                raise SelfEvolutionContractError(
                    f"authority-implementation module '{self.path}' cannot be DELETEd by a "
                    "self-evolution proposal (governed architecture change required)"
                )
            if self.payload.strip():
                raise SelfEvolutionContractError(
                    "DELETE-class changes carry no payload (the payload is the deletion itself)"
                )
        elif not self.payload.strip():
            raise SelfEvolutionContractError(
                f"{self.kind.value}-class changes require a diff-shaped payload"
            )


@dataclass(frozen=True)
class SelfImprovementHypothesis:
    """The "self-improvement hypothesis" stage of the composed lifecycle.

    ``trigger_evidence_ids`` cite real W4 evidence records (validated against
    caller-supplied registries); ``causal_hypothesis_ids`` cite W5 priors
    (memory as a prior, never as proof); ``predicted_effects`` are DATA —
    predictions are never evidence and never truth; ``uncertainty`` is a W1
    ``TruthfulValue`` that may never claim SUCCESS (a hypothesis is a
    prediction, not a proven fact).
    """

    rationale: str
    trigger_evidence_ids: tuple[str, ...]
    predicted_effects: tuple[str, ...]
    uncertainty: TruthfulValue[Any]
    causal_hypothesis_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not self.rationale or not self.rationale.strip():
            raise SelfEvolutionContractError(
                "SelfImprovementHypothesis.rationale is required"
            )
        if not self.trigger_evidence_ids:
            raise SelfEvolutionContractError(
                "SelfImprovementHypothesis.trigger_evidence_ids is required "
                "(a self-improvement hypothesis is evidence-triggered)"
            )
        for eid in self.trigger_evidence_ids:
            if not eid or not eid.strip():
                raise SelfEvolutionContractError("trigger evidence ids must be non-empty")
        if not self.predicted_effects:
            raise SelfEvolutionContractError(
                "SelfImprovementHypothesis.predicted_effects is required (as DATA, "
                "never as evidence)"
            )
        for effect in self.predicted_effects:
            if not effect or not effect.strip():
                raise SelfEvolutionContractError("predicted effects must be non-empty")
        for hid in self.causal_hypothesis_ids:
            if not hid or not hid.strip():
                raise SelfEvolutionContractError("causal hypothesis ids must be non-empty")
        if not isinstance(self.uncertainty, TruthfulValue):
            raise SelfEvolutionContractError(
                "SelfImprovementHypothesis.uncertainty must be a W1 TruthfulValue"
            )
        self.uncertainty.validate()
        if self.uncertainty.state == TruthState.SUCCESS:
            raise SelfEvolutionContractError(
                "SelfImprovementHypothesis.uncertainty may not be SUCCESS "
                "(a self-improvement hypothesis is a prediction, not a proven fact)"
            )


# ---------------------------------------------------------------------------
# Governed lifecycle state machine (frozen FROM->TO table; no free-form
# narrative transitions — Work Order required outcome 2)
# ---------------------------------------------------------------------------


class SelfEvolutionState(str, Enum):
    """The governed lifecycle states of a self-evolution proposal."""

    PROPOSED = "PROPOSED"
    UNDER_ASSURANCE = "UNDER_ASSURANCE"
    UNDER_EXPERIMENT = "UNDER_EXPERIMENT"
    UNDER_AUTHORITY = "UNDER_AUTHORITY"
    PAUSED_ASKING = "PAUSED_ASKING"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"
    ROLLED_BACK = "ROLLED_BACK"


#: Terminal lifecycle states: no record is ever silently re-opened.
SELF_EVOLUTION_TERMINAL_STATES: frozenset[SelfEvolutionState] = frozenset({
    SelfEvolutionState.REJECTED,
    SelfEvolutionState.ROLLED_BACK,
})

# Valid direct transitions FROM -> {allowed TO states}. The table is frozen
# code: gate requirements are never read from data (C6/P2).
_VALID_SELF_EVOLUTION_TRANSITIONS: dict[SelfEvolutionState, frozenset[SelfEvolutionState]] = {
    SelfEvolutionState.PROPOSED: frozenset({
        SelfEvolutionState.UNDER_ASSURANCE, SelfEvolutionState.REJECTED,
    }),
    SelfEvolutionState.UNDER_ASSURANCE: frozenset({
        SelfEvolutionState.UNDER_EXPERIMENT, SelfEvolutionState.REJECTED,
    }),
    SelfEvolutionState.UNDER_EXPERIMENT: frozenset({
        SelfEvolutionState.UNDER_AUTHORITY, SelfEvolutionState.REJECTED,
        SelfEvolutionState.ROLLED_BACK,
    }),
    SelfEvolutionState.UNDER_AUTHORITY: frozenset({
        SelfEvolutionState.PROMOTED, SelfEvolutionState.PAUSED_ASKING,
        SelfEvolutionState.REJECTED, SelfEvolutionState.ROLLED_BACK,
    }),
    SelfEvolutionState.PAUSED_ASKING: frozenset({
        SelfEvolutionState.UNDER_AUTHORITY, SelfEvolutionState.REJECTED,
    }),
    SelfEvolutionState.PROMOTED: frozenset({SelfEvolutionState.ROLLED_BACK}),
    SelfEvolutionState.REJECTED: frozenset(),
    SelfEvolutionState.ROLLED_BACK: frozenset(),
}


def validate_self_evolution_transition(
    from_state: SelfEvolutionState,
    to_state: SelfEvolutionState,
) -> None:
    """Validate a lifecycle transition against the frozen machine (C3).

    Raises ``SelfEvolutionContractError`` for out-of-table transitions
    (skipped gates, free-form moves, re-opened terminal records).
    """
    if not isinstance(from_state, SelfEvolutionState):
        raise SelfEvolutionContractError(
            f"from_state must be a SelfEvolutionState, got {from_state!r}"
        )
    if not isinstance(to_state, SelfEvolutionState):
        raise SelfEvolutionContractError(
            f"to_state must be a SelfEvolutionState, got {to_state!r}"
        )
    allowed = _VALID_SELF_EVOLUTION_TRANSITIONS.get(from_state, frozenset())
    if to_state not in allowed:
        raise SelfEvolutionContractError(
            f"invalid self-evolution lifecycle transition: {from_state.value} -> {to_state.value}"
        )


class SelfEvolutionGate(str, Enum):
    """Which governed gate produced a lifecycle step (frozen vocabulary)."""

    INTAKE = "intake"
    W7_ASSURANCE = "w7-assurance"
    W8_PROMOTION = "w8-promotion"
    W8_EXPERIMENT_ROLLBACK = "w8-experiment-rollback"
    W9_AUTHORITY = "w9-authority"
    W9_ASK = "w9-ask"
    W9_REJECT = "w9-reject"
    W9_ROLLBACK = "w9-rollback"
    W9_RESUME = "w9-resume"
    W9_DEFERRAL = "w9-deferral"


# ---------------------------------------------------------------------------
# Pending records (the explicit ASK pause + the truthful deferral markers)
# ---------------------------------------------------------------------------


class PendingResolution(str, Enum):
    """The resolution state of a pending record. PENDING is the only member:
    this slice provides no code path that resolves a pending record — leaving
    a pause or a deferral requires a fresh W9 decision under human authority."""

    PENDING = "pending"


@dataclass(frozen=True)
class PendingProposalAuthorization:
    """The explicit pending-authorization pause record (W9 ASK).

    Constructed only from a real W9 ``AutonomyDecision`` whose state is ASK.
    Frozen with ``resolution == PENDING``; exposes no method that grants,
    mints, or upgrades authorization — the lifecycle can never auto-approve
    its own pause (C5).
    """

    proposal_id: str
    decision_id: str
    decision_state: AutonomyDecisionState
    requested_action: str
    rationale: str
    reasons: tuple[str, ...]
    resolution: PendingResolution = PendingResolution.PENDING
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", _pending_id(self))
        self.validate()

    def validate(self) -> None:
        for name, value in (
            ("proposal_id", self.proposal_id),
            ("decision_id", self.decision_id),
            ("requested_action", self.requested_action),
            ("rationale", self.rationale),
        ):
            if not value or not value.strip():
                raise SelfEvolutionContractError(f"PendingProposalAuthorization.{name} is required")
        if not isinstance(self.decision_state, AutonomyDecisionState):
            raise SelfEvolutionContractError(
                "PendingProposalAuthorization.decision_state must be an AutonomyDecisionState"
            )
        if self.decision_state != AutonomyDecisionState.ASK:
            raise SelfEvolutionContractError(
                "PendingProposalAuthorization may only arise from an ASK decision "
                f"(got {self.decision_state.value})"
            )
        if not self.reasons:
            raise SelfEvolutionContractError("PendingProposalAuthorization.reasons are required")
        if self.resolution != PendingResolution.PENDING:
            raise SelfEvolutionContractError(
                "a pending authorization cannot be constructed in a resolved state "
                "(approval requires a fresh W9 decision under human authority)"
            )
        if self.id != _pending_id(self):
            raise SelfEvolutionContractError(
                "PendingProposalAuthorization.id does not match its content-addressed material"
            )

    @classmethod
    def from_decision(
        cls, decision: AutonomyDecision, *, proposal_id: str
    ) -> "PendingProposalAuthorization":
        """Build the pause record from a real W9 ASK decision."""
        if not isinstance(decision, AutonomyDecision):
            raise SelfEvolutionContractError(
                "PendingProposalAuthorization.from_decision requires a real W9 AutonomyDecision"
            )
        if decision.state != AutonomyDecisionState.ASK:
            raise SelfEvolutionContractError(
                "PendingProposalAuthorization.from_decision requires an ASK decision "
                f"(got {decision.state.value})"
            )
        return cls(
            proposal_id=proposal_id,
            decision_id=decision.id,
            decision_state=decision.state,
            requested_action=str(decision.action.value),
            rationale=decision.rationale,
            reasons=tuple(decision.reasons),
        )


@dataclass(frozen=True)
class PendingProposalEvidence:
    """The explicit pending-evidence deferral record (W9 GATHER_EVIDENCE /
    EXPERIMENT): a truthful deferral — no advancement, no refusal (C5)."""

    proposal_id: str
    decision_id: str
    decision_state: AutonomyDecisionState
    requested_action: str
    rationale: str
    reasons: tuple[str, ...]
    resolution: PendingResolution = PendingResolution.PENDING
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", _deferred_id(self))
        self.validate()

    def validate(self) -> None:
        for name, value in (
            ("proposal_id", self.proposal_id),
            ("decision_id", self.decision_id),
            ("requested_action", self.requested_action),
            ("rationale", self.rationale),
        ):
            if not value or not value.strip():
                raise SelfEvolutionContractError(f"PendingProposalEvidence.{name} is required")
        if not isinstance(self.decision_state, AutonomyDecisionState):
            raise SelfEvolutionContractError(
                "PendingProposalEvidence.decision_state must be an AutonomyDecisionState"
            )
        if self.decision_state not in (AutonomyDecisionState.GATHER_EVIDENCE, AutonomyDecisionState.EXPERIMENT):
            raise SelfEvolutionContractError(
                "PendingProposalEvidence may only arise from a non-resolving W9 decision "
                f"(GATHER_EVIDENCE or EXPERIMENT; got {self.decision_state.value})"
            )
        if not self.reasons:
            raise SelfEvolutionContractError("PendingProposalEvidence.reasons are required")
        if self.resolution != PendingResolution.PENDING:
            raise SelfEvolutionContractError(
                "a pending-evidence record cannot be constructed in a resolved state"
            )
        if self.id != _deferred_id(self):
            raise SelfEvolutionContractError(
                "PendingProposalEvidence.id does not match its content-addressed material"
            )

    @classmethod
    def from_decision(
        cls, decision: AutonomyDecision, *, proposal_id: str
    ) -> "PendingProposalEvidence":
        """Build the deferral record from a real non-resolving W9 decision."""
        if not isinstance(decision, AutonomyDecision):
            raise SelfEvolutionContractError(
                "PendingProposalEvidence.from_decision requires a real W9 AutonomyDecision"
            )
        if decision.state not in (AutonomyDecisionState.GATHER_EVIDENCE, AutonomyDecisionState.EXPERIMENT):
            raise SelfEvolutionContractError(
                "PendingProposalEvidence.from_decision requires a non-resolving W9 decision "
                f"(got {decision.state.value})"
            )
        return cls(
            proposal_id=proposal_id,
            decision_id=decision.id,
            decision_state=decision.state,
            requested_action=str(decision.action.value),
            rationale=decision.rationale,
            reasons=tuple(decision.reasons),
        )


def _pending_id(p: PendingProposalAuthorization) -> str:
    material = "|".join([
        p.proposal_id, p.decision_id, p.decision_state.value,
        p.requested_action, p.rationale, ",".join(p.reasons),
    ])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"selfevo-pending-{digest}"


def _deferred_id(p: PendingProposalEvidence) -> str:
    material = "|".join([
        p.proposal_id, p.decision_id, p.decision_state.value,
        p.requested_action, p.rationale, ",".join(p.reasons),
    ])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"selfevo-deferred-{digest}"


# ---------------------------------------------------------------------------
# The proposal record (typed, frozen, construction-validated, content-addressed)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SelfEvolutionProposal:
    """A governed self-evolution proposal: SOS's candidate change to itself,
    carried as inert DATA (Work Order required outcome 1).

    The identity is content-addressed over the INTAKE material only
    (target revision/paths, changes, hypothesis, origin, rollback reference,
    recursion fields, W6 citation, traceability) and is therefore STABLE across
    the lifecycle: every governed transition returns a new record with the
    same id and accumulated gate references (the W8 ``Experiment`` precedent).
    Field presence is validated against the lifecycle state so the
    W7-before-W8-before-W9 ordering is visible in the record itself (C3).
    """

    target_revision: str
    target_paths: tuple[str, ...]
    changes: tuple[SourceChange, ...]
    hypothesis: SelfImprovementHypothesis
    origin: ProposalOrigin
    rollback_ref: str
    meta_depth: int
    traceability: Traceability
    ancestor_proposal_id: str | None = None
    candidate_ref: str | None = None
    state: SelfEvolutionState = SelfEvolutionState.PROPOSED
    assurance_result_id: str | None = None
    assurance_status: AssuranceStatus | None = None
    experiment_id: str | None = None
    evaluation_id: str | None = None
    promotion_id: str | None = None
    autonomy_decision_id: str | None = None
    evidence_ids: tuple[str, ...] = ()
    pending_authorization: PendingProposalAuthorization | None = None
    pending_evidence: PendingProposalEvidence | None = None
    adoption_revision: str | None = None
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", _proposal_id(self))
        self.validate()

    # -- construction + registry validation ---------------------------------

    def validate(
        self,
        *,
        known_evidence: Mapping[str, Evidence] | None = None,
        known_hypotheses: Mapping[str, CausalHypothesis] | None = None,
        known_candidates: Mapping[str, CandidateProposal] | None = None,
        known_proposals: Mapping[str, "SelfEvolutionProposal"] | None = None,
    ) -> None:
        """Validate the record structurally and, when registries are supplied,
        validate every W4/W5/W6 citation and the recursion-bound ancestor
        chain against them (Work Order required outcome 7 / C10)."""
        if not self.target_revision or not self.target_revision.strip():
            raise SelfEvolutionContractError("SelfEvolutionProposal.target_revision is required")
        if not isinstance(self.hypothesis, SelfImprovementHypothesis):
            raise SelfEvolutionContractError(
                "SelfEvolutionProposal.hypothesis must be a SelfImprovementHypothesis"
            )
        self.hypothesis.validate()
        if not isinstance(self.origin, ProposalOrigin):
            raise SelfEvolutionContractError("SelfEvolutionProposal.origin must be a ProposalOrigin")
        if not self.rollback_ref or not self.rollback_ref.strip():
            raise SelfEvolutionContractError("SelfEvolutionProposal.rollback_ref is required")
        if not self.changes:
            raise SelfEvolutionContractError("SelfEvolutionProposal.changes is required")
        if isinstance(self.meta_depth, bool) or not isinstance(self.meta_depth, int):
            raise SelfEvolutionContractError("SelfEvolutionProposal.meta_depth must be an integer")
        if self.meta_depth < 0 or self.meta_depth > MAX_META_DEPTH:
            raise SelfEvolutionContractError(
                f"SelfEvolutionProposal.meta_depth must be within [0, {MAX_META_DEPTH}] "
                f"(got {self.meta_depth}); the recursion bound is fixed"
            )
        if self.meta_depth == 0 and self.ancestor_proposal_id is not None:
            raise SelfEvolutionContractError(
                "a root proposal (meta_depth 0) carries no ancestor_proposal_id"
            )
        if self.meta_depth > 0 and not (self.ancestor_proposal_id or "").strip():
            raise SelfEvolutionContractError(
                f"a meta-proposal (meta_depth {self.meta_depth}) requires ancestor_proposal_id"
            )
        if self.candidate_ref is not None and not self.candidate_ref.strip():
            raise SelfEvolutionContractError(
                "SelfEvolutionProposal.candidate_ref must be non-empty when supplied"
            )
        if not isinstance(self.state, SelfEvolutionState):
            raise SelfEvolutionContractError(
                "SelfEvolutionProposal.state must be a SelfEvolutionState"
            )
        self.traceability.validate(require_value=True, require_context=True)

        # -- payload shape + intake path policy (C2/C6, defense in depth) ----
        for change in self.changes:
            if not isinstance(change, SourceChange):
                raise SelfEvolutionContractError(
                    "SelfEvolutionProposal.changes must be SourceChange records"
                )
            change.validate()
            if change.base_revision != self.target_revision:
                raise SelfEvolutionContractError(
                    f"change '{change.path}' base revision '{change.base_revision}' does not "
                    f"bind to the proposal target revision '{self.target_revision}'"
                )
        paths = [c.path for c in self.changes]
        if len(set(paths)) != len(paths):
            raise SelfEvolutionContractError(
                "SelfEvolutionProposal.changes must not target the same path twice"
            )
        if not self.target_paths:
            raise SelfEvolutionContractError("SelfEvolutionProposal.target_paths is required")
        if list(self.target_paths) != sorted(set(self.target_paths)):
            raise SelfEvolutionContractError(
                "SelfEvolutionProposal.target_paths must be sorted and deduplicated"
            )
        if set(self.target_paths) != set(paths):
            raise SelfEvolutionContractError(
                "SelfEvolutionProposal.target_paths must exactly match the change paths"
            )

        # -- state-dependent field presence (the ordering made visible) ------
        self._validate_state_fields()

        # -- citation + recursion validation against caller registries ------
        # (house pattern: each registry is consulted only when supplied; the
        # governed intake transition additionally REFUSES unvalidatable
        # citations — see transition_self_evolution)
        if known_evidence is not None:
            for eid in self.hypothesis.trigger_evidence_ids:
                if eid not in known_evidence:
                    raise SelfEvolutionContractError(
                        f"trigger evidence '{eid}' is not present in the caller-supplied "
                        "evidence registry"
                    )
        if known_hypotheses is not None:
            for hid in self.hypothesis.causal_hypothesis_ids:
                record = known_hypotheses.get(hid)
                if record is None:
                    raise SelfEvolutionContractError(
                        f"W5 causal prior '{hid}' is not present in the caller-supplied "
                        "hypothesis registry"
                    )
                if not isinstance(record, CausalHypothesis):
                    raise SelfEvolutionContractError(
                        f"W5 causal prior '{hid}' is not a real CausalHypothesis"
                    )
        if known_candidates is not None:
            if self.candidate_ref is not None:
                record = known_candidates.get(self.candidate_ref)
                if record is None:
                    raise SelfEvolutionContractError(
                        f"W6 candidate '{self.candidate_ref}' is not present in the "
                        "caller-supplied candidate registry"
                    )
                if not isinstance(record, CandidateProposal):
                    raise SelfEvolutionContractError(
                        f"W6 candidate '{self.candidate_ref}' is not a real CandidateProposal"
                    )
        if known_proposals is not None:
            resolve_meta_chain(self, known_proposals)

        # -- identity integrity (tamper-evident content addressing) ----------
        if self.id != _proposal_id(self):
            raise SelfEvolutionContractError(
                "SelfEvolutionProposal.id does not match its content-addressed intake material"
            )

    def _validate_state_fields(self) -> None:
        state = self.state
        if self.assurance_status is not None:
            if not isinstance(self.assurance_status, AssuranceStatus):
                raise SelfEvolutionContractError(
                    "SelfEvolutionProposal.assurance_status must be an AssuranceStatus"
                )
            if self.assurance_result_id is None:
                raise SelfEvolutionContractError(
                    "assurance_status is only lawful alongside assurance_result_id"
                )
        for name, value in (
            ("assurance_result_id", self.assurance_result_id),
            ("experiment_id", self.experiment_id),
            ("evaluation_id", self.evaluation_id),
            ("promotion_id", self.promotion_id),
            ("autonomy_decision_id", self.autonomy_decision_id),
            ("adoption_revision", self.adoption_revision),
        ):
            if value is not None and not value.strip():
                raise SelfEvolutionContractError(
                    f"SelfEvolutionProposal.{name} must be non-empty when supplied"
                )
        for eid in self.evidence_ids:
            if not eid or not eid.strip():
                raise SelfEvolutionContractError("evidence ids must be non-empty")

        # Monotonic ordering visibility: an experiment requires the assurance
        # that preceded it; an evaluation requires the experiment; a promotion
        # reference requires the evaluation (the W7->W8 chain in the record).
        if self.experiment_id is not None and self.assurance_result_id is None:
            raise SelfEvolutionContractError(
                "an experiment reference requires the W7 assurance reference "
                "(W7-before-W8 ordering)"
            )
        if self.evaluation_id is not None and self.experiment_id is None:
            raise SelfEvolutionContractError(
                "an evaluation reference requires the W8 experiment reference"
            )
        if self.promotion_id is not None and self.evaluation_id is None:
            raise SelfEvolutionContractError(
                "a promotion reference requires the W8 evaluation reference"
            )
        if self.experiment_id is not None and self.assurance_status != AssuranceStatus.PASS:
            raise SelfEvolutionContractError(
                "records beyond the assurance stage require a PASS W7 assurance status"
            )

        if state == SelfEvolutionState.PROPOSED:
            for name, value in (
                ("assurance_result_id", self.assurance_result_id),
                ("experiment_id", self.experiment_id),
                ("evaluation_id", self.evaluation_id),
                ("promotion_id", self.promotion_id),
                ("autonomy_decision_id", self.autonomy_decision_id),
                ("adoption_revision", self.adoption_revision),
            ):
                if value is not None:
                    raise SelfEvolutionContractError(
                        f"a PROPOSED record cannot carry {name} (no gate has run yet)"
                    )
            if self.assurance_status is not None:
                raise SelfEvolutionContractError(
                    "a PROPOSED record cannot carry assurance_status"
                )
            if self.evidence_ids != ():
                raise SelfEvolutionContractError(
                    "a PROPOSED record carries no transition evidence yet"
                )
        elif state == SelfEvolutionState.UNDER_ASSURANCE:
            for name, value in (
                ("assurance_result_id", self.assurance_result_id),
                ("experiment_id", self.experiment_id),
                ("evaluation_id", self.evaluation_id),
                ("promotion_id", self.promotion_id),
                ("autonomy_decision_id", self.autonomy_decision_id),
                ("adoption_revision", self.adoption_revision),
            ):
                if value is not None:
                    raise SelfEvolutionContractError(
                        f"an UNDER_ASSURANCE record cannot carry {name} "
                        "(the W7 gate has not resolved yet)"
                    )
            if self.assurance_status is not None:
                raise SelfEvolutionContractError(
                    "an UNDER_ASSURANCE record cannot carry assurance_status"
                )
            if not self.evidence_ids:
                raise SelfEvolutionContractError(
                    "a record beyond PROPOSED carries the W4 evidence of its transitions"
                )
        elif state == SelfEvolutionState.UNDER_EXPERIMENT:
            if self.assurance_result_id is None or self.assurance_status != AssuranceStatus.PASS:
                raise SelfEvolutionContractError(
                    "UNDER_EXPERIMENT requires the PASS W7 assurance reference (C3)"
                )
            for name, value in (
                ("experiment_id", self.experiment_id),
                ("evaluation_id", self.evaluation_id),
                ("promotion_id", self.promotion_id),
                ("autonomy_decision_id", self.autonomy_decision_id),
                ("adoption_revision", self.adoption_revision),
            ):
                if value is not None:
                    raise SelfEvolutionContractError(
                        f"an UNDER_EXPERIMENT record cannot carry {name} "
                        "(the W8 gate has not resolved yet)"
                    )
            if not self.evidence_ids:
                raise SelfEvolutionContractError(
                    "a record beyond PROPOSED carries the W4 evidence of its transitions"
                )
        elif state == SelfEvolutionState.UNDER_AUTHORITY:
            if self.assurance_result_id is None or self.assurance_status != AssuranceStatus.PASS:
                raise SelfEvolutionContractError(
                    "UNDER_AUTHORITY requires the PASS W7 assurance reference (C3)"
                )
            for name, value in (
                ("experiment_id", self.experiment_id),
                ("evaluation_id", self.evaluation_id),
                ("promotion_id", self.promotion_id),
            ):
                if value is None:
                    raise SelfEvolutionContractError(
                        f"UNDER_AUTHORITY requires the W8 {name} reference (C3)"
                    )
            if self.pending_authorization is not None:
                raise SelfEvolutionContractError(
                    "a pending-authorization record is only lawful on PAUSED_ASKING"
                )
            if self.adoption_revision is not None:
                raise SelfEvolutionContractError(
                    "adoption_revision is only lawful on PROMOTED (or preserved on "
                    "ROLLED_BACK) records"
                )
            if not self.evidence_ids:
                raise SelfEvolutionContractError(
                    "a record beyond PROPOSED carries the W4 evidence of its transitions"
                )
        elif state == SelfEvolutionState.PAUSED_ASKING:
            for name, value in (
                ("assurance_result_id", self.assurance_result_id),
                ("experiment_id", self.experiment_id),
                ("evaluation_id", self.evaluation_id),
                ("promotion_id", self.promotion_id),
                ("autonomy_decision_id", self.autonomy_decision_id),
            ):
                if value is None:
                    raise SelfEvolutionContractError(
                        f"PAUSED_ASKING requires the governed chain including {name} (C3/C5)"
                    )
            if self.assurance_status != AssuranceStatus.PASS:
                raise SelfEvolutionContractError("PAUSED_ASKING requires a PASS W7 assurance")
            if self.pending_authorization is None:
                raise SelfEvolutionContractError(
                    "PAUSED_ASKING requires the explicit pending-authorization record (C5)"
                )
            if self.adoption_revision is not None:
                raise SelfEvolutionContractError(
                    "adoption_revision is only lawful on PROMOTED (or preserved on "
                    "ROLLED_BACK) records"
                )
            if not self.evidence_ids:
                raise SelfEvolutionContractError(
                    "a record beyond PROPOSED carries the W4 evidence of its transitions"
                )
        elif state == SelfEvolutionState.PROMOTED:
            for name, value in (
                ("assurance_result_id", self.assurance_result_id),
                ("experiment_id", self.experiment_id),
                ("evaluation_id", self.evaluation_id),
                ("promotion_id", self.promotion_id),
                ("autonomy_decision_id", self.autonomy_decision_id),
            ):
                if value is None:
                    raise SelfEvolutionContractError(
                        f"PROMOTED requires the full governed chain including {name} (C3/C4)"
                    )
            if self.assurance_status != AssuranceStatus.PASS:
                raise SelfEvolutionContractError("PROMOTED requires a PASS W7 assurance")
            if self.pending_authorization is not None or self.pending_evidence is not None:
                raise SelfEvolutionContractError(
                    "a PROMOTED record carries no pending records (the authority gate resolved)"
                )
            if not self.evidence_ids:
                raise SelfEvolutionContractError(
                    "a record beyond PROPOSED carries the W4 evidence of its transitions"
                )
        elif state == SelfEvolutionState.REJECTED:
            grounds = (
                self.autonomy_decision_id is not None
                or self.assurance_result_id is not None
                or self.promotion_id is not None
            )
            if not grounds:
                raise SelfEvolutionContractError(
                    "a REJECTED record carries at least one rejection ground "
                    "(a W9 REJECT decision, a resolved non-PASS W7 result, or a refused "
                    "W8 promotion decision)"
                )
            if self.pending_authorization is not None or self.pending_evidence is not None:
                raise SelfEvolutionContractError(
                    "a REJECTED record carries no pending records (the refusal resolved)"
                )
            if self.adoption_revision is not None:
                raise SelfEvolutionContractError(
                    "a REJECTED record cannot carry adoption_revision"
                )
            if not self.evidence_ids:
                raise SelfEvolutionContractError(
                    "a record beyond PROPOSED carries the W4 evidence of its transitions"
                )
        elif state == SelfEvolutionState.ROLLED_BACK:
            if self.experiment_id is None:
                raise SelfEvolutionContractError(
                    "ROLLED_BACK requires the governed W8 experiment reference "
                    "(rollback is governed recovery)"
                )
            if self.pending_authorization is not None or self.pending_evidence is not None:
                raise SelfEvolutionContractError(
                    "a ROLLED_BACK record carries no pending records (the recovery resolved)"
                )
            if not self.evidence_ids:
                raise SelfEvolutionContractError(
                    "a record beyond PROPOSED carries the W4 evidence of its transitions"
                )


def _proposal_id(p: SelfEvolutionProposal) -> str:
    """Content-addressed identity over the INTAKE material only (stable across
    the lifecycle — the W8 ``Experiment`` precedent)."""
    change_material = "|".join(
        f"{c.path}:{c.kind.value}:{c.base_revision}:"
        f"{hashlib.sha256(c.payload.encode('utf-8')).hexdigest()}"
        for c in p.changes
    )
    hypothesis_material = "|".join([
        p.hypothesis.rationale,
        ",".join(p.hypothesis.trigger_evidence_ids),
        ",".join(p.hypothesis.causal_hypothesis_ids),
        ",".join(p.hypothesis.predicted_effects),
        p.hypothesis.uncertainty.state.value,
        str(p.hypothesis.uncertainty.value),
        str(p.hypothesis.uncertainty.detail),
    ])
    material = "|".join([
        p.target_revision,
        ",".join(p.target_paths),
        change_material,
        hypothesis_material,
        p.origin.value,
        p.rollback_ref,
        str(p.meta_depth),
        p.ancestor_proposal_id or "",
        p.candidate_ref or "",
        p.traceability.constitution_ref,
        p.traceability.mission_ref,
        p.traceability.value_model_ref or "",
        p.traceability.context_ref or "",
    ])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"selfevo-{digest}"


# ---------------------------------------------------------------------------
# Bounded recursion: the ancestor chain (resolved from caller-supplied
# known_proposals; overflow/inconsistency rejected)
# ---------------------------------------------------------------------------


def resolve_meta_chain(
    proposal: SelfEvolutionProposal,
    known_proposals: Mapping[str, SelfEvolutionProposal],
) -> tuple[str, ...]:
    """Resolve and validate the proposal's ancestor chain (C10).

    Returns the ancestor proposal ids ordered from the root (meta_depth 0) to
    the immediate parent. Every link must exist in ``known_proposals``, be a
    real ``SelfEvolutionProposal``, and declare exactly ``child.meta_depth - 1``
    (a strictly decreasing chain bounded by ``MAX_META_DEPTH``). A missing,
    inconsistent, or over-deep chain is rejected.
    """
    if not isinstance(proposal, SelfEvolutionProposal):
        raise SelfEvolutionContractError(
            "resolve_meta_chain requires a SelfEvolutionProposal"
        )
    if proposal.meta_depth > MAX_META_DEPTH:
        raise SelfEvolutionContractError(
            f"meta_depth {proposal.meta_depth} exceeds the fixed bound MAX_META_DEPTH={MAX_META_DEPTH}"
        )
    chain: list[str] = []
    current = proposal
    while current.meta_depth > 0:
        ancestor_id = current.ancestor_proposal_id or ""
        ancestor = known_proposals.get(ancestor_id)
        if ancestor is None:
            raise SelfEvolutionContractError(
                f"ancestor proposal '{ancestor_id}' is not present in the caller-supplied "
                "known_proposals registry; the recursion chain cannot be resolved"
            )
        if not isinstance(ancestor, SelfEvolutionProposal):
            raise SelfEvolutionContractError(
                f"ancestor proposal '{ancestor_id}' is not a real SelfEvolutionProposal"
            )
        if ancestor.meta_depth != current.meta_depth - 1:
            raise SelfEvolutionContractError(
                f"ancestor chain inconsistent at '{ancestor_id}': declares meta_depth "
                f"{ancestor.meta_depth}, expected {current.meta_depth - 1}"
            )
        if ancestor.meta_depth > MAX_META_DEPTH:
            raise SelfEvolutionContractError(
                f"ancestor chain exceeds the fixed bound MAX_META_DEPTH={MAX_META_DEPTH}"
            )
        chain.append(ancestor.id)
        current = ancestor
    chain.reverse()
    return tuple(chain)


# ---------------------------------------------------------------------------
# The lifecycle step record (convertible verbatim into W4 evidence)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SelfEvolutionStep:
    """One consequential governed transition record (required outcome 10).

    ``from_state``/``to_state`` are table-validated at construction (a step
    for an out-of-table transition is unconstructible, except the lawful
    W9_DEFERRAL which keeps the state); ``outcome`` is a W1 ``TruthfulValue``
    preserved verbatim into the W4 evidence; ``gate_record_ids`` carries the
    exact chain records the gate consulted, in deterministic order.
    """

    proposal_id: str
    target_revision: str
    from_state: SelfEvolutionState
    to_state: SelfEvolutionState
    gate: SelfEvolutionGate
    gate_record_ids: tuple[str, ...]
    outcome: TruthfulValue[Any]
    detail: str
    traceability: Traceability
    timestamp: str | None = None
    environment: str = "simulation"
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", _step_id(self))
        self.validate()

    def validate(self) -> None:
        for name, value in (
            ("proposal_id", self.proposal_id),
            ("target_revision", self.target_revision),
            ("detail", self.detail),
        ):
            if not value or not value.strip():
                raise SelfEvolutionContractError(f"SelfEvolutionStep.{name} is required")
        if not isinstance(self.from_state, SelfEvolutionState):
            raise SelfEvolutionContractError(
                "SelfEvolutionStep.from_state must be a SelfEvolutionState"
            )
        if not isinstance(self.to_state, SelfEvolutionState):
            raise SelfEvolutionContractError(
                "SelfEvolutionStep.to_state must be a SelfEvolutionState"
            )
        if not isinstance(self.gate, SelfEvolutionGate):
            raise SelfEvolutionContractError("SelfEvolutionStep.gate must be a SelfEvolutionGate")
        if not self.gate_record_ids:
            raise SelfEvolutionContractError(
                "SelfEvolutionStep.gate_record_ids is required (the consulted chain records)"
            )
        seen: set[str] = set()
        for rid in self.gate_record_ids:
            if not rid or not rid.strip():
                raise SelfEvolutionContractError("gate record ids must be non-empty")
            if rid in seen:
                raise SelfEvolutionContractError("gate record ids must not repeat")
            seen.add(rid)
        if not isinstance(self.outcome, TruthfulValue):
            raise SelfEvolutionContractError(
                "SelfEvolutionStep.outcome must be a W1 TruthfulValue"
            )
        self.outcome.validate()
        if self.timestamp is not None and not self.timestamp.strip():
            raise SelfEvolutionContractError(
                "SelfEvolutionStep.timestamp must be non-empty when supplied (caller data)"
            )
        self.traceability.validate(require_value=True, require_context=True)
        if self.gate == SelfEvolutionGate.W9_DEFERRAL:
            if self.from_state != self.to_state:
                raise SelfEvolutionContractError(
                    "a W9 deferral step keeps the current state (no advancement, no refusal)"
                )
            if self.from_state not in (SelfEvolutionState.UNDER_AUTHORITY, SelfEvolutionState.PAUSED_ASKING):
                raise SelfEvolutionContractError(
                    "a W9 deferral is only lawful while the proposal awaits W9 authority"
                )
        else:
            if self.from_state == self.to_state:
                raise SelfEvolutionContractError(
                    "a governed step changes the lifecycle state (use the deferral gate "
                    "for state-keeping records)"
                )
            validate_self_evolution_transition(self.from_state, self.to_state)
        if self.id != _step_id(self):
            raise SelfEvolutionContractError(
                "SelfEvolutionStep.id does not match its content-addressed material"
            )


def _step_id(s: SelfEvolutionStep) -> str:
    material = "|".join([
        s.proposal_id, s.target_revision,
        s.from_state.value, s.to_state.value, s.gate.value,
        ",".join(s.gate_record_ids),
        s.outcome.state.value, str(s.outcome.value), str(s.outcome.detail),
        s.detail,
        s.timestamp or "", s.environment,
    ])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"selfevo-step-{digest}"


def step_to_w4_evidence(step: SelfEvolutionStep, *, traceability: Traceability) -> Evidence:
    """Convert a lifecycle step into a W4 evidence record (observed, not
    inferred), reusing the W4 module's own content-addressed assembly so the
    evidence-id algorithm exists exactly once (the W11 receipt-conversion
    precedent). Rollback steps become ``rollback`` evidence; every other step
    becomes an ``observation``. Only existing evidence kinds; the truth state
    is preserved verbatim (FAILED / UNKNOWN / UNAVAILABLE / UNSUPPORTED never
    collapse). Hypothesis predictions and payload contents are never ingested.
    """
    step.validate()
    kind = (
        EvidenceKind.ROLLBACK
        if step.to_state == SelfEvolutionState.ROLLED_BACK
        else EvidenceKind.OBSERVATION
    )
    provenance = EvidenceProvenance(
        source="sos-self-evolution-lifecycle",
        observed_subject=step.proposal_id,
        timestamp=step.timestamp,
        environment=step.environment,
        implementation_revision=step.target_revision,
    )
    return _build_evidence(
        kind=kind,
        source_ref=f"self-evolution-step:{step.id}",
        subject_ref=step.proposal_id,
        result=step.outcome,
        provenance=provenance,
        traceability=traceability,
        timestamp=step.timestamp,
        environment=step.environment,
        confidence=None,
        availability=TruthState.SUCCESS,
    )


# ---------------------------------------------------------------------------
# The transition result (one advanced proposal + its step + its W4 evidence)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SelfEvolutionTransitionResult:
    """The result of one governed lifecycle call: the advanced proposal record,
    the consequential step record, and the verbatim W4 evidence for the step.

    The caller ingests the evidence into their W4 graph and passes the
    enriched registries to the next call; this module holds no hidden state.
    """

    proposal: SelfEvolutionProposal
    step: SelfEvolutionStep
    evidence: Evidence

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not isinstance(self.proposal, SelfEvolutionProposal):
            raise SelfEvolutionContractError(
                "SelfEvolutionTransitionResult.proposal must be a SelfEvolutionProposal"
            )
        if not isinstance(self.step, SelfEvolutionStep):
            raise SelfEvolutionContractError(
                "SelfEvolutionTransitionResult.step must be a SelfEvolutionStep"
            )
        if not isinstance(self.evidence, Evidence):
            raise SelfEvolutionContractError(
                "SelfEvolutionTransitionResult.evidence must be a W4 Evidence record"
            )
        if self.step.proposal_id != self.proposal.id:
            raise SelfEvolutionContractError(
                "the step is not bound to the exact proposal"
            )
        if self.step.to_state != self.proposal.state:
            raise SelfEvolutionContractError(
                "the step's target state does not match the advanced proposal"
            )
        if self.evidence.subject_ref != self.proposal.id:
            raise SelfEvolutionContractError(
                "the evidence is not bound to the exact proposal"
            )
        if self.evidence.id not in self.proposal.evidence_ids:
            raise SelfEvolutionContractError(
                "the advanced proposal must record the appended evidence id"
            )


# ---------------------------------------------------------------------------
# Chain-check helpers (every cross-authority reference chain-checked — C1)
# ---------------------------------------------------------------------------

# W7 statuses map to distinct W1 truth states (injective; none collapses).
_ASSURANCE_TRUTH: dict[AssuranceStatus, TruthState] = {
    AssuranceStatus.PASS: TruthState.SUCCESS,
    AssuranceStatus.FAIL: TruthState.FAILED,
    AssuranceStatus.UNKNOWN: TruthState.UNKNOWN,
    AssuranceStatus.BLOCKED: TruthState.UNAVAILABLE,
}


def _resolve_decision(
    autonomy_decision_id: str | None,
    known_decisions: Mapping[str, AutonomyDecision],
) -> AutonomyDecision:
    if not autonomy_decision_id or not autonomy_decision_id.strip():
        raise SelfEvolutionContractError(
            "the transition requires the W9 autonomy decision id (no decision, no gate)"
        )
    decision = known_decisions.get(autonomy_decision_id)
    if decision is None:
        raise SelfEvolutionContractError(
            f"W9 decision '{autonomy_decision_id}' is not present in the caller-supplied "
            "known_decisions registry (unresolved W9 reference)"
        )
    if not isinstance(decision, AutonomyDecision):
        raise SelfEvolutionContractError(
            f"known_decisions['{autonomy_decision_id}'] is not a real W9 AutonomyDecision"
        )
    return decision


def _check_decision_chain(
    decision: AutonomyDecision,
    proposal: SelfEvolutionProposal,
    *,
    require_promotion_ref: bool = False,
) -> None:
    """Bind a W9 decision to the exact proposal chain (C1/C4)."""
    expected_assurance = proposal.assurance_result_id or ""
    if decision.assurance_id != expected_assurance:
        raise SelfEvolutionContractError(
            f"the W9 decision is not bound to the exact assurance chain: decision carries "
            f"'{decision.assurance_id}', the proposal chain requires '{expected_assurance}'"
        )
    if proposal.experiment_id is None:
        if decision.experiment_id is not None:
            raise SelfEvolutionContractError(
                "the W9 decision references an experiment but the proposal chain has none yet"
            )
    elif decision.experiment_id != proposal.experiment_id:
        raise SelfEvolutionContractError(
            f"the W9 decision is not bound to the exact experiment: decision carries "
            f"'{decision.experiment_id}', the proposal chain requires '{proposal.experiment_id}'"
        )
    if decision.promotion_id is not None:
        if proposal.promotion_id is None or decision.promotion_id != proposal.promotion_id:
            raise SelfEvolutionContractError(
                f"the W9 decision is not bound to the exact promotion reference: decision "
                f"carries '{decision.promotion_id}', the proposal chain requires "
                f"'{proposal.promotion_id}'"
            )
    elif require_promotion_ref:
        raise SelfEvolutionContractError(
            "the authorizing W9 ACT decision must carry the W8 promotion reference"
        )


def _resolve_w7(
    assurance_result_id: str | None,
    known_assurance: Mapping[str, AssuranceResult],
    proposal: SelfEvolutionProposal,
) -> AssuranceResult:
    if not assurance_result_id or not assurance_result_id.strip():
        raise SelfEvolutionContractError(
            "the transition requires the W7 assurance result id"
        )
    assurance = known_assurance.get(assurance_result_id)
    if assurance is None:
        raise SelfEvolutionContractError(
            f"W7 assurance result '{assurance_result_id}' is not present in the "
            "caller-supplied known_assurance registry"
        )
    if not isinstance(assurance, AssuranceResult):
        raise SelfEvolutionContractError(
            f"known_assurance['{assurance_result_id}'] is not a real W7 AssuranceResult"
        )
    # C1/C3: bound to the exact proposal id / target revision chain.
    if assurance.candidate_id != proposal.id:
        raise SelfEvolutionContractError(
            f"the W7 assurance result is not bound to the exact proposal: candidate "
            f"'{assurance.candidate_id}' is not proposal '{proposal.id}'"
        )
    if assurance.provenance_revision != proposal.target_revision:
        raise SelfEvolutionContractError(
            f"the W7 assurance result provenance revision '{assurance.provenance_revision}' "
            f"does not bind to the proposal target revision '{proposal.target_revision}'"
        )
    return assurance


def _resolve_w8_chain(
    proposal: SelfEvolutionProposal,
    *,
    experiment_id: str | None,
    evaluation_id: str | None,
    known_assurance: Mapping[str, AssuranceResult],
    known_experiments: Mapping[str, Experiment],
    known_evaluations: Mapping[str, ExperimentEvaluation],
) -> tuple[AssuranceResult, Experiment, ExperimentEvaluation]:
    """Resolve and chain-check the full W7->W8 chain from the registries."""
    assurance = _resolve_w7(proposal.assurance_result_id, known_assurance, proposal)
    if not experiment_id or not experiment_id.strip():
        raise SelfEvolutionContractError("the transition requires the W8 experiment id")
    experiment = known_experiments.get(experiment_id)
    if experiment is None:
        raise SelfEvolutionContractError(
            f"W8 experiment '{experiment_id}' is not present in the caller-supplied "
            "known_experiments registry"
        )
    if not isinstance(experiment, Experiment):
        raise SelfEvolutionContractError(
            f"known_experiments['{experiment_id}'] is not a real W8 Experiment"
        )
    if experiment.candidate_id != proposal.id:
        raise SelfEvolutionContractError(
            f"the W8 experiment is not bound to the exact proposal: candidate "
            f"'{experiment.candidate_id}' is not proposal '{proposal.id}'"
        )
    if experiment.assurance_result_id != assurance.id:
        raise SelfEvolutionContractError(
            "the W8 experiment is not bound to the exact W7 assurance result"
        )
    if experiment.provenance_revision != proposal.target_revision:
        raise SelfEvolutionContractError(
            f"the W8 experiment provenance revision '{experiment.provenance_revision}' "
            f"does not bind to the proposal target revision '{proposal.target_revision}'"
        )
    # The W8 authority re-validates its own candidate/assurance/graph/revision
    # chain (SOS-W8-F01) — composed, never duplicated.
    experiment.validate(known_assurance=assurance)
    if not evaluation_id or not evaluation_id.strip():
        raise SelfEvolutionContractError("the transition requires the W8 evaluation id")
    evaluation = known_evaluations.get(evaluation_id)
    if evaluation is None:
        raise SelfEvolutionContractError(
            f"W8 evaluation '{evaluation_id}' is not present in the caller-supplied "
            "known_evaluations registry"
        )
    if not isinstance(evaluation, ExperimentEvaluation):
        raise SelfEvolutionContractError(
            f"known_evaluations['{evaluation_id}'] is not a real W8 ExperimentEvaluation"
        )
    if evaluation.experiment_id != experiment.id:
        raise SelfEvolutionContractError(
            "the W8 evaluation is not bound to the exact experiment"
        )
    if evaluation.candidate_id != proposal.id:
        raise SelfEvolutionContractError(
            "the W8 evaluation is not bound to the exact proposal"
        )
    if evaluation.assurance_result_id != assurance.id:
        raise SelfEvolutionContractError(
            "the W8 evaluation is not bound to the exact W7 assurance result"
        )
    if evaluation.base_graph_id != experiment.base_graph_id or evaluation.base_graph_revision != experiment.base_graph_revision:
        raise SelfEvolutionContractError(
            "the W8 evaluation is not bound to the exact W8 experiment graph chain"
        )
    if evaluation.provenance_revision != proposal.target_revision:
        raise SelfEvolutionContractError(
            f"the W8 evaluation provenance revision '{evaluation.provenance_revision}' "
            f"does not bind to the proposal target revision '{proposal.target_revision}'"
        )
    return assurance, experiment, evaluation


def _resolve_promotion(
    promotion_id: str | None,
    known_promotions: Mapping[str, PromotionDecision],
    experiment: Experiment,
    evaluation: ExperimentEvaluation,
) -> PromotionDecision:
    if not promotion_id or not promotion_id.strip():
        raise SelfEvolutionContractError(
            "the transition requires the W8 promotion decision id "
            "(the PromotionGate result: '<experiment-id>:<evaluation-id>')"
        )
    decision = known_promotions.get(promotion_id)
    if decision is None:
        raise SelfEvolutionContractError(
            f"W8 promotion decision '{promotion_id}' is not present in the caller-supplied "
            "known_promotions registry"
        )
    if not isinstance(decision, PromotionDecision):
        raise SelfEvolutionContractError(
            f"known_promotions['{promotion_id}'] is not a real W8 PromotionDecision"
        )
    expected_ref = f"{experiment.id}:{evaluation.id}"
    if promotion_id != expected_ref:
        raise SelfEvolutionContractError(
            f"the promotion reference '{promotion_id}' does not bind the exact gate decision "
            f"('{expected_ref}')"
        )
    if decision.experiment_id != experiment.id or decision.evaluation_id != evaluation.id:
        raise SelfEvolutionContractError(
            "the W8 promotion decision is not bound to the exact experiment/evaluation pair"
        )
    return decision


def _validate_recovery(
    proposal: SelfEvolutionProposal,
    rollback_path: RollbackPath | None,
    known_evidence: Mapping[str, Evidence],
) -> RollbackPath:
    """Every promotion-carrying/rollback transition requires a bounded W8
    ``RollbackPath`` whose reference binds to the proposal's declared rollback
    reference, backed by SUCCESS recovery evidence provenance-bound to the
    proposal's target revision (C7/P5 — no defaulting, no stripping)."""
    if rollback_path is None:
        raise SelfEvolutionContractError(
            "the transition requires a bounded W8 RollbackPath (governed recovery; "
            "the rollback binding cannot be skipped)"
        )
    if not isinstance(rollback_path, RollbackPath):
        raise SelfEvolutionContractError("the rollback path must be a real W8 RollbackPath")
    if rollback_path.reference != proposal.rollback_ref:
        raise SelfEvolutionContractError(
            f"rollback reference '{rollback_path.reference}' does not bind to the proposal's "
            f"declared rollback reference '{proposal.rollback_ref}'"
        )
    if not rollback_path.evidence_ids:
        raise SelfEvolutionContractError(
            "a bounded rollback path must carry recovery evidence ids"
        )
    for eid in rollback_path.evidence_ids:
        record = known_evidence.get(eid)
        if record is None:
            raise SelfEvolutionContractError(
                f"recovery evidence '{eid}' is not present in the caller-supplied "
                "known_evidence registry"
            )
        if record.result.state != TruthState.SUCCESS:
            raise SelfEvolutionContractError(
                f"recovery evidence '{eid}' observed state {record.result.state.value}; "
                "governed recovery requires SUCCESS recovery evidence"
            )
        record_revision = record.provenance.implementation_revision
        if record_revision is not None and record_revision != proposal.target_revision:
            raise SelfEvolutionContractError(
                f"recovery evidence '{eid}' provenance revision '{record_revision}' does not "
                f"bind to the proposal target revision '{proposal.target_revision}'"
            )
    return rollback_path


def _advanced(
    proposal: SelfEvolutionProposal,
    *,
    state: SelfEvolutionState,
    evidence_id: str,
    **overrides: Any,
) -> SelfEvolutionProposal:
    """Return the advanced record via a field-preserving copy: same identity,
    accumulated references, appended evidence, cleared pendings (unless
    overridden). The copy runs the full construction validation, so the
    advanced record's state-dependent field contract is enforced.

    A state-KEEPING step (the W9 deferral) preserves the existing pendings —
    only a state-changing transition supersedes them."""
    state_changing = state != proposal.state
    fields: dict[str, Any] = dict(
        state=state,
        evidence_ids=proposal.evidence_ids + (evidence_id,),
        pending_authorization=None if state_changing else proposal.pending_authorization,
        pending_evidence=None if state_changing else proposal.pending_evidence,
    )
    fields.update(overrides)
    return replace(proposal, **fields)


def _finish(
    proposal: SelfEvolutionProposal,
    *,
    gate: SelfEvolutionGate,
    from_state: SelfEvolutionState,
    to_state: SelfEvolutionState,
    gate_record_ids: tuple[str, ...],
    outcome: TruthfulValue[Any],
    detail: str,
    timestamp: str | None,
    environment: str,
    **overrides: Any,
) -> SelfEvolutionTransitionResult:
    step = SelfEvolutionStep(
        proposal_id=proposal.id,
        target_revision=proposal.target_revision,
        from_state=from_state,
        to_state=to_state,
        gate=gate,
        gate_record_ids=gate_record_ids,
        outcome=outcome,
        detail=detail,
        traceability=proposal.traceability,
        timestamp=timestamp,
        environment=environment,
    )
    evidence = step_to_w4_evidence(step, traceability=proposal.traceability)
    advanced = _advanced(proposal, state=to_state, evidence_id=evidence.id, **overrides)
    return SelfEvolutionTransitionResult(proposal=advanced, step=step, evidence=evidence)


# ---------------------------------------------------------------------------
# The governed evaluation surface (one call advances exactly one proposal;
# NO proposal-generation path — it evaluates proposals, it never creates,
# mutates, or re-generates them)
# ---------------------------------------------------------------------------


def transition_self_evolution(
    proposal: SelfEvolutionProposal,
    new_state: SelfEvolutionState,
    *,
    known_assurance: Mapping[str, AssuranceResult],
    known_experiments: Mapping[str, Experiment],
    known_evaluations: Mapping[str, ExperimentEvaluation],
    known_promotions: Mapping[str, PromotionDecision],
    known_decisions: Mapping[str, AutonomyDecision],
    known_evidence: Mapping[str, Evidence],
    known_proposals: Mapping[str, SelfEvolutionProposal],
    known_hypotheses: Mapping[str, CausalHypothesis] | None = None,
    known_candidates: Mapping[str, CandidateProposal] | None = None,
    assurance_result_id: str | None = None,
    experiment_id: str | None = None,
    evaluation_id: str | None = None,
    promotion_id: str | None = None,
    autonomy_decision_id: str | None = None,
    rollback_path: RollbackPath | None = None,
    adoption_revision: str | None = None,
    timestamp: str | None = None,
    environment: str = "simulation",
) -> SelfEvolutionTransitionResult:
    """Advance exactly one proposal through one governed lifecycle transition.

    Every gate requirement below is frozen in code and validated against the
    caller-supplied registries; nothing is data-configurable. Skipping a gate,
    an out-of-table transition, or an unbound/forged gate record is rejected
    with ``SelfEvolutionContractError``. The W8 ``PromotionGate`` engine is
    re-run at every promotion-carrying transition so a supplied gate decision
    can never outrank the real authority.
    """
    if not isinstance(proposal, SelfEvolutionProposal):
        raise SelfEvolutionContractError(
            "transition_self_evolution requires a real SelfEvolutionProposal"
        )
    if not isinstance(new_state, SelfEvolutionState):
        raise SelfEvolutionContractError(
            f"new_state must be a SelfEvolutionState, got {new_state!r}"
        )
    # Full record re-validation (intake policy + citations + recursion chain)
    # against the caller-supplied registries, then the frozen table check.
    proposal.validate(
        known_evidence=known_evidence,
        known_hypotheses=known_hypotheses,
        known_candidates=known_candidates,
        known_proposals=known_proposals,
    )
    # Governed intake strictness: a citation that CANNOT be validated (the
    # registry was not supplied) is refused — provenance is never assumed.
    if proposal.hypothesis.causal_hypothesis_ids and known_hypotheses is None:
        raise SelfEvolutionContractError(
            "the hypothesis cites W5 causal priors but no known_hypotheses registry "
            "was supplied; citations must be validated"
        )
    if proposal.candidate_ref is not None and known_candidates is None:
        raise SelfEvolutionContractError(
            "the proposal cites a W6 candidate but no known_candidates registry was "
            "supplied; citations must be validated"
        )
    validate_self_evolution_transition(proposal.state, new_state)
    from_state = proposal.state

    # -- PROPOSED -> UNDER_ASSURANCE: the only entry (intake) ---------------
    if new_state == SelfEvolutionState.UNDER_ASSURANCE:
        chain_ids = resolve_meta_chain(proposal, known_proposals)
        citations = (
            tuple(chain_ids)
            + tuple(proposal.hypothesis.trigger_evidence_ids)
            + tuple(proposal.hypothesis.causal_hypothesis_ids)
            + ((proposal.candidate_ref,) if proposal.candidate_ref is not None else ())
        )
        return _finish(
            proposal,
            gate=SelfEvolutionGate.INTAKE,
            from_state=from_state,
            to_state=new_state,
            gate_record_ids=citations,
            outcome=TruthfulValue(
                TruthState.SUCCESS, SelfEvolutionState.UNDER_ASSURANCE.value, None
            ),
            detail=(
                "intake validation passed: payload shape, path policy, recursion bound, "
                "provenance citations, and traceability verified; proposal admitted to "
                "governed assurance"
            ),
            timestamp=timestamp,
            environment=environment,
        )

    # -- * -> UNDER_EXPERIMENT: the W7 PASS gate (C3) -----------------------
    if new_state == SelfEvolutionState.UNDER_EXPERIMENT:
        assurance = _resolve_w7(assurance_result_id, known_assurance, proposal)
        if assurance.status != AssuranceStatus.PASS:
            raise SelfEvolutionContractError(
                f"W7-before-W8 ordering invariant: UNDER_EXPERIMENT requires a PASS W7 "
                f"assurance result bound to the exact proposal/target-revision chain; "
                f"the supplied result status is {assurance.status.value}"
            )
        return _finish(
            proposal,
            gate=SelfEvolutionGate.W7_ASSURANCE,
            from_state=from_state,
            to_state=new_state,
            gate_record_ids=(assurance.id,),
            outcome=TruthfulValue(TruthState.SUCCESS, assurance.id, None),
            detail=(
                "W7 assurance PASS bound to the exact proposal/target-revision chain; "
                "the governed experiment stage is unlocked"
            ),
            timestamp=timestamp,
            environment=environment,
            assurance_result_id=assurance.id,
            assurance_status=AssuranceStatus.PASS,
        )

    # -- * -> UNDER_AUTHORITY: the W8 promotion gate or the W9 resume gate ---
    if new_state == SelfEvolutionState.UNDER_AUTHORITY:
        if from_state == SelfEvolutionState.UNDER_EXPERIMENT:
            assurance, experiment, evaluation = _resolve_w8_chain(
                proposal,
                experiment_id=experiment_id,
                evaluation_id=evaluation_id,
                known_assurance=known_assurance,
                known_experiments=known_experiments,
                known_evaluations=known_evaluations,
            )
            gate_decision = _resolve_promotion(
                promotion_id, known_promotions, experiment, evaluation
            )
            if not gate_decision.promoted:
                raise SelfEvolutionContractError(
                    "the W8 promotion gate did not grant promotion: "
                    f"{gate_decision.rationale}"
                )
            # Re-run the REAL W8 PromotionGate over the supplied chain: a
            # supplied decision can never outrank the real authority.
            rederived = PromotionGate().evaluate(experiment, evaluation, known_assurance=assurance)
            if not rederived.promoted:
                raise SelfEvolutionContractError(
                    "the real W8 PromotionGate refused promotion over the supplied chain: "
                    f"{rederived.rationale}"
                )
            _validate_recovery(proposal, rollback_path, known_evidence)
            return _finish(
                proposal,
                gate=SelfEvolutionGate.W8_PROMOTION,
                from_state=from_state,
                to_state=new_state,
                gate_record_ids=(experiment.id, evaluation.id, promotion_id or ""),
                outcome=TruthfulValue(TruthState.SUCCESS, promotion_id, None),
                detail=(
                    "W8 PromotionGate granted promotion over the exact experiment/evaluation "
                    "chain with a bounded rollback path bound to the declared rollback "
                    "reference; the authority stage is unlocked"
                ),
                timestamp=timestamp,
                environment=environment,
                experiment_id=experiment.id,
                evaluation_id=evaluation.id,
                promotion_id=promotion_id,
            )
        # from PAUSED_ASKING: leaving the pause requires a NEW resolved
        # decision (C5) — never a silent default, never an auto-approve.
        decision = _resolve_decision(autonomy_decision_id, known_decisions)
        if decision.state != AutonomyDecisionState.ACT:
            raise SelfEvolutionContractError(
                f"leaving PAUSED_ASKING requires a NEW resolved W9 ACT decision; the supplied "
                f"decision state is {decision.state.value}"
            )
        _check_decision_chain(decision, proposal)
        return _finish(
            proposal,
            gate=SelfEvolutionGate.W9_RESUME,
            from_state=from_state,
            to_state=new_state,
            gate_record_ids=(decision.id,),
            outcome=TruthfulValue(TruthState.SUCCESS, decision.id, None),
            detail=(
                "the ASK pause was left via a new resolved W9 ACT decision (human authority); "
                "the proposal re-enters the authority stage"
            ),
            timestamp=timestamp,
            environment=environment,
            autonomy_decision_id=decision.id,
        )

    # -- UNDER_AUTHORITY -> PROMOTED: the ONLY promotion point (C4) ---------
    if new_state == SelfEvolutionState.PROMOTED:
        decision = _resolve_decision(autonomy_decision_id, known_decisions)
        if decision.state != AutonomyDecisionState.ACT:
            raise SelfEvolutionContractError(
                f"PROMOTED requires a resolved W9 ACT decision; the supplied decision state "
                f"is {decision.state.value} (no auto-promotion without ACT)"
            )
        _check_decision_chain(decision, proposal, require_promotion_ref=True)
        assurance, experiment, evaluation = _resolve_w8_chain(
            proposal,
            experiment_id=proposal.experiment_id,
            evaluation_id=proposal.evaluation_id,
            known_assurance=known_assurance,
            known_experiments=known_experiments,
            known_evaluations=known_evaluations,
        )
        # Re-run the real W8 PromotionGate at the promotion point too.
        rederived = PromotionGate().evaluate(experiment, evaluation, known_assurance=assurance)
        if not rederived.promoted:
            raise SelfEvolutionContractError(
                "the real W8 PromotionGate refused promotion at the promotion point: "
                f"{rederived.rationale}"
            )
        # The authorizing decision's evidence must be the W8 evaluation's own
        # observed evidence, all SUCCESS (the W9-F15 binding).
        if not decision.evidence_ids:
            raise SelfEvolutionContractError(
                "the authorizing W9 ACT decision must carry the W8 evaluation's evidence ids"
            )
        if set(decision.evidence_ids) != set(evaluation.evidence_ids):
            raise SelfEvolutionContractError(
                "the authorizing W9 decision's evidence ids do not match the W8 evaluation's "
                "observed evidence (chain mismatch)"
            )
        for eid in decision.evidence_ids:
            record = known_evidence.get(eid)
            if record is None:
                raise SelfEvolutionContractError(
                    f"authorizing decision evidence '{eid}' is not present in the "
                    "known_evidence registry"
                )
            if record.result.state != TruthState.SUCCESS:
                raise SelfEvolutionContractError(
                    f"authorizing decision evidence '{eid}' observed state "
                    f"{record.result.state.value}; ACT requires SUCCESS evidence"
                )
        # C7: every promotion-carrying transition binds the bounded rollback.
        _validate_recovery(proposal, rollback_path, known_evidence)
        if adoption_revision is not None and not adoption_revision.strip():
            raise SelfEvolutionContractError(
                "adoption_revision must be a non-empty revision citation when supplied"
            )
        return _finish(
            proposal,
            gate=SelfEvolutionGate.W9_AUTHORITY,
            from_state=from_state,
            to_state=new_state,
            gate_record_ids=(decision.id, proposal.rollback_ref),
            outcome=TruthfulValue(TruthState.SUCCESS, decision.id, None),
            detail=(
                "W9 ACT decision resolved the authority gate; the proposal is PROMOTED as a "
                "governed decision record (adoption into SOS sources remains ordinary "
                "repository governance outside this machinery)"
            ),
            timestamp=timestamp,
            environment=environment,
            autonomy_decision_id=decision.id,
            adoption_revision=adoption_revision,
        )

    # -- UNDER_AUTHORITY -> PAUSED_ASKING: the W9 ASK pause (C5) ------------
    if new_state == SelfEvolutionState.PAUSED_ASKING:
        decision = _resolve_decision(autonomy_decision_id, known_decisions)
        if decision.state != AutonomyDecisionState.ASK:
            raise SelfEvolutionContractError(
                f"PAUSED_ASKING requires a resolved W9 ASK decision; the supplied decision "
                f"state is {decision.state.value}"
            )
        _check_decision_chain(decision, proposal)
        pending = PendingProposalAuthorization.from_decision(decision, proposal_id=proposal.id)
        return _finish(
            proposal,
            gate=SelfEvolutionGate.W9_ASK,
            from_state=from_state,
            to_state=new_state,
            gate_record_ids=(decision.id,),
            outcome=TruthfulValue(
                TruthState.UNKNOWN, None,
                f"proposal paused pending human authorization (W9 ASK): {decision.rationale}",
            ),
            detail=(
                "the authority gate resolved to ASK; the proposal is paused with an explicit "
                "pending-authorization record (never auto-approved)"
            ),
            timestamp=timestamp,
            environment=environment,
            autonomy_decision_id=decision.id,
            pending_authorization=pending,
        )

    # -- * -> REJECTED: refusal grounds (W9 REJECT / resolved non-PASS W7 /
    #    refused W8 promotion decision) --------------------------------------
    if new_state == SelfEvolutionState.REJECTED:
        if from_state == SelfEvolutionState.UNDER_ASSURANCE:
            assurance = _resolve_w7(assurance_result_id, known_assurance, proposal)
            if assurance.status == AssuranceStatus.PASS:
                raise SelfEvolutionContractError(
                    "a PASS W7 assurance result cannot ground a rejection; advance to "
                    "UNDER_EXPERIMENT instead"
                )
            truth = _ASSURANCE_TRUTH[assurance.status]
            return _finish(
                proposal,
                gate=SelfEvolutionGate.W7_ASSURANCE,
                from_state=from_state,
                to_state=new_state,
                gate_record_ids=(assurance.id,),
                outcome=TruthfulValue(
                    truth, None,
                    f"W7 assurance status {assurance.status.value}: the proposal is rejected "
                    "on a resolved non-PASS result",
                ),
                detail=(
                    f"W7 assurance resolved to {assurance.status.value}; the distinct status "
                    "is preserved verbatim in the step and its W4 evidence"
                ),
                timestamp=timestamp,
                environment=environment,
                assurance_result_id=assurance.id,
                assurance_status=assurance.status,
            )
        if from_state == SelfEvolutionState.UNDER_EXPERIMENT:
            assurance, experiment, evaluation = _resolve_w8_chain(
                proposal,
                experiment_id=experiment_id,
                evaluation_id=evaluation_id,
                known_assurance=known_assurance,
                known_experiments=known_experiments,
                known_evaluations=known_evaluations,
            )
            gate_decision = _resolve_promotion(
                promotion_id, known_promotions, experiment, evaluation
            )
            if gate_decision.promoted:
                raise SelfEvolutionContractError(
                    "a promoted W8 gate decision cannot ground a rejection; advance to "
                    "UNDER_AUTHORITY instead"
                )
            rederived = PromotionGate().evaluate(experiment, evaluation, known_assurance=assurance)
            if rederived.promoted:
                raise SelfEvolutionContractError(
                    "the supplied promotion decision disagrees with the real W8 PromotionGate "
                    "(the real gate granted promotion over this chain)"
                )
            return _finish(
                proposal,
                gate=SelfEvolutionGate.W8_PROMOTION,
                from_state=from_state,
                to_state=new_state,
                gate_record_ids=(experiment.id, evaluation.id, promotion_id or ""),
                outcome=TruthfulValue(
                    TruthState.FAILED, None,
                    f"the W8 promotion gate refused promotion: {gate_decision.rationale}",
                ),
                detail=(
                    "the W8 promotion gate resolved negatively over the exact chain; the "
                    "proposal is rejected with the refusal preserved"
                ),
                timestamp=timestamp,
                environment=environment,
                experiment_id=experiment.id,
                evaluation_id=evaluation.id,
                promotion_id=promotion_id,
            )
        # from PROPOSED / UNDER_AUTHORITY / PAUSED_ASKING: a W9 REJECT decision.
        decision = _resolve_decision(autonomy_decision_id, known_decisions)
        if decision.state != AutonomyDecisionState.REJECT:
            raise SelfEvolutionContractError(
                f"REJECTED requires a resolved W9 REJECT decision; the supplied decision "
                f"state is {decision.state.value}"
            )
        _check_decision_chain(decision, proposal)
        return _finish(
            proposal,
            gate=SelfEvolutionGate.W9_REJECT,
            from_state=from_state,
            to_state=new_state,
            gate_record_ids=(decision.id,),
            outcome=TruthfulValue(
                TruthState.FAILED, None,
                f"W9 REJECT refused the proposal: {decision.rationale}",
            ),
            detail=(
                "the W9 authority gate refused the proposal; the refusal is terminal"
            ),
            timestamp=timestamp,
            environment=environment,
            autonomy_decision_id=decision.id,
        )

    # -- * -> ROLLED_BACK: governed recovery, always evidence-backed (C7) ---
    if new_state == SelfEvolutionState.ROLLED_BACK:
        if from_state == SelfEvolutionState.UNDER_EXPERIMENT:
            assurance = _resolve_w7(proposal.assurance_result_id, known_assurance, proposal)
            if not experiment_id or not experiment_id.strip():
                raise SelfEvolutionContractError(
                    "the experiment rollback requires the W8 experiment id"
                )
            experiment = known_experiments.get(experiment_id)
            if experiment is None:
                raise SelfEvolutionContractError(
                    f"W8 experiment '{experiment_id}' is not present in the caller-supplied "
                    "known_experiments registry"
                )
            if not isinstance(experiment, Experiment):
                raise SelfEvolutionContractError(
                    f"known_experiments['{experiment_id}'] is not a real W8 Experiment"
                )
            if experiment.candidate_id != proposal.id:
                raise SelfEvolutionContractError(
                    "the W8 experiment is not bound to the exact proposal"
                )
            if experiment.assurance_result_id != assurance.id:
                raise SelfEvolutionContractError(
                    "the W8 experiment is not bound to the exact W7 assurance result"
                )
            if experiment.provenance_revision != proposal.target_revision:
                raise SelfEvolutionContractError(
                    "the W8 experiment is not bound to the proposal target revision"
                )
            experiment.validate(known_assurance=assurance)
            if experiment.state != ExperimentState.ROLLED_BACK:
                raise SelfEvolutionContractError(
                    "the W8 experiment lifecycle must itself be ROLLED_BACK (W8-governed "
                    f"recovery); experiment state is {experiment.state.value}"
                )
            path = _validate_recovery(proposal, rollback_path, known_evidence)
            return _finish(
                proposal,
                gate=SelfEvolutionGate.W8_EXPERIMENT_ROLLBACK,
                from_state=from_state,
                to_state=new_state,
                gate_record_ids=(experiment.id, path.reference),
                outcome=TruthfulValue(
                    TruthState.SUCCESS, path.reference,
                    "W8 experiment lifecycle rolled back with governed recovery evidence",
                ),
                detail=(
                    "the governed W8 experiment lifecycle itself rolled back; recovery is "
                    "backed by SUCCESS evidence bound to the declared rollback reference"
                ),
                timestamp=timestamp,
                environment=environment,
                experiment_id=experiment.id,
            )
        # from UNDER_AUTHORITY / PROMOTED: a resolved W9 ROLLBACK decision.
        decision = _resolve_decision(autonomy_decision_id, known_decisions)
        if decision.state != AutonomyDecisionState.ROLLBACK:
            raise SelfEvolutionContractError(
                f"ROLLED_BACK requires a resolved W9 ROLLBACK decision; the supplied "
                f"decision state is {decision.state.value}"
            )
        _check_decision_chain(decision, proposal)
        path = _validate_recovery(proposal, rollback_path, known_evidence)
        return _finish(
            proposal,
            gate=SelfEvolutionGate.W9_ROLLBACK,
            from_state=from_state,
            to_state=new_state,
            gate_record_ids=(decision.id, path.reference),
            outcome=TruthfulValue(
                TruthState.SUCCESS, path.reference,
                f"governed rollback applied under W9 ROLLBACK authority with recovery "
                f"evidence: {decision.rationale}",
            ),
            detail=(
                "the W9 authority gate resolved to ROLLBACK; the recovery is backed by "
                "SUCCESS evidence bound to the declared rollback reference"
            ),
            timestamp=timestamp,
            environment=environment,
            autonomy_decision_id=decision.id,
        )

    raise SelfEvolutionContractError(
        f"unhandled governed transition {from_state.value} -> {new_state.value}"
    )


def defer_self_evolution(
    proposal: SelfEvolutionProposal,
    autonomy_decision_id: str,
    *,
    known_decisions: Mapping[str, AutonomyDecision],
    timestamp: str | None = None,
    environment: str = "simulation",
) -> SelfEvolutionTransitionResult:
    """Record a non-resolving W9 deferral (GATHER_EVIDENCE / EXPERIMENT).

    The proposal keeps its current state (no advancement, no refusal) and
    carries an explicit pending-evidence record; the step and its W4 evidence
    record the truthful UNKNOWN deferral. One call advances exactly one
    proposal; there is no chaining.
    """
    if not isinstance(proposal, SelfEvolutionProposal):
        raise SelfEvolutionContractError(
            "defer_self_evolution requires a real SelfEvolutionProposal"
        )
    if proposal.state not in (SelfEvolutionState.UNDER_AUTHORITY, SelfEvolutionState.PAUSED_ASKING):
        raise SelfEvolutionContractError(
            "a deferral is only lawful while the proposal awaits W9 authority "
            f"(state is {proposal.state.value})"
        )
    decision = _resolve_decision(autonomy_decision_id, known_decisions)
    if decision.state not in (AutonomyDecisionState.GATHER_EVIDENCE, AutonomyDecisionState.EXPERIMENT):
        raise SelfEvolutionContractError(
            f"a deferral requires a non-resolving W9 decision (GATHER_EVIDENCE or "
            f"EXPERIMENT); the supplied decision state is {decision.state.value}"
        )
    _check_decision_chain(decision, proposal)
    pending = PendingProposalEvidence.from_decision(decision, proposal_id=proposal.id)
    return _finish(
        proposal,
        gate=SelfEvolutionGate.W9_DEFERRAL,
        from_state=proposal.state,
        to_state=proposal.state,
        gate_record_ids=(decision.id,),
        outcome=TruthfulValue(
            TruthState.UNKNOWN, None,
            f"W9 {decision.state.value} deferral: no advancement, no refusal: "
            f"{decision.rationale}",
        ),
        detail=(
            "the W9 authority gate deferred (evidence not yet resolved); the proposal keeps "
            "its state and carries an explicit pending-evidence record"
        ),
        timestamp=timestamp,
        environment=environment,
        autonomy_decision_id=decision.id,
        pending_evidence=pending,
    )
