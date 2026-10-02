"""Wire DTOs: experiments, executions (W11 receipts), learning/memory, jobs,
provider status, health (§C.3; directive §8 job fields exactly)."""
from __future__ import annotations

from typing import Any, Literal

from sos.experimentation import ExperimentState

from .common import CamelModel, TruthStateWire
from .candidate import ReversibilityDTO  # noqa: F401  (shared export)


class ExperimentEventDTO(CamelModel):
    at: str
    type: str
    detail: str


class ExperimentDTO(CamelModel):
    id: str
    workspace_id: str
    candidate_id: str
    status: ExperimentState  # frozen W8 lifecycle vocabulary, verbatim
    events: list[ExperimentEventDTO]
    created_at: str


class CreateExperimentRequestDTO(CamelModel):
    workspace_id: str
    candidate_id: str
    assurance_id: str


class SideEffectDTO(CamelModel):
    kind: str
    target: str
    detail: str


class RollbackRefDTO(CamelModel):
    reference: str
    evidence_ids: list[str]
    detail: str


class OutcomeDTO(CamelModel):
    state: TruthStateWire
    value: Any = None
    detail: str | None = None


class ExecutionReceiptDTO(CamelModel):
    """A W11 receipt serialized verbatim; ``demo`` is explicitly true for
    DemoProvider receipts (never a real deployment claim)."""

    id: str
    request_id: str
    provider_id: str
    action_scope: str
    lifecycle: str
    outcome: OutcomeDTO
    w9_decision_id: str
    w7_assurance_id: str | None = None
    source_revision: str
    provenance_revision: str
    base_graph_id: str
    base_graph_revision: str
    environment: str
    started_at: str | None = None
    finished_at: str | None = None
    side_effects: list[SideEffectDTO] = []
    stdout_ref: str | None = None
    stderr_ref: str | None = None
    log_ref: str | None = None
    changed_revisions: list[str] = []
    rollback_reference: RollbackRefDTO | None = None
    demo: bool = False


class ExecutionDTO(CamelModel):
    id: str
    workspace_id: str
    experiment_id: str | None = None
    provider: Literal["demo", "apify"]
    request_hash: str
    receipt: ExecutionReceiptDTO | None = None
    artifact_refs: list[str] = []
    status: TruthStateWire
    created_at: str


class DispatchExecutionRequestDTO(CamelModel):
    experiment_id: str
    intent: str = ""


class LearningRecordDTO(CamelModel):
    """LearningRecord / MemoryEntry share one wire shape (§C.3)."""

    id: str
    workspace_id: str
    context: dict[str, Any]
    candidate: str
    predicted_effects: list[dict[str, Any]]
    actual_effects: list[dict[str, Any]]
    uncertainty: dict[str, Any]
    verdict: str
    lessons: list[str]
    created_at: str


MemoryEntryDTO = LearningRecordDTO


JobStatusWire = Literal[
    "queued", "running", "succeeded", "failed", "cancelled"
]


class JobDTO(CamelModel):
    """Directive §8 job fields, exactly."""

    id: str
    tenant_id: str
    type: str
    requested_by: str
    authority_snapshot: dict[str, Any]
    input_hash: str
    source_revision: str
    provider: str
    status: JobStatusWire
    started_at: str | None = None
    completed_at: str | None = None
    receipt: dict[str, Any] | None = None
    artifact_refs: list[str] = []
    error_state: str | None = None
    created_at: str


class CreateJobRequestDTO(CamelModel):
    workspace_id: str
    type: Literal["system_recovery", "experiment_execution"]
    experiment_id: str | None = None
    repository_url: str | None = None
    ref: str | None = None
    idempotency_key: str | None = None


class ProviderStatusDTO(CamelModel):
    name: str  # persistence | coordination | artifacts | execution | github
    mode: str
    implementation: str
    status: TruthStateWire
    detail: str
    capabilities: list[str] = []
    demo: bool = False


class HealthCheckDTO(CamelModel):
    status: TruthStateWire
    mode: str
    detail: str


class HealthResponseDTO(CamelModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, HealthCheckDTO]
