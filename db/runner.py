#!/usr/bin/env python3
"""Migration runner for the Public Deployment Overlay (PUB-01; Postgres
dialect + async support landed with PUB-05).

Conventions (contract §D PUB-01 / §B):

- migrations are numbered ``NNNN_name.up.sql`` + ``NNNN_name.down.sql`` pairs
  under ``db/migrations/``;
- forward-creatable: ``migrate_up`` applies every pending migration in
  number order inside a transaction and records it in ``_migrations``;
- REVERSIBLE: ``migrate_down`` reverts applied migrations in reverse number
  order, also transactionally;
- SQLite runs the scripts verbatim (LOCAL). PostgreSQL (Neon) runs the SAME
  migration set through a deterministic dialect translation
  (:func:`translate_script_to_postgres`): JSON-column ``TEXT`` → ``JSONB``
  (registry: ``db/mapping.JSON_COLUMNS`` — single source of truth, shared
  with both persistence adapters) and ``REAL`` → ``DOUBLE PRECISION``.
  Both dialects are exercised by the PUB-05 parity suite against a REAL
  Postgres (migrations up/down round-trip on both backends).

CLI (operators / tests)::

    python3 -m db.runner up     [--db PATH | --url DSN]
    python3 -m db.runner down   [--db PATH | --url DSN] [--target N]
    python3 -m db.runner status [--db PATH | --url DSN]

``--url`` selects the PostgreSQL dialect (asyncpg driver, lazy import — the
Neon adapter dependency; fail-closed with a precise message when absent).
"""
from __future__ import annotations

import asyncio
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

from db.mapping import JSON_COLUMNS

DB_ROOT = Path(__file__).resolve().parent
MIGRATIONS_DIR = DB_ROOT / "migrations"

_MIGRATION_TABLE = "_migrations"

_MIGRATION_RE = re.compile(r"^(?P<num>\d{4})_(?P<name>[a-z0-9_]+)\.(?P<dir>up|down)\.sql$")

# -- Postgres dialect translation (PUB-05) ----------------------------------

_PG_CREATE_TABLE_RE = re.compile(
    r"^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"\"?([a-zA-Z_][a-zA-Z0-9_]*)\"?\s*\(",
    re.IGNORECASE,
)

_PG_COLUMN_RE = re.compile(
    r"^(\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s+)(TEXT|REAL)(\b.*)$"
)


def discover_migrations() -> dict[int, dict[str, Path]]:
    """All migration number → {'name':…, 'up': Path, 'down': Path}."""
    found: dict[int, dict[str, Path]] = {}
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        match = _MIGRATION_RE.match(path.name)
        if match is None:
            raise SystemExit(f"unrecognized migration file: {path.name}")
        num = int(match.group("num"))
        entry = found.setdefault(num, {"name": match.group("name")})
        entry[match.group("dir")] = path
    for num, entry in found.items():
        if "up" not in entry or "down" not in entry:
            raise SystemExit(
                f"migration {num:04d} ({entry['name']}) is not reversible: "
                "both .up.sql and .down.sql are required"
            )
    return found


def _ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {_MIGRATION_TABLE} ("
        "number INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT "
        "NOT NULL DEFAULT (datetime('now')))"
    )
    conn.commit()


def applied_numbers(conn: sqlite3.Connection) -> list[int]:
    _ensure_migration_table(conn)
    rows = conn.execute(
        f"SELECT number FROM {_MIGRATION_TABLE} ORDER BY number"
    ).fetchall()
    return [int(r[0]) for r in rows]


def _run_script(conn: sqlite3.Connection, path: Path) -> None:
    """Run one migration script inside an explicit transaction (partial
    application rolls back)."""
    sql = path.read_text(encoding="utf-8")
    try:
        conn.executescript("BEGIN;\n" + sql + "\nCOMMIT;")
    except Exception:
        conn.rollback()
        raise


