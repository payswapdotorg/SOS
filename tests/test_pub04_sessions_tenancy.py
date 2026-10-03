"""PUB-04 — sessions, tenancy and the Journey-2 acceptance flow in LOCAL
mode (fake-GitHub): login → workspace create (owner role) → tenant
isolation 403/404 with zero rows → protected mutations → logout with
server-side revocation. Plus session expiry and PUB-01 stub compatibility.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

fastapi = pytest.importorskip(
    "fastapi",
    reason=(
        "PUB-04 API tests require the 'api' dependency group "
        "(pyproject [project.optional-dependencies].api)"
    ),
)

REPO_ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(REPO_ROOT / "src"), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from services.api.testing import make_client  # noqa: E402


def _fake_login(client, login: str) -> None:
    """Drive the LOCAL fake-GitHub flow to a signed-in session."""
    start = client.get(
        "/api/v1/auth/github/start", follow_redirects=False
    )
    assert start.status_code == 302, start.text
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    consent = client.post(
        "/api/v1/auth/github/fake/consent",
        data={"state": state, "login": login},
        follow_redirects=False,
    )
    assert consent.status_code == 302, consent.text
    callback = client.get(consent.headers["location"], follow_redirects=False)
    assert callback.status_code == 302
    assert "status=ok" in callback.headers["location"]
    session = client.get("/api/v1/auth/session").json()
    assert session["authenticated"] is True, session


def _csrf_header(client) -> dict[str, str]:
    """The double-submit pair: the readable cookie + the echo header."""
    token = client.cookies.get("sos_csrf")
    assert token, "the sign-in callback must have issued the sos_csrf cookie"
    return {"x-sos-csrf": token}


# ---------------------------------------------------------------------------
# Journey-2: the PUB-04 acceptance flow, end to end in LOCAL mode
# ---------------------------------------------------------------------------


def test_journey2_login_workspace_isolation_logout(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        # -- login (new user via fake-GitHub) ------------------------------
        _fake_login(client, "octo-newcomer")
        account = client.get("/api/v1/auth/account").json()
        assert account["authenticated"] is True
        assert account["user"]["login"] == "octo-newcomer"
        assert account["workspaces"] == []  # a brand-new user owns nothing

        # -- workspace creation: the creator becomes the OWNER -------------
        created = client.post(
            "/api/v1/workspaces",
            json={"name": "Newco Lab", "slug": "newco-lab"},
        )
        assert created.status_code == 200, created.text
        assert created.json()["slug"] == "newco-lab"

        account = client.get("/api/v1/auth/account").json()
        by_id = {w["id"]: w for w in account["workspaces"]}
        assert "ws-newco-lab" in by_id
        assert by_id["ws-newco-lab"]["role"] == "owner"
        assert by_id["ws-newco-lab"]["isDemo"] is False

        # -- tenant-aware navigation: MY workspaces + the public demo ------
        listing = client.get("/api/v1/workspaces").json()["items"]
        slugs = {w["slug"] for w in listing}
        assert slugs == {"demo", "newco-lab"}
        # seeded private workspaces of OTHER users never surface
        assert "alice-lab" not in slugs
        assert "bob-lab" not in slugs

        # -- tenant isolation: cross-tenant reads 404 / zero rows ----------
        assert client.get("/api/v1/workspaces/ws-alice").status_code == 404
        evidence = client.get(
            "/api/v1/evidence?workspaceId=ws-alice"
        ).json()
        assert evidence["items"] == []
        assert client.get("/api/v1/jobs?workspaceId=ws-bob").json()["items"] == []

        # -- cross-tenant mutations 404 BEFORE any write -------------------
        stolen = client.post(
            "/api/v1/missions",
            json={
                "workspaceId": "ws-bob", "title": "steal", "goals": ["g"],
                "outcomes": ["o"], "stakeholders": ["s"], "measures": ["m"],
                "constraints": ["c"],
            },
        )
        assert stolen.status_code == 404
        # the demo workspace is readable but NOT mutable by non-members
        demo_mutation = client.post(
            "/api/v1/missions",
            json={
                "workspaceId": "ws-demo", "title": "demo write", "goals": ["g"],
                "outcomes": ["o"], "stakeholders": ["s"], "measures": ["m"],
                "constraints": ["c"],
            },
        )
        assert demo_mutation.status_code == 404

        # -- mutations in MY workspace succeed (and are audited) ----------
        mission = client.post(
            "/api/v1/missions",
            json={
                "workspaceId": "ws-newco-lab", "title": "First mission",
                "goals": ["g"], "outcomes": ["o"], "stakeholders": ["s"],
                "measures": ["m"], "constraints": ["c"],
            },
        )
        assert mission.status_code == 200, mission.text
        detail = client.get("/api/v1/workspaces/ws-newco-lab").json()
        actions = [e["action"] for e in detail["recentActivity"]]
        assert "workspace.created" in actions
        assert "mission.created" in actions

        # -- logout: CSRF-protected, server-side revocation ----------------
        old_session_cookie = client.cookies.get("sos_session")
        without_csrf = client.post("/api/v1/auth/logout")
        assert without_csrf.status_code == 403
        assert without_csrf.json()["error"]["code"] == "FORBIDDEN"

        with_csrf = client.post(
            "/api/v1/auth/logout", headers=_csrf_header(client)
        )
        assert with_csrf.status_code == 200

        # the OLD bearer token is dead even when replayed (server-side
        # revocation — the cookie deletion alone is not the boundary)
        client.cookies.set("sos_session", old_session_cookie)
        replayed = client.get("/api/v1/auth/session").json()
        assert replayed["authenticated"] is False
        assert replayed["provider"] == "none"

        # post-logout: mutations fail closed (401) and reads are demo-only
        assert client.post(
            "/api/v1/workspaces", json={"name": "X", "slug": "x-lab"}
        ).status_code == 401
        slugs = {
            w["slug"] for w in client.get("/api/v1/workspaces").json()["items"]
        }
        assert slugs == {"demo"}


def test_account_anonymous_shape_and_stub_sessions(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        anonymous = client.get("/api/v1/auth/account").json()
        assert anonymous == {
            "authenticated": False, "user": None, "stub": False,
            "provider": "none", "workspaces": [],
        }
        # PUB-01 stub sessions keep working (frozen behavior)
        assert client.post(
            "/api/v1/auth/login", json={"login": "demo-owner"}
        ).status_code == 200
        session = client.get("/api/v1/auth/session").json()
        assert session["stub"] is True
        assert session["provider"] == "local-stub"
        account = client.get("/api/v1/auth/account").json()
        roles = {w["id"]: w["role"] for w in account["workspaces"]}
        assert roles.get("ws-demo") == "owner"
        # stub mutations stay exempt from the CSRF pair (LOCAL test facility)
        assert client.post(
            "/api/v1/workspaces", json={"name": "S", "slug": "stub-ws"}
        ).status_code == 200
        assert client.post("/api/v1/auth/logout").status_code == 200
        assert client.get("/api/v1/auth/session").json()["authenticated"] is False


# ---------------------------------------------------------------------------
# Session lifecycle details
# ---------------------------------------------------------------------------


def test_session_expiry_fails_closed(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        _fake_login(client, "bob")
        conn = sqlite3.connect(str(tmp_path / "api.sqlite3"))
        conn.execute(
            "UPDATE auth_sessions SET expires_at = '2000-01-01T00:00:00Z'"
        )
        conn.commit()
        conn.close()
        session = client.get("/api/v1/auth/session").json()
        assert session["authenticated"] is False  # expired → anonymous


def test_unknown_session_token_form_is_anonymous(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        client.cookies.set("sos_session", "sos1.not-a-real-token")
        assert client.get(
            "/api/v1/auth/session"
        ).json()["authenticated"] is False
        client.cookies.set("sos_session", "garbage")
        assert client.get(
            "/api/v1/auth/session"
        ).json()["authenticated"] is False


def test_csrf_pair_required_on_real_session_logout_only(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path) as client:
        _fake_login(client, "alice")
        # missing header → 403 (S6: mutation without token)
        assert client.post("/api/v1/auth/logout").status_code == 403
        # wrong header value → 403
        wrong = client.post(
            "/api/v1/auth/logout", headers={"x-sos-csrf": "forged"}
        )
        assert wrong.status_code == 403
        assert wrong.json()["error"]["code"] == "FORBIDDEN"
        # correct pair → 200 (asserted fully in the journey test)


def test_workspace_slug_conflict_is_conflict_envelope(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        _fake_login(client, "alice")
        response = client.post(
            "/api/v1/workspaces", json={"name": "Alice Lab", "slug": "demo"}
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CONFLICT"
