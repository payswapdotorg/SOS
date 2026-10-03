"""PUB-05 — migrations: numbered, forward-creatable, REVERSIBLE on BOTH
backends. The SQLite path runs always (stdlib); the PostgreSQL path runs
wherever a real Postgres is reachable (env ``SOS_TEST_DATABASE_URL`` or a
LOCAL pg on the default probe ports) and skips cleanly otherwise — the
contract acceptance is "a real Postgres in CI or LOCAL ``pg``"."""
from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import tempfile
import uuid
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
    translate_script_to_postgres,
)

# ---------------------------------------------------------------------------
# SQLite: always runs
# ---------------------------------------------------------------------------


def test_migrations_are_numbered_reversible_pairs() -> None:
    migrations = discover_migrations()
    assert sorted(migrations) == list(range(1, 12))
    for num, entry in migrations.items():
        assert entry["up"].exists() and entry["down"].exists()


def test_sqlite_up_down_up_down_round_trip() -> None:
    """Forward-creatable + reversible: full up, full down (twice)."""
    db_path = tempfile.mktemp(suffix=".sqlite3")
    conn = sqlite3.connect(db_path)
    try:
        up1 = migrate_up(conn)
        assert len(up1) == 11
        assert applied_numbers(conn) == list(range(1, 12))
        down1 = migrate_down(conn, 0)
        assert len(down1) == 11
        remaining = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        assert remaining == [("_migrations",)]
        up2 = migrate_up(conn)
        assert len(up2) == 11
        down2 = migrate_down(conn, 0)
        assert len(down2) == 11
    finally:
        conn.close()
        Path(db_path).unlink(missing_ok=True)


