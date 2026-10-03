"""The PUB-04 auth store: server-side sessions + OAuth flow states + a
membership-role read for the account surface.

Scope note (disclosed in the PUB-04 checkpoint): the persistence seam
(``providers/neon/**``) is PUB-05's lane, so this store owns ONLY the
auth-package tables (``auth_sessions``, ``oauth_states`` — created by
migration 0004) plus a READ-ONLY membership-role lookup (the
``workspace_members`` table from migration 0001; writes to memberships stay
in the persistence seam's ``create_workspace``). The LOCAL implementation
opens its own connection to the same migrated SQLite file (WAL +
busy_timeout make multi-connection access safe). Non-LOCAL persistence
modes fail closed until PUB-05 unifies the auth tables into the Neon seam:
passive session resolution degrades to anonymous (never a forged identity),
and the active auth routes report a precise PROVIDER_UNAVAILABLE.
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from providers.github.oauth import (  # noqa: E402  (repo-root import)
    new_code_verifier as new_verifier_token,
    new_state as new_state_token,
)

SESSION_TOKEN_PREFIX = "sos1."  # versioned opaque bearer tokens (cookie side)
SESSION_TTL_SECONDS = 7 * 24 * 3600  # 7 days, absolute (documented)
OAUTH_STATE_TTL_SECONDS = 600  # 10 minutes for the authorization round-trip


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _expires_in(seconds: int) -> str:
    return time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + seconds)
    )


def new_session_token() -> str:
    """A fresh opaque bearer token (the raw value lives ONLY in the cookie)."""
    return SESSION_TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """The stored form of a session token (sha256 hex) — a DB read never
    yields a usable bearer token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SessionRecord:
    """A resolved auth-session row (validity already checked)."""

    id: str
    user_id: str
    provider: str
    csrf_token: str
    created_at: str
    expires_at: str


@dataclass(frozen=True)
class OAuthStateRecord:
    """A pending (or just-consumed) authorization-flow state row."""

    state: str
    code_verifier: str
    created_at: str
    expires_at: str
    next_path: str | None


@dataclass(frozen=True)
class MembershipRecord:
    """One (user, workspace, role) membership row — the owner/member model
    (migration 0001 CHECK constraint) surfaced for the account navigation."""

    workspace_id: str
    name: str
    slug: str
    is_demo: bool
    created_at: str
    role: str  # 'owner' | 'member' (DB-enforced)


class AuthStore(Protocol):
    """The auth-package storage port (LOCAL SQLite now; PUB-05 unifies)."""

    def create_session(
        self, *, user_id: str, provider: str
    ) -> tuple[str, SessionRecord]:
        """Create a session; returns (raw_token, record)."""

    def resolve_session(self, raw_token: str) -> SessionRecord | None: ...

    def revoke_session(self, session_id: str) -> None: ...

    def create_oauth_state(self, *, next_path: str | None) -> OAuthStateRecord: ...

    def take_oauth_state(self, state: str) -> OAuthStateRecord:
        """Atomically consume a PENDING, UNEXPIRED state row (single use).

        Raises ``StateConsumedError`` / ``StateExpiredError`` /
        ``StateUnknownError`` — never returns a stale row twice."""

    def memberships_for_user(self, user_id: str) -> tuple[MembershipRecord, ...]: ...


class StateUnknownError(Exception):
    """The state parameter is not present in the pending set (CSRF failure)."""


class StateConsumedError(Exception):
    """The state row was already used (replay — rejected)."""


class StateExpiredError(Exception):
    """The state row expired before the callback arrived."""


