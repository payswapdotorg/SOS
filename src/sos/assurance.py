"""W7 — assurance + impact analysis boundary for SOS.

Evaluates W6 candidate proposals for evidence-backed feasibility, impact, risk,
safety/constraint compliance, and uncertainty **without becoming an execution,
promotion, autonomy, or authority plane** (frozen W7 Work Order; architecture
§§4.6, 9, 13).

Design invariants:

- assurance is **non-authorizing**: a result carries no "authorized"/"approved"
  flag; it cannot authorize application, production promotion, autonomy, or user
  actions (architecture §13.7; W7 Work Order C10/C12);
- candidate generation/reasoning is untrusted — LLM text, candidate scores,
  confidence, or narrative cannot establish truth, safety, authorization,
  completion, or causal efficacy (§13.4);
- evidence gates are truthful: UNKNOWN/FAILED/UNAVAILABLE evidence cannot become
  PASS (C2); hard-constraint violations deterministically FAIL and cannot be
  offset by objective improvements (C4);
- causal qualification: observational W4 evidence and proposed W5 hypotheses are
  distinguishable from intervention-grade evidence; causal efficacy is never
  established from narrative or confidence alone (C6);
- impact/blast radius is bounded — no hidden unbounded graph traversal (C3);
- multi-objective integrity: W6 objectives are preserved; no single scalar
  authoritative score (C8);
- reversibility/containment is recorded but not executed (W8 owns rollback
  lifecycle) (C7);
- evaluation is deterministic and bounded — same inputs produce the same result
  (C9);
- W7 introduces no W8+ execution/authority semantics (C12).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING

from .model import ModelValidationError, Traceability, TruthState, TruthfulValue
from .evidence import Evidence, EvidenceKind

if TYPE_CHECKING:
    from .graph import ArchitectureGraph
    from .causal import CausalHypothesis
    from .candidates import CandidateProposal


# ---------------------------------------------------------------------------
# Frozen vocabulary
# ---------------------------------------------------------------------------


class AssuranceStatus(str, Enum):
    """Truthful assurance result/gate states. PASS is never the default."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    BLOCKED = "BLOCKED"


# ---------------------------------------------------------------------------
# Evidence gate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AssuranceGate:
    """A single evidence-backed assurance check with a truthful status."""

    name: str
    status: AssuranceStatus
    evidence_ids: tuple[str, ...]
    detail: str

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not self.name or not self.name.strip():
            raise ModelValidationError("AssuranceGate.name is required")
        if not isinstance(self.status, AssuranceStatus):
            raise ModelValidationError("AssuranceGate.status must be an AssuranceStatus")
        if not self.detail or not self.detail.strip():
            raise ModelValidationError("AssuranceGate.detail is required")


# ---------------------------------------------------------------------------
# Impact + blast radius
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BlastRadius:
    """A deterministic, bounded blast-radius representation."""

    level: str  # "limited" | "service" | "system" | "organization"
    affected_count: int
    detail: str

    def __post_init__(self) -> None:
        if self.level not in ("limited", "service", "system", "organization"):
            raise ModelValidationError(f"BlastRadius.level '{self.level}' is not a known level")
        if self.affected_count < 0:
            raise ModelValidationError("BlastRadius.affected_count must be non-negative")
        if not self.detail.strip():
            raise ModelValidationError("BlastRadius.detail is required")


@dataclass(frozen=True)
class ImpactAnalysis:
    """Identifies the affected graph scope, boundary exposure, and blast radius.

    Bounded: affected nodes are a subset of the graph's node ids; dependency
    reach is a finite set derived from direct adjacency (no unbounded traversal).
    """

    affected_node_ids: tuple[str, ...]
    affected_edge_ids: tuple[str, ...]
    boundary_interface_ids: tuple[str, ...]
    dependency_reach: tuple[str, ...]
    blast_radius: BlastRadius

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not self.affected_node_ids:
            raise ModelValidationError("ImpactAnalysis.affected_node_ids is required")
        if not isinstance(self.blast_radius, BlastRadius):
            raise ModelValidationError("ImpactAnalysis.blast_radius must be a BlastRadius")


