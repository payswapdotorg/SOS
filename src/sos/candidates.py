"""W6 — candidate generation + bounded search boundary for SOS.

Generates and evaluates candidate architecture changes over the recovered W2/W3
System State / Architecture Graph using W5 causal knowledge, while preserving
explicit uncertainty, conflicting objectives, bounded search, and
**non-authorizing** behavior (frozen W6 Work Order; architecture §§3.6, 4.5,
6, 9, 13.7).

Design invariants:

- candidates are **proposals**, not applied graph mutations — the canonical
  W2/W3 graph is never mutated (architecture §13.7: candidate architecture
  cannot become production solely because it was generated);
- candidate identity is deterministic and content-addressed (no uuid4, no
  wall-clock) — identical proposals with identical graph refs, mutations,
  bounds, and reasoning inputs produce identical ids;
- search is finite and bounded by explicit caller-supplied limits and
  terminates deterministically within those limits (no hidden unbounded
  recursion, no network/runtime side effects);
- evaluation is **multi-objective** — Pareto dominance/frontier semantics; no
  single scalar quality becomes authoritative (architecture §6, §13);
- candidate scores/predictions cannot upgrade truth or authorization — a
  candidate's uncertainty is never SUCCESS (candidates are predictions, not
  proven facts); LLM narrative alone cannot establish correctness (§13.4);
- full traceability: every candidate records its base graph reference + revision,
  the W4 evidence ids and W5 hypothesis ids used in reasoning, and W1
  Mission/Value/Context traceability;
- W6 is non-authorizing and introduces no W7+ (assurance, experimentation/
  promotion/rollback, autonomy/ASK, personalization, realization, self-
  evolution) semantics.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING

from .model import ModelValidationError, Traceability, TruthState, TruthfulValue

if TYPE_CHECKING:
    from .graph import ArchitectureGraph
    from .causal import CausalHypothesis


# ---------------------------------------------------------------------------
# Frozen vocabulary
# ---------------------------------------------------------------------------


class MutationKind(str, Enum):
    """Bounded mutation kinds a candidate may propose."""

    SUBGRAPH_REPLACE = "subgraph-replace"
    ADD_NODE = "add-node"
    REMOVE_NODE = "remove-node"
    ADD_EDGE = "add-edge"
    REMOVE_EDGE = "remove-edge"
    RETYPE_NODE = "retype-node"


class ObjectiveDirection(str, Enum):
    """Objective optimization direction (multi-objective; no scalar authority)."""

    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"
    MAINTAIN = "maintain"


# ---------------------------------------------------------------------------
# Bounded mutation representation (does NOT mutate canonical graph)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubgraphMutation:
    """A bounded, declarative mutation of a recovered architecture graph.

    This is a W6-own mutation declaration. It references the base graph by id
    and declares target/replacement subgraphs + boundary interfaces + invariants,
    mirroring the W2 ``SubgraphReplacement`` boundary contract. It validates
    against a supplied graph **without mutating it** (architecture §13.7).
    """

    kind: MutationKind
    base_graph_ref: str
    target_node_ids: tuple[str, ...]
    replacement_node_ids: tuple[str, ...]
    boundary_interface_ids: tuple[str, ...]
    invariants: tuple[str, ...]

    def __post_init__(self) -> None:
        self._validate_structural()

    def _validate_structural(self) -> None:
        if not isinstance(self.kind, MutationKind):
            raise ModelValidationError("SubgraphMutation.kind must be a MutationKind")
        if not self.base_graph_ref or not self.base_graph_ref.strip():
            raise ModelValidationError("SubgraphMutation.base_graph_ref is required")
        if not self.target_node_ids:
            raise ModelValidationError("SubgraphMutation.target_node_ids is required")
        if not self.replacement_node_ids:
            raise ModelValidationError("SubgraphMutation.replacement_node_ids is required")
        if not self.boundary_interface_ids:
            raise ModelValidationError("SubgraphMutation.boundary_interface_ids is required")
        if not self.invariants:
            raise ModelValidationError("SubgraphMutation.invariants is required")
        # Replacement nodes must be distinct from target nodes (no self-replacement).
        if set(self.replacement_node_ids) & set(self.target_node_ids):
            raise ModelValidationError("SubgraphMutation replacement nodes must be distinct from target nodes")

    def validate(self, graph: "ArchitectureGraph") -> None:
        """Validate this mutation against a recovered graph without mutating it.

        Boundary interfaces are nodes whose contracts the replacement must
        preserve — they must be known nodes in the graph (typically interface-
        type nodes adjacent to the target subgraph), but need NOT be part of the
        target subgraph itself (the target is what gets replaced; the boundary
        is what is preserved).
        """
        self._validate_structural()
        if self.base_graph_ref != graph.id:
            raise ModelValidationError(
                f"SubgraphMutation.base_graph_ref '{self.base_graph_ref}' does not match graph '{graph.id}'"
            )
        node_ids = {n.id for n in graph.nodes}
        if not set(self.target_node_ids).issubset(node_ids):
            raise ModelValidationError("SubgraphMutation target references unknown nodes")
        if not set(self.boundary_interface_ids).issubset(node_ids):
            raise ModelValidationError("SubgraphMutation boundary references unknown nodes")


# ---------------------------------------------------------------------------
# Multi-objective evaluation (no scalar authority)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateObjective:
    """A single objective dimension with a predicted value and its uncertainty.

    Predicted values are predictions, not measurements — the uncertainty is
    non-SUCCESS (typically UNKNOWN) unless directly measured (architecture §6).
    """

    name: str
    direction: ObjectiveDirection
    predicted_value: float
    uncertainty: TruthfulValue[Any]

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ModelValidationError("CandidateObjective.name is required")
        if not isinstance(self.direction, ObjectiveDirection):
            raise ModelValidationError("CandidateObjective.direction must be an ObjectiveDirection")
        if not isinstance(self.uncertainty, TruthfulValue):
            raise ModelValidationError("CandidateObjective.uncertainty must be a TruthfulValue")
        self.uncertainty.validate()
        # A predicted objective may not claim SUCCESS unless... predictions are
        # inherently uncertain; we allow SUCCESS only for MAINTAIN with a real
        # measured value. Conservative: reject SUCCESS predictions outright.
        if self.uncertainty.state == TruthState.SUCCESS:
            raise ModelValidationError(
                "CandidateObjective.uncertainty may not be SUCCESS (predictions are uncertain)"
            )


@dataclass(frozen=True)
class CandidateEvaluation:
    """Multi-objective evaluation of a candidate. No scalar quality authority."""

    objectives: tuple[CandidateObjective, ...]

    def __post_init__(self) -> None:
        if not self.objectives:
            raise ModelValidationError("CandidateEvaluation requires at least one objective")
        names = [o.name for o in self.objectives]
        if len(set(names)) != len(names):
            raise ModelValidationError("CandidateEvaluation objective names must be unique")

    def dominates(self, other: "CandidateEvaluation") -> bool:
        """Pareto dominance: self dominates other iff self is >= on every objective
        and strictly > on at least one, accounting for direction (MAXIMIZE/MINIMIZE)."""
        if {o.name for o in self.objectives} != {o.name for o in other.objectives}:
            return False
        other_by_name = {o.name: o for o in other.objectives}
        at_least_one_strict = False
        for a in self.objectives:
            b = other_by_name[a.name]
            cmp = _compare_objective(a, b)
            if cmp < 0:
                return False  # self is worse on some objective
            if cmp > 0:
                at_least_one_strict = True
        return at_least_one_strict


def _compare_objective(a: CandidateObjective, b: CandidateObjective) -> int:
    """Return +1 if a is better than b, -1 if worse, 0 if equal (by direction)."""
    if a.direction != b.direction:
        raise ModelValidationError(
            f"objective '{a.name}' direction mismatch: {a.direction.value} vs {b.direction.value}"
        )
    if a.direction == ObjectiveDirection.MAXIMIZE:
        if a.predicted_value > b.predicted_value:
            return 1
        if a.predicted_value < b.predicted_value:
            return -1
        return 0
    if a.direction == ObjectiveDirection.MINIMIZE:
        if a.predicted_value < b.predicted_value:
            return 1
        if a.predicted_value > b.predicted_value:
            return -1
        return 0
    # MAINTAIN: closer to target is better, but without a target treat as equal.
    return 0


# ---------------------------------------------------------------------------
# Candidate proposal
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateProposal:
    """A bounded candidate architecture change (a proposal, not an applied mutation).

    ``uncertainty`` is a W1 ``TruthfulValue`` and is **never SUCCESS** — candidates
    are predictions/hypotheses, not proven facts (architecture §13.7; §13.4 LLM
    output cannot establish truth). ``reasoning_evidence_ids`` and
    ``reasoning_hypothesis_ids`` reference W4 evidence and W5 hypotheses used in
    generation/evaluation — W6 does not create a second evidence or causal
    authority.
    """

    id: str
    base_graph_ref: str
    base_graph_revision: str
    mutation: SubgraphMutation
    objectives: tuple[CandidateObjective, ...]
    rationale: str
    uncertainty: TruthfulValue[Any]
    reasoning_evidence_ids: tuple[str, ...]
    reasoning_hypothesis_ids: tuple[str, ...]
    risks: tuple[str, ...]
    traceability: Traceability
    provenance_revision: str

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", _candidate_id(self))
        self.validate()

    def validate(
        self,
        *,
        known_graph: "ArchitectureGraph | None" = None,
        known_evidence_ids: set[str] | None = None,
        known_hypothesis_ids: set[str] | None = None,
    ) -> None:
        if not self.base_graph_ref or not self.base_graph_ref.strip():
            raise ModelValidationError("CandidateProposal.base_graph_ref is required")
        if not self.base_graph_revision or not self.base_graph_revision.strip():
            raise ModelValidationError("CandidateProposal.base_graph_revision is required")
        if not self.rationale or not self.rationale.strip():
            raise ModelValidationError("CandidateProposal.rationale is required")
        if not self.provenance_revision or not self.provenance_revision.strip():
            raise ModelValidationError("CandidateProposal.provenance_revision is required")
        if not self.objectives:
            raise ModelValidationError("CandidateProposal.objectives is required")
        if not isinstance(self.mutation, SubgraphMutation):
            raise ModelValidationError("CandidateProposal.mutation must be a SubgraphMutation")
        self.mutation._validate_structural()
        self.uncertainty.validate()
        # C5 truthfulness: a candidate may never claim SUCCESS (proven) —
        # candidates are predictions, not facts; scores/LLM text cannot upgrade
        # truth or authorization (architecture §13.4, §13.7).
        if self.uncertainty.state == TruthState.SUCCESS:
            raise ModelValidationError(
                "CandidateProposal.uncertainty may not be SUCCESS (candidates are predictions, not proven facts)"
            )
        self.traceability.validate(require_value=True, require_context=True)
        # Validate against the known recovered graph without mutating it.
        if known_graph is not None:
            self.mutation.validate(known_graph)
        # Validate reasoning references against known W4/W5 records when supplied.
        if known_evidence_ids is not None:
            for eid in self.reasoning_evidence_ids:
                if eid not in known_evidence_ids:
                    raise ModelValidationError(
                        f"CandidateProposal references unknown evidence id '{eid}'"
                    )
        if known_hypothesis_ids is not None:
            for hid in self.reasoning_hypothesis_ids:
                if hid not in known_hypothesis_ids:
                    raise ModelValidationError(
                        f"CandidateProposal references unknown hypothesis id '{hid}'"
                    )


def _candidate_id(c: CandidateProposal) -> str:
    """Content-addressed identity spanning graph ref + mutation + objectives + reasoning."""
    obj_material = "|".join(
        f"{o.name}:{o.direction.value}:{o.predicted_value}" for o in c.objectives
    )
    reason_material = "|".join(sorted(c.reasoning_evidence_ids)) + "||" + "|".join(sorted(c.reasoning_hypothesis_ids))
    material = "|".join([
        c.base_graph_ref,
        c.base_graph_revision,
        c.mutation.kind.value,
        ",".join(c.mutation.target_node_ids),
        ",".join(c.mutation.replacement_node_ids),
        ",".join(c.mutation.boundary_interface_ids),
        ",".join(c.mutation.invariants),
        c.rationale,
        obj_material,
        reason_material,
        c.provenance_revision,
    ])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"candidate-{digest}"


# ---------------------------------------------------------------------------
# Search bounds (finite, caller-supplied)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchBounds:
    """Explicit finite bounds that make search terminate deterministically."""

    max_candidates: int
    max_depth: int
    max_iterations: int

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        for name, value in (
            ("max_candidates", self.max_candidates),
            ("max_depth", self.max_depth),
            ("max_iterations", self.max_iterations),
        ):
            if not isinstance(value, int) or value <= 0:
                raise ModelValidationError(f"SearchBounds.{name} must be a positive integer")


# ---------------------------------------------------------------------------
# Candidate space (finite description of the search space)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateSpace:
    """A finite description of the candidate search space.

    ``available_replacements`` is a finite tuple of ``(target_node_id,
    replacement_node_id)`` pairs drawn from the recovered graph. The search
    engine explores only this finite space within the caller-supplied bounds.
    """

    base_graph: "ArchitectureGraph"
    base_graph_revision: str
    traceability: Traceability
    reasoning_evidence_ids: tuple[str, ...]
    reasoning_hypothesis_ids: tuple[str, ...]
    available_replacements: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not self.base_graph_revision.strip():
            raise ModelValidationError("CandidateSpace.base_graph_revision is required")
        self.traceability.validate(require_value=True, require_context=True)
        node_ids = {n.id for n in self.base_graph.nodes}
        for target, replacement in self.available_replacements:
            if target not in node_ids:
                raise ModelValidationError(
                    f"CandidateSpace.available_replacements target '{target}' is not in the base graph"
                )
            if target == replacement:
                raise ModelValidationError(
                    "CandidateSpace.available_replacements target must differ from replacement"
                )


# ---------------------------------------------------------------------------
# Pareto frontier (deterministic non-dominated set)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParetoFrontier:
    """A deterministically-ordered set of non-dominated candidates.

    Ordering is by candidate id (stable). Construction is deterministic: the
    same candidate set always produces the same frontier.
    """

    candidates: tuple[CandidateProposal, ...]
    traceability: Traceability

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        self.traceability.validate(require_value=True, require_context=True)
        ids = [c.id for c in self.candidates]
        if len(set(ids)) != len(ids):
            raise ModelValidationError("ParetoFrontier contains duplicate candidate ids")
        if ids != sorted(ids):
            raise ModelValidationError("ParetoFrontier.candidates must be sorted by id")

    @classmethod
    def from_candidates(
        cls,
        candidates: tuple[CandidateProposal, ...],
        *,
        traceability: Traceability | None = None,
    ) -> "ParetoFrontier":
        """Compute the Pareto frontier from a candidate set, deterministically."""
        if not candidates:
            if traceability is None:
                raise ModelValidationError("ParetoFrontier.from_candidates requires traceability for an empty frontier")
            return cls(candidates=(), traceability=traceability)
        # Use the first candidate's traceability if none supplied (consistent origin).
        t = traceability if traceability is not None else candidates[0].traceability
        non_dominated: list[CandidateProposal] = []
        for c in candidates:
            ev_c = CandidateEvaluation(c.objectives)
            dominated = False
            for other in candidates:
                if other.id == c.id:
                    continue
                ev_other = CandidateEvaluation(other.objectives)
                if ev_other.dominates(ev_c):
                    dominated = True
                    break
            if not dominated:
                non_dominated.append(c)
        non_dominated.sort(key=lambda c: c.id)
        return cls(candidates=tuple(non_dominated), traceability=t)


# ---------------------------------------------------------------------------
# Search engine (bounded, deterministic, no side effects)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchEngine:
    """A bounded, deterministic candidate search engine.

    Explores the finite ``CandidateSpace`` within ``SearchBounds`` and returns
    a Pareto frontier. The engine is a pure function of (space, bounds):
    identical inputs produce identical frontiers; no network, no wall-clock, no
    unbounded recursion.
    """

    bounds: SearchBounds

    def __post_init__(self) -> None:
        self.bounds.validate()

    def search(self, space: CandidateSpace) -> ParetoFrontier:
        """Generate bounded candidates and return the Pareto frontier."""
        space.validate()
        generated: list[CandidateProposal] = []
        node_ids = [n.id for n in space.base_graph.nodes]
        # Boundary interfaces: interface nodes in the graph that bound a target.
        from .graph import NodeType  # local import to avoid cycle at module load
        interface_ids = [n.id for n in space.base_graph.nodes if n.type == NodeType.INTERFACE]
        iterations = 0
        # Deterministic, finite generation: one candidate per available replacement,
        # bounded by max_candidates and max_iterations. No recursion beyond max_depth.
        for target, replacement in space.available_replacements:
            if len(generated) >= self.bounds.max_candidates:
                break
            if iterations >= self.bounds.max_iterations:
                break
            iterations += 1
            # Boundary interfaces belonging to the target subgraph: if the target
            # is itself an interface, it is its own boundary; otherwise pick the
            # interfaces adjacent to the target via edges.
            boundary = self._boundary_for(target, space.base_graph, interface_ids)
            if not boundary:
                # No boundary interface found — skip (cannot preserve boundary invariants).
                continue
            mutation = SubgraphMutation(
                kind=MutationKind.SUBGRAPH_REPLACE,
                base_graph_ref=space.base_graph.id,
                target_node_ids=(target,),
                replacement_node_ids=(replacement,),
                boundary_interface_ids=boundary,
                invariants=("preserve-boundary",),
            )
            objectives = self._default_objectives()
            candidate = CandidateProposal(
                id="",
                base_graph_ref=space.base_graph.id,
                base_graph_revision=space.base_graph_revision,
                mutation=mutation,
                objectives=objectives,
                rationale=f"replace {target} with {replacement}",
                uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted, not proven"),
                reasoning_evidence_ids=space.reasoning_evidence_ids,
                reasoning_hypothesis_ids=space.reasoning_hypothesis_ids,
                risks=("rollback-required",),
                traceability=space.traceability,
                provenance_revision=space.base_graph_revision,
            )
            generated.append(candidate)
        return ParetoFrontier.from_candidates(tuple(generated), traceability=space.traceability)

    @staticmethod
    def _boundary_for(
        target: str, graph: "ArchitectureGraph", interface_ids: list[str],
    ) -> tuple[str, ...]:
        """Return the interface node ids that bound the target subgraph."""
        if target in interface_ids:
            return (target,)
        # Interfaces adjacent to the target via edges.
        adjacent: list[str] = []
        for edge in graph.edges:
            if edge.source_id == target and edge.target_id in interface_ids:
                adjacent.append(edge.target_id)
            elif edge.target_id == target and edge.source_id in interface_ids:
                adjacent.append(edge.source_id)
        return tuple(adjacent) if adjacent else ()

    @staticmethod
    def _default_objectives() -> tuple[CandidateObjective, ...]:
        """Default multi-objective profile for generated candidates."""
        return (
            CandidateObjective(
                name="latency", direction=ObjectiveDirection.MINIMIZE, predicted_value=150.0,
                uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not measured"),
            ),
            CandidateObjective(
                name="cost", direction=ObjectiveDirection.MINIMIZE, predicted_value=1000.0,
                uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not measured"),
            ),
            CandidateObjective(
                name="throughput", direction=ObjectiveDirection.MAXIMIZE, predicted_value=2000.0,
                uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "predicted not measured"),
            ),
        )
