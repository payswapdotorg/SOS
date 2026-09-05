"""W3 — existing-system architecture recovery invariant tests.

These tests define the behavioural contract of `src/sos/recovery.py` before the
module exists (failing-first per SOS-IMPLEMENTATION-PROCESS §5). They cover the
W3 Work Order acceptance criteria: deterministic root recovery, typed W2 graph
population with provenance, repository-local dependency extraction only when
directly resolvable, truthful UNKNOWN/UNAVAILABLE for runtime facts, W1/W2
traceability, determinism, invalid-root rejection, and absence of runtime side
effects.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from sos import (
    ArchitectureGraph,
    EdgeType,
    GraphUncertainty,
    JsonModelStore,
    ModelValidationError,
    NodeType,
    StateReference,
    SystemState,
    Traceability,
    TruthState,
    TruthfulValue,
)
from sos.recovery import (
    FileClassification,
    RecoveryResult,
    RepositoryInventory,
    UnresolvedFact,
    recover_repository,
    inventory_repository,
)


def tr() -> Traceability:
    return Traceability(
        constitution_ref="constitution:1",
        mission_ref="mission:1",
        value_model_ref="value:1",
        context_ref="context:1",
    )


def write_fixture_repo(root: Path) -> None:
    """A tiny but representative repository recovered deterministically."""
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["pytest>=9.0", "rich>=13"]\n',
        encoding="utf-8",
    )
    (root / "requirements.txt").write_text("pytest>=9.0\n# a comment\nrich>=13\n", encoding="utf-8")
    (root / "src" / "demo").mkdir(parents=True)
    (root / "src" / "demo" / "__init__.py").write_text('"""demo package"""\n', encoding="utf-8")
    (root / "src" / "demo" / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    (root / "Dockerfile").write_text("FROM python:3.12\nCOPY . /app\n", encoding="utf-8")
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "test.yml").write_text("name: test\non: [push]\n", encoding="utf-8")
    (root / "config.yaml").write_text("service:\n  port: 8080\n", encoding="utf-8")
    (root / ".env.example").write_text("DATABASE_URL=postgres://example\n", encoding="utf-8")
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    (root / "assets").mkdir()
    (root / "assets" / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
    (root / "node_modules" / "ignored").mkdir(parents=True)
    (root / "node_modules" / "ignored" / "dep.js").write_text("module.exports = 1;\n", encoding="utf-8")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "app.cpython-312.pyc").write_bytes(b"\x00\x00")


REVISION = "abc123def4567890abc123def4567890abc12345"


# --- acceptance criteria 1 & 7 -------------------------------------------


def test_recovery_rejects_nonexistent_root():
    with pytest.raises(ModelValidationError):
        recover_repository(root="/does/not/exist", revision=REVISION, traceability=tr())


def test_recovery_rejects_file_as_root(tmp_path):
    f = tmp_path / "not-a-dir"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(ModelValidationError):
        recover_repository(root=f, revision=REVISION, traceability=tr())


def test_recovery_rejects_empty_revision(tmp_path):
    write_fixture_repo(tmp_path)
    with pytest.raises(ModelValidationError):
        recover_repository(root=tmp_path, revision="", traceability=tr())


def test_recovery_rejects_traceability_missing_context(tmp_path):
    write_fixture_repo(tmp_path)
    bad = Traceability(
        constitution_ref="constitution:1",
        mission_ref="mission:1",
        value_model_ref="value:1",
        context_ref=None,
    )
    with pytest.raises(ModelValidationError):
        recover_repository(root=tmp_path, revision=REVISION, traceability=bad)


# --- acceptance criteria 2 & 5 -------------------------------------------


def test_recovery_produces_valid_w2_system_state_and_graph(tmp_path):
    write_fixture_repo(tmp_path)
    result = recover_repository(root=tmp_path, revision=REVISION, traceability=tr())
    assert isinstance(result, RecoveryResult)
    assert isinstance(result.system_state, SystemState)
    assert isinstance(result.system_state.architecture, ArchitectureGraph)
    # The recovered artifacts must satisfy the W2 invariants.
    result.system_state.validate()
    result.system_state.architecture.validate()
    # implementation_ref carries the exact recovered revision (directly observable).
    assert result.system_state.implementation_ref.ref.state == TruthState.SUCCESS
    assert result.system_state.implementation_ref.ref.value == REVISION


def test_recovered_graph_uses_frozen_node_and_edge_vocab(tmp_path):
    write_fixture_repo(tmp_path)
    result = recover_repository(root=tmp_path, revision=REVISION, traceability=tr())
    node_types = {n.type for n in result.system_state.architecture.nodes}
    edge_types = {e.type for e in result.system_state.architecture.edges}
    assert node_types.issubset(set(NodeType))
    assert edge_types.issubset(set(EdgeType))


def test_recovered_facts_carry_source_path_and_revision_provenance(tmp_path):
    write_fixture_repo(tmp_path)
    result = recover_repository(root=tmp_path, revision=REVISION, traceability=tr())
    assert result.inventory.revision == REVISION
    assert len(result.inventory.files) > 0
    for f in result.inventory.files:
        assert f.revision == REVISION
        assert f.relative_path  # non-empty posix-relative path
        assert "/" not in f.relative_path.lstrip("/") or f.relative_path.count("/") >= 0
    # pyproject.toml is recovered and classified as a manifest.
    manifests = [f for f in result.inventory.files if f.classification == FileClassification.MANIFEST]
    assert any(f.relative_path == "pyproject.toml" for f in manifests)


def test_recovered_graph_facts_carry_explicit_source_path_and_revision_provenance(tmp_path):
    """F02: recovered W2 graph/dependency facts must carry explicit source-path +
    revision provenance on their attributes (the existing W2 extensibility seam),
    not only on the RecoveredFile inventory records.

    Covers representative facts across the recovered vocabulary: component,
    deployment, policy, external-dependency nodes, and dependency edges.
    """
    write_fixture_repo(tmp_path)
    result = recover_repository(root=tmp_path, revision=REVISION, traceability=tr())
    arch = result.system_state.architecture

    # Every recovered graph node carries explicit source_path + revision provenance.
    for node in arch.nodes:
        attrs = dict(node.attributes)
        assert "source_path" in attrs, f"node {node.id} ({node.type}) missing source_path provenance"
        assert "revision" in attrs, f"node {node.id} ({node.type}) missing revision provenance"
        assert attrs["revision"] == REVISION, f"node {node.id} revision mismatch"
        assert attrs["source_path"], f"node {node.id} has empty source_path"

    # Every recovered dependency edge carries explicit source-path + revision provenance.
    dep_edges = [e for e in arch.edges if e.type == EdgeType.DEPENDENCY]
    assert dep_edges, "expected at least one dependency edge in the fixture repo"
    for edge in dep_edges:
        attrs = dict(edge.attributes)
        assert "source_path" in attrs, f"edge {edge.id} missing source_path provenance"
        assert "source_manifest" in attrs, f"edge {edge.id} missing source_manifest provenance"
        assert "revision" in attrs, f"edge {edge.id} missing revision provenance"
        assert attrs["revision"] == REVISION, f"edge {edge.id} revision mismatch"
        assert attrs["source_path"] == attrs["source_manifest"], (
            f"edge {edge.id}: dependency edge source_path must equal its source_manifest"
        )

    # Representative node-type provenance spot checks (component/deployment/policy/external-dependency).
    component_nodes = [n for n in arch.nodes if n.type == NodeType.COMPONENT]
    deployment_nodes = [n for n in arch.nodes if n.type == NodeType.DEPLOYMENT]
    policy_nodes = [n for n in arch.nodes if n.type == NodeType.POLICY]
    ext_dep_nodes = [n for n in arch.nodes if n.type == NodeType.EXTERNAL_DEPENDENCY]
    assert component_nodes, "fixture must recover at least one component node"
    assert deployment_nodes, "fixture must recover at least one deployment node"
    assert policy_nodes, "fixture must recover at least one policy node"
    assert ext_dep_nodes, "fixture must recover at least one external-dependency node"

    # A source component's source_path is its own file path.
    source_component = next(n for n in component_nodes if dict(n.attributes).get("kind") == "source")
    assert source_component.attributes["source_path"] == source_component.name
    assert source_component.attributes["revision"] == REVISION

    # A deployment node's source_path is the recovered deployment artifact path.
    deployment = deployment_nodes[0]
    assert deployment.attributes["source_path"] == deployment.name
    assert deployment.attributes["revision"] == REVISION

    # A policy node's source_path is the recovered config artifact path.
    policy = policy_nodes[0]
    assert policy.attributes["source_path"] == policy.name
    assert policy.attributes["revision"] == REVISION

    # An external-dependency node's provenance points at the manifest that
    # declared it (not a repo file), at the recovered revision.
    ext_dep = ext_dep_nodes[0]
    assert ext_dep.attributes["revision"] == REVISION
    assert ext_dep.attributes["source_manifest"] in {"pyproject.toml", "requirements.txt", "package.json"}
    assert ext_dep.attributes["source_path"] == ext_dep.attributes["source_manifest"]


def test_recovered_graph_provenance_is_deterministic(tmp_path, tmp_path_factory):
    """F02: provenance attributes are deterministic — identical bytes + same
    revision produce identical provenance on the recovered graph facts."""
    r1 = tmp_path_factory.mktemp("repo-a")
    r2 = tmp_path_factory.mktemp("repo-b")
    write_fixture_repo(r1)
    write_fixture_repo(r2)
    a = recover_repository(root=r1, revision=REVISION, traceability=tr())
    b = recover_repository(root=r2, revision=REVISION, traceability=tr())
    a_attrs = {n.id: dict(n.attributes) for n in a.system_state.architecture.nodes}
    b_attrs = {n.id: dict(n.attributes) for n in b.system_state.architecture.nodes}
    assert a_attrs == b_attrs
    a_edges = {e.id: dict(e.attributes) for e in a.system_state.architecture.edges}
    b_edges = {e.id: dict(e.attributes) for e in b.system_state.architecture.edges}
    assert a_edges == b_edges


def test_recovered_state_carries_w1_traceability(tmp_path):
    write_fixture_repo(tmp_path)
    t = tr()
    result = recover_repository(root=tmp_path, revision=REVISION, traceability=t)
    assert result.system_state.traceability == t
    assert result.system_state.architecture.traceability == t


# --- acceptance criterion 3 ----------------------------------------------


def test_repository_local_dependencies_extracted_when_resolvable(tmp_path):
    write_fixture_repo(tmp_path)
    result = recover_repository(root=tmp_path, revision=REVISION, traceability=tr())
    dep_names = {d.name for d in result.dependencies}
    assert "pytest" in dep_names
    assert "rich" in dep_names
    # external_dependency nodes were created for each recovered dependency.
    ext_dep_nodes = [
        n for n in result.system_state.architecture.nodes if n.type == NodeType.EXTERNAL_DEPENDENCY
    ]
    ext_dep_names = {n.name for n in ext_dep_nodes}
    assert "pytest" in ext_dep_names
    assert "rich" in ext_dep_names
    # dependency edges connect manifests to their parsed deps.
    dep_edges = [e for e in result.system_state.architecture.edges if e.type == EdgeType.DEPENDENCY]
    assert len(dep_edges) >= 2


def test_unparseable_manifest_does_not_silently_become_empty_success(tmp_path):
    write_fixture_repo(tmp_path)
    # Corrupt the manifest so dependency extraction fails for it.
    (tmp_path / "pyproject.toml").write_text("not [valid toml\n", encoding="utf-8")
    result = recover_repository(root=tmp_path, revision=REVISION, traceability=tr())
    # The manifest file is still recovered as an inventory fact (existence is observable).
    manifests = [f for f in result.inventory.files if f.relative_path == "pyproject.toml"]
    assert manifests and manifests[0].classification == FileClassification.MANIFEST
    # But its dependency extraction is recorded as a FAILED/UNKNOWN unresolved fact — never empty success.
    manifest_parse_facts = [
        u for u in result.unresolved_facts if "pyproject.toml" in (u.detail or "")
    ]
    assert manifest_parse_facts, "unparseable manifest must record an explicit failed/unknown extraction"
    assert all(u.truth.state in (TruthState.FAILED, TruthState.UNKNOWN) for u in manifest_parse_facts)
    # requirements.txt still parsed → its deps survive.
    dep_names = {d.name for d in result.dependencies}
    assert "pytest" in dep_names


# --- acceptance criterion 4 (the heart of W3) ----------------------------


def test_runtime_deployment_environment_facts_remain_unavailable(tmp_path):
    write_fixture_repo(tmp_path)
    result = recover_repository(root=tmp_path, revision=REVISION, traceability=tr())
    # Runtime deployment topology is NOT observable from static recovery.
    assert result.system_state.deployment_ref.ref.state == TruthState.UNAVAILABLE
    assert result.system_state.deployment_ref.ref.detail
    # Runtime environment is NOT observable from static recovery.
    assert result.system_state.environment_ref.ref.state == TruthState.UNAVAILABLE
    assert result.system_state.environment_ref.ref.detail
    # No runtime fact was converted into a SUCCESS value.
    for u in result.unresolved_facts:
        assert u.truth.state != TruthState.SUCCESS
        assert u.truth.value is None
        assert u.truth.detail  # every gap carries an explanatory detail


def test_no_runtime_facts_disguised_as_success_in_refs(tmp_path):
    write_fixture_repo(tmp_path)
    result = recover_repository(root=tmp_path, revision=REVISION, traceability=tr())
    # Only directly-observable static facts may be SUCCESS.
    success_refs = [
        ref for ref in (
            result.system_state.implementation_ref,
            result.system_state.configuration_ref,
            result.system_state.policy_ref,
        ) if ref.ref.state == TruthState.SUCCESS
    ]
    assert all(r.ref.value is not None for r in success_refs)


# --- acceptance criterion 6 (determinism) --------------------------------


def test_recovery_is_deterministic_same_bytes_same_revision(tmp_path, tmp_path_factory):
    r1 = tmp_path_factory.mktemp("repo-a")
    r2 = tmp_path_factory.mktemp("repo-b")
    write_fixture_repo(r1)
    write_fixture_repo(r2)
    out1 = recover_repository(root=r1, revision=REVISION, traceability=tr())
    out2 = recover_repository(root=r2, revision=REVISION, traceability=tr())
    p1 = Path(tmp_path_factory.mktemp("out")) / "a.json"
    p2 = Path(tmp_path_factory.mktemp("out")) / "b.json"
    JsonModelStore(p1).save(out1.system_state)
    JsonModelStore(p2).save(out2.system_state)
    assert p1.read_text(encoding="utf-8") == p2.read_text(encoding="utf-8")
    # Deterministic ids: no random uuid4 leaked into recovered artifacts.
    assert out1.system_state.id == out2.system_state.id
    assert out1.system_state.revision_id == out2.system_state.revision_id


def test_different_revision_produces_different_artifact_identity(tmp_path):
    write_fixture_repo(tmp_path)
    a = recover_repository(root=tmp_path, revision="aaaa0000", traceability=tr())
    b = recover_repository(root=tmp_path, revision="bbbb1111", traceability=tr())
    assert a.system_state.id != b.system_state.id
    assert a.system_state.implementation_ref.ref.value == "aaaa0000"
    assert b.system_state.implementation_ref.ref.value == "bbbb1111"


# --- acceptance criterion 8 (no runtime/experiment side effects) ---------


def test_recovery_has_no_runtime_side_effects(tmp_path, monkeypatch):
    write_fixture_repo(tmp_path)
    # Block any network use — recovery must be a pure static read.
    import socket

    def boom(*args, **kwargs):
        raise AssertionError("recovery must not open a network socket")

    monkeypatch.setattr(socket, "socket", boom)
    # Snapshot repo content hash before/after recovery.
    before = hashlib.sha256(
        b"".join(p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file())
    ).hexdigest()
    result = recover_repository(root=tmp_path, revision=REVISION, traceability=tr())
    result.system_state.validate()
    after = hashlib.sha256(
        b"".join(p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file())
    ).hexdigest()
    assert before == after
    # No active experiments are introduced (W8 territory).
    assert result.system_state.active_experiments == ()


def test_recovery_excludes_build_and_dependency_caches(tmp_path):
    write_fixture_repo(tmp_path)
    result = recover_repository(root=tmp_path, revision=REVISION, traceability=tr())
    paths = {f.relative_path for f in result.inventory.files}
    assert not any(p.startswith("node_modules/") for p in paths)
    assert not any(p.startswith("__pycache__/") for p in paths)
    assert not any(".pyc" in p for p in paths)


# --- inventory + boundary rejection --------------------------------------


def test_inventory_is_deterministically_ordered(tmp_path):
    write_fixture_repo(tmp_path)
    inv = inventory_repository(tmp_path, REVISION)
    assert isinstance(inv, RepositoryInventory)
    paths = [f.relative_path for f in inv.files]
    assert paths == sorted(paths)


def test_recovered_graph_validates_subgraph_replacement_boundary(tmp_path):
    """Recovered graph must satisfy W2 subgraph-replacement boundary rules."""
    from sos import SubgraphReplacement

    write_fixture_repo(tmp_path)
    result = recover_repository(root=tmp_path, revision=REVISION, traceability=tr())
    arch = result.system_state.architecture
    node_ids = {n.id for n in arch.nodes}
    assert node_ids  # recovered graph is non-empty
    # A boundary referencing an unknown node is rejected.
    bad = SubgraphReplacement(
        id="bad",
        base_graph_ref=arch.id,
        target_node_ids=(next(iter(node_ids)),),
        replacement_node_ids=("replacement-1",),
        boundary_interface_ids=("does-not-exist",),
        invariants=("preserve-api",),
        traceability=tr(),
    )
    with pytest.raises(ModelValidationError):
        bad.validate(arch)