# ---------------------------------------------------------------------------
# Risk assessment
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RiskItem:
    """A material risk with severity, likelihood/uncertainty, and mitigation."""

    name: str
    severity: str  # "low" | "medium" | "high" | "critical"
    uncertainty: TruthfulValue[Any]
    mitigation: str | None
    residual: str | None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ModelValidationError("RiskItem.name is required")
        if self.severity not in ("low", "medium", "high", "critical"):
            raise ModelValidationError(f"RiskItem.severity '{self.severity}' is not a known severity")
        self.uncertainty.validate()
        # Risk is never "certain" — uncertainty must not be SUCCESS.
        if self.uncertainty.state == TruthState.SUCCESS:
            raise ModelValidationError("RiskItem.uncertainty may not be SUCCESS (risk is inherently uncertain)")
        if not (self.mitigation or self.residual):
            raise ModelValidationError("RiskItem requires a mitigation or residual note")


@dataclass(frozen=True)
class RiskAssessment:
    """A collection of material risks without false certainty."""

    items: tuple[RiskItem, ...]

    def __post_init__(self) -> None:
        if not self.items:
            raise ModelValidationError("RiskAssessment requires at least one RiskItem")


# ---------------------------------------------------------------------------
# Reversibility / containment (recorded, not executed)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReversibilityAssessment:
    """Records whether governed rollback/recovery evidence exists.

    W7 records reversibility; it does NOT execute rollback (W8 owns the
    experiment/promotion/rollback lifecycle).

    Per SOS-W7-F01: reversibility is truthfully evidence/policy-backed, not
    inferred from a risk-name substring. ``rollback_evidence_ids`` references
    the W4 evidence records that demonstrate rollback/recovery availability;
    ``containment_policy_ref`` references a documented containment exception.
    At least one of the two must be supplied for the gate to PASS.
    """

    rollback_available: bool
    detail: str
    rollback_evidence_ids: tuple[str, ...] = ()
    containment_policy_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.detail.strip():
            raise ModelValidationError("ReversibilityAssessment.detail is required")
        # SOS-W7-F01: rollback_available must be backed by evidence ids, not a
        # substring inference. If rollback_available is True, evidence ids must
        # be present.
        if self.rollback_available and not self.rollback_evidence_ids:
            raise ModelValidationError(
                "ReversibilityAssessment.rollback_available=True requires rollback_evidence_ids"
            )


# ---------------------------------------------------------------------------
# Assurance result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AssuranceResult:
    """A structured, non-authorizing assurance result for a candidate.

    The result binds to the exact candidate id, base graph id/revision,
    provenance revision, and W1 traceability. It is deterministic (content-
    addressed id). It carries no "authorized"/"approved" flag — W7 cannot
    authorize execution, promotion, or autonomy.
    """

    id: str
    candidate_id: str
    base_graph_id: str
    base_graph_revision: str
    provenance_revision: str
    status: AssuranceStatus
    gates: tuple[AssuranceGate, ...]
    impact: ImpactAnalysis
    risk: RiskAssessment
    reversibility: ReversibilityAssessment
    objectives: tuple[Any, ...]  # W6 CandidateObjective tuple (preserved, not scalarized)
    traceability: Traceability

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", _result_id(self))
        self.validate()

    def validate(self) -> None:
        if not self.candidate_id.strip():
            raise ModelValidationError("AssuranceResult.candidate_id is required")
        if not self.base_graph_id.strip():
            raise ModelValidationError("AssuranceResult.base_graph_id is required")
        if not self.base_graph_revision.strip():
            raise ModelValidationError("AssuranceResult.base_graph_revision is required")
        if not self.provenance_revision.strip():
            raise ModelValidationError("AssuranceResult.provenance_revision is required")
        if not isinstance(self.status, AssuranceStatus):
            raise ModelValidationError("AssuranceResult.status must be an AssuranceStatus")
        if not self.gates:
            raise ModelValidationError("AssuranceResult.gates is required")
        if not isinstance(self.impact, ImpactAnalysis):
            raise ModelValidationError("AssuranceResult.impact must be an ImpactAnalysis")
        if not isinstance(self.risk, RiskAssessment):
            raise ModelValidationError("AssuranceResult.risk must be a RiskAssessment")
        if not isinstance(self.reversibility, ReversibilityAssessment):
            raise ModelValidationError("AssuranceResult.reversibility must be a ReversibilityAssessment")
        self.traceability.validate(require_value=True, require_context=True)
        for g in self.gates:
            g.validate()


