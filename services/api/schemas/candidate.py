"""Wire DTOs: candidates (multi-objective; NO single authoritative score —
architecture invariant), assurance runs, decisions, authorizations (§C.3)."""
from __future__ import annotations

from typing import Any, Literal

from sos.assurance import AssuranceStatus

from .common import CamelModel, DecisionActionWire


class SubgraphReplacementDTO(CamelModel):
    kind: str
    target_node_ids: list[str]
    replacement_node_ids: list[str]
    boundary_interface_ids: list[str]
    invariants: list[str]


class ObjectiveEvaluationDTO(CamelModel):
    name: str
    direction: Literal["maximize", "minimize", "maintain"]
    predicted_value: float
    uncertainty: dict[str, Any] | None = None


class ParetoEntryDTO(CamelModel):
    candidate_id: str
    values: dict[str, float]


class CandidateEvaluationDTO(CamelModel):
    objectives: list[ObjectiveEvaluationDTO]
    pareto_front: list[ParetoEntryDTO]


class ReversibilityDTO(CamelModel):
    rollback_available: bool
    detail: str


class CandidateDTO(CamelModel):
    id: str
    workspace_id: str
    name: str
    subgraph_replacement: SubgraphReplacementDTO
    effects: list[dict[str, Any]]
    costs: list[dict[str, Any]]
    risks: list[str]
    constraints: list[str]
    evidence_refs: list[str]
    reversibility: ReversibilityDTO
    evaluation: CandidateEvaluationDTO
    created_at: str


class AssuranceCheckDTO(CamelModel):
    name: str
    status: AssuranceStatus  # PASS|FAIL|UNKNOWN|BLOCKED (frozen W7 vocabulary)
    evidence_ids: list[str] = []
    detail: str


class AssuranceRunDTO(CamelModel):
    id: str
    workspace_id: str
    candidate_id: str
    checks: list[AssuranceCheckDTO]
    verdict: AssuranceStatus
    created_at: str


class AskPayloadDTO(CamelModel):
    decision: str
    alternatives: list[str]
    evidence_quality: str
    uncertainty: str
    tradeoffs: list[str]


class DecisionDTO(CamelModel):
    id: str
    workspace_id: str
    action: DecisionActionWire  # the decision OUTCOME (ASK stays ASK)
    rationale: str
    evidence_refs: list[str]
    authority_snapshot: dict[str, Any]
    expected_impact: dict[str, Any]
    risk: float
    blast_radius: str
    reversibility: ReversibilityDTO
    required_approvals: list[str]
    ask_payload: AskPayloadDTO | None = None
    created_at: str


class AuthorizationDTO(CamelModel):
    id: str
    workspace_id: str
    decision_id: str | None = None
    principal: str
    scope: str
    decision: Literal["granted", "denied"]
    created_at: str
