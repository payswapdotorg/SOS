"""Auth package: session identity resolution (LOCAL stub; PUB-04 adds the
real GitHub OAuth flow)."""
from .session import (
    SESSION_COOKIE,
    STUB_PROVIDER,
    SessionIdentity,
    login_local_stub,
    resolve_session,
)

__all__ = [
    "SESSION_COOKIE",
    "STUB_PROVIDER",
    "SessionIdentity",
    "login_local_stub",
    "resolve_session",
]
