"""W2 System State and Architecture Graph domain model for SOS."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4

from .model import JsonModelStore, ModelValidationError, Traceability, TruthState, TruthfulValue


class NodeType(str, Enum):
    CAPABILITY = "capability"
    SERVICE = "service"
    COMPONENT = "component"
    DATA_STORE = "data_store"
    INTERFACE = "interface"
    DEPLOYMENT = "deployment"
    TRUST_BOUNDARY = "trust_boundary"
    POLICY = "policy"
    MODEL = "model"
    ADAPTER = "adapter"
    EXTERNAL_DEPENDENCY = "external_dependency"


class EdgeType(str, Enum):
    CALL = "call"
    DATA_FLOW = "data-flow"
    DEPENDENCY = "dependency"
    TRUST = "trust"
    DEPLOYMENT = "deployment"
    RUNTIME_INTERACTION = "runtime-interaction"
    REALIZES = "realizes"
    OBSERVES = "observes"
    INFLUENCES = "influences"
    OWNS = "owns"
    CONSTRAINS = "constrains"


@dataclass(frozen=True)
class GraphUncertainty:
    state: TruthState
    reason: str | None = None
    confidence: float | None = None

    def validate(self) -> None:
        if self.state == TruthState.SUCCESS and self.confidence is None:
            raise ModelValidationError("SUCCESS graph uncertainty requires confidence")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ModelValidationError("Graph uncertainty confidence must be within [0, 1]")
        if self.state != TruthState.SUCCESS and not self.reason:
            raise ModelValidationError("Non-success graph uncertainty requires a reason")


@dataclass(frozen=True)
class GraphNode:
    id: str
    type: NodeType
    name: str
    attributes: Mapping[str, Any]
    uncertainty: GraphUncertainty

    def validate(self) -> None:
        if not self.id or not self.name:
            raise ModelValidationError("GraphNode requires id and name")
        self.uncertainty.validate()


@dataclass(frozen=True)
class GraphEdge:
    id: str
    type: EdgeType
    source_id: str
    target_id: str
    attributes: Mapping[str, Any]
    uncertainty: GraphUncertainty

    def validate(self, node_ids: set[str]) -> None:
        if not self.id or not self.source_id or not self.target_id:
            raise ModelValidationError("GraphEdge requires id, source_id and target_id")
        if self.source_id not in node_ids or self.target_id not in node_ids:
            raise ModelValidationError("GraphEdge references a missing node")
        self.uncertainty.validate()


@dataclass(frozen=True)
class BoundaryContract:
    id: str
    interface_node_id: str
    contract: str
    invariants: tuple[str, ...]
    uncertainty: GraphUncertainty

    def validate(self, node_ids: set[str]) -> None:
        if not self.id or self.interface_node_id not in node_ids:
            raise ModelValidationError("BoundaryContract requires an existing interface node")
        if not self.contract.strip() or not self.invariants:
            raise ModelValidationError("BoundaryContract requires contract text and invariants")
        self.uncertainty.validate()


@dataclass(frozen=True)
class ArchitectureGraph:
    id: str
    version: int
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    boundary_contracts: tuple[BoundaryContract, ...]
    uncertainty: GraphUncertainty
    traceability: Traceability

    def validate(self) -> None:
        if not self.id or self.version < 1:
            raise ModelValidationError("ArchitectureGraph requires id and version >= 1")
        self.traceability.validate(require_value=True, require_context=True)
        self.uncertainty.validate()
        node_ids = {n.id for n in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ModelValidationError("ArchitectureGraph node ids must be unique")
        for node in self.nodes:
            node.validate()
        edge_ids = {e.id for e in self.edges}
        if len(edge_ids) != len(self.edges):
            raise ModelValidationError("ArchitectureGraph edge ids must be unique")
        for edge in self.edges:
            edge.validate(node_ids)
        for contract in self.boundary_contracts:
            contract.validate(node_ids)


@dataclass(frozen=True)
class StateReference:
    ref: TruthfulValue[str]

    def validate(self) -> None:
        self.ref.validate()


@dataclass(frozen=True)
class SystemState:
    id: str
    version: int
    architecture_ref: str
    implementation_ref: StateReference
    configuration_ref: StateReference
    deployment_ref: StateReference
    policy_ref: StateReference
    environment_ref: StateReference
    active_experiments: tuple[str, ...]
    architecture: ArchitectureGraph
    traceability: Traceability
    revision_id: str
    parent_revision_id: str | None = None

    def validate(self) -> None:
        if not self.id or self.version < 1 or not self.revision_id:
            raise ModelValidationError("SystemState requires id, version and revision_id")
        if not self.architecture_ref or self.architecture.id != self.architecture_ref:
            raise ModelValidationError("SystemState architecture_ref must match attached ArchitectureGraph")
        if self.version > 1 and not self.parent_revision_id:
            raise ModelValidationError("Versioned SystemState revisions require parent_revision_id")
        self.traceability.validate(require_value=True, require_context=True)
        for reference in (self.implementation_ref, self.configuration_ref, self.deployment_ref, self.policy_ref, self.environment_ref):
            reference.validate()
        self.architecture.validate()

    @classmethod
    def create(cls, *, version: int, architecture: ArchitectureGraph, implementation_ref: StateReference,
               configuration_ref: StateReference, deployment_ref: StateReference, policy_ref: StateReference,
               environment_ref: StateReference, active_experiments: tuple[str, ...], traceability: Traceability,
               parent_revision_id: str | None = None) -> "SystemState":
        state = cls(id=f"system-state-{uuid4()}", version=version, architecture_ref=architecture.id,
                    implementation_ref=implementation_ref, configuration_ref=configuration_ref,
                    deployment_ref=deployment_ref, policy_ref=policy_ref, environment_ref=environment_ref,
                    active_experiments=active_experiments, architecture=architecture, traceability=traceability,
                    revision_id=str(uuid4()), parent_revision_id=parent_revision_id)
        state.validate()
        return state

    def next_revision(self, **changes: Any) -> "SystemState":
        """Create an immutable child revision with an explicit parent revision."""
        allowed = {
            "architecture", "implementation_ref", "configuration_ref", "deployment_ref",
            "policy_ref", "environment_ref", "active_experiments", "traceability",
        }
        unexpected = set(changes) - allowed
        if unexpected:
            raise ModelValidationError(f"Unsupported SystemState revision fields: {sorted(unexpected)}")
        values = {
            "id": self.id,
            "version": self.version + 1,
            "architecture_ref": changes.get("architecture", self.architecture).id,
            "implementation_ref": changes.get("implementation_ref", self.implementation_ref),
            "configuration_ref": changes.get("configuration_ref", self.configuration_ref),
            "deployment_ref": changes.get("deployment_ref", self.deployment_ref),
            "policy_ref": changes.get("policy_ref", self.policy_ref),
            "environment_ref": changes.get("environment_ref", self.environment_ref),
            "active_experiments": changes.get("active_experiments", self.active_experiments),
            "architecture": changes.get("architecture", self.architecture),
            "traceability": changes.get("traceability", self.traceability),
            "revision_id": str(uuid4()),
            "parent_revision_id": self.revision_id,
        }
        child = SystemState(**values)
        child.validate()
        return child


@dataclass(frozen=True)
class SubgraphReplacement:
    id: str
    base_graph_ref: str
    target_node_ids: tuple[str, ...]
    replacement_node_ids: tuple[str, ...]
    boundary_interface_ids: tuple[str, ...]
    invariants: tuple[str, ...]
    traceability: Traceability

    def validate(self, graph: ArchitectureGraph) -> None:
        if not self.id or not self.base_graph_ref:
            raise ModelValidationError("SubgraphReplacement requires id and base graph reference")
        if self.base_graph_ref != graph.id:
            raise ModelValidationError("SubgraphReplacement base_graph_ref must match graph")
        node_ids = {n.id for n in graph.nodes}
        if not self.target_node_ids or not self.replacement_node_ids:
            raise ModelValidationError("SubgraphReplacement requires target and replacement subgraphs")
        if not self.invariants or not self.boundary_interface_ids:
            raise ModelValidationError("SubgraphReplacement requires boundary interfaces and invariants")
        if not set(self.target_node_ids).issubset(node_ids):
            raise ModelValidationError("SubgraphReplacement target references unknown nodes")
        if not set(self.boundary_interface_ids).issubset(node_ids):
            raise ModelValidationError("SubgraphReplacement boundary references unknown nodes")
        if not set(self.boundary_interface_ids).issubset(set(self.target_node_ids)):
            raise ModelValidationError("Boundary interfaces must belong to the declared target subgraph")
        if set(self.replacement_node_ids) & set(self.target_node_ids):
            raise ModelValidationError("Replacement nodes must be distinct from target nodes")
        self.traceability.validate(require_value=True, require_context=True)


def save_json(artifact: Any, path: str) -> None:
    JsonModelStore(path).save(artifact)