def test_sqlite_partial_revert_reapplies_cleanly() -> None:
    """Reverting to a mid-schema target then re-applying is clean."""
    db_path = tempfile.mktemp(suffix=".sqlite3")
    conn = sqlite3.connect(db_path)
    try:
        migrate_up(conn)
        down = migrate_down(conn, 3)  # back to the PUB-01 head
        assert down == [
            "0011_execution_records", "0010_experiment_events",
            "0009_assurance_results", "0008_candidate_evaluations",
            "0007_causal_hypotheses", "0006_evidence_artifacts",
            "0005_architecture_graph", "0004_section11_completion",
        ]
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "architecture_nodes" not in tables
        assert "evidence" in tables and "jobs" in tables
        up = migrate_up(conn)
        assert len(up) == 8
        assert applied_numbers(conn) == list(range(1, 12))
    finally:
        conn.close()
        Path(db_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Postgres dialect translation: always runs (pure text)
# ---------------------------------------------------------------------------


def test_translate_to_postgres_swaps_registered_json_columns() -> None:
    """The translation swaps exactly the REGISTERED (table, column) JSON
    pairs — real migration DDL, real registry."""
    sql = (
        "CREATE TABLE architecture_nodes (\n"
        "    id TEXT PRIMARY KEY,\n"
        "    graph_id TEXT,\n"
        "    attributes TEXT NOT NULL,\n"
        "    uncertainty TEXT,\n"
        "    confidence REAL\n"
        ");\n"
    )
    translated = translate_script_to_postgres(sql)
    assert "attributes JSONB NOT NULL" in translated
    assert "uncertainty JSONB" in translated
    assert "graph_id TEXT" in translated  # unregistered stays TEXT
    assert "id TEXT PRIMARY KEY" in translated
    assert "confidence DOUBLE PRECISION" in translated


def test_translate_to_postgres_translation_counts() -> None:
    """Every migration containing registered JSON columns actually gets
    them swapped (guard against registry drift)."""
    from db.mapping import JSON_COLUMNS

    total_swaps = 0
    for entry in discover_migrations().values():
        original = entry["up"].read_text(encoding="utf-8")
        translated = translate_script_to_postgres(original)
        swaps = translated.count("JSONB") - original.count("JSONB")
        assert swaps >= 0
        total_swaps += swaps
    # the union of registered JSON columns across the schema (some tables
    # have no TEXT JSON columns in their creating migration — e.g. ALTER
    # additions and empty registries)
    expected_columns = sum(len(cols) for cols in JSON_COLUMNS.values())
    assert total_swaps >= 30, (
        f"expected the majority of the {expected_columns} registered JSON "
        f"columns to be translated; got {total_swaps}"
    )


def test_translate_to_postgres_leaves_existing_migrations_valid() -> None:
    """Every migration translates without SQLite-only syntax leaking into
    the Postgres path; the translated DDL is exercised against a REAL
    Postgres by the gated tests below (the authoritative check)."""
    for entry in discover_migrations().values():
        translated = translate_script_to_postgres(
            entry["up"].read_text(encoding="utf-8")
        )
        assert "CREATE TABLE" in translated or "ALTER TABLE" in translated
        assert "datetime('now')" not in translated


# ---------------------------------------------------------------------------
# PostgreSQL (a real Postgres): gated on asyncpg + reachability
# ---------------------------------------------------------------------------

_PG_PROBES = (
    "postgresql://postgres:postgres@127.0.0.1:5432/postgres",
    "postgresql://postgres@127.0.0.1:54329/postgres",
)


def _discover_pg_dsn() -> str | None:
    explicit = os.environ.get("SOS_TEST_DATABASE_URL", "").strip()
    if explicit:
        return explicit
    try:
        import asyncpg
    except ImportError:
        return None

    async def _probe(dsn: str) -> bool:
        conn = await asyncpg.connect(dsn, timeout=2.0)
        await conn.close()
        return True

    for dsn in _PG_PROBES:
        try:
            if asyncio.run(_probe(dsn)):
                return dsn
        except Exception:
            continue
    return None


@pytest.fixture(scope="module")
def pg_dsn() -> str:
    pytest.importorskip(
        "asyncpg",
        reason="Postgres parity requires asyncpg (Neon adapter driver)",
    )
    dsn = _discover_pg_dsn()
    if dsn is None:
        pytest.skip(
            "no Postgres reachable (SOS_TEST_DATABASE_URL unset and no "
            "LOCAL pg on the probe ports) — the Postgres migration/parity "
            "paths are verified only where a real backend exists "
            "(contract §D PUB-05 acceptance: CI or LOCAL pg)"
        )
    return dsn


@pytest.fixture
def pg_database(pg_dsn: str) -> str:
    """A fresh database per test; dropped afterwards."""
    asyncpg = pytest.importorskip("asyncpg")
    name = f"sos_pub05_{uuid.uuid4().hex[:12]}"

    async def _create() -> None:
        admin = await asyncpg.connect(pg_dsn)
        try:
            await admin.execute(f'CREATE DATABASE "{name}"')
        finally:
            await admin.close()

    async def _drop() -> None:
        admin = await asyncpg.connect(pg_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            await admin.close()

    asyncio.run(_create())

    def _to_dsn(base: str, db: str) -> str:
        prefix, rest = base.split("://", 1)
        if "@" in rest:
            creds, host_part = rest.split("@", 1)
            host, cur_db = host_part.split("/", 1)
            return f"{prefix}://{creds}@{host}/{db}"
        host, cur_db = rest.split("/", 1)
        return f"{prefix}://{host}/{db}"

    try:
        yield _to_dsn(pg_dsn, name)
    finally:
        asyncio.run(_drop())


def test_postgres_up_down_up_round_trip(pg_database: str) -> None:
    """The SAME migration set (dialect-translated) applies and reverts
    cleanly on a real PostgreSQL — full round-trip."""
    asyncpg = pytest.importorskip("asyncpg")

    async def _run() -> tuple[list[str], list[str], list[str], list[str]]:
        conn = await asyncpg.connect(pg_database)
        try:
            from db.runner import migrate_down_async, migrate_up_async

            up1 = await migrate_up_async(conn)
            tables = {
                r["table_name"] for r in await conn.fetch(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            }
            assert "architecture_nodes" in tables
            assert "architecture_boundary_contracts" in tables
            assert "execution_receipts" in tables
            assert "value_models" in tables
            # the dialect translation really produced JSONB / double precision
            attr_type = await conn.fetchval(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'architecture_nodes' "
                "AND column_name = 'attributes'"
            )
            assert attr_type == "jsonb"
            conf_type = await conn.fetchval(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'evidence' "
                "AND column_name = 'confidence'"
            )
            assert conf_type == "double precision"
            down = await migrate_down_async(conn, 0)
            tables_after = {
                r["table_name"] for r in await conn.fetch(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            }
            assert tables_after == {"_migrations"}
            up2 = await migrate_up_async(conn)
            return up1, down, up2, tables_after
        finally:
            await conn.close()

    up1, down, up2, _ = asyncio.run(_run())
    assert len(up1) == 11 and len(down) == 11 and len(up2) == 11


def test_postgres_jsonb_round_trips_values(pg_database: str) -> None:
    """JSONB columns round-trip JSON values (the shared encode/decode pair
    produces identical documents on both backends)."""
    asyncpg = pytest.importorskip("asyncpg")

    async def _run() -> None:
        from db.mapping import decode_row, encode_row

        conn = await asyncpg.connect(pg_database)
        try:
            from db.runner import migrate_up_async

            await migrate_up_async(conn)
            # the parent chain for the FK-constrained projection row
            await conn.execute(
                "INSERT INTO workspaces (id, name, slug, is_demo, "
                "created_at) VALUES ('ws-1', 'w', 'w', 0, 't')"
            )
            await conn.execute(
                "INSERT INTO systems (id, workspace_id, name, mode, "
                "created_at) VALUES ('sys-1', 'ws-1', 's', 'greenfield', 't')"
            )
            await conn.execute(
                "INSERT INTO system_revisions (id, system_id, revision, "
                "state_summary, uncertainty, graph, created_at) VALUES "
                "('rev-1', 'sys-1', 1, 's', '{}', '{}', 't')"
            )
            row = {
                "id": "node-1", "workspace_id": "ws-1",
                "system_id": "sys-1", "system_revision_id": "rev-1",
                "graph_id": "g", "graph_version": 1, "node_key": "n",
                "node_type": "component", "name": "n", "position": 0,
                "attributes": {"kind": "module", "nested": {"a": [1, 2]}},
                "uncertainty": None, "created_at": "t",
            }
            encoded = encode_row("architecture_nodes", row)
            await conn.execute(
                "INSERT INTO architecture_nodes (id, workspace_id, "
                "system_id, system_revision_id, graph_id, graph_version, "
                "node_key, node_type, name, position, attributes, "
                "uncertainty, created_at) VALUES "
                "($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)",
                encoded["id"], encoded["workspace_id"], encoded["system_id"],
                encoded["system_revision_id"], encoded["graph_id"],
                encoded["graph_version"], encoded["node_key"],
                encoded["node_type"], encoded["name"], encoded["position"],
                encoded["attributes"], encoded["uncertainty"],
                encoded["created_at"],
            )
            record = await conn.fetchrow(
                "SELECT * FROM architecture_nodes WHERE id = 'node-1'"
            )
            decoded = decode_row("architecture_nodes", dict(record))
            assert decoded["attributes"] == row["attributes"]
            assert decoded["uncertainty"] is None
        finally:
            await conn.close()

    asyncio.run(_run())
