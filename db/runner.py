#!/usr/bin/env python3
"""Migration runner for the Public Deployment Overlay (PUB-01).

Conventions (contract §D PUB-01 / §B):

- migrations are numbered ``NNNN_name.up.sql`` + ``NNNN_name.down.sql`` pairs
  under ``db/migrations/``;
- forward-creatable: ``migrate_up`` applies every pending migration in
  number order inside a transaction and records it in ``_migrations``;
- REVERSIBLE: ``migrate_down`` reverts applied migrations in reverse number
  order, also transactionally;
- SQLite-compatible now; the Postgres-compatible DDL strategy is documented
  in ``docs/deployment/database.md`` (PUB-05 finalizes the Neon migrations).

CLI (operators / tests)::

    python3 -m db.runner up     [--db PATH]
    python3 -m db.runner down   [--db PATH] [--target N]
    python3 -m db.runner status [--db PATH]
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

DB_ROOT = Path(__file__).resolve().parent
MIGRATIONS_DIR = DB_ROOT / "migrations"

_MIGRATION_TABLE = "_migrations"

_MIGRATION_RE = re.compile(r"^(?P<num>\d{4})_(?P<name>[a-z0-9_]+)\.(?P<dir>up|down)\.sql$")


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
    if db_flag in argv:
        db_path = Path(argv[argv.index(db_flag) + 1])
    target = 0
    if "--target" in argv:
        target = int(argv[argv.index("--target") + 1])
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


if __name__ == "__main__":
    raise SystemExit(main())
