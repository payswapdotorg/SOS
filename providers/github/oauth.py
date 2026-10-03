"""The GitHub OAuth identity provider seam (PUB-04).

Two implementations behind one provider-neutral interface:

- :class:`FakeGitHubOAuth` — the **deterministic LOCAL test provider**
  (``mode = "local"``). It simulates the GitHub web-flow end-to-end with
  canned fixture identities so the full authentication journey runs with
  zero secrets and zero network. Every surface it serves is clearly labeled
  ``FAKE GITHUB — LOCAL TEST MODE``; it is refused whenever
  ``SOS_ENV != local`` (SECURITY threat notes: the fake provider is never
  enabled for public deployments).
- :class:`LiveGitHubOAuth` — the real GitHub web application flow
  (authorization-code + PKCE S256, scope ``read:user``). Server-side only;
  exchange/user calls run through httpx with short timeouts. The access
  token is used once to fetch the identity and is never persisted and never
  reaches the browser (directive §6; SECURITY S1).

The seam is identity-only: it maps a GitHub identity to an SOS user via the
persistence seam's ``upsert_user``. It carries NO tenant semantics —
workspace/tenant context always derives from the server-side session
(directive §6: the browser never supplies the tenant identifier).

PKCE (RFC 7636): the code_verifier is generated and held SERVER-side in the
``oauth_states`` table; only the S256 code_challenge travels in the
authorization URL. The token exchange presents the verifier.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
REQUESTED_SCOPE = "read:user"

# The fake provider's consent surface lives under the API's own /api/v1/auth
# prefix (relative URLs so the browser resolves them against the request
# origin — the same-origin proxy topology keeps the whole flow on one origin).
FAKE_AUTHORIZE_PATH = "/api/v1/auth/github/fake/authorize"
FAKE_CONSENT_PATH = "/api/v1/auth/github/fake/consent"

# Deterministic fixture identities (LOCAL only). github_id values 900001-3
# intentionally collide with the seeded demo identities (db/seeds/demo_seed)
# so the fake provider maps onto the SAME accounts deterministically; 910001
# is the Journey-2 "new user" (auto-provisioned on first sign-in).
FAKE_IDENTITIES: tuple[dict[str, str], ...] = (
    {"login": "demo-owner", "github_id": "900001",
     "display_name": "Demo Owner (fake GitHub fixture)"},
    {"login": "alice", "github_id": "900002",
     "display_name": "Alice (fake GitHub fixture)"},
    {"login": "bob", "github_id": "900003",
     "display_name": "Bob (fake GitHub fixture)"},
    {"login": "octo-newcomer", "github_id": "910001",
     "display_name": "Octo Newcomer (fake GitHub fixture)"},
)


class OAuthFlowError(Exception):
    """A truthful OAuth flow failure (state/PKCE/exchange). Never a fake
    success: the caller reports an honest error state to the user."""


class GitHubIdentityError(OAuthFlowError):
    """The provider could not resolve an identity from the issued token."""


@dataclass(frozen=True)
class GitHubIdentity:
    """The GitHub identity the provider resolved (pre-user-upsert)."""

    github_id: str
    login: str
    display_name: str
    fixture: bool  # True = fake-provider fixture identity (clearly labeled)


def new_state() -> str:
    """The OAuth `state` parameter: 24 random bytes, url-safe (CSRF token
    for the authorization request — SECURITY S6 for the auth flow)."""
    return secrets.token_urlsafe(24)


def new_code_verifier() -> str:
    """A RFC 7636 code_verifier (43-128 chars, unreserved)."""
    return secrets.token_urlsafe(48)  # 64 chars, entropy 384 bits


def code_challenge_s256(verifier: str) -> str:
    """The S256 code_challenge for a verifier (RFC 7636 §4.2)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def is_s256_challenge(candidate: str) -> bool:
    """True when the string is shaped like an S256 challenge (43 chars,
    url-safe base64 — the sha256 of a 32-byte verifier)."""
    if len(candidate) != 43:
        return False
    return all(c.isalnum() or c in "-_=" for c in candidate)


class GitHubOAuthPort:
    """The provider-neutral OAuth identity interface (implemented by the
    fake LOCAL provider and the live GitHub client; duck-typed like the
    other provider seams)."""

    mode: str
    implementation: str

    def authorize_url(
        self, *, state: str, code_challenge: str, redirect_uri: str
    ) -> str: ...

    def exchange_code(
        self, *, code: str, code_verifier: str, redirect_uri: str
    ) -> str: ...

    def identity_for(self, access_token: str) -> GitHubIdentity: ...


