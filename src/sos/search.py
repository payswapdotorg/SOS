"""W6 candidate generation and bounded multi-objective search."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable, Sequence

from .causal import ArchitectureMemory
from .graph import ArchitectureGraph, SubgraphReplacement
from .model import ModelValidationError, Traceability


@dataclass(frozen=True)
class SearchBudget:
    max_candidates: int

    def validate(self) -> None:
        if self.max_candidates < 1:
            raise ModelValidationError("max_candidates must be >= 1")


@dataclass(frozen=True)
class CandidateMetrics:
    """Comparable candidate attributes; benefit is maximized, others minimized."""

    benefit: float
    cost: float
    risk: float
    uncertainty: float
    reversibility: float
    blast_radius: float
    memory_prior: float = 0.0

    def validate(self) -> None:
        for name, value in (
            ("benefit", self.benefit),
            ("cost", self.cost),
            ("risk", self.risk),
            ("uncertainty", self.uncertainty),
            ("reversibility", self.reversibility),
            ("blast_radius", self.blast_radius),
            ("memory_prior", self.memory_prior),
        ):
            if not 0 <= value <= 1:
                raise ModelValidationError(f"{name} must be within [0, 1]")


@dataclass(frozen=True)
class CandidateState:
    id: str
    base_system_state_ref: str
    replacement: SubgraphReplacement
    predicted_effects: tuple[str, ...]
    risks: tuple[str, ...]
    authority_required: str
    metrics: CandidateMetrics
    traceability: Traceability
    memory_refs: tuple[str, ...] = ()

    def validate(self, graph: ArchitectureGraph) -> None:
        if not self.id or not self.base_system_state_ref or not self.authority_required:
            raise ModelValidationError("CandidateState requires id, base_system_state_ref and authority_required")
        if not self.predicted_effects or not self.risks:
            raise ModelValidationError("CandidateState requires predicted effects and risks")
        self.metrics.validate()
        self.replacement.validate(graph)
        self.traceability.validate(require_value=True, require_context=True)


@dataclass(frozen=True)
class RankedCandidates:
    candidates: tuple[CandidateState, ...]
    pareto_front: tuple[str, ...]

    def validate(self, graph: ArchitectureGraph) -> None:
        ids = {candidate.id for candidate in self.candidates}
        if len(ids) != len(self.candidates):
            raise ModelValidationError("Candidate ids must be unique")
        for candidate in self.candidates:
            candidate.validate(graph)
        if not set(self.pareto_front).issubset(ids):
            raise ModelValidationError("Pareto front references unknown candidates")


def _dominates(left: CandidateState, right: CandidateState) -> bool:
    """Pareto dominance: benefit/reversibility/prior higher; cost/risk/uncertainty/blast lower."""
    a, b = left.metrics, right.metrics
    values_a = (a.benefit, a.cost, a.risk, a.uncertainty, -a.reversibility, a.blast_radius, -a.memory_prior)
    values_b = (b.benefit, b.cost, b.risk, b.uncertainty, -b.reversibility, b.blast_radius, -b.memory_prior)
    no_worse = all(x >= y if idx in (0,) else x <= y for idx, (x, y) in enumerate(zip(values_a, values_b)))
    strictly_better = any(x > y if idx in (0,) else x < y for idx, (x, y) in enumerate(zip(values_a, values_b)))
    return no_worse and strictly_better


def pareto_front(candidates: Sequence[CandidateState]) -> tuple[CandidateState, ...]:
    front = [candidate for candidate in candidates if not any(
        other.id != candidate.id and _dominates(other, candidate) for other in candidates
    )]
    return tuple(sorted(front, key=lambda candidate: candidate.id))


def _candidate_id(replacement: SubgraphReplacement, metrics: CandidateMetrics) -> str:
    material = "|".join(
        [
            replacement.base_graph_ref,
            ",".join(replacement.target_node_ids),
            ",".join(replacement.replacement_node_ids),
            ",".join(replacement.boundary_interface_ids),
            repr((metrics.benefit, metrics.cost, metrics.risk, metrics.uncertainty, metrics.reversibility, metrics.blast_radius, metrics.memory_prior)),
        ]
    )
    return "candidate:" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


def _prior_for(replacement: SubgraphReplacement, memories: Sequence[ArchitectureMemory]) -> tuple[float, tuple[str, ...]]:
    refs: list[str] = []
    scores: list[float] = []
    target = set(replacement.target_node_ids)
    for memory in memories:
        token = memory.candidate_pattern.lower()
        if any(token in node.lower() for node in replacement.replacement_node_ids) or any(token in node.lower() for node in target):
            refs.append(memory.id)
            scores.append(memory.confidence)
    return (sum(scores) / len(scores) if scores else 0.0, tuple(sorted(refs)))


def generate_candidates(
    *,
    graph: ArchitectureGraph,
    base_system_state_ref: str,
    replacements: Iterable[SubgraphReplacement],
    metrics: Iterable[CandidateMetrics],
    authority_required: str,
    predicted_effects: Iterable[str],
    risks: Iterable[str],
    traceability: Traceability,
    budget: SearchBudget,
    memories: Sequence[ArchitectureMemory] = (),
) -> RankedCandidates:
    """Generate and rank bounded CandidateState proposals without mutation/execution."""
    budget.validate()
    graph.validate()
    traceability.validate(require_value=True, require_context=True)
    replacement_list = tuple(replacements)
    metric_list = tuple(metrics)
    if not replacement_list or not metric_list:
        raise ModelValidationError("At least one replacement and metric set are required")
    candidates: list[CandidateState] = []
    for replacement in replacement_list:
        replacement.validate(graph)
        prior, refs = _prior_for(replacement, memories)
        for base_metrics in metric_list:
            metric = CandidateMetrics(
                benefit=base_metrics.benefit,
                cost=base_metrics.cost,
                risk=base_metrics.risk,
                uncertainty=base_metrics.uncertainty,
                reversibility=base_metrics.reversibility,
                blast_radius=base_metrics.blast_radius,
                memory_prior=prior,
            )
            candidate = CandidateState(
                id=_candidate_id(replacement, metric),
                base_system_state_ref=base_system_state_ref,
                replacement=replacement,
                predicted_effects=tuple(predicted_effects),
                risks=tuple(risks),
                authority_required=authority_required,
                metrics=metric,
                traceability=traceability,
                memory_refs=refs,
            )
            candidate.validate(graph)
            candidates.append(candidate)
            if len(candidates) >= budget.max_candidates:
                break
        if len(candidates) >= budget.max_candidates:
            break

    # Deterministic candidate ordering. Memory prior is only a tie-break/input signal.
    ordered = tuple(sorted(candidates, key=lambda c: (
        -c.metrics.benefit,
        c.metrics.cost,
        c.metrics.risk,
        c.metrics.uncertainty,
        -c.metrics.reversibility,
        c.metrics.blast_radius,
        -c.metrics.memory_prior,
        c.id,
    )))
    front = pareto_front(ordered)
    result = RankedCandidates(ordered, tuple(candidate.id for candidate in front))
    result.validate(graph)
    return result