def translate_script_to_postgres(sql_text: str) -> str:
    """Translate a SQLite-dialect migration script to PostgreSQL DDL.

    Deterministic, line-based translation of the common DDL subset the
    migration files are written in:

    - JSON-column ``TEXT`` → ``JSONB`` (exactly the columns registered in
      ``db/mapping.JSON_COLUMNS`` — the shared single source of truth);
    - ``REAL`` → ``DOUBLE PRECISION`` (8-byte float on both backends).

    Everything else (TEXT keys, INTEGER flags, CHECK constraints, partial
    unique indexes, REFERENCES … ON DELETE) is valid in both dialects and
    passes through verbatim. Covered by the PUB-05 parity suite, which runs
    the translated scripts against a REAL Postgres.
    """
    out: list[str] = []
    table: str | None = None
    for line in sql_text.splitlines():
        create = _PG_CREATE_TABLE_RE.match(line)
        if create is not None:
            table = create.group(1)
            out.append(line)
            continue
        if table is not None:
            stripped = line.strip()
            if stripped.startswith(")"):
                table = None
                out.append(line)
                continue
            column = _PG_COLUMN_RE.match(line)
            if column is not None:
                lead, name, gap, coltype, rest = column.groups()
                json_cols = JSON_COLUMNS.get(table, frozenset())
                if coltype.upper() == "TEXT" and name in json_cols:
                    out.append(f"{lead}{name}{gap}JSONB{rest}")
                    continue
                if coltype.upper() == "REAL":
                    out.append(f"{lead}{name}{gap}DOUBLE PRECISION{rest}")
                    continue
        out.append(line)
    return "\n".join(out) + ("\n" if sql_text.endswith("\n") else "")


# -- PostgreSQL (asyncpg) migration runner (PUB-05) --------------------------

_PG_MIGRATION_TABLE_DDL = (
    "CREATE TABLE IF NOT EXISTS _migrations ("
    "number INTEGER PRIMARY KEY, name TEXT NOT NULL, "
    "applied_at TEXT NOT NULL DEFAULT (now()::text))"
)


def _require_asyncpg() -> Any:
    try:
        import asyncpg  # noqa: PLC0415 — lazy by design (optional driver)
    except ImportError as exc:  # pragma: no cover - depends on env
        raise ImportError(
            "the PostgreSQL migration path requires the asyncpg driver "
            "(Neon adapter dependency; not part of the default/hermetic "
            "test environment) — install asyncpg to run Postgres migrations"
        ) from exc
    return asyncpg


async def applied_numbers_async(conn: Any) -> list[int]:
    """Applied migration numbers on an asyncpg connection (Postgres)."""
    await conn.execute(_PG_MIGRATION_TABLE_DDL)
    rows = await conn.fetch(
        f"SELECT number FROM {_MIGRATION_TABLE} ORDER BY number"
    )
    return [int(row["number"]) for row in rows]


async def _run_script_async(conn: Any, path: Path) -> None:
    """Run one translated migration script inside one transaction."""
    script = translate_script_to_postgres(path.read_text(encoding="utf-8"))
    async with conn.transaction():
        await conn.execute(script)


async def migrate_up_async(conn: Any) -> list[str]:
    """Apply every pending migration (Postgres dialect, asyncpg connection);
    returns labels applied."""
    migrations = discover_migrations()
    applied = set(await applied_numbers_async(conn))
    labels: list[str] = []
    for num in sorted(migrations):
        if num in applied:
            continue
        entry = migrations[num]
        label = f"{num:04d}_{entry['name']}"
        await _run_script_async(conn, entry["up"])
        async with conn.transaction():
            await conn.execute(
                f"INSERT INTO {_MIGRATION_TABLE} (number, name) "
                "VALUES ($1, $2)",
                num, entry["name"],
            )
        labels.append(label)
    return labels