class LocalSqliteAuthStore:
    """The LOCAL implementation (same migrated SQLite file, own connection).

    Auth-package tables only (auth_sessions, oauth_states) + the read-only
    membership lookup; all other reads/writes belong to the persistence
    seam. Tenant isolation of the membership read is by user_id (the
    membership IS the tenant boundary for a user), mirroring the seam's
    ``workspaces_for_user``.
    """

    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self._db_path), check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- sessions -----------------------------------------------------------

    def create_session(
        self, *, user_id: str, provider: str
    ) -> tuple[str, SessionRecord]:
        raw_token = new_session_token()
        token_hash = hash_session_token(raw_token)
        session_id = "sess-" + token_hash[:16]
        csrf_token = secrets.token_urlsafe(24)
        created_at = _now_iso()
        expires_at = _expires_in(SESSION_TTL_SECONDS)
        with self._lock:
            self._conn.execute(
                "INSERT INTO auth_sessions (id, token_hash, user_id, provider, "
                "csrf_token, created_at, expires_at, revoked_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (session_id, token_hash, user_id, provider, csrf_token,
                 created_at, expires_at),
            )
            self._conn.commit()
        return raw_token, SessionRecord(
            id=session_id, user_id=user_id, provider=provider,
            csrf_token=csrf_token, created_at=created_at,
            expires_at=expires_at,
        )

    def resolve_session(self, raw_token: str) -> SessionRecord | None:
        """Resolve a bearer token to a live session (fail-closed: revoked,
        expired or unknown → None — never a partial identity)."""
        if not raw_token.startswith(SESSION_TOKEN_PREFIX):
            return None
        token_hash = hash_session_token(raw_token)
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM auth_sessions WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
        if row is None or row["revoked_at"] is not None:
            return None
        if row["expires_at"] <= _now_iso():
            return None  # expired — honest anonymous, not an error
        return SessionRecord(
            id=str(row["id"]), user_id=str(row["user_id"]),
            provider=str(row["provider"]), csrf_token=str(row["csrf_token"]),
            created_at=str(row["created_at"]), expires_at=str(row["expires_at"]),
        )

    def revoke_session(self, session_id: str) -> None:
        """Server-side logout invalidation (SECURITY: logout invalidates
        server-side; the cookie deletion is belt-and-braces)."""
        with self._lock:
            self._conn.execute(
                "UPDATE auth_sessions SET revoked_at = ? WHERE id = ? "
                "AND revoked_at IS NULL",
                (_now_iso(), session_id),
            )
            self._conn.commit()

    # -- OAuth flow states ----------------------------------------------------

    def create_oauth_state(self, *, next_path: str | None) -> OAuthStateRecord:
        state = new_state_token()
        verifier = new_verifier_token()
        created_at = _now_iso()
        expires_at = _expires_in(OAUTH_STATE_TTL_SECONDS)
        with self._lock:
            self._conn.execute(
                "INSERT INTO oauth_states (state, code_verifier, created_at, "
                "expires_at, consumed_at, next_path) VALUES (?, ?, ?, ?, NULL, ?)",
                (state, verifier, created_at, expires_at, next_path),
            )
            self._conn.commit()
        return OAuthStateRecord(
            state=state, code_verifier=verifier, created_at=created_at,
            expires_at=expires_at, next_path=next_path,
        )

    def take_oauth_state(self, state: str) -> OAuthStateRecord:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM oauth_states WHERE state = ?", (state,)
            ).fetchone()
            if row is None:
                raise StateUnknownError(state)
            if row["consumed_at"] is not None:
                raise StateConsumedError(state)
            if row["expires_at"] <= _now_iso():
                raise StateExpiredError(state)
            # Consume INSIDE the lock: exactly one callback can use a state.
            self._conn.execute(
                "UPDATE oauth_states SET consumed_at = ? WHERE state = ? "
                "AND consumed_at IS NULL",
                (_now_iso(), state),
            )
            self._conn.commit()
        return OAuthStateRecord(
            state=str(row["state"]), code_verifier=str(row["code_verifier"]),
            created_at=str(row["created_at"]), expires_at=str(row["expires_at"]),
            next_path=(str(row["next_path"]) if row["next_path"] else None),
        )

    def peek_oauth_state(self, state: str) -> OAuthStateRecord | None:
        """Validate a state row is PENDING WITHOUT consuming it (the LOCAL
        consent page may render repeatedly; consumption happens exactly
        once, at the callback's ``take_oauth_state``)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM oauth_states WHERE state = ?", (state,)
            ).fetchone()
            if row is None or row["consumed_at"] is not None:
                return None
            if row["expires_at"] <= _now_iso():
                return None
        return OAuthStateRecord(
            state=str(row["state"]), code_verifier=str(row["code_verifier"]),
            created_at=str(row["created_at"]), expires_at=str(row["expires_at"]),
            next_path=(str(row["next_path"]) if row["next_path"] else None),
        )

    # -- membership roles (read-only; writes live in the persistence seam) ----

    def memberships_for_user(self, user_id: str) -> tuple[MembershipRecord, ...]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT w.id, w.name, w.slug, w.is_demo, w.created_at, m.role "
                "FROM workspace_members m JOIN workspaces w "
                "ON w.id = m.workspace_id WHERE m.user_id = ? "
                "ORDER BY w.created_at, w.id",
                (user_id,),
            ).fetchall()
        return tuple(
            MembershipRecord(
                workspace_id=str(r["id"]), name=str(r["name"]),
                slug=str(r["slug"]), is_demo=bool(r["is_demo"]),
                created_at=str(r["created_at"]), role=str(r["role"]),
            )
            for r in rows
        )


class UnsupportedAuthStore:
    """The fail-closed store for non-LOCAL persistence modes (PUB-05 unifies
    the auth tables into the Neon seam). Every method refuses with a precise
    error — no silent degradation, no fake sessions."""

    def __init__(self, mode: str) -> None:
        self.mode = mode

    def _refuse(self) -> None:
        raise RuntimeError(
            "the PUB-04 auth store requires SOS_PERSISTENCE=local until "
            "PUB-05 lands the unified persistence seam (current mode: "
            f"{self.mode!r}); refusing — no silent fallback is permitted"
        )

    def create_session(self, *, user_id: str, provider: str) -> tuple[str, SessionRecord]:
        del user_id, provider
        self._refuse()  # pragma: no cover - refusal path
        raise AssertionError("unreachable")

    def resolve_session(self, raw_token: str) -> SessionRecord | None:
        # Passive resolution: an unvalidatable token is ANONYMOUS
        # (fail-closed authentication — never a forged identity, never a
        # crash on unrelated routes). The active auth endpoints surface the
        # precise error instead.
        del raw_token
        return None

    def revoke_session(self, session_id: str) -> None:
        del session_id
        self._refuse()  # pragma: no cover - refusal path

    def create_oauth_state(self, *, next_path: str | None) -> OAuthStateRecord:
        del next_path
        self._refuse()  # pragma: no cover - refusal path
        raise AssertionError("unreachable")

    def take_oauth_state(self, state: str) -> OAuthStateRecord:
        del state
        self._refuse()  # pragma: no cover - refusal path
        raise AssertionError("unreachable")

    def peek_oauth_state(self, state: str) -> OAuthStateRecord | None:
        del state
        return None

    def memberships_for_user(self, user_id: str) -> tuple[MembershipRecord, ...]:
        del user_id
        return ()


def build_auth_store(settings: Any) -> Any:
    """LOCAL persistence → the SQLite store; anything else → the fail-closed
    refusal store (PUB-05 unifies; disclosed in the PUB-04 checkpoint)."""
    if getattr(settings, "persistence_mode", "local") == "local":
        return LocalSqliteAuthStore(settings.local_db_path)
    return UnsupportedAuthStore(settings.persistence_mode)
