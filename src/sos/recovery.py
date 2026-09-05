"""W3 — existing-system architecture recovery.

Recover an existing software repository into the authoritative W2
``SystemState`` / ``ArchitectureGraph`` boundary **without pretending static
repository evidence proves runtime reality**.

Design invariants (frozen W3 Work Order):

* deterministic file inventory with stable, sorted, posix-relative paths;
* conservative static classification of source / manifest / config / deployment
  / documentation artifacts into typed W2 graph nodes;
* repository-local dependency extraction **only** when directly supported by a
  parseable manifest (pyproject.toml PEP-621, requirements.txt, package.json);
* exact repository-revision provenance on every recovered fact;
* runtime / deployment / environment gaps represented as explicit ``UNKNOWN`` /
  ``UNAVAILABLE`` truthful state — never converted into successful facts;
* full W1 Mission/Value/Context traceability threaded through W2 contracts;
* deterministic output: identical repository bytes + same supplied revision ⇒
  identical semantic output (no random identifiers, sorted iteration);
* no runtime, telemetry, candidate, assurance, experiment or execution side
  effects — recovery is a pure read boundary.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID  # noqa: F401  (documented as intentionally unused)

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
from .model import (
    ModelValidationError,
    Traceability,
    TruthState,
    TruthfulValue,
)


# ---------------------------------------------------------------------------
# Classification vocabulary
# ---------------------------------------------------------------------------


class FileClassification(str, Enum):
    """Conservative static classification of a recovered repository artifact."""

    SOURCE = "source"
    MANIFEST = "manifest"
    CONFIG = "config"
    DEPLOYMENT = "deployment"
    POLICY = "policy"
    DOCUMENTATION = "documentation"
    BINARY = "binary"
    UNCLASSIFIED = "unclassified"


# Directories that are build/dependency caches or VCS internals — never
# architecture. Recovered facts never descend into these.
_EXCLUDED_DIRS: frozenset[str] = frozenset({
    ".git", ".hg", ".svn",
    "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".tox", ".venv", "venv", "env",
    "dist", "build", "target", ".next", ".turbo", ".cache",
    ".idea", ".vscode",
})

_MANIFEST_NAMES: frozenset[str] = frozenset({
    "pyproject.toml", "package.json", "requirements.txt", "setup.py",
    "Pipfile", "go.mod", "Cargo.toml", "pom.xml", "build.gradle",
    "build.gradle.kts", "Gemfile",
})

_SOURCE_SUFFIXES: frozenset[str] = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".rb", ".php", ".c", ".h", ".cc", ".cpp",
    ".hpp", ".cs", ".swift", ".scala", ".clj", ".ex", ".exs",
})

_DEPLOYMENT_NAMES: frozenset[str] = frozenset({
    "Dockerfile", "Containerfile",
})

_DEPLOYMENT_PREFIXES: tuple[str, ...] = ("docker-compose", "compose")

_DOC_SUFFIXES: frozenset[str] = frozenset({".md", ".rst", ".txt"})


# ---------------------------------------------------------------------------
# Provenance-bearing recovered records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecoveredFile:
    """A single recovered file with source-path + exact-revision provenance."""

    relative_path: str
    classification: FileClassification
    revision: str


@dataclass(frozen=True)
class RecoveredDependency:
    """A repository-local dependency relationship that was directly resolvable."""

    name: str
    spec: str | None
    source_manifest: str
    revision: str


@dataclass(frozen=True)
class UnresolvedFact:
    """A runtime/deployment/environment gap that remained unobservable."""

    dimension: str
    truth: TruthfulValue[Any]
    detail: str

    def __post_init__(self) -> None:
        # Truthfulness gate: a gap must never masquerade as a successful value.
        if self.truth.state == TruthState.SUCCESS:
            raise ModelValidationError("UnresolvedFact must not be SUCCESS")
        if self.truth.value is not None:
            raise ModelValidationError("UnresolvedFact must not carry a value")
        if not self.detail:
            raise ModelValidationError("UnresolvedFact requires an explanatory detail")


@dataclass(frozen=True)
class RepositoryInventory:
    """Deterministic inventory of a recovered repository root."""

    root: str
    revision: str
    files: tuple[RecoveredFile, ...]


@dataclass(frozen=True)
class RecoveryResult:
    """The recovered W2 System State plus recovery evidence."""

    system_state: SystemState
    inventory: RepositoryInventory
    dependencies: tuple[RecoveredDependency, ...]
    unresolved_facts: tuple[UnresolvedFact, ...]
    revision: str


# ---------------------------------------------------------------------------
# Deterministic helpers (no randomness — required by criterion 6)
# ---------------------------------------------------------------------------


def _deterministic_id(prefix: str, *parts: str) -> str:
    """Derive a stable, content-addressed identifier from provenance parts."""
    material = ":".join(parts)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _posix_relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_excluded(rel_path: str) -> bool:
    parts = rel_path.split("/")
    return any(p in _EXCLUDED_DIRS for p in parts)


def _is_binary(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:2048]
    except OSError:
        return True
    if b"\x00" in chunk:
        return True
    return False


def _classify(path: Path, rel_path: str) -> FileClassification:
    name = path.name
    suffix = path.suffix.lower()
    if name in _MANIFEST_NAMES:
        return FileClassification.MANIFEST
    if name in _DEPLOYMENT_NAMES or any(name.startswith(p) for p in _DEPLOYMENT_PREFIXES):
        return FileClassification.DEPLOYMENT
    # .github/workflows/*.yml describe CI/deployment topology.
    if rel_path.startswith(".github/workflows/") and suffix in (".yml", ".yaml"):
        return FileClassification.DEPLOYMENT
    if suffix in _SOURCE_SUFFIXES:
        return FileClassification.SOURCE
    if suffix in (".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf") or name == ".env.example":
        if name in _MANIFEST_NAMES:
            return FileClassification.MANIFEST
        return FileClassification.CONFIG
    if suffix in _DOC_SUFFIXES:
        return FileClassification.DOCUMENTATION
    if suffix in (".json",) and name not in _MANIFEST_NAMES:
        # Non-manifest JSON is treated as config (conservative).
        return FileClassification.CONFIG
    if _is_binary(path):
        return FileClassification.BINARY
    return FileClassification.UNCLASSIFIED


# ---------------------------------------------------------------------------
# Repository inventory
# ---------------------------------------------------------------------------


def inventory_repository(root: str | Path, revision: str) -> RepositoryInventory:
    """Walk a repository root deterministically and classify its artifacts."""
    root_path = Path(root)
    if not root_path.exists():
        raise ModelValidationError(f"repository root does not exist: {root}")
    if not root_path.is_dir():
        raise ModelValidationError(f"repository root is not a directory: {root}")
    if not revision or not str(revision).strip():
        raise ModelValidationError("repository revision must be supplied")

    discovered: list[RecoveredFile] = []
    # sorted() guarantees deterministic ordering independent of filesystem walk order.
    for path in sorted(root_path.rglob("*")):
        if not path.is_file():
            continue
        rel = _posix_relative(root_path, path)
        if _is_excluded(rel):
            continue
        classification = _classify(path, rel)
        discovered.append(RecoveredFile(relative_path=rel, classification=classification, revision=revision))

    return RepositoryInventory(root=str(root_path.resolve()), revision=revision, files=tuple(discovered))


# ---------------------------------------------------------------------------
# Manifest dependency extraction (only when directly resolvable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ManifestParse:
    manifest_path: str
    deps: tuple[RecoveredDependency, ...]
    truth: TruthfulValue[Any]
    detail: str


def _extract_dependencies(manifest_path: str, content: bytes, revision: str) -> _ManifestParse:
    name = Path(manifest_path).name
    if name == "pyproject.toml":
        return _extract_pyproject(manifest_path, content, revision)
    if name == "requirements.txt":
        return _extract_requirements(manifest_path, content, revision)
    if name == "package.json":
        return _extract_package_json(manifest_path, content, revision)
    # A manifest kind we recognise but do not parse — record as UNKNOWN, not empty success.
    return _ManifestParse(
        manifest_path=manifest_path,
        deps=(),
        truth=TruthfulValue(TruthState.UNKNOWN, None, f"dependency extraction unsupported for {name}"),
        detail=f"dependency extraction unsupported for {name}",
    )


def _extract_pyproject(manifest_path: str, content: bytes, revision: str) -> _ManifestParse:
    try:
        data = tomllib.loads(content.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        return _ManifestParse(
            manifest_path=manifest_path,
            deps=(),
            truth=TruthfulValue(TruthState.FAILED, None, f"pyproject.toml parse error: {exc}"),
            detail=f"pyproject.toml parse error: {exc}",
        )
    raw_deps = data.get("project", {}).get("dependencies", []) or []
    deps: list[RecoveredDependency] = []
    for entry in raw_deps:
        name, spec = _split_dep_spec(str(entry))
        if name:
            deps.append(RecoveredDependency(name=name, spec=spec, source_manifest=manifest_path, revision=revision))
    detail = f"extracted {len(deps)} dependencies from pyproject.toml"
    return _ManifestParse(
        manifest_path=manifest_path,
        deps=tuple(deps),
        truth=TruthfulValue(TruthState.SUCCESS, len(deps), detail),
        detail=detail,
    )


def _extract_requirements(manifest_path: str, content: bytes, revision: str) -> _ManifestParse:
    deps: list[RecoveredDependency] = []
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        return _ManifestParse(
            manifest_path=manifest_path,
            deps=(),
            truth=TruthfulValue(TruthState.FAILED, None, f"requirements.txt decode error: {exc}"),
            detail=f"requirements.txt decode error: {exc}",
        )
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, spec = _split_dep_spec(line)
        if name:
            deps.append(RecoveredDependency(name=name, spec=spec, source_manifest=manifest_path, revision=revision))
    detail = f"extracted {len(deps)} dependencies from requirements.txt"
    return _ManifestParse(
        manifest_path=manifest_path,
        deps=tuple(deps),
        truth=TruthfulValue(TruthState.SUCCESS, len(deps), detail),
        detail=detail,
    )


def _extract_package_json(manifest_path: str, content: bytes, revision: str) -> _ManifestParse:
    try:
        data = json.loads(content.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _ManifestParse(
            manifest_path=manifest_path,
            deps=(),
            truth=TruthfulValue(TruthState.FAILED, None, f"package.json parse error: {exc}"),
            detail=f"package.json parse error: {exc}",
        )
    deps: list[RecoveredDependency] = []
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        section_map = data.get(section, {}) or {}
        for dep_name, spec in section_map.items():
            deps.append(RecoveredDependency(name=str(dep_name), spec=str(spec) if spec is not None else None, source_manifest=manifest_path, revision=revision))
    detail = f"extracted {len(deps)} dependencies from package.json"
    return _ManifestParse(
        manifest_path=manifest_path,
        deps=tuple(deps),
        truth=TruthfulValue(TruthState.SUCCESS, len(deps), detail),
        detail=detail,
    )


def _split_dep_spec(entry: str) -> tuple[str, str | None]:
    """Split a dependency specifier into name and version spec.

    Handles PEP-508-ish and package.json-ish forms conservatively. Only direct,
    deterministically-resolvable relationships are produced.
    """
    s = entry.strip()
    if not s:
        return "", None
    # Strip environment markers / extras conservatively: name[extras]==1.0 ; python_version<"4"
    for sep in (";", " #"):
        s = s.split(sep, 1)[0].strip()
    if not s:
        return "", None
    # Strip extras: name[extras] -> name
    if "[" in s:
        s = s.split("[", 1)[0].strip()
    # Find the first version operator and split there.
    for i, ch in enumerate(s):
        if ch in "><=!~":
            name = s[:i].strip()
            spec = s[i:].strip() or None
            return name, spec
    return s, None


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------


def _certain() -> GraphUncertainty:
    return GraphUncertainty(TruthState.SUCCESS, confidence=1.0)


def _file_provenance(file: RecoveredFile) -> dict[str, str]:
    """Explicit source-path + repository-revision provenance for a file-derived graph fact."""
    return {"source_path": file.relative_path, "revision": file.revision}


def _dep_provenance(dep: RecoveredDependency) -> dict[str, str]:
    """Explicit provenance for a dependency-derived graph fact.

    A recovered external dependency is not itself a repository file; its provenance
    is the manifest that declared it at the recovered revision. ``source_path`` is
    set to that manifest path so dependency facts carry the same explicit
    source-path + revision provenance seam as file-derived facts.
    """
    return {"source_manifest": dep.source_manifest, "source_path": dep.source_manifest, "revision": dep.revision}


def _build_graph(inventory: RepositoryInventory, traceability: Traceability) -> tuple[ArchitectureGraph, tuple[RecoveredDependency, ...], tuple[UnresolvedFact, ...]]:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    deps: list[RecoveredDependency] = []
    unresolved: list[UnresolvedFact] = []

    manifest_nodes: dict[str, str] = {}  # manifest_path -> node_id

    for f in inventory.files:
        node_id = _deterministic_id("node", inventory.revision, f.relative_path)
        provenance = _file_provenance(f)
        if f.classification == FileClassification.SOURCE:
            nodes.append(GraphNode(
                id=node_id, type=NodeType.COMPONENT, name=f.relative_path,
                attributes={
                    "kind": "source",
                    "language": Path(f.relative_path).suffix.lstrip("."),
                    **provenance,
                },
                uncertainty=_certain(),
            ))
        elif f.classification == FileClassification.MANIFEST:
            manifest_nodes[f.relative_path] = node_id
            nodes.append(GraphNode(
                id=node_id, type=NodeType.COMPONENT, name=f.relative_path,
                attributes={"kind": "manifest", **provenance},
                uncertainty=_certain(),
            ))
        elif f.classification == FileClassification.DEPLOYMENT:
            nodes.append(GraphNode(
                id=node_id, type=NodeType.DEPLOYMENT, name=f.relative_path,
                attributes={"kind": "deployment-artifact", **provenance},
                uncertainty=_certain(),
            ))
        elif f.classification in (FileClassification.CONFIG, FileClassification.POLICY):
            nodes.append(GraphNode(
                id=node_id, type=NodeType.POLICY, name=f.relative_path,
                attributes={"kind": "config", **provenance},
                uncertainty=_certain(),
            ))
        # DOCUMENTATION / BINARY / UNCLASSIFIED are recorded in the inventory
        # but do not become architecture nodes (conservative classification).

    # Dependency extraction: only when directly resolvable.
    for f in inventory.files:
        if f.classification != FileClassification.MANIFEST:
            continue
        root_path = Path(inventory.root) / f.relative_path
        try:
            content = root_path.read_bytes()
        except OSError as exc:
            unresolved.append(UnresolvedFact(
                dimension="dependency-extraction",
                truth=TruthfulValue(TruthState.UNAVAILABLE, None, f"could not read {f.relative_path}: {exc}"),
                detail=f"could not read {f.relative_path}: {exc}",
            ))
            continue
        parsed = _extract_dependencies(f.relative_path, content, inventory.revision)
        if parsed.truth.state == TruthState.SUCCESS:
            deps.extend(parsed.deps)
        else:
            # Record the failed/unknown extraction explicitly — never silently empty.
            unresolved.append(UnresolvedFact(
                dimension="dependency-extraction",
                truth=parsed.truth,
                detail=parsed.detail,
            ))

    # Create external_dependency nodes (deduplicated by name) + dependency edges.
    dep_node_ids: dict[str, str] = {}
    for dep in deps:
        if dep.name in dep_node_ids:
            continue
        dep_node_id = _deterministic_id("dep", inventory.revision, dep.name)
        dep_node_ids[dep.name] = dep_node_id
        nodes.append(GraphNode(
            id=dep_node_id, type=NodeType.EXTERNAL_DEPENDENCY, name=dep.name,
            attributes={
                "kind": "external-dependency",
                "spec": dep.spec,
                **_dep_provenance(dep),
            },
            uncertainty=_certain(),
        ))
    for dep in deps:
        manifest_node_id = manifest_nodes.get(dep.source_manifest)
        if not manifest_node_id:
            continue
        edge_id = _deterministic_id("edge", inventory.revision, dep.source_manifest, dep.name, "dependency")
        edges.append(GraphEdge(
            id=edge_id, type=EdgeType.DEPENDENCY,
            source_id=manifest_node_id, target_id=dep_node_ids[dep.name],
            attributes={
                "spec": dep.spec,
                **_dep_provenance(dep),
            },
            uncertainty=_certain(),
        ))

    graph_id = _deterministic_id("arch", inventory.revision)
    graph = ArchitectureGraph(
        id=graph_id,
        version=1,
        nodes=tuple(nodes),
        edges=tuple(edges),
        boundary_contracts=(),  # static recovery does not establish boundary contracts
        uncertainty=GraphUncertainty(
            TruthState.SUCCESS,
            confidence=1.0,
            reason=None,
        ),
        traceability=traceability,
    )
    return graph, tuple(deps), tuple(unresolved)


# ---------------------------------------------------------------------------
# Public recovery entry point
# ---------------------------------------------------------------------------


def recover_repository(
    *,
    root: str | Path,
    revision: str,
    traceability: Traceability,
) -> RecoveryResult:
    """Recover a repository into the W2 System State / Architecture Graph boundary.

    The recovery is a pure static read: no network, no subprocess, no writes to
    the recovered repository. Runtime/deployment/environment facts that are not
    directly observable from the repository are represented as explicit
    ``UNKNOWN`` / ``UNAVAILABLE`` truthful state — never as successful facts.
    """
    # Authority gate: W2 graph contracts require full W1 traceability.
    traceability.validate(require_value=True, require_context=True)

    inventory = inventory_repository(root, revision)
    graph, deps, unresolved_extraction = _build_graph(inventory, traceability)
    graph.validate()

    # Truthful SystemState reference population.
    implementation_ref = StateReference(TruthfulValue(TruthState.SUCCESS, revision, None))

    # Configuration is recovered as static artifacts; runtime/deployed config is not observable.
    config_count = sum(1 for f in inventory.files if f.classification in (FileClassification.CONFIG, FileClassification.POLICY))
    if config_count > 0:
        configuration_ref = StateReference(TruthfulValue(
            TruthState.SUCCESS,
            f"recovered {config_count} static configuration artifacts",
            None,
        ))
    else:
        configuration_ref = StateReference(TruthfulValue(
            TruthState.UNKNOWN,
            None,
            "no static configuration artifacts recovered",
        ))

    # Policy is recovered as static artifacts where present.
    policy_count = sum(1 for f in inventory.files if f.classification == FileClassification.POLICY)
    if policy_count > 0:
        policy_ref = StateReference(TruthfulValue(
            TruthState.SUCCESS,
            f"recovered {policy_count} static policy artifacts",
            None,
        ))
    else:
        policy_ref = StateReference(TruthfulValue(
            TruthState.UNKNOWN,
            None,
            "no static policy artifacts recovered",
        ))

    # Runtime deployment topology is NOT observable from static recovery.
    deployment_ref = StateReference(TruthfulValue(
        TruthState.UNAVAILABLE,
        None,
        "runtime deployment topology not observable from static repository recovery",
    ))
    # Runtime environment is NOT observable from static recovery.
    environment_ref = StateReference(TruthfulValue(
        TruthState.UNAVAILABLE,
        None,
        "runtime environment not observable from static repository recovery",
    ))

    unresolved_facts: list[UnresolvedFact] = list(unresolved_extraction)
    unresolved_facts.append(UnresolvedFact(
        dimension="runtime-deployment",
        truth=TruthfulValue(TruthState.UNAVAILABLE, None, "runtime deployment topology not observable from static recovery"),
        detail="runtime deployment topology not observable from static recovery",
    ))
    unresolved_facts.append(UnresolvedFact(
        dimension="runtime-environment",
        truth=TruthfulValue(TruthState.UNAVAILABLE, None, "runtime environment not observable from static recovery"),
        detail="runtime environment not observable from static recovery",
    ))
    unresolved_facts.append(UnresolvedFact(
        dimension="runtime-configuration",
        truth=TruthfulValue(TruthState.UNAVAILABLE, None, "runtime/deployed configuration not observable from static recovery"),
        detail="runtime/deployed configuration not observable from static recovery",
    ))

    state_id = _deterministic_id("state", revision)
    revision_id = _deterministic_id("recovered-rev", revision)

    system_state = SystemState(
        id=state_id,
        version=1,
        architecture_ref=graph.id,
        implementation_ref=implementation_ref,
        configuration_ref=configuration_ref,
        deployment_ref=deployment_ref,
        policy_ref=policy_ref,
        environment_ref=environment_ref,
        active_experiments=(),
        architecture=graph,
        traceability=traceability,
        revision_id=revision_id,
        parent_revision_id=None,
    )
    system_state.validate()

    return RecoveryResult(
        system_state=system_state,
        inventory=inventory,
        dependencies=deps,
        unresolved_facts=tuple(unresolved_facts),
        revision=revision,
    )
