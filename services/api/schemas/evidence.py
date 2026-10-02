"""Wire DTOs: evidence + hypotheses (§C.3). The public 7-kind evidence
classification (directive §5) and its documented mapping to the frozen
``sos.evidence.EvidenceKind`` vocabulary live in
``services.api.orchestration`` (mapping only — no semantic invention)."""
from __future__ import annotations

from typing import Any, Literal

from .common import CamelModel, TruthStateWire

EvidenceKindWire = Literal[
    "source_revision",
    "runtime_observation",
    "test_result",
    "telemetry",
    "environment",
    "experiment",
    "business_outcome",
]


class EvidenceProvenanceDTO(CamelModel):
    source: str
    observed_subject: str
    timestamp: str | None = None
    environment: str | None = None
    implementation_revision: str | None = None
    availability: TruthStateWire | None = None


class EvidenceDTO(CamelModel):
    id: str
    workspace_id: str
    system_id: str | None = None
    kind: EvidenceKindWire
    status: TruthStateWire  # the observed result truth state, verbatim
    provenance: EvidenceProvenanceDTO
    timestamp: str | None = None
    source_revision: str | None = None
    related_system_state: str | None = None
    confidence: float | None = None
    artifact_ref: str | None = None
    result: dict[str, Any] | None = None
    created_at: str


class HypothesisDTO(CamelModel):
    id: str
    statement: str
    causal: dict[str, Any]
    evidence_refs: list[str]
    status: TruthStateWire
    created_at: str
