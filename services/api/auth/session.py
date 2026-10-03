"""Session identity (PUB-01 stub + PUB-04 real sessions).

Two session transports, one resolver:

- **Real sessions (PUB-04):** opaque versioned bearer tokens
  (``sos1.<urlsafe>``) issued by the GitHub OAuth callback, stored
  server-side as sha256 hashes in ``auth_sessions`` (migration 0004) and
  delivered ONLY as the ``sos_session`` httpOnly/SameSite=Lax cookie
  (Secure outside LOCAL). Logout revokes the row server-side. The browser
  NEVER holds an OAuth token and never supplies tenant identifiers — the
  tenant scope always derives from the resolved session (directive §6).
- **LOCAL stub sessions (PUB-01, unchanged):** deterministic
  ``stub-session:<user_id>`` tokens for the seeded fixture identities, so
  the frozen PUB-01 tests keep their exact behavior. The stub is a clearly
  labeled LOCAL test facility, refused outside ``SOS_ENV=local``.

``resolve_session(request, persistence)`` keeps the PUB-01 signature (its
callers in ``services/api/dependencies`` and the rate-limit middleware are
outside PUB-04's allowed surface); the auth store is resolved lazily from
``request.app.state`` and cached per app.
"""
from __future__ import annotations

from typing import Any

from fastapi import Request

from .store import SESSION_TOKEN_PREFIX, build_auth_store

SESSION_COOKIE = "sos_session"
SESSION_HEADER = "x-sos-session"
STUB_PROVIDER = "local-stub"

# The auth-store cache key on app.state (one store per app; the LOCAL
# store opens its own connection to the same migrated SQLite file).
_AUTH_STORE_ATTR = "sos_auth_store"


class SessionIdentity:
    """The resolved server-side identity (NEVER browser-supplied tenant ids)."""

    def __init__(
        self,
        *,
        user: dict[str, Any] | None,
        stub: bool,
        provider: str,
        token: str | None,
        session_id: str | None = None,
        csrf_token: str | None = None,
    ) -> None:
        self.user = user
        self.stub = stub
        self.provider = provider
        self.token = token
        # Real-session extras (None for anonymous/stub — PUB-01 compat).
        self.session_id = session_id
        self.csrf_token = csrf_token

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


def get_auth_store(request: Request, settings: Any) -> Any:
    """The per-app auth store (lazily built, cached on ``app.state``).

    LOCAL persistence → the SQLite store; non-LOCAL → the fail-closed
    refusal store (PUB-05 unifies the auth tables into the Neon seam).
    """
    state = getattr(request.app.state, _AUTH_STORE_ATTR, None)
    if state is None or state[0] is not settings:
        store = build_auth_store(settings)
        try:
            setattr(request.app.state, _AUTH_STORE_ATTR, (settings, store))
        except Exception:  # pragma: no cover - defensive: state not writable
            return store
        return store
    return state[1]


def resolve_session(request: Request, persistence: Any) -> SessionIdentity:
    """Resolve the session from the request cookie/header (server-side).

    Real tokens resolve through the auth store (fail-closed: revoked,
    expired, unknown or unvalidatable → anonymous — never a forged
    identity). Stub tokens keep the deterministic PUB-01 behavior.
    """
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        token = request.headers.get(SESSION_HEADER)
    if not token:
        return SessionIdentity(user=None, stub=False, provider="none", token=None)

    if token.startswith(SESSION_TOKEN_PREFIX):
        # A real (PUB-04) session token: cookie transport only in the
        # browser; the header fallback keeps test/tooling parity with the
        # PUB-01 resolution contract (the token itself is still verified
        # server-side against the auth store — it is a bearer credential).
        container = getattr(request.app.state, "container", None)
        settings = getattr(container, "settings", None) if container else None
        if settings is None:
            return SessionIdentity(
                user=None, stub=False, provider="none", token=None
            )
        store = get_auth_store(request, settings)
        record = store.resolve_session(token)
        if record is None:
            # Fail-closed: unknown/expired/revoked/unvalidatable → anonymous.
            return SessionIdentity(
                user=None, stub=False, provider="none", token=None
            )
        user = persistence.get_user(record.user_id) if persistence else None
        if user is None:
            return SessionIdentity(
                user=None, stub=False, provider="none", token=None
            )
        return SessionIdentity(
            user=user, stub=False, provider=record.provider, token=token,
            session_id=record.id, csrf_token=record.csrf_token,
        )

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


def session_cookie_params(env: str) -> dict[str, Any]:
    """The binding cookie flags for the session cookie (PUB-04):

    httpOnly ALWAYS (no JS access to the bearer token); SameSite=Lax (the
    OAuth callback is a top-level GET navigation — Lax carries it, and
    cross-site POST mutations never carry the cookie); Secure outside
    LOCAL (PUBLIC/preview run HTTPS-only).
    """
    return {
        "key": SESSION_COOKIE,
        "httponly": True,
        "samesite": "lax",
        "secure": env != "local",
    }


def _token_for(user_id: str) -> str:
    """Deterministic LOCAL stub session token (no crypto — LOCAL only)."""
    return f"stub-session:{user_id}"


_KNOWN_IDENTITIES = {
    "demo-owner": "user-demo-owner",
    "alice": "user-alice",
    "bob": "user-bob",
}
