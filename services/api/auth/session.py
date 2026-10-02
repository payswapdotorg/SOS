"""Session identity (PUB-01: LOCAL deterministic stub; real GitHub OAuth is
PUB-04 — deliberately NOT built here).

Rules:
- LOCAL mode exposes deterministic test identities (``demo-owner``, ``alice``,
  ``bob``) through clearly-labeled STUB sessions. The stub is NEVER enabled
  for ``SOS_ENV=public`` (SECURITY auth notes).
- Anonymous requests carry no session: read-only demo access (the tenant
  resolution layer enforces the boundary).
- Session tokens are deterministic functions of the user id (LOCAL only);
  real signed sessions arrive with PUB-04.
"""
from __future__ import annotations

from typing import Any

from fastapi import Request

SESSION_COOKIE = "sos_session"
SESSION_HEADER = "x-sos-session"
STUB_PROVIDER = "local-stub"


class SessionIdentity:
    """The resolved server-side identity (NEVER browser-supplied tenant ids)."""

    def __init__(
        self,
        *,
        user: dict[str, Any] | None,
        stub: bool,
        provider: str,
        token: str | None,
    ) -> None:
        self.user = user
        self.stub = stub
        self.provider = provider
        self.token = token

    @property
    def authenticated(self) -> bool:
        return self.user is not None

    @property
    def user_id(self) -> str | None:
        return str(self.user["id"]) if self.user else None

    @property
    def display(self) -> str:
        if self.user is None:
            return "anonymous"
        return f"{self.user['login']}({self.user['id']})"


def _token_for(user_id: str) -> str:
    """Deterministic LOCAL stub session token (no crypto — LOCAL only)."""
    return f"stub-session:{user_id}"


def resolve_session(request: Request, persistence: Any) -> SessionIdentity:
    """Resolve the session from the request cookie/header (server-side)."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        token = request.headers.get(SESSION_HEADER)
    if not token:
        return SessionIdentity(user=None, stub=False, provider="none", token=None)
    if not token.startswith("stub-session:"):
        # Unknown token form: treat as anonymous (fail-closed, no error leak).
        return SessionIdentity(user=None, stub=False, provider="none", token=None)
    user_id = token[len("stub-session:"):]
    user = persistence.get_user(user_id) if persistence is not None else None
    if user is None:
        return SessionIdentity(user=None, stub=False, provider="none", token=None)
    return SessionIdentity(
        user=user, stub=True, provider=STUB_PROVIDER, token=token
    )


def login_local_stub(
    persistence: Any, *, login: str, created_at: str
) -> tuple[dict[str, Any], str]:
    """Log in a deterministic LOCAL test identity; returns (user, token).

    Only the seeded fixture identities are accepted. Raises KeyError for
    unknown logins (the route maps that to VALIDATION).
    """
    user_id = _KNOWN_IDENTITIES.get(login)
    if user_id is None:
        raise KeyError(login)
    user = persistence.get_user(user_id)
    if user is None:
        raise KeyError(login)
    return user, _token_for(user_id)


_KNOWN_IDENTITIES = {
    "demo-owner": "user-demo-owner",
    "alice": "user-alice",
    "bob": "user-bob",
}
