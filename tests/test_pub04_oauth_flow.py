"""PUB-04 — the GitHub OAuth web flow (LOCAL fake provider + live-flow
shape), state/PKCE validation, cookie flags, rate limits, audit events.

Hermetic: LOCAL adapters on tmp dirs; the live github.com endpoints are
NEVER contacted (public-mode tests stop at the authorize redirect).
"""
from __future__ import annotations

import base64
import hashlib
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
from providers.github.oauth import (  # noqa: E402
    FakeGitHubOAuth,
    LiveGitHubOAuth,
    OAuthFlowError,
    build_github_oauth,
    code_challenge_s256,
    is_s256_challenge,
    new_code_verifier,
)

PUBLIC_SETTINGS = {
    "env": "public",
    "session_secret": "x" * 48,
    "github_client_id": "test-client-id",
    "github_client_secret": "test-client-secret",
}


def _start(client, next_path: str = "/workspace"):
    response = client.get(
        f"/api/v1/auth/github/start?next={next_path}",
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    return response.headers["location"]


def _complete_fake_flow(client, login: str, *, follow: bool = False):
    """Drive the full LOCAL flow: start → authorize page → consent →
    callback. Returns the final callback response (unfollowed redirect to
    the cockpit callback page + session cookies)."""
    authorize_url = _start(client)
    assert authorize_url.startswith(
        "/api/v1/auth/github/fake/authorize?state="
    ), authorize_url
    state = parse_qs(urlparse(authorize_url).query)["state"][0]

    page = client.get(authorize_url)
    assert page.status_code == 200
    assert "FAKE GITHUB" in page.text
    assert "NOT github.com" in page.text  # clearly labeled

    consent = client.post(
        "/api/v1/auth/github/fake/consent",
        data={"state": state, "login": login},
        follow_redirects=False,
    )
    assert consent.status_code == 302, consent.text
    assert consent.headers["location"].startswith(
        "/api/v1/auth/github/callback?code="
    )
    return client.get(consent.headers["location"], follow_redirects=follow)


# ---------------------------------------------------------------------------
# PKCE + provider selection units
# ---------------------------------------------------------------------------


def test_pkce_s256_derivation_matches_rfc7636() -> None:
    verifier = new_code_verifier()
    challenge = code_challenge_s256(verifier)
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")
    assert challenge == expected
    assert is_s256_challenge(challenge)
    assert not is_s256_challenge("short")


def test_provider_selection_fails_closed() -> None:
    class _Settings:
        env = "local"
        github_client_id = None
        github_client_secret = None

    assert isinstance(build_github_oauth(_Settings()), FakeGitHubOAuth)

    class _PublicNoCreds:
        env = "public"
        github_client_id = None
        github_client_secret = None

    with pytest.raises(OAuthFlowError, match="SOS_GITHUB_CLIENT_ID"):
        build_github_oauth(_PublicNoCreds())

    class _PublicWithCreds:
        env = "public"
        github_client_id = "cid"
        github_client_secret = "secret"

    live = build_github_oauth(_PublicWithCreds())
    assert isinstance(live, LiveGitHubOAuth)


def test_live_authorize_url_carries_pkce_and_scope() -> None:
    provider = LiveGitHubOAuth(client_id="cid", client_secret="secret")
    verifier = new_code_verifier()
    url = provider.authorize_url(
        state="st", code_challenge=code_challenge_s256(verifier),
        redirect_uri="https://sos.example.com/api/v1/auth/github/callback",
    )
    parsed = urlparse(url)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == (
        "https://github.com/login/oauth/authorize"
    )
    query = parse_qs(parsed.query)
    assert query["client_id"] == ["cid"]
    assert query["state"] == ["st"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["scope"] == ["read:user"]
    assert query["redirect_uri"] == [
        "https://sos.example.com/api/v1/auth/github/callback"
    ]
    assert is_s256_challenge(query["code_challenge"][0])


# ---------------------------------------------------------------------------
# The LOCAL fake flow end-to-end
# ---------------------------------------------------------------------------


def test_fake_flow_issues_flagged_session_cookies(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        callback = _complete_fake_flow(client, "octo-newcomer")
        assert callback.status_code == 302
        location = callback.headers["location"]
        assert location.startswith(
            "http://testserver/signin/callback?status=ok"
        ), location
        assert "next=%2Fworkspace" in location

        cookies = [c.lower() for c in callback.headers.get_list("set-cookie")]
        session_cookie = next(c for c in cookies if c.startswith("sos_session="))
        assert "sos_session=sos1." in session_cookie
        assert "httponly" in session_cookie  # no JS access to the bearer
        assert "samesite=lax" in session_cookie
        assert "secure" not in session_cookie  # LOCAL: http dev origins
        csrf_cookie = next(c for c in cookies if c.startswith("sos_csrf="))
        assert "httponly" not in csrf_cookie  # readable: double-submit echo

        session = client.get("/api/v1/auth/session").json()
        assert session["authenticated"] is True
        assert session["stub"] is False
        assert session["provider"] == "fake-github"  # honestly labeled
        assert session["user"]["login"] == "octo-newcomer"


def test_fake_flow_new_user_auto_provisioned_and_idempotent(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path) as client:
        _complete_fake_flow(client, "octo-newcomer", follow=False)
        user = client.get("/api/v1/auth/session").json()["user"]
        assert user["id"] == "user-octo-newcomer"
        assert user["githubId"] == "910001"
        # A second sign-in maps to the SAME account (deterministic upsert).
        client.post("/api/v1/auth/logout")
        _complete_fake_flow(client, "octo-newcomer", follow=False)
        again = client.get("/api/v1/auth/session").json()["user"]
        assert again["id"] == "user-octo-newcomer"


def test_fake_flow_seeded_identity_maps_to_existing_account(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path) as client:
        _complete_fake_flow(client, "alice", follow=False)
        session = client.get("/api/v1/auth/session").json()
        # github_id 900002 collides with the seeded alice → same account.
        assert session["user"]["id"] == "user-alice"
        account = client.get("/api/v1/auth/account").json()
        roles = {
            w["id"]: w["role"] for w in account["workspaces"]
        }
        assert roles.get("ws-alice") == "owner"


def test_fake_authorize_page_labels_and_state_gating(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path) as client:
        # unknown state → honest page, no identities offered
        page = client.get(
            "/api/v1/auth/github/fake/authorize?state=nope"
        )
        assert page.status_code == 200
        assert "expired or unknown state" in page.text
        assert "octo-newcomer" not in page.text
        # pending state → the consent page with the fixture identities
        authorize_url = _start(client)
        page = client.get(authorize_url)
        assert page.status_code == 200
        for login in ("demo-owner", "alice", "bob", "octo-newcomer"):
            assert f'value="{login}"' in page.text
        assert "PKCE S256" in page.text


def test_fake_flow_refused_outside_local(tmp_path: Path) -> None:
    with make_client(tmp_path, **PUBLIC_SETTINGS) as client:
        response = client.get("/api/v1/auth/github/fake/authorize?state=x")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"
        response = client.post(
            "/api/v1/auth/github/fake/consent",
            data={"state": "x", "login": "alice"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"


def test_public_mode_start_redirects_to_github_with_pkce(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path, **PUBLIC_SETTINGS) as client:
        location = _start(client)
        parsed = urlparse(location)
        assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == (
            "https://github.com/login/oauth/authorize"
        )
        query = parse_qs(parsed.query)
        assert query["client_id"] == ["test-client-id"]
        assert query["code_challenge_method"] == ["S256"]
        assert is_s256_challenge(query["code_challenge"][0])
        # redirect_uri derives from the (proxied) request origin
        assert query["redirect_uri"] == [
            "http://testserver/api/v1/auth/github/callback"
        ]


def test_public_mode_without_credentials_fails_closed(
    tmp_path: Path,
) -> None:
    settings = dict(PUBLIC_SETTINGS)
    settings.pop("github_client_id")
    settings.pop("github_client_secret")
    with make_client(tmp_path, **settings) as client:
        response = client.get(
            "/api/v1/auth/github/start", follow_redirects=False
        )
        assert response.status_code == 302
        assert "status=error" in response.headers["location"]
        assert "reason=provider_unconfigured" in response.headers["location"]


# ---------------------------------------------------------------------------
# State validation (CSRF for the flow) — single use, expiry, unknown, denial
# ---------------------------------------------------------------------------


def test_callback_unknown_state_rejected(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get(
            "/api/v1/auth/github/callback?code=fake:x:y&state=unknown",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "status=error" in response.headers["location"]
        assert "reason=invalid_state" in response.headers["location"]
        assert not response.headers.get_list("set-cookie")


def test_callback_state_single_use_replay_rejected(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        authorize_url = _start(client)
        state = parse_qs(urlparse(authorize_url).query)["state"][0]
        first = client.post(
            "/api/v1/auth/github/fake/consent",
            data={"state": state, "login": "bob"},
            follow_redirects=False,
        )
        callback_url = first.headers["location"]
        assert client.get(callback_url, follow_redirects=False).status_code == 302
        # replaying the same code+state must fail honestly
        replay = client.get(callback_url, follow_redirects=False)
        assert replay.status_code == 302
        assert "reason=replayed_state" in replay.headers["location"]


def test_callback_expired_state_rejected(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        authorize_url = _start(client)
        state = parse_qs(urlparse(authorize_url).query)["state"][0]
        # age the state row past its 10-minute TTL (direct DB, test-only)
        db_path = tmp_path / "api.sqlite3"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "UPDATE oauth_states SET expires_at = '2000-01-01T00:00:00Z' "
            "WHERE state = ?",
            (state,),
        )
        conn.commit()
        conn.close()
        code = FakeGitHubOAuth.code_for(state, "alice")
        response = client.get(
            f"/api/v1/auth/github/callback?code={code}&state={state}",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "reason=expired_state" in response.headers["location"]
        assert not response.headers.get_list("set-cookie")


def test_callback_github_denial_redirects_honestly(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get(
            "/api/v1/auth/github/callback?error=access_denied",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "status=error" in response.headers["location"]
        assert "reason=authorization_denied" in response.headers["location"]


def test_start_open_redirect_guard(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        for evil in ("https://evil.example.com", "//evil.example.com", "\\x"):
            response = client.get(
                f"/api/v1/auth/github/start?next={evil}",
                follow_redirects=False,
            )
            assert response.status_code in (302, 422)
            if response.status_code == 302:
                # a provider_unconfigured-style redirect must never embed
                # the attacker URL
                assert "evil" not in response.headers["location"]
        response = client.get(
            "/api/v1/auth/github/start?next=https://evil.example.com",
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION"


def test_fake_consent_validates_login_choice(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        authorize_url = _start(client)
        state = parse_qs(urlparse(authorize_url).query)["state"][0]
        response = client.post(
            "/api/v1/auth/github/fake/consent",
            data={"state": state, "login": "evil-attacker"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION"


# ---------------------------------------------------------------------------
# Rate limiting + audit
# ---------------------------------------------------------------------------


def test_auth_endpoints_rate_limited(tmp_path: Path) -> None:
    with make_client(tmp_path, rate_anon_per_min=4) as client:
        statuses = []
        for _ in range(8):
            response = client.get(
                "/api/v1/auth/github/start", follow_redirects=False
            )
            statuses.append(response.status_code)
        assert 429 in statuses
        limited = next(
            r for r in [client.get("/api/v1/auth/github/start")]
            if r.status_code == 429
        )
        assert limited.json()["error"]["code"] == "RATE_LIMITED"


def test_auth_flow_writes_audit_events(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        _complete_fake_flow(client, "alice", follow=False)
        conn = sqlite3.connect(str(tmp_path / "api.sqlite3"))
        rows = conn.execute(
            "SELECT action, actor, meta FROM audit_events "
            "WHERE action LIKE 'auth.%' ORDER BY ts"
        ).fetchall()
        conn.close()
        actions = [r[0] for r in rows]
        assert "auth.login" in actions
        login_row = next(r for r in rows if r[0] == "auth.login")
        assert "alice" in login_row[1]
        assert "fake-github" in login_row[2]