def _result_id(r: AssuranceResult) -> str:
    """Content-addressed identity for the assurance result."""
    material = "|".join([
        r.candidate_id, r.base_graph_id, r.base_graph_revision, r.provenance_revision,
        r.status.value,
        ",".join(g.name for g in r.gates),
    ])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"assurance-{digest}"


# ---------------------------------------------------------------------------
# Assurance engine (deterministic, bounded, non-authorizing)
# ---------------------------------------------------------------------------


# W4 EvidenceKind values that count as intervention-grade for the causal gate.
_INTERVENTION_KINDS: frozenset[EvidenceKind] = frozenset({
    EvidenceKind.EXPERIMENT, EvidenceKind.CANARY, EvidenceKind.SHADOW,
    EvidenceKind.REPLAY, EvidenceKind.SIMULATION,
})


def assure_candidate(
    *,
    candidate: "CandidateProposal",
    base_graph: "ArchitectureGraph",
    known_evidence: dict[str, Evidence],
    known_hypotheses: dict[str, "CausalHypothesis"],
    hard_constraints: tuple[str, ...] = (),
    rollback_evidence_ids: tuple[str, ...] = (),
    containment_policy_ref: str | None = None,
) -> AssuranceResult:
    """Evaluate a W6 candidate and produce a structured, non-authorizing result.

    Deterministic and bounded: same inputs produce the same result; evaluation
    is finite. Non-authorizing: the result carries no authorization flag.
    """
    if candidate is None:
        raise ModelValidationError("assure_candidate requires a candidate")
    if base_graph is None:
        raise ModelValidationError("assure_candidate requires a base_graph")
    # C1: candidate binding + provenance — verify graph id match.
    if candidate.base_graph_ref != base_graph.id:
        raise ModelValidationError(
            f"candidate.base_graph_ref '{candidate.base_graph_ref}' does not match base_graph '{base_graph.id}'"
        )
    # Validate candidate against the known graph + evidence + hypotheses.
    candidate.validate(
        known_graph=base_graph,
        known_evidence_ids=set(known_evidence.keys()),
        known_hypothesis_ids=set(known_hypotheses.keys()),
    )

    gates: list[AssuranceGate] = []

    # --- C2: evidence-backed gate evaluation ---
    # Evidence availability gate: check the candidate's reasoning evidence.
    ev_statuses: list[AssuranceStatus] = []
    for eid in candidate.reasoning_evidence_ids:
        ev = known_evidence.get(eid)
        if ev is None:
            ev_statuses.append(AssuranceStatus.BLOCKED)
        else:
            ev_statuses.append(_evidence_to_gate_status(ev))
    evidence_gate_status = _aggregate_gate_status(ev_statuses)
    gates.append(AssuranceGate(
        name="evidence-availability",
        status=evidence_gate_status,
        evidence_ids=tuple(candidate.reasoning_evidence_ids),
        detail=f"aggregated evidence status: {evidence_gate_status.value}",
    ))

    # --- C3: impact + blast radius (bounded) ---
    impact = _compute_impact(candidate, base_graph)

    # --- C4: hard-constraint enforcement ---
    hard_status = AssuranceStatus.PASS
    hard_detail = "no hard-constraint violations"
    violated: list[str] = []
    target_nodes = set(candidate.mutation.target_node_ids)
    for constraint in hard_constraints:
        # Conservative: if a hard constraint names a target node, it's a violation.
        # (Real W7 would parse constraint semantics; this bounded slice checks
        # node-name containment.)
        if any(node in constraint for node in target_nodes):
            violated.append(constraint)
    if violated:
        hard_status = AssuranceStatus.FAIL
        hard_detail = f"hard-constraint violations: {', '.join(violated)}"
    gates.append(AssuranceGate(
        name="hard-constraint",
        status=hard_status,
        evidence_ids=(),
        detail=hard_detail,
    ))

    # --- C6: causal qualification (F02: evidence-traceable to the actual intervention record) ---
    # Collect the exact intervention-grade support evidence ids that establish
    # the causal gate's PASS — not the candidate's full reasoning_evidence_ids.
    causal_evidence_ids: list[str] = []
    causal_status = AssuranceStatus.UNKNOWN
    causal_detail = "no intervention-grade causal evidence"
    for hid in candidate.reasoning_hypothesis_ids:
        h = known_hypotheses.get(hid)
        if h is None:
            continue
        for support in h.supporting_evidence:
            if support.support_kind == SupportKind.INTERVENTION:
                ev = known_evidence.get(support.evidence_id)
                if ev is not None and ev.kind in _INTERVENTION_KINDS:
                    # Record the EXACT intervention-grade support evidence id
                    # used to establish this gate's status (SOS-W7-F02).
                    if support.evidence_id not in causal_evidence_ids:
                        causal_evidence_ids.append(support.evidence_id)
    if causal_evidence_ids:
        causal_status = AssuranceStatus.PASS
        causal_detail = (
            f"intervention-grade causal evidence present: {', '.join(causal_evidence_ids)}"
        )
    else:
        causal_detail = "observational evidence only; causal efficacy not established"
    gates.append(AssuranceGate(
        name="causal-qualification",
        status=causal_status,
        evidence_ids=tuple(causal_evidence_ids),  # F02: the actual supporting records
        detail=causal_detail,
    ))

    # --- C7: reversibility / containment (F01: evidence/policy-backed, a gate) ---
    # Per SOS-W7-F01: do NOT infer rollback availability from a risk-name
    # substring. Reversibility is caller-supplied and validated: either
    # rollback_evidence_ids (real W4 records) or a documented containment
    # exception reference (containment_policy_ref). Assurance cannot PASS when
    # neither is present.
    rollback_available = bool(rollback_evidence_ids)
    # Validate that rollback evidence records actually exist + are SUCCESS.
    rev_status = AssuranceStatus.UNKNOWN
    rev_detail = "no rollback/recovery evidence or documented containment exception supplied"
    rev_evidence_ids: list[str] = []
    if rollback_available:
        for eid in rollback_evidence_ids:
            ev = known_evidence.get(eid)
            if ev is None:
                rev_status = AssuranceStatus.BLOCKED
                rev_detail = f"rollback evidence id '{eid}' not found in known_evidence"
                rev_evidence_ids = []
                break
            rev_evidence_ids.append(eid)
            if ev.result.state != TruthState.SUCCESS:
                rev_status = AssuranceStatus.FAIL
                rev_detail = f"rollback evidence '{eid}' observed state {ev.result.state.value}"
        else:
            if rev_status == AssuranceStatus.UNKNOWN:
                rev_status = AssuranceStatus.PASS
                rev_detail = f"rollback/recovery evidence present: {', '.join(rev_evidence_ids)}"
    elif containment_policy_ref is not None and containment_policy_ref.strip():
        # A documented containment exception is a governed alternative to rollback.
        rev_status = AssuranceStatus.PASS
        rev_detail = f"documented containment exception: {containment_policy_ref}"
    else:
        # SOS-W7-F01: neither rollback evidence nor a documented containment
        # exception — assurance cannot PASS. This is a BLOCKED gate.
        rev_status = AssuranceStatus.BLOCKED
        rev_detail = "no rollback/recovery evidence and no documented containment exception"
    reversibility = ReversibilityAssessment(
        rollback_available=rollback_available,
        detail=rev_detail,
        rollback_evidence_ids=tuple(rev_evidence_ids),
        containment_policy_ref=containment_policy_ref if (containment_policy_ref and containment_policy_ref.strip()) else None,
    )
    gates.append(AssuranceGate(
        name="reversibility-containment",
        status=rev_status,
        evidence_ids=tuple(rev_evidence_ids),
        detail=rev_detail,
    ))

    # --- C5: risk assessment ---
    risk_items: list[RiskItem] = []
    for risk_name in candidate.risks:
        risk_items.append(RiskItem(
            name=risk_name,
            severity="medium",
            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "risk likelihood not quantified"),
            mitigation="monitor and rollback if degraded" if rollback_available else None,
            residual="residual risk remains; bounded by containment" if not rollback_available else None,
        ))
    if not risk_items:
        risk_items.append(RiskItem(
            name="unquantified-risk",
            severity="medium",
            uncertainty=TruthfulValue(TruthState.UNKNOWN, None, "no risks identified; residual uncertainty"),
            mitigation=None,
            residual="no explicit risks recorded",
        ))
    risk = RiskAssessment(items=tuple(risk_items))

    # --- C8: multi-objective integrity (preserve W6 objectives; no scalar) ---
    objectives = candidate.objectives

    # --- Overall status: FAIL if any gate FAILs; else BLOCKED/UNKNOWN if any; else PASS ---
    # But PASS requires evidence gate PASS + hard-constraint PASS + causal PASS.
    all_statuses = [g.status for g in gates]
    if AssuranceStatus.FAIL in all_statuses:
        overall = AssuranceStatus.FAIL
    elif AssuranceStatus.BLOCKED in all_statuses:
        overall = AssuranceStatus.BLOCKED
    elif AssuranceStatus.UNKNOWN in all_statuses:
        overall = AssuranceStatus.UNKNOWN
    else:
        overall = AssuranceStatus.PASS

    result = AssuranceResult(
        id="",
        candidate_id=candidate.id,
        base_graph_id=base_graph.id,
        base_graph_revision=candidate.base_graph_revision,
        provenance_revision=candidate.provenance_revision,
        status=overall,
        gates=tuple(gates),
        impact=impact,
        risk=risk,
        reversibility=reversibility,
        objectives=objectives,
        traceability=candidate.traceability,
    )
    return result


