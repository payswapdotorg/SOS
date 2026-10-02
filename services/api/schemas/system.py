"""Wire DTOs: system, system revision, architecture graph (§C.3; W2 graph
semantics via the schema mapping — node/edge types are the frozen
``sos.graph`` vocabularies)."""
from __future__ import annotations

from typing import Any, Literal

from sos.graph import EdgeType, NodeType

from .common import CamelModel, TruthStateWire


class UncertaintyDTO(CamelModel):
    state: TruthStateWire
    reason: str | None = None
    confidence: float | None = None


class SourceRefDTO(CamelModel):
    kind: str  # github | none
    url: str | None = None
    revision: str | None = None  # exact pinned revision — never "latest"
    immutable: bool = False
    fixture: bool = False  # LOCAL fixture metadata is clearly labeled


class RecoveryInfoDTO(CamelModel):
    job_id: str | None = None
    status: str | None = None  # JobStatus values


class GraphNodeDTO(CamelModel):
    id: str
    type: NodeType  # the frozen W2 node vocabulary, verbatim
    name: str
    attributes: dict[str, Any] = {}
    uncertainty: UncertaintyDTO | None = None


class GraphEdgeDTO(CamelModel):
    id: str
    type: EdgeType  # the frozen W2 edge vocabulary, verbatim
    source_id: str
    target_id: str
    attributes: dict[str, Any] = {}
    uncertainty: UncertaintyDTO | None = None


class ArchitectureGraphDTO(CamelModel):
    id: str | None = None
    version: int | None = None
    nodes: list[GraphNodeDTO]
    edges: list[GraphEdgeDTO]


class SystemRevisionDTO(CamelModel):
    id: str
    system_id: str
    revision: int
    state_summary: str
    uncertainty: UncertaintyDTO
    source_ref: SourceRefDTO | None = None
    recovery: RecoveryInfoDTO | None = None
    graph: ArchitectureGraphDTO | None = None
    created_at: str


class SystemDTO(CamelModel):
    id: str
    workspace_id: str
    name: str
    mode: Literal["greenfield", "brownfield"]
    current_revision_id: str | None = None
    current_revision: SystemRevisionDTO | None = None
    created_at: str


class CreateSystemRequestDTO(CamelModel):
    workspace_id: str
    name: str
    mode: Literal["greenfield", "brownfield"]
    repository_url: str | None = None  # brownfield: resolved via the GitHub seam
    ref: str | None = None  # brownfield: branch or commit to pin


class RecoveryRequestDTO(CamelModel):
    ref: str | None = None  # defaults to the recorded source ref's revision
