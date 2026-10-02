"""PUB-01 — route-level API tests: the full ``/api/v1`` surface round-trips
on LOCAL adapters with the contract §C.2/§C.3 envelope shapes (hermetic:
tmp dirs, no network, no env; requires the ``api`` dependency group — skips
cleanly when absent so the frozen dependency-free CI suite stays green)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

fastapi = pytest.importorskip(
    "fastapi",
    reason=(
        "PUB-01 API tests require the 'api' dependency group "
        "(pyproject [project.optional-dependencies].api); the frozen 'tests' "
        "CI workflow runs the dependency-free baseline suite only"
    ),
)

REPO_ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(REPO_ROOT / "src"), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from services.api.testing import login, make_client  # noqa: E402

DEMO_WS = "ws-demo"


def test_health_ok_all_local_adapters(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert set(body["checks"]) == {
            "persistence", "coordination", "artifacts", "execution",
        }
        for check in body["checks"].values():
            assert check["status"] == "SUCCESS"


def test_collection_envelope_shape(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        for path in (
            "/api/v1/workspaces", "/api/v1/evidence", "/api/v1/hypotheses",
            "/api/v1/candidates", "/api/v1/assurance", "/api/v1/decisions",
            "/api/v1/authorizations", "/api/v1/experiments",
            "/api/v1/executions", "/api/v1/learning", "/api/v1/memory",
            "/api/v1/jobs", "/api/v1/providers/status",
            "/api/v1/missions", "/api/v1/systems",
        ):
            response = client.get(path)
            assert response.status_code == 200, (path, response.text)
            body = response.json()
            assert set(body) == {"items", "nextCursor"}, path
            assert isinstance(body["items"], list)


def test_full_surface_round_trip(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        # workspaces
        response = client.get("/api/v1/workspaces")
        slugs = {w["slug"] for w in response.json()["items"]}
        assert "demo" in slugs
        # workspace detail with activity trail
        response = client.get(f"/api/v1/workspaces/{DEMO_WS}")
        assert response.status_code == 200
        detail = response.json()
        assert detail["slug"] == "demo"
        assert detail["isDemo"] is True
        assert isinstance(detail["recentActivity"], list)
        assert detail["recentActivity"], "seeded activity trail present"
        # missions + revisions
        response = client.get(f"/api/v1/missions?workspaceId={DEMO_WS}")
        missions = response.json()["items"]
        assert missions and missions[0]["currentRevisionId"]
        mission_id = missions[0]["id"]
        response = client.get(f"/api/v1/missions/{mission_id}")
        mission = response.json()
        assert mission["currentRevision"]["approval"]["state"] == "approved"
        response = client.get(f"/api/v1/missions/{mission_id}/revisions")
        revisions = response.json()["items"]
        assert len(revisions) >= 2
        for field in (
            "goals", "outcomes", "stakeholders", "measures", "constraints",
            "preferences", "approval",
        ):
            assert field in revisions[0], field
        # systems with graph
        response = client.get(f"/api/v1/systems?workspaceId={DEMO_WS}")
        systems = response.json()["items"]
        assert systems and systems[0]["mode"] == "brownfield"
        system = systems[0]
        revision = system["currentRevision"]
        assert revision["sourceRef"]["immutable"] is True
        assert len(revision["sourceRef"]["revision"]) == 40
        assert revision["graph"]["nodes"] and revision["graph"]["edges"]
        # evidence across kinds/statuses
        response = client.get(f"/api/v1/evidence?workspaceId={DEMO_WS}")
        evidence = response.json()["items"]
        kinds = {e["kind"] for e in evidence}
        assert kinds == {
            "source_revision", "runtime_observation", "test_result",
            "telemetry", "environment", "experiment", "business_outcome",
        }
        # hypotheses
        response = client.get("/api/v1/hypotheses")
        assert response.json()["items"]
        # candidates: multi-objective evaluation, no scalar score
        response = client.get("/api/v1/candidates")
        candidates = response.json()["items"]
        assert len(candidates) >= 2
        evaluation = candidates[0]["evaluation"]
        assert len(evaluation["objectives"]) >= 3
        assert evaluation["paretoFront"]
        assert "score" not in candidates[0]
        # assurance
        response = client.get("/api/v1/assurance")
        assurance = response.json()["items"]
        verdicts = {a["verdict"] for a in assurance}
        assert verdicts == {"PASS", "UNKNOWN"}
        assert all(a["checks"] for a in assurance)
        # decisions: ACT + ASK with full panel
        response = client.get("/api/v1/decisions")
        decisions = response.json()["items"]
        actions = {d["action"] for d in decisions}
        assert actions == {"ACT", "ASK"}
        ask = next(d for d in decisions if d["action"] == "ASK")
        assert ask["askPayload"]["decision"]
        assert ask["requiredApprovals"]
        act = next(d for d in decisions if d["action"] == "ACT")
        for field in (
            "rationale", "evidenceRefs", "authoritySnapshot",
            "expectedImpact", "risk", "blastRadius", "reversibility",
        ):
            assert field in act, field
        # authorizations
        response = client.get("/api/v1/authorizations")
        authorizations = response.json()["items"]
        assert {a["decision"] for a in authorizations} == {"granted", "denied"}
        # experiments + events
        response = client.get("/api/v1/experiments")
        experiments = response.json()["items"]
        assert experiments and experiments[0]["status"] == "completed"
        assert experiments[0]["events"]
        experiment_id = experiments[0]["id"]
        response = client.get(f"/api/v1/experiments/{experiment_id}")
        assert response.json()["id"] == experiment_id
        # executions with receipts
        response = client.get("/api/v1/executions")
        executions = response.json()["items"]
        assert executions and executions[0]["provider"] == "demo"
        assert executions[0]["receipt"]["demo"] is True
        execution_id = executions[0]["id"]
        response = client.get(f"/api/v1/executions/{execution_id}")
        assert response.json()["id"] == execution_id
        # learning + memory
        response = client.get("/api/v1/learning")
        learning = response.json()["items"]
        assert learning and learning[0]["lessons"]
        response = client.get("/api/v1/memory")
        assert response.json()["items"]
        # jobs with directive §8 fields
        response = client.get("/api/v1/jobs")
        jobs = response.json()["items"]
        assert jobs
        for field in (
            "tenantId", "type", "requestedBy", "authoritySnapshot",
            "inputHash", "sourceRevision", "provider", "status", "receipt",
            "artifactRefs", "errorState",
        ):
            assert field in jobs[0], field
        # providers status
        response = client.get("/api/v1/providers/status")
        names = {p["name"] for p in response.json()["items"]}
        assert names == {
            "persistence", "coordination", "artifacts", "execution", "github",
        }
        response = client.get("/api/v1/providers/status/execution")
        assert response.status_code == 200
        assert response.json()["demo"] is True
        # me + auth session
        response = client.get("/api/v1/me")
        assert response.json()["authenticated"] is True
        response = client.get("/api/v1/auth/session")
        assert response.json()["stub"] is True


def test_cursor_pagination(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        first = client.get("/api/v1/evidence?limit=3").json()
        assert len(first["items"]) == 3
        assert first["nextCursor"]
        second = client.get(
            f"/api/v1/evidence?limit=3&cursor={first['nextCursor']}"
        ).json()
        ids_first = {e["id"] for e in first["items"]}
        ids_second = {e["id"] for e in second["items"]}
        assert not (ids_first & ids_second)
        invalid = client.get("/api/v1/evidence?cursor=not-a-cursor")
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "VALIDATION"


def test_error_envelope_on_unknown_routes_and_404(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/api/v1/workspaces/does-not-exist")
        assert response.status_code == 404
        body = response.json()
        assert body["error"]["code"] == "NOT_FOUND"
        assert body["error"]["message"]
        response = client.get("/api/v1/providers/status/nope")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


def test_mutation_flows(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        # workspace create → conflict on duplicate slug
        response = client.post(
            "/api/v1/workspaces", json={"name": "Lab", "slug": "worker-lab"}
        )
        assert response.status_code == 200
        assert response.json()["slug"] == "worker-lab"
        response = client.post(
            "/api/v1/workspaces", json={"name": "Lab", "slug": "worker-lab"}
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CONFLICT"
        # mission create + revision propose
        response = client.post(
            "/api/v1/missions",
            json={
                "workspaceId": DEMO_WS, "title": "Improve reliability",
                "goals": ["g"], "outcomes": ["o"], "stakeholders": ["s"],
                "measures": ["m"], "constraints": ["c"], "preferences": [],
            },
        )
        assert response.status_code == 200
        mission_id = response.json()["id"]
        assert response.json()["currentRevision"]["approval"]["state"] == "pending"
        response = client.post(
            f"/api/v1/missions/{mission_id}/revisions",
            json={
                "goals": ["g", "g2"], "outcomes": ["o"], "stakeholders": ["s"],
                "measures": ["m"], "constraints": ["c"], "preferences": [],
            },
        )
        assert response.status_code == 200
        assert response.json()["revision"] == 2
        # greenfield + brownfield onboarding
        response = client.post(
            "/api/v1/systems",
            json={
                "workspaceId": DEMO_WS, "name": "Green App",
                "mode": "greenfield",
            },
        )
        assert response.status_code == 200
        assert response.json()["mode"] == "greenfield"
        response = client.post(
            "/api/v1/systems",
            json={
                "workspaceId": DEMO_WS, "name": "Another API",
                "mode": "brownfield",
                "repositoryUrl": "https://github.com/sos-demo/example-api",
                "ref": "staging",
            },
        )
        assert response.status_code == 200
        system = response.json()
        assert system["mode"] == "brownfield"
        assert system["currentRevision"]["sourceRef"]["fixture"] is True
        assert len(system["currentRevision"]["sourceRef"]["revision"]) == 40
        # experiment creation
        response = client.post(
            "/api/v1/experiments",
            json={
                "workspaceId": DEMO_WS,
                "candidateId": "cand-demo-cache",
                "assuranceId": _assurance_id_for(client, "cand-demo-cache"),
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "planned"


def _assurance_id_for(client, candidate_id: str) -> str:
    response = client.get(f"/api/v1/assurance?candidateId={candidate_id}")
    items = response.json()["items"]
    assert items
    return items[0]["id"]
