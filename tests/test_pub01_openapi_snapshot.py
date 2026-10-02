"""PUB-01 — OpenAPI snapshot: the generated schema at ``/api/v1/openapi.json``
is complete for the §C surface and deterministic (canonicalized hash)."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

fastapi = pytest.importorskip(
    "fastapi",
    reason=(
        "PUB-01 API tests require the 'api' dependency group "
        "(pyproject [project.optional-dependencies].api)"
    ),
)

REPO_ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(REPO_ROOT / "src"), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from services.api.testing import make_client  # noqa: E402

EXPECTED_OPERATIONS = {
    ("/api/v1/health", "GET"),
    ("/api/v1/auth/session", "GET"),
    ("/api/v1/auth/login", "POST"),
    ("/api/v1/auth/logout", "POST"),
    ("/api/v1/me", "GET"),
    ("/api/v1/workspaces", "GET"),
    ("/api/v1/workspaces", "POST"),
    ("/api/v1/workspaces/{workspace_id}", "GET"),
    ("/api/v1/missions", "GET"),
    ("/api/v1/missions", "POST"),
    ("/api/v1/missions/{mission_id}", "GET"),
    ("/api/v1/missions/{mission_id}/revisions", "GET"),
    ("/api/v1/missions/{mission_id}/revisions", "POST"),
    ("/api/v1/systems", "GET"),
    ("/api/v1/systems", "POST"),
    ("/api/v1/systems/{system_id}", "GET"),
    ("/api/v1/systems/{system_id}/recovery", "GET"),
    ("/api/v1/systems/{system_id}/recovery", "POST"),
    ("/api/v1/evidence", "GET"),
    ("/api/v1/hypotheses", "GET"),
    ("/api/v1/candidates", "GET"),
    ("/api/v1/assurance", "GET"),
    ("/api/v1/decisions", "GET"),
    ("/api/v1/authorizations", "GET"),
    ("/api/v1/experiments", "GET"),
    ("/api/v1/experiments", "POST"),
    ("/api/v1/experiments/{experiment_id}", "GET"),
    ("/api/v1/executions", "GET"),
    ("/api/v1/executions", "POST"),
    ("/api/v1/executions/{execution_id}", "GET"),
    ("/api/v1/learning", "GET"),
    ("/api/v1/memory", "GET"),
    ("/api/v1/jobs", "GET"),
    ("/api/v1/jobs", "POST"),
    ("/api/v1/jobs/{job_id}", "GET"),
    ("/api/v1/providers/status", "GET"),
    ("/api/v1/providers/status/{name}", "GET"),
}

EXPECTED_COMPONENT_SCHEMAS = {
    "WorkspaceDTO", "WorkspaceDetailDTO", "AuditEventDTO", "UserDTO",
    "SessionDTO", "LoginRequestDTO", "LoginResponseDTO", "MissionDTO",
    "MissionRevisionDTO", "MissionApprovalDTO", "SystemDTO",
    "SystemRevisionDTO", "SourceRefDTO", "RecoveryInfoDTO",
    "ArchitectureGraphDTO", "GraphNodeDTO", "GraphEdgeDTO",
    "UncertaintyDTO", "EvidenceDTO", "EvidenceProvenanceDTO",
    "HypothesisDTO", "CandidateDTO", "SubgraphReplacementDTO",
    "CandidateEvaluationDTO", "ObjectiveEvaluationDTO", "ParetoEntryDTO",
    "ReversibilityDTO", "AssuranceRunDTO", "AssuranceCheckDTO",
    "DecisionDTO", "AskPayloadDTO", "AuthorizationDTO", "ExperimentDTO",
    "ExperimentEventDTO", "ExecutionDTO", "ExecutionReceiptDTO",
    "OutcomeDTO", "SideEffectDTO", "RollbackRefDTO", "LearningRecordDTO",
    "JobDTO", "ProviderStatusDTO", "HealthResponseDTO", "HealthCheckDTO",
    # MemoryEntryDTO aliases LearningRecordDTO (identical wire shape §C.3),
    # so only one component schema is emitted — asserted explicitly:
    # the frozen vocabularies imported verbatim from src/sos
    "TruthState", "DecisionAction", "AssuranceStatus", "ExperimentState",
    "NodeType", "EdgeType",
}


def _openapi(client) -> dict:
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    return response.json()


def test_openapi_covers_the_full_surface(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        spec = _openapi(client)
        present = {
            (path, method.upper())
            for path, ops in spec["paths"].items()
            for method in ops
            if method in ("get", "post", "put", "delete", "patch")
        }
        missing = EXPECTED_OPERATIONS - present
        assert not missing, f"missing operations: {sorted(missing)}"
        assert set(present) == EXPECTED_OPERATIONS, sorted(set(present) - EXPECTED_OPERATIONS)


def test_openapi_component_schemas_complete(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        spec = _openapi(client)
        schemas = set(spec["components"]["schemas"])
        missing = EXPECTED_COMPONENT_SCHEMAS - schemas
        assert not missing, f"missing schemas: {sorted(missing)}"


def test_openapi_truth_state_enum_is_the_six_state_vocabulary(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path) as client:
        spec = _openapi(client)
        schemas = spec["components"]["schemas"]
        # the truth-state enum component IS the frozen sos.model vocabulary
        assert set(schemas["TruthState"]["enum"]) == {
            "SUCCESS", "EMPTY", "FAILED", "UNKNOWN", "UNSUPPORTED",
            "UNAVAILABLE",
        }
        assert set(schemas["DecisionAction"]["enum"]) == {
            "ACT", "EXPERIMENT", "GATHER_EVIDENCE", "ASK", "REJECT",
            "ROLLBACK",
        }
        # and the DTOs reference it (status fields use the enum component)
        evidence = schemas["EvidenceDTO"]["properties"]
        assert evidence["status"]["$ref"].endswith("/TruthState")
        kinds = evidence["kind"]["enum"]
        assert set(kinds) == {
            "source_revision", "runtime_observation", "test_result",
            "telemetry", "environment", "experiment", "business_outcome",
        }
        assert set(schemas["AssuranceStatus"]["enum"]) == {
            "PASS", "FAIL", "UNKNOWN", "BLOCKED",
        }


def test_openapi_is_deterministic_and_snapshotted(tmp_path: Path) -> None:
    """Canonicalized OpenAPI JSON is byte-stable across boots and matches
    the recorded snapshot hash (update the constant intentionally when the
    wire contract changes)."""
    with make_client(tmp_path) as client:
        first = _openapi(client)
    with make_client(tmp_path) as client:
        second = _openapi(client)
    canon_first = json.dumps(first, sort_keys=True, separators=(",", ":"))
    canon_second = json.dumps(second, sort_keys=True, separators=(",", ":"))
    assert canon_first == canon_second
    digest = hashlib.sha256(canon_first.encode("utf-8")).hexdigest()
    assert digest == OPENAPI_SNAPSHOT_SHA256, (
        f"OpenAPI snapshot changed: {digest}; update "
        "OPENAPI_SNAPSHOT_SHA256 in tests/test_pub01_openapi_snapshot.py "
        "intentionally (wire contract change) after review"
    )


# Recorded at the PUB-01 implementation head (canonicalized OpenAPI JSON).
OPENAPI_SNAPSHOT_SHA256 = "6469732c4b6488d08cc5cbebad31fa57b59aec7dd693b909ea147a56ec6c40ba"