# Import SupportKind here to avoid a cycle at module load (causal imports evidence).
from .causal import SupportKind  # noqa: E402


def _evidence_to_gate_status(ev: Evidence) -> AssuranceStatus:
    """Map an evidence record's observed result to a gate status (truthful)."""
    if ev.result.state == TruthState.SUCCESS:
        return AssuranceStatus.PASS
    if ev.result.state in (TruthState.FAILED,):
        return AssuranceStatus.FAIL
    if ev.result.state in (TruthState.UNKNOWN, TruthState.UNSUPPORTED):
        return AssuranceStatus.UNKNOWN
    if ev.result.state == TruthState.UNAVAILABLE:
        return AssuranceStatus.BLOCKED
    return AssuranceStatus.UNKNOWN


def _aggregate_gate_status(statuses: list[AssuranceStatus]) -> AssuranceStatus:
    """Aggregate per-evidence statuses into a gate status. No PASS from non-PASS."""
    if not statuses:
        return AssuranceStatus.UNKNOWN
    if AssuranceStatus.FAIL in statuses:
        return AssuranceStatus.FAIL
    if AssuranceStatus.BLOCKED in statuses:
        return AssuranceStatus.BLOCKED
    if AssuranceStatus.UNKNOWN in statuses:
        return AssuranceStatus.UNKNOWN
    if all(s == AssuranceStatus.PASS for s in statuses):
        return AssuranceStatus.PASS
    return AssuranceStatus.UNKNOWN