class FakeGitHubOAuth(GitHubOAuthPort):
    """The deterministic fake-GitHub provider (LOCAL ONLY, clearly labeled).

    Determinism contract (testable without secrets):

    - ``authorize_url`` → the relative fake consent surface
      ``/api/v1/auth/github/fake/authorize?state=…&code_challenge=…``
      (browser-resolvable against the request origin);
    - the consent step (routes layer) redirects to the callback with the
      deterministic code ``fake:<state>:<login>``;
    - ``exchange_code`` validates the code format and binds it to the
      SINGLE-USE state row the caller resolved (the route passes the row's
      verifier — the PKCE machinery stays on the same path as the live
      flow) and returns the deterministic token ``fake-token:<login>``;
    - ``identity_for`` maps the token back to the fixture identity.
    """

    mode = "local"
    implementation = "fake-github-oauth"

    def authorize_url(
        self, *, state: str, code_challenge: str, redirect_uri: str
    ) -> str:
        # redirect_uri is unused by the fake provider (the consent surface
        # posts back to the API itself); it stays in the signature so both
        # implementations share one code path at the route layer.
        del redirect_uri
        return (
            f"{FAKE_AUTHORIZE_PATH}?state={state}"
            f"&code_challenge={code_challenge}&code_challenge_method=S256"
        )

    def exchange_code(
        self, *, code: str, code_verifier: str, redirect_uri: str
    ) -> str:
        del redirect_uri
        if not code_verifier:
            raise OAuthFlowError("PKCE code_verifier missing for fake exchange")
        parts = code.split(":", 2)
        if len(parts) != 3 or parts[0] != "fake" or not parts[1] or not parts[2]:
            raise OAuthFlowError(f"malformed fake authorization code {code!r}")
        login = parts[2]
        if login not in {i["login"] for i in FAKE_IDENTITIES}:
            raise OAuthFlowError(
                f"fake authorization code names unknown identity {login!r}"
            )
        return f"fake-token:{login}"

    def identity_for(self, access_token: str) -> GitHubIdentity:
        if not access_token.startswith("fake-token:"):
            raise GitHubIdentityError(
                "not a fake-provider token (the fake provider never sees "
                "real GitHub tokens)"
            )
        login = access_token[len("fake-token:"):]
        for identity in FAKE_IDENTITIES:
            if identity["login"] == login:
                return GitHubIdentity(
                    github_id=identity["github_id"],
                    login=identity["login"],
                    display_name=identity["display_name"],
                    fixture=True,
                )
        raise GitHubIdentityError(f"unknown fake identity {login!r}")

    @staticmethod
    def code_for(state: str, login: str) -> str:
        """The deterministic authorization code the consent step issues."""
        if ":" in state or ":" in login:
            raise OAuthFlowError("state/login must not contain ':'")
        return f"fake:{state}:{login}"

    @staticmethod
    def parse_code(code: str) -> tuple[str, str]:
        """Split a fake code into (state, login); raises OAuthFlowError."""
        parts = code.split(":", 2)
        if len(parts) != 3 or parts[0] != "fake":
            raise OAuthFlowError(f"malformed fake authorization code {code!r}")
        return parts[1], parts[2]


class LiveGitHubOAuth(GitHubOAuthPort):
    """The real GitHub OAuth web-application flow (authorization code +
    PKCE S256, scope ``read:user``). Server-side only; no network calls run
    in the default test suite (this class is constructed only for
    ``SOS_ENV`` preview/public with credentials configured)."""

    mode = "public"
    implementation = "github-live-oauth"

    def __init__(self, *, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout = 10.0

    def authorize_url(
        self, *, state: str, code_challenge: str, redirect_uri: str
    ) -> str:
        from urllib.parse import urlencode

        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "scope": REQUESTED_SCOPE,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_code(
        self, *, code: str, code_verifier: str, redirect_uri: str
    ) -> str:
        import httpx

        try:
            response = httpx.post(
                GITHUB_TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "code": code,
                    "code_verifier": code_verifier,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise OAuthFlowError(f"github.com token endpoint unreachable: {exc}") from exc
        if response.status_code != 200:
            raise OAuthFlowError(
                f"github.com token endpoint returned HTTP {response.status_code}"
            )
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            # GitHub reports {error, error_description} on failure — the
            # honest error state, never a fake success.
            raise OAuthFlowError(
                "github.com token exchange refused: "
                + str(payload.get("error_description") or payload.get("error") or "unknown error")
            )
        return str(token)

    def identity_for(self, access_token: str) -> GitHubIdentity:
        import httpx

        try:
            response = httpx.get(
                GITHUB_USER_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise GitHubIdentityError(f"github.com user endpoint unreachable: {exc}") from exc
        if response.status_code != 200:
            raise GitHubIdentityError(
                f"github.com user endpoint returned HTTP {response.status_code}"
            )
        payload = response.json()
        github_id = payload.get("id")
        login = payload.get("login")
        if github_id is None or login is None:
            raise GitHubIdentityError("github.com user payload missing id/login")
        display = str(payload.get("name") or login)
        return GitHubIdentity(
            github_id=str(github_id),
            login=str(login),
            display_name=display,
            fixture=False,
        )


def build_github_oauth(settings) -> GitHubOAuthPort:
    """Fail-closed provider selection.

    ``SOS_ENV=local`` → the deterministic fake provider (clearly labeled,
    zero secrets, zero network). ``preview``/``public`` → the live GitHub
    client, which REQUIRES ``SOS_GITHUB_CLIENT_ID`` and
    ``SOS_GITHUB_CLIENT_SECRET`` — a public deployment without credentials
    fails closed with a precise error, never a silent fallback to the fake.
    """
    env = getattr(settings, "env", "local")
    if env == "local":
        return FakeGitHubOAuth()
    client_id = getattr(settings, "github_client_id", None)
    client_secret = getattr(settings, "github_client_secret", None)
    if not client_id or not client_secret:
        raise OAuthFlowError(
            f"SOS_ENV={env} requires SOS_GITHUB_CLIENT_ID and "
            "SOS_GITHUB_CLIENT_SECRET for real GitHub OAuth (fail-closed: "
            "the LOCAL fake provider is never enabled outside SOS_ENV=local)"
        )
    return LiveGitHubOAuth(
        client_id=str(client_id), client_secret=str(client_secret)
    )


def constant_time_equals(left: str, right: str) -> bool:
    """Constant-time string comparison (state/CSRF checks)."""
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
