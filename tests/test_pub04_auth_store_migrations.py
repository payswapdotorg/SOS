"""PUB-04 — the auth store (sessions, OAuth states, membership reads) and
migration 0004 (auth_sessions + oauth_states): reversible round-trip,
store semantics, fail-closed non-LOCAL refusal.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(REPO_ROOT / "src"), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from db.runner import (  # noqa: E402
    applied_numbers,
    discover_migrations,
    migrate_down,
    migrate_up,
)
from services.api.auth.store import (  # noqa: E402
    SESSION_TOKEN_PREFIX,
    StateConsumedError,
    StateExpiredError,
    StateUnknownError,
    UnsupportedAuthStore,
    build_auth_store,
    hash_session_token,
    LocalSqliteAuthStore,
    new_session_token,
)
from providers.neon.local import LocalSqlitePersistence  # noqa: E402


def test_migration_0004_is_a_reversible_pair() -> None:
    migrations = discover_migrations()
    assert 4 in migrations
    entry = migrations[4]
    assert entry["name"] == "auth_sessions_oauth_states"
    assert entry["up"].name == "0004_auth_sessions_oauth_states.up.sql"
    assert entry["down"].name == "0004_auth_sessions_oauth_states.down.sql"


def test_migration_0004_round_trip(tmp_path: Path) -> None:
    conn = sqlite3.connect(str(tmp_path / "rt.sqlite3"))
    try:
        labels = migrate_up(conn)
        assert "0004_auth_sessions_oauth_states" in labels
        assert applied_numbers(conn) == [1, 2, 3, 4]
        conn.execute(
            "INSERT INTO users (id, github_id, login, display_name, created_at) "
            "VALUES ('u1', '1', 'one', 'One', '2026-01-01T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO auth_sessions (id, token_hash, user_id, provider, "
            "csrf_token, created_at, expires_at) VALUES "
            "('s1', 'h1', 'u1', 'github', 'c1', 't', '2999-01-01T00:00:00Z')"
        )
        reverted = migrate_down(conn, target=3)
        assert reverted == ["0004_auth_sessions_oauth_states"]
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("SELECT * FROM auth_sessions")
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("SELECT * FROM oauth_states")
        again = migrate_up(conn)
        assert "0004_auth_sessions_oauth_states" in again
        # users survived the round trip (auth tables are additive)
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    finally:
        conn.close()


def _seeded_store(tmp_path: Path) -> tuple[LocalSqliteAuthStore, Path]:
    """A migrated + seeded database and an auth store over the same file."""
    db_path = tmp_path / "api.sqlite3"
    persistence = LocalSqlitePersistence(db_path)
    persistence.migrate()
    from db.seeds.demo_seed import seed_demo

    persistence.seed_demo(seed_demo)
    persistence.close()
    return LocalSqliteAuthStore(db_path), db_path


def test_session_lifecycle_in_store(tmp_path: Path) -> None:
    store, _ = _seeded_store(tmp_path)
    try:
        raw, record = store.create_session(
            user_id="user-alice", provider="fake-github"
        )
        assert raw.startswith(SESSION_TOKEN_PREFIX)
        assert record.csrf_token and record.csrf_token != raw
        # only the hash is stored — a DB read yields no bearer token
        assert record.id != raw
        resolved = store.resolve_session(raw)
        assert resolved is not None
        assert resolved.user_id == "user-alice"
        assert resolved.csrf_token == record.csrf_token
        assert store.resolve_session("sos1.forged-token") is None
        assert store.resolve_session("stub-session:user-alice") is None

        store.revoke_session(record.id)
        assert store.resolve_session(raw) is None  # server-side invalidation
    finally:
        store.close()


def test_oauth_state_single_use_in_store(tmp_path: Path) -> None:
    store, _ = _seeded_store(tmp_path)
    try:
        record = store.create_oauth_state(next_path="/workspace")
        peeked = store.peek_oauth_state(record.state)
        assert peeked is not None  # pending, not consumed by peeking
        taken = store.take_oauth_state(record.state)
        assert taken.code_verifier == record.code_verifier
        assert taken.next_path == "/workspace"
        # second take: replayed → rejected
        with pytest.raises(StateConsumedError):
            store.take_oauth_state(record.state)
        assert store.peek_oauth_state(record.state) is None
        with pytest.raises(StateUnknownError):
            store.take_oauth_state("no-such-state")
    finally:
        store.close()


def test_oauth_state_expiry_in_store(tmp_path: Path) -> None:
    store, db_path = _seeded_store(tmp_path)
    try:
        record = store.create_oauth_state(next_path=None)
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "UPDATE oauth_states SET expires_at = '2000-01-01T00:00:00Z' "
            "WHERE state = ?",
            (record.state,),
        )
        conn.commit()
        conn.close()
        with pytest.raises(StateExpiredError):
            store.take_oauth_state(record.state)
        assert store.peek_oauth_state(record.state) is None
    finally:
        store.close()


def test_membership_reads_owner_member(tmp_path: Path) -> None:
    store, _ = _seeded_store(tmp_path)
    try:
        # alice owns her seeded workspace (role from migration 0001's model)
        memberships = store.memberships_for_user("user-alice")
        by_id = {m.workspace_id: m for m in memberships}
        assert by_id["ws-alice"].role == "owner"
        assert by_id["ws-alice"].slug == "alice-lab"
        assert by_id["ws-alice"].is_demo is False
        assert store.memberships_for_user("user-nobody") == ()
        # a second member joins bob's workspace → role 'member'
        conn = sqlite3.connect(str(tmp_path / "api.sqlite3"))
        conn.execute(
            "INSERT INTO workspace_members (workspace_id, user_id, role, "
            "created_at) VALUES ('ws-bob', 'user-alice', 'member', "
            "'2026-01-01T00:00:00Z')"
        )
        conn.commit()
        conn.close()
        by_id = {m.workspace_id: m for m in store.memberships_for_user("user-alice")}
        assert by_id["ws-alice"].role == "owner"
        assert by_id["ws-bob"].role == "member"
    finally:
        store.close()


def test_token_hash_shape() -> None:
    token = new_session_token()
    digest = hash_session_token(token)
    assert len(digest) == 64  # sha256 hex
    assert digest == hash_session_token(token)  # deterministic
    assert hash_session_token("other") != digest


def test_non_local_persistence_fails_closed(tmp_path: Path) -> None:
    class _NeonSettings:
        persistence_mode = "neon"
        local_db_path = str(tmp_path / "unused.sqlite3")

    store = build_auth_store(_NeonSettings())
    assert isinstance(store, UnsupportedAuthStore)
    assert store.resolve_session("sos1.anything") is None  # passive → anon
    with pytest.raises(RuntimeError, match="PUB-05"):
        store.create_session(user_id="u", provider="github")
    with pytest.raises(RuntimeError, match="PUB-05"):
        store.create_oauth_state(next_path=None)
    assert store.memberships_for_user("u") == ()

    class _LocalSettings:
        persistence_mode = "local"
        local_db_path = str(tmp_path / "api.sqlite3")

    assert isinstance(build_auth_store(_LocalSettings()), LocalSqliteAuthStore)
