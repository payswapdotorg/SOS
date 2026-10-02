"""PUB-01 — auth/tenant boundary tests (SECURITY S5/S7/S21): anonymous
read-demo-only, cross-tenant 403/404 with zero rows leaked, mutation audit
events recorded. Hermetic (LOCAL adapters on tmp dirs)."""
from __future__ import annotations

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

from fastapi.testclient import TestClient  # noqa: E402

from services.api.testing import login, make_client  # noqa: E402

MUTATION_PROBES = (
    ("POST", "/api/v1/workspaces",
     {"name": "Evil", "slug": "evil-ws"}),
    ("POST", "/api/v1/missions",
     {"workspaceId": "ws-demo", "title": "x", "goals": ["g"],
      "outcomes": ["o"], "stakeholders": ["s"], "measures": ["m"],
      "constraints": ["c"]}),
    ("POST", "/api/v1/systems",
     {"workspaceId": "ws-demo", "name": "x", "mode": "greenfield"}),
    ("POST", "/api/v1/experiments",
     {"workspaceId": "ws-demo", "candidateId": "cand-demo-cache",
      "assuranceId": "assurance-x"}),
    ("POST", "/api/v1/executions", {"experimentId": "exp-demo-cache"}),
    ("POST", "/api/v1/jobs",
     {"workspaceId": "ws-demo", "type": "system_recovery",
      "repositoryUrl": "https://github.com/sos-demo/example-api"}),
)


def test_anonymous_reads_demo_only(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/api/v1/workspaces")
        slugs = {w["slug"] for w in response.json()["items"]}
        assert slugs == {"demo"}, "anonymous sees ONLY the demo workspace"
        # demo reads succeed anonymously
        assert client.get("/api/v1/evidence").status_code == 200
        assert client.get("/api/v1/systems").status_code == 200
        assert client.get("/api/v1/decisions").status_code == 200
        # authenticated workspaces are invisible to anonymous (zero rows)
        response = client.get("/api/v1/workspaces/ws-alice")
        assert response.status_code == 404
        response = client.get("/api/v1/workspaces/ws-bob")
        assert response.status_code == 404


def test_anonymous_mutations_rejected_401(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        for method, path, body in MUTATION_PROBES:
            response = client.request(method, path, json=body)
            assert response.status_code == 401, (path, response.text)
            assert response.json()["error"]["code"] == "UNAUTHENTICATED"
        # the demo workspace mutation surface is closed to anonymous (S21)
        response = client.post("/api/v1/auth/login", json={"login": "nope"})
        assert response.status_code == 422


def test_cross_tenant_isolation_404_zero_rows(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client, "alice")
        # alice cannot see bob's workspace or its resources (404, not 403:
        # existence is hidden; zero rows leaked from the adapter)
        response = client.get("/api/v1/workspaces/ws-bob")
        assert response.status_code == 404
        response = client.get("/api/v1/evidence?workspaceId=ws-bob")
        assert response.status_code == 200
        assert response.json()["items"] == []
        response = client.get("/api/v1/jobs?workspaceId=ws-bob")
        assert response.json()["items"] == []
        # bob's missions/systems never surface in alice's collections
        response = client.get("/api/v1/missions")
        workspaces = {m["workspaceId"] for m in response.json()["items"]}
        assert "ws-bob" not in workspaces
        # cross-tenant mutations 404 before any write
        response = client.post(
            "/api/v1/missions",
            json={
                "workspaceId": "ws-bob", "title": "steal", "goals": ["g"],
                "outcomes": ["o"], "stakeholders": ["s"], "measures": ["m"],
                "constraints": ["c"],
            },
        )
        assert response.status_code == 404
        response = client.post(
            "/api/v1/workspaces/ws-bob/recover",
            json={},
        )
        assert response.status_code in (404, 405)


def test_authenticated_scope_includes_demo_read(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client, "alice")
        response = client.get("/api/v1/workspaces")
        slugs = {w["slug"] for w in response.json()["items"]}
        assert slugs == {"demo", "alice-lab"}
        # alice reads the demo workspace detail (public demo read)
        assert client.get("/api/v1/workspaces/ws-demo").status_code == 200


def test_demo_workspace_mutation_is_owner_scoped(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client, "alice")
        # alice CAN create her own mission in her own workspace
        response = client.post(
            "/api/v1/missions",
            json={
                "workspaceId": "ws-alice", "title": "Alice mission",
                "goals": ["g"], "outcomes": ["o"], "stakeholders": ["s"],
                "measures": ["m"], "constraints": ["c"],
            },
        )
        assert response.status_code == 200
        # …and cannot dispatch a demo-workspace governed execution
        response = client.post(
            "/api/v1/executions", json={"experimentId": "exp-demo-cache"}
        )
        assert response.status_code == 404


def test_mutations_write_audit_events(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        client.post(
            "/api/v1/workspaces", json={"name": "Audited", "slug": "audited"}
        )
        response = client.get("/api/v1/workspaces/ws-audited")
        activity = response.json()["recentActivity"]
        assert activity, "mutation audit event recorded"
        event = activity[0]
        assert event["action"] == "workspace.created"
        assert event["actor"].startswith("demo-owner")
        assert event["target"] == "workspace/ws-audited"
        assert event["ts"]
        # a second mutation appends (audit trail is append-only)
        client.post(
            "/api/v1/missions",
            json={
                "workspaceId": "ws-audited", "title": "Mission",
                "goals": ["g"], "outcomes": ["o"], "stakeholders": ["s"],
                "measures": ["m"], "constraints": ["c"],
            },
        )
        response = client.get("/api/v1/workspaces/ws-audited")
        actions = [e["action"] for e in response.json()["recentActivity"]]
        assert actions.count("mission.created") == 1
        assert "workspace.created" in actions


def test_session_stub_is_local_only(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        response = client.get("/api/v1/auth/session")
        body = response.json()
        assert body["stub"] is True
        assert body["provider"] == "local-stub"
        # logout clears the session
        assert client.post("/api/v1/auth/logout").status_code == 200
        response = client.get("/api/v1/me")
        assert response.json()["authenticated"] is False