async def migrate_down_async(conn: Any, target: int = 0) -> list[str]:
    """Revert migrations above ``target`` (Postgres dialect); returns labels."""
    migrations = discover_migrations()
    applied = await applied_numbers_async(conn)
    labels: list[str] = []
    for num in sorted(applied, reverse=True):
        if num <= target:
            continue
        entry = migrations.get(num)
        if entry is None:
            raise SystemExit(
                f"applied migration {num:04d} has no source pair on disk; "
                "cannot revert"
            )
        label = f"{num:04d}_{entry['name']}"
        await _run_script_async(conn, entry["down"])
        async with conn.transaction():
            await conn.execute(
                f"DELETE FROM {_MIGRATION_TABLE} WHERE number = $1", num
            )
        labels.append(label)
    return labels


def migrate_up(conn: sqlite3.Connection) -> list[str]:
    """Apply every pending migration in number order; returns labels applied."""
    migrations = discover_migrations()
    applied = set(applied_numbers(conn))
    labels: list[str] = []
    for num in sorted(migrations):
        if num in applied:
            continue
        entry = migrations[num]
        label = f"{num:04d}_{entry['name']}"
        _run_script(conn, entry["up"])
        conn.execute(
            f"INSERT INTO {_MIGRATION_TABLE} (number, name) VALUES (?, ?)",
            (num, entry["name"]),
        )
        conn.commit()
        labels.append(label)
    return labels


def migrate_down(conn: sqlite3.Connection, target: int = 0) -> list[str]:
    """Revert migrations above ``target`` in reverse order; returns labels."""
    migrations = discover_migrations()
    applied = applied_numbers(conn)
    labels: list[str] = []
    for num in sorted(applied, reverse=True):
        if num <= target:
            continue
        entry = migrations.get(num)
        if entry is None:
            raise SystemExit(
                f"applied migration {num:04d} has no source pair on disk; "
                "cannot revert"
            )
        label = f"{num:04d}_{entry['name']}"
        _run_script(conn, entry["down"])
        conn.execute(
            f"DELETE FROM {_MIGRATION_TABLE} WHERE number = ?", (num,)
        )
        conn.commit()
        labels.append(label)
    return labels


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in {"up", "down", "status"}:
        print(__doc__)
        return 2
    command = argv[0]
    db_flag = "--db"
    db_path = DB_ROOT / "local" / "sos-api.sqlite3"
    url: str | None = None
    if db_flag in argv:
        db_path = Path(argv[argv.index(db_flag) + 1])
    if "--url" in argv:
        url = argv[argv.index("--url") + 1]
    target = 0
    if "--target" in argv:
        target = int(argv[argv.index("--target") + 1])
    if url is not None:
        return _run_cli_postgres(command, url, target)
    conn = sqlite3.connect(str(db_path))
    try:
        if command == "status":
            applied = applied_numbers(conn)
            print(f"applied: {applied or '[]'} (latest head: "
                  f"{max(applied) if applied else 0:04d})")
            return 0
        if command == "up":
            labels = migrate_up(conn)
            print("applied: " + (", ".join(labels) if labels else "(none pending)"))
            return 0
        labels = migrate_down(conn, target)
        print("reverted: " + (", ".join(labels) if labels else "(none applied)"))
        return 0
    finally:
        conn.close()


def _run_cli_postgres(command: str, url: str, target: int) -> int:
    """CLI path for ``--url``: the PostgreSQL dialect over asyncpg."""
    asyncpg = _require_asyncpg()

    async def _run() -> list[str]:
        conn = await asyncpg.connect(url)
        try:
            if command == "status":
                applied = await applied_numbers_async(conn)
                print(f"applied: {applied or '[]'} (latest head: "
                      f"{max(applied) if applied else 0:04d})")
                return []
            if command == "up":
                return await migrate_up_async(conn)
            return await migrate_down_async(conn, target)
        finally:
            await conn.close()

    labels = asyncio.run(_run())
    if command == "up":
        print("applied: " + (", ".join(labels) if labels else "(none pending)"))
    elif command == "down":
        print("reverted: " + (", ".join(labels) if labels else "(none applied)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
