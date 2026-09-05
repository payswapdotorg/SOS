"""Deterministic static architecture recovery for W3.

This module inspects repository bytes only. It does not execute the target
system, query telemetry, infer runtime behavior, or mutate the recovered graph.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .graph import (
    ArchitectureGraph,
    EdgeType,
    GraphEdge,
    GraphNode,
    GraphUncertainty,
    NodeType,
    StateReference,
    SystemState,
)
from .model import ModelValidationError, Traceability, TruthState, TruthfulValue


SOURCE_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".c", ".cpp", ".h", ".hpp"}
POLICY_NAMES = {"pyproject.toml", "package.json", "requirements.txt", "go.mod", "Cargo.toml"}
DEPLOYMENT_NAMES = {"Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}
CONFIG_NAMES = {".env", ".env.example"}
IGNORED_PARTS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules", "dist", "build"}


@dataclass(frozen=True)
class RecoveryFinding:
    code: str
    state: TruthState
    subject: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "state": self.state.value, "subject": self.subject, "detail": self.detail}


@dataclass(frozen=True)
class RecoveryInventory:
    paths: tuple[str, ...]
    source_paths: tuple[str, ...]
    manifest_paths: tuple[str, ...]
    deployment_hint_paths: tuple[str, ...]


@dataclass(frozen=True)
class RecoveryReport:
    repository_revision: str
    inventory: RecoveryInventory
    architecture: ArchitectureGraph
    system_state: SystemState
    findings: tuple[RecoveryFinding, ...]

    def validate(self) -> None:
        if not self.repository_revision.strip():
            raise ModelValidationError("repository_revision is required")
        self.architecture.validate()
        self.system_state.validate()
        if self.system_state.architecture_ref != self.architecture.id:
            raise ModelValidationError("RecoveryReport state must reference its recovered graph")

    def to_dict(self) -> dict[str, object]:
        def graph_dict(graph: ArchitectureGraph) -> dict[str, object]:
            return {
                "id": graph.id,
                "version": graph.version,
                "nodes": [
                    {"id": n.id, "type": n.type.value, "name": n.name, "attributes": dict(n.attributes), "uncertainty": _uncertainty_dict(n.uncertainty)}
                    for n in graph.nodes
                ],
                "edges": [
                    {"id": e.id, "type": e.type.value, "source_id": e.source_id, "target_id": e.target_id, "attributes": dict(e.attributes), "uncertainty": _uncertainty_dict(e.uncertainty)}
                    for e in graph.edges
                ],
                "boundary_contracts": [
                    {"id": c.id, "interface_node_id": c.interface_node_id, "contract": c.contract, "invariants": list(c.invariants), "uncertainty": _uncertainty_dict(c.uncertainty)}
                    for c in graph.boundary_contracts
                ],
                "uncertainty": _uncertainty_dict(graph.uncertainty),
            }

        return {
            "repository_revision": self.repository_revision,
            "inventory": {
                "paths": list(self.inventory.paths),
                "source_paths": list(self.inventory.source_paths),
                "manifest_paths": list(self.inventory.manifest_paths),
                "deployment_hint_paths": list(self.inventory.deployment_hint_paths),
            },
            "architecture": graph_dict(self.architecture),
            "system_state": {
                "id": self.system_state.id,
                "version": self.system_state.version,
                "revision_id": self.system_state.revision_id,
                "parent_revision_id": self.system_state.parent_revision_id,
                "architecture_ref": self.system_state.architecture_ref,
            },
            "findings": [finding.to_dict() for finding in self.findings],
        }


def _uncertainty_dict(value: GraphUncertainty) -> dict[str, object]:
    return {"state": value.state.value, "reason": value.reason, "confidence": value.confidence}


def _iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*"), key=lambda p: p.as_posix()):
        if not path.is_file():
            continue
        if any(part in IGNORED_PARTS for part in path.parts):
            continue
        yield path


def _module_path(import_name: str, source: Path, source_files: set[Path], root: Path) -> Path | None:
    if not import_name:
        return None
    parts = import_name.split(".")
    direct = root.joinpath(*parts).with_suffix(".py")
    package = root.joinpath(*parts, "__init__.py")
    if direct in source_files:
        return direct
    if package in source_files:
        return package
    current = source.parent
    dotted = parts
    # Resolve simple relative imports within the source package.
    while dotted and current != root:
        candidate = current.joinpath(*dotted).with_suffix(".py")
        if candidate in source_files:
            return candidate
        current = current.parent
    return None


def _python_imports(path: Path) -> tuple[str, ...]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return ()
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return tuple(sorted(imports))


def recover_repository(
    root: str | Path,
    *,
    repository_revision: str,
    traceability: Traceability,
    version: int = 1,
) -> RecoveryReport:
    """Recover a conservative W2 graph from repository contents."""
    base = Path(root).resolve()
    if not base.is_dir():
        raise ModelValidationError("Recovery root must be an existing directory")
    if not repository_revision.strip():
        raise ModelValidationError("repository_revision is required")
    traceability.validate(require_value=True, require_context=True)

    files = tuple(_iter_files(base))
    rel_paths = tuple(p.relative_to(base).as_posix() for p in files)
    source_paths = tuple(sorted(p.relative_to(base).as_posix() for p in files if p.suffix.lower() in SOURCE_SUFFIXES))
    manifest_paths = tuple(sorted(p.relative_to(base).as_posix() for p in files if p.name in POLICY_NAMES))
    deployment_hints = tuple(sorted(p.relative_to(base).as_posix() for p in files if p.name in DEPLOYMENT_NAMES))

    nodes: list[GraphNode] = []
    path_to_id: dict[Path, str] = {}
    for path in files:
        rel = path.relative_to(base).as_posix()
        node_id = f"repo:{rel}"
        path_to_id[path] = node_id
        if path.suffix.lower() in SOURCE_SUFFIXES:
            node_type = NodeType.COMPONENT
        elif path.name in POLICY_NAMES or path.name in CONFIG_NAMES:
            node_type = NodeType.POLICY
        elif path.name in DEPLOYMENT_NAMES or path.name.lower().startswith("dockerfile"):
            node_type = NodeType.DEPLOYMENT
        else:
            continue
        nodes.append(
            GraphNode(
                node_id,
                node_type,
                rel,
                {"source_path": rel, "repository_revision": repository_revision},
                GraphUncertainty(TruthState.SUCCESS, confidence=0.98),
            )
        )

    node_ids = {n.id for n in nodes}
    edges: list[GraphEdge] = []
    source_set = {p for p in files if p.suffix.lower() == ".py"}
    for source in sorted(source_set, key=lambda p: p.as_posix()):
        source_id = path_to_id[source]
        for index, imported in enumerate(_python_imports(source)):
            target = _module_path(imported, source, source_set, base)
            if target is None or path_to_id.get(target) not in node_ids:
                continue
            edges.append(
                GraphEdge(
                    f"dep:{source.relative_to(base).as_posix()}:{index}:{imported}",
                    EdgeType.DEPENDENCY,
                    source_id,
                    path_to_id[target],
                    {"import": imported, "source_path": source.relative_to(base).as_posix(), "repository_revision": repository_revision},
                    GraphUncertainty(TruthState.SUCCESS, confidence=0.9),
                )
            )

    graph_id = f"recovered-architecture:{repository_revision}"
    graph = ArchitectureGraph(
        graph_id,
        version,
        tuple(sorted(nodes, key=lambda n: n.id)),
        tuple(sorted(edges, key=lambda e: e.id)),
        (),
        GraphUncertainty(TruthState.SUCCESS, confidence=0.9),
        traceability,
    )
    graph.validate()

    revision_id = f"recovery:{repository_revision}:{version}"
    state = SystemState.create(
        version=version,
        architecture=graph,
        implementation_ref=StateReference(TruthfulValue(TruthState.SUCCESS, repository_revision)),
        configuration_ref=StateReference(TruthfulValue(TruthState.SUCCESS, "repository-static-config")),
        deployment_ref=StateReference(TruthfulValue(TruthState.UNAVAILABLE, detail="Repository inspection cannot establish live deployment state")),
        policy_ref=StateReference(TruthfulValue(TruthState.SUCCESS, "repository-static-policy")),
        environment_ref=StateReference(TruthfulValue(TruthState.UNAVAILABLE, detail="Repository inspection cannot establish live environment state")),
        active_experiments=(),
        traceability=traceability,
    )
    # SystemState.create generates its own revision identity; recovery's supplied revision is used as provenance.
    findings = (
        RecoveryFinding("RUNTIME_DEPLOYMENT_UNAVAILABLE", TruthState.UNAVAILABLE, "deployment", "No live deployment evidence was available to static repository recovery."),
        RecoveryFinding("RUNTIME_ENVIRONMENT_UNAVAILABLE", TruthState.UNAVAILABLE, "environment", "No live environment evidence was available to static repository recovery."),
    )
    report = RecoveryReport(repository_revision, RecoveryInventory(rel_paths, source_paths, manifest_paths, deployment_hints), graph, state, findings)
    report.validate()
    return report
