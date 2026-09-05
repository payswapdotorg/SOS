from pathlib import Path

import pytest

from sos import Context, Traceability, TruthState, recover_repository
from sos import ModelValidationError


def trace():
    return Traceability("constitution:1", "mission:1", "value:1", "context:1")


def make_repo(root: Path) -> None:
    (root / "src" / "app").mkdir(parents=True)
    (root / "src" / "app" / "a.py").write_text("from app import b\n", encoding="utf-8")
    (root / "src" / "app" / "b.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='example'\n", encoding="utf-8")
    (root / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")


def test_recovery_is_deterministic_and_inventory_is_sorted(tmp_path: Path):
    make_repo(tmp_path)
    report1 = recover_repository(tmp_path, repository_revision="rev-1", traceability=trace())
    report2 = recover_repository(tmp_path, repository_revision="rev-1", traceability=trace())
    assert report1.to_dict() == report2.to_dict()
    assert report1.inventory.paths == tuple(sorted(report1.inventory.paths))
    assert report1.inventory.source_paths == ("src/app/a.py", "src/app/b.py")


def test_python_import_becomes_dependency_only_when_target_resolves(tmp_path: Path):
    make_repo(tmp_path)
    report = recover_repository(tmp_path, repository_revision="rev-1", traceability=trace())
    edges = {(edge.source_id, edge.target_id, edge.type.value) for edge in report.architecture.edges}
    assert ("repo:src/app/a.py", "repo:src/app/b.py", "dependency") in edges


def test_recovered_facts_have_provenance_and_uncertainty(tmp_path: Path):
    make_repo(tmp_path)
    report = recover_repository(tmp_path, repository_revision="rev-abc", traceability=trace())
    node = next(node for node in report.architecture.nodes if node.id == "repo:src/app/a.py")
    assert node.attributes["source_path"] == "src/app/a.py"
    assert node.attributes["repository_revision"] == "rev-abc"
    assert node.uncertainty.state == TruthState.SUCCESS


def test_runtime_facts_remain_unavailable(tmp_path: Path):
    make_repo(tmp_path)
    report = recover_repository(tmp_path, repository_revision="rev-1", traceability=trace())
    assert {f.state for f in report.findings} == {TruthState.UNAVAILABLE}
    assert report.system_state.deployment_ref.ref.state == TruthState.UNAVAILABLE
    assert report.system_state.environment_ref.ref.state == TruthState.UNAVAILABLE


def test_invalid_root_is_rejected():
    with pytest.raises(ModelValidationError):
        recover_repository("/does/not/exist", repository_revision="rev-1", traceability=trace())