def _compute_impact(candidate: "CandidateProposal", graph: "ArchitectureGraph") -> ImpactAnalysis:
    """Compute a bounded impact analysis (no unbounded traversal)."""
    target_nodes = set(candidate.mutation.target_node_ids)
    node_ids = {n.id for n in graph.nodes}
    # Affected nodes: the target subgraph (bounded by what the candidate declares).
    affected_nodes = tuple(sorted(target_nodes & node_ids))
    # Affected edges: edges touching any target node (bounded, single-hop).
    affected_edges = tuple(sorted(
        e.id for e in graph.edges if e.source_id in target_nodes or e.target_id in target_nodes
    ))
    # Boundary interfaces: declared by the candidate mutation.
    boundary = tuple(sorted(set(candidate.mutation.boundary_interface_ids) & node_ids))
    # Dependency reach: direct adjacency from target nodes (bounded, single-hop).
    reach: set[str] = set()
    for e in graph.edges:
        if e.source_id in target_nodes:
            reach.add(e.target_id)
        if e.target_id in target_nodes:
            reach.add(e.source_id)
    reach -= target_nodes
    # Blast radius: conservative — level by affected count.
    n = len(affected_nodes)
    if n == 0:
        level = "limited"
    elif n <= 2:
        level = "service"
    elif n <= 5:
        level = "system"
    else:
        level = "organization"
    blast = BlastRadius(
        level=level, affected_count=n,
        detail=f"{n} affected node(s); bounded single-hop dependency reach",
    )
    return ImpactAnalysis(
        affected_node_ids=affected_nodes,
        affected_edge_ids=affected_edges,
        boundary_interface_ids=boundary,
        dependency_reach=tuple(sorted(reach)),
        blast_radius=blast,
    )
