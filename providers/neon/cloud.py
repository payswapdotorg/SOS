"""The Neon (PostgreSQL) cloud persistence adapter (PUB-05).

Implements the provider-neutral persistence seam
(:class:`providers.neon.seam.PersistencePort` — final since PUB-01) over
PostgreSQL via the **asyncpg** async driver, Neon serverless-compatible:

- TLS via the DSN (``sslmode=require`` — Neon requires it);
- ``statement_cache_size=0`` so pooled/transaction-mode endpoints (Neon's
  PgBouncer pooler) work without prepared-statement support;
- ``max_inactive_connection_lifetime`` recycles connections so Neon's
  suspend/compute-wake cycles never serve a dead socket silently.

The seam interface is SYNCHRONOUS (final); this adapter drives asyncpg on a
DEDICATED event-loop thread (:class:`_LoopRunner`) — every seam call
submits its coroutine to that loop and blocks on the result. All asyncpg
work (pool included) lives on that one loop; sync route handlers in the
FastAPI threadpool call the seam freely.

Truth rules (identical to the LOCAL SQLite adapter):

- tenant scoping in EVERY scoped query (SECURITY S5) — the ``TenantScope``
  allowlist becomes an ``= ANY($1::text[])`` filter inside this adapter, so
  a cross-tenant id yields zero rows;
- stored ``status`` truth states pass through verbatim (six-state
  vocabulary; no conversion anywhere in the seam);
- cursor pagination is deterministic (``ORDER BY created_at, id``) with the
  SAME opaque cursor encoding as the SQLite adapter;
- every ``insert_*`` write projects the payload's decomposed content into
  the normalized §11 tables through the SHARED ``db/mapping`` module
  (single mapping authority — same rows as SQLite, byte-identical JSON);
- JSON columns are JSONB on PostgreSQL (translated by ``db.runner``; values
  round-trip through the shared ``encode_row``/``decode_row``).

Fail-closed configuration (never a silent LOCAL fallback): a missing or
malformed DSN raises :class:`NeonConfigError`; a missing asyncpg driver
raises a precise ImportError — boot aborts with the exact reason.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import sys
import threading
from pathlib import Path
from typing import Any

from .seam import ConflictError, Page, SeamHealth, TenantScope

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from db.mapping import (  # noqa: E402
    JSON_COLUMNS as _JSON_COLUMNS,
    PARENT_LINKS as _PARENT_LINKS,
    TENANT_TABLES as _TENANT_TABLES,
    assurance_result_rows,
    candidate_evaluation_rows,
    causal_hypothesis_row,
    decode_row,
    encode_row,
    evidence_artifact_row,
    execution_receipt_row,
    execution_request_row,
    experiment_event_rows,
    graph_boundary_contract_rows,
    graph_edge_rows,
    graph_node_rows,
    snake_case as _snake,
)
from db.runner import (  # noqa: E402
    migrate_down_async,
    migrate_up_async,
)

from .local import decode_cursor, encode_cursor  # noqa: E402  single authority


class NeonConfigError(Exception):
    """Invalid Neon persistence configuration (fail-closed, boot aborts)."""


class NeonTimeoutError(Exception):
    """A bridged seam call exceeded its timeout (never hangs silently)."""


def _require_asyncpg() -> Any:
    try:
        import asyncpg  # noqa: PLC0415 — lazy by design (optional driver)
    except ImportError as exc:
        raise ImportError(
            "SOS_PERSISTENCE=neon requires the asyncpg driver (the PUB-05 "
            "Neon adapter's PostgreSQL dependency; not part of the "
            "hermetic default test environment). Install asyncpg, or use "
            "SOS_PERSISTENCE=local for LOCAL mode — no silent fallback."
        ) from exc
    return asyncpg


def normalize_database_url(database_url: str | None) -> str:
    """Validate/normalize the DSN: accepts ``postgresql://``,
    ``postgres://`` and SQLAlchemy-style ``postgresql+asyncpg://`` (the
    driver suffix is stripped). Anything else (including a missing URL)
    aborts boot fail-closed with a precise message."""
    raw = (database_url or "").strip()
    lowered = raw.lower()
    if lowered.startswith("postgresql+asyncpg://"):
        return "postgresql://" + raw[len("postgresql+asyncpg://"):]
    if lowered.startswith("postgresql://") or lowered.startswith("postgres://"):
        return raw
    raise NeonConfigError(
        "SOS_PERSISTENCE=neon requires SOS_DATABASE_URL with a PostgreSQL "
        "DSN (postgresql://user:password@host/db?sslmode=require — the "
        "Neon branch). The PUB-05 Neon adapter refuses to boot without a "
        "valid DSN (fail-closed: no silent fallback to the LOCAL SQLite "
        f"adapter). Got: {database_url!r}"
    )


def _dsn_label(dsn: str) -> str:
    """A credential-free label for logs/health details (never secrets)."""
    try:
        rest = dsn.split("://", 1)[1]
        host_db = rest.split("@", 1)[-1]
        host = host_db.split("/", 1)[0]
        db = host_db.split("/", 1)[1].split("?", 1)[0] if "/" in host_db else ""
        return f"{host}/{db}" if db else host
    except Exception:  # pragma: no cover - defensive
        return "postgres"


class _LoopRunner:
    """A dedicated event-loop thread: the sync seam bridge for asyncpg.

    All asyncpg work (the pool and every query) runs on this ONE loop; seam
    methods (called from FastAPI worker threads) submit coroutines here and
    block on the result with a timeout.
    """

    def __init__(self, name: str) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._serve, name=name, daemon=True
        )
        self._thread.start()

    def _serve(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run(self, coro: Any, timeout: float = 120.0) -> Any:
        if not self._thread.is_alive():  # pragma: no cover - defensive
            raise NeonTimeoutError("the Neon adapter loop thread is gone")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise NeonTimeoutError(
                f"a Neon persistence call exceeded {timeout:.0f}s — the "
                "database may be unreachable (truthful failure, no hang)"
            ) from exc

    def close(self, timeout: float = 15.0) -> None:
        # Give cancelled tasks one loop iteration to settle (avoids
        # "Task was destroyed but it is pending" on interpreter teardown).
        async def _drain() -> None:
            await asyncio.sleep(0.05)

        try:
            asyncio.run_coroutine_threadsafe(
                _drain(), self._loop
            ).result(timeout=2.0)
        except Exception:  # pragma: no cover - best-effort drain
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():  # pragma: no cover - defensive
            raise NeonTimeoutError("the Neon adapter loop thread did not stop")
        self._loop.close()


class NeonPostgresPersistence:
    """The Neon (PostgreSQL) implementation of the provider-neutral seam."""

    mode = "neon"
    implementation = "postgres-asyncpg"

    def __init__(
        self,
        database_url: str,
        *,
        min_size: int = 1,
        max_size: int = 4,
        command_timeout: float = 60.0,
        call_timeout: float = 120.0,
    ) -> None:
        asyncpg = _require_asyncpg()
        self._dsn = normalize_database_url(database_url)
        self._db_label = _dsn_label(self._dsn)
        self._call_timeout = call_timeout
        self._closed = False
        self._loop_runner = _LoopRunner("neon-persistence")
        try:

            async def _make_pool() -> Any:
                # Created ON the bridge loop (the Pool binds to the running
                # loop; all subsequent pool operations stay on that loop).
                # Neon serverless compatibility: no prepared-statement cache
                # (pooled/transaction-mode endpoints) + connection recycling
                # (suspend/compute-wake); TLS comes from the DSN (sslmode).
                return await asyncpg.create_pool(
                    self._dsn,
                    min_size=min_size,
                    max_size=max_size,
                    command_timeout=command_timeout,
                    max_inactive_connection_lifetime=300.0,
                    statement_cache_size=0,
                )

            self._pool = self._loop_runner.run(_make_pool(), timeout=45.0)
        except Exception:
            self._loop_runner.close()
            raise

    # -- bridge / row helpers ------------------------------------------------

    def _run(self, coro: Any) -> Any:
        if self._closed:  # pragma: no cover - defensive
            coro.close()  # never-awaited coroutine on the closed path
            raise NeonConfigError("the Neon persistence adapter is closed")
        return self._loop_runner.run(coro, timeout=self._call_timeout)

    def _row(self, table: str, record: Any) -> dict[str, Any]:
        return decode_row(table, dict(record))

    async def _insert_row_async(
        self, conn: Any, table: str, row: dict[str, Any]
    ) -> dict[str, Any]:
        columns = list(row.keys())
        marks = ", ".join(f"${i + 1}" for i in range(len(columns)))
        encoded = encode_row(table, row)
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) "
            f"VALUES ({marks}) RETURNING *"
        )
        record = await conn.fetchrow(
            sql, *[encoded[c] for c in columns]
        )
        assert record is not None
        return self._row(table, record)

    async def _insert_rows_async(
        self, conn: Any, table: str, rows: list[dict[str, Any]]
    ) -> None:
        """Insert mapping rows (PUB-05 normalized projection): JSON columns
        encoded via the shared ``encode_row`` — byte-identical to SQLite."""
        if not rows:
            return
        columns = list(rows[0].keys())
        marks = ", ".join(f"${i + 1}" for i in range(len(columns)))
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({marks})"
        await conn.executemany(
            sql, [tuple(encode_row(table, r).values()) for r in rows]
        )

    def _scope_clause(
        self, table: str, scope: TenantScope
    ) -> tuple[str, list[list[str]]]:
        """The tenant-scope WHERE fragment (S5) — always the FIRST
        parameter (``$1::text[]`` = the exact allowlist)."""
        ids = sorted(scope.workspace_ids)
        if table == "workspaces":
            return "workspaces.id = ANY($1::text[])", [ids]
        if table in _PARENT_LINKS:
            parent, fk, tenant_col = _PARENT_LINKS[table]
            return (
                f"{table}.{fk} IN (SELECT id FROM {parent} WHERE "
                f"{parent}.{tenant_col} = ANY($1::text[]))",
                [ids],
            )
        tenant_col = _TENANT_TABLES[table]
        return f"{table}.{tenant_col} = ANY($1::text[])", [ids]

    async def _fetch_page_async(
        self,
        conn: Any,
        table: str,
        scope: TenantScope,
        extra: list[tuple[str, Any]] | None = None,
        *,
        cursor: str | None,
        limit: int,
    ) -> Page:
        """Deterministic cursor pagination — the SQLite adapter's exact
        semantics (ORDER BY created_at, id; opaque cursor)."""
        scope_sql, scope_params = self._scope_clause(table, scope)
        params: list[Any] = list(scope_params)
        clauses: list[str] = [scope_sql]
        for template, value in extra or ():
            idx = len(params) + 1
            clauses.append(template.format(n=f"${idx}"))
            params.append(value)
        if cursor is not None:
            decoded = decode_cursor(cursor)
            if decoded is None:
                raise ValueError("invalid cursor")
            base = len(params)
            clauses.append(f"(created_at, id) > (${base + 1}, ${base + 2})")
            params.extend(decoded)
        where = " AND ".join(clauses)
        limit_idx = len(params) + 1
        sql = (
            f"SELECT * FROM {table} WHERE {where} "
            f"ORDER BY created_at ASC, id ASC LIMIT ${limit_idx}"
        )
        params.append(limit + 1)
        rows = await conn.fetch(sql, *params)
        items = tuple(self._row(table, r) for r in rows[:limit])
        next_cursor = None
        if len(rows) > limit and items:
            last = items[-1]
            next_cursor = encode_cursor(
                str(last["created_at"]), str(last["id"])
            )
        return Page(items=items, next_cursor=next_cursor)

    async def _get_scoped_async(
        self, conn: Any, table: str, scope: TenantScope,
        key_col: str, key_value: str,
    ) -> dict[str, Any] | None:
        scope_sql, scope_params = self._scope_clause(table, scope)
        sql = (
            f"SELECT * FROM {table} WHERE {table}.{key_col} = $2 "
            f"AND {scope_sql}"
        )
        row = await conn.fetchrow(sql, *scope_params, key_value)
        return self._row(table, row) if row else None

    # -- lifecycle -------------------------------------------------------------

    def close(self) -> None:
        """Close the pool and the bridge loop (tests / shutdown)."""
        if self._closed:
            return
        self._closed = True
        pool = getattr(self, "_pool", None)

        async def _close_pool() -> None:
            if pool is not None:
                await pool.close()

        try:
            self._loop_runner.run(_close_pool(), timeout=30.0)
        finally:
            self._loop_runner.close()

    def health_check(self) -> SeamHealth:
        async def _check() -> int:
            async with self._pool.acquire() as conn:
                return await conn.fetchval(
                    "SELECT COUNT(*) FROM workspaces"
                )

        coro = _check()
        try:
            count = self._run(coro)
        except Exception as exc:  # truthful failure, never a fake ok
            coro.close()  # never-awaited coroutine under fault injection
            return SeamHealth(
                status="FAILED",
                detail=f"postgres check failed: {exc}",
            )
        return SeamHealth(
            status="SUCCESS",
            detail=(
                f"postgres ok ({count} workspaces) at {self._db_label} "
                f"(asyncpg, jsonb)"
            ),
        )

    def migrate(self) -> list[str]:
        async def _migrate() -> list[str]:
            async with self._pool.acquire() as conn:
                return await migrate_up_async(conn)

        return self._run(_migrate())

    def migrate_down(self, target: int = 0) -> list[str]:
        async def _migrate_down() -> list[str]:
            async with self._pool.acquire() as conn:
                return await migrate_down_async(conn, target)

        return self._run(_migrate_down())

    def is_seeded(self) -> bool:
        async def _seeded() -> int:
            async with self._pool.acquire() as conn:
                return await conn.fetchval(
                    "SELECT COUNT(*) FROM workspaces WHERE is_demo = 1"
                )

        return bool(self._run(_seeded()))

    def seed_demo(self, seed_fn: Any) -> None:
        seed_fn(self)

    # -- users / membership ---------------------------------------------------

    def upsert_user(self, *, user_id: str, github_id: str, login: str,
                    display_name: str, created_at: str) -> dict[str, Any]:
        return self._run(
            self._upsert_user_async(
                user_id=user_id, github_id=github_id, login=login,
                display_name=display_name, created_at=created_at,
            )
        )

    async def _upsert_user_async(self, *, user_id: str, github_id: str,
                                 login: str, display_name: str,
                                 created_at: str) -> dict[str, Any]:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetchrow(
                    "SELECT * FROM users WHERE id = $1 OR github_id = $2",
                    user_id, github_id,
                )
                if existing is not None:
                    await conn.execute(
                        "UPDATE users SET login = $1, display_name = $2 "
                        "WHERE id = $3",
                        login, display_name, existing["id"],
                    )
                    row = await conn.fetchrow(
                        "SELECT * FROM users WHERE id = $1",
                        existing["id"],
                    )
                    assert row is not None
                    return self._row("users", row)
                return await self._insert_row_async(conn, "users", {
                    "id": user_id,
                    "github_id": github_id,
                    "login": login,
                    "display_name": display_name,
                    "created_at": created_at,
                })

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        async def _get() -> dict[str, Any] | None:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM users WHERE id = $1", user_id
                )
                return self._row("users", row) if row else None

        return self._run(_get())

    def workspaces_for_user(self, user_id: str) -> tuple[dict[str, Any], ...]:
        async def _list() -> tuple[dict[str, Any], ...]:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT w.* FROM workspaces w JOIN workspace_members m "
                    "ON m.workspace_id = w.id WHERE m.user_id = $1 "
                    "ORDER BY w.created_at, w.id",
                    user_id,
                )
                return tuple(self._row("workspaces", r) for r in rows)

        return self._run(_list())

    def demo_workspace(self) -> dict[str, Any] | None:
        async def _demo() -> dict[str, Any] | None:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM workspaces WHERE is_demo = 1"
                )
                return self._row("workspaces", row) if row else None

        return self._run(_demo())

    # -- workspaces -------------------------------------------------------------

    def list_workspaces(self, scope: TenantScope, *, cursor: str | None,
                        limit: int) -> Page:
        async def _page() -> Page:
            async with self._pool.acquire() as conn:
                return await self._fetch_page_async(
                    conn, "workspaces", scope, cursor=cursor, limit=limit
                )

        return self._run(_page())

    def get_workspace(self, scope: TenantScope,
                      workspace_id: str) -> dict[str, Any] | None:
        if not scope.allows(workspace_id):
            return None

        async def _get() -> dict[str, Any] | None:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM workspaces WHERE id = $1", workspace_id
                )
                return self._row("workspaces", row) if row else None

        return self._run(_get())

    def create_workspace(self, *, workspace_id: str, name: str, slug: str,
                         owner_user_id: str, is_demo: bool,
                         created_at: str) -> dict[str, Any]:
        return self._run(
            self._create_workspace_async(
                workspace_id=workspace_id, name=name, slug=slug,
                owner_user_id=owner_user_id, is_demo=is_demo,
                created_at=created_at,
            )
        )

    async def _create_workspace_async(self, *, workspace_id: str, name: str,
                                      slug: str, owner_user_id: str,
                                      is_demo: bool,
                                      created_at: str) -> dict[str, Any]:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                clash = await conn.fetchrow(
                    "SELECT id FROM workspaces WHERE slug = $1", slug
                )
                if clash is not None:
                    raise ConflictError(
                        f"workspace slug '{slug}' already exists"
                    )
                workspace = await self._insert_row_async(
                    conn, "workspaces", {
                        "id": workspace_id,
                        "name": name,
                        "slug": slug,
                        "is_demo": 1 if is_demo else 0,
                        "created_at": created_at,
                    }
                )
                await self._insert_row_async(conn, "workspace_members", {
                    "workspace_id": workspace_id,
                    "user_id": owner_user_id,
                    "role": "owner",
                    "created_at": created_at,
                })
                return workspace

    def list_workspace_activity(self, scope: TenantScope, workspace_id: str,
                                *, limit: int) -> tuple[dict[str, Any], ...]:
        if not scope.allows(workspace_id):
            return ()

        async def _list() -> tuple[dict[str, Any], ...]:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM audit_events WHERE tenant_id = $1 "
                    "ORDER BY ts DESC, id DESC LIMIT $2",
                    workspace_id, limit,
                )
                return tuple(self._row("audit_events", r) for r in rows)

        return self._run(_list())

    # -- missions -----------------------------------------------------------------

    def list_missions(self, scope: TenantScope, *, workspace_id: str | None,
                      cursor: str | None, limit: int) -> Page:
        extra: list[tuple[str, Any]] = []
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra.append(("missions.workspace_id = {n}", workspace_id))

        async def _page() -> Page:
            async with self._pool.acquire() as conn:
                return await self._fetch_page_async(
                    conn, "missions", scope, extra, cursor=cursor, limit=limit
                )

        return self._run(_page())

    def get_mission(self, scope: TenantScope,
                    mission_id: str) -> dict[str, Any] | None:
        async def _get() -> dict[str, Any] | None:
            async with self._pool.acquire() as conn:
                return await self._get_scoped_async(
                    conn, "missions", scope, "id", mission_id
                )

        return self._run(_get())

    def insert_mission(self, *, workspace_id: str, mission_id: str, title: str,
                       status: str, current_revision_id: str | None,
                       created_at: str) -> dict[str, Any]:
        async def _insert() -> dict[str, Any]:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    return await self._insert_row_async(conn, "missions", {
                        "id": mission_id,
                        "workspace_id": workspace_id,
                        "title": title,
                        "status": status,
                        "current_revision_id": current_revision_id,
                        "created_at": created_at,
                    })

        return self._run(_insert())

    def list_mission_revisions(self, scope: TenantScope, mission_id: str,
                               *, cursor: str | None, limit: int) -> Page:
        parent = self.get_mission(scope, mission_id)
        if parent is None:
            return Page(items=(), next_cursor=None)
        extra = [("mission_revisions.mission_id = {n}", mission_id)]

        async def _page() -> Page:
            async with self._pool.acquire() as conn:
                return await self._fetch_page_async(
                    conn, "mission_revisions", scope, extra,
                    cursor=cursor, limit=limit,
                )

        return self._run(_page())

    def get_mission_revision(self, scope: TenantScope,
                             revision_id: str) -> dict[str, Any] | None:
        async def _get() -> dict[str, Any] | None:
            async with self._pool.acquire() as conn:
                return await self._get_scoped_async(
                    conn, "mission_revisions", scope, "id", revision_id
                )

        return self._run(_get())

    def insert_mission_revision(self, *, mission_id: str, revision_id: str,
                                revision: int, payload: dict[str, Any],
                                created_at: str, set_current: bool) -> dict[str, Any]:
        return self._run(
            self._insert_mission_revision_async(
                mission_id=mission_id, revision_id=revision_id,
                revision=revision, payload=payload, created_at=created_at,
                set_current=set_current,
            )
        )

    async def _insert_mission_revision_async(
        self, *, mission_id: str, revision_id: str, revision: int,
        payload: dict[str, Any], created_at: str, set_current: bool,
    ) -> dict[str, Any]:
        # JSON columns serialize ONCE via the shared ``encode_row`` (called
        # by ``_insert_row_async``) — identical bytes on both backends.
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await self._insert_row_async(
                    conn, "mission_revisions", {
                        "id": revision_id,
                        "mission_id": mission_id,
                        "revision": revision,
                        "goals": payload["goals"],
                        "outcomes": payload["outcomes"],
                        "stakeholders": payload["stakeholders"],
                        "measures": payload["measures"],
                        "constraints": payload["constraints"],
                        "preferences": payload["preferences"],
                        "approval": payload["approval"],
                        "created_at": created_at,
                    }
                )
                if set_current:
                    await conn.execute(
                        "UPDATE missions SET current_revision_id = $1 "
                        "WHERE id = $2",
                        revision_id, mission_id,
                    )
                return row

    # -- systems --------------------------------------------------------------------

    def list_systems(self, scope: TenantScope, *, workspace_id: str | None,
                     cursor: str | None, limit: int) -> Page:
        extra: list[tuple[str, Any]] = []
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra.append(("systems.workspace_id = {n}", workspace_id))

        async def _page() -> Page:
            async with self._pool.acquire() as conn:
                return await self._fetch_page_async(
                    conn, "systems", scope, extra, cursor=cursor, limit=limit
                )

        return self._run(_page())

    def get_system(self, scope: TenantScope,
                   system_id: str) -> dict[str, Any] | None:
        async def _get() -> dict[str, Any] | None:
            async with self._pool.acquire() as conn:
                return await self._get_scoped_async(
                    conn, "systems", scope, "id", system_id
                )

        return self._run(_get())

    def get_system_revision(self, scope: TenantScope,
                            revision_id: str) -> dict[str, Any] | None:
        async def _get() -> dict[str, Any] | None:
            async with self._pool.acquire() as conn:
                return await self._get_scoped_async(
                    conn, "system_revisions", scope, "id", revision_id
                )

        return self._run(_get())

    def insert_system(self, *, workspace_id: str, system_id: str, name: str,
                      mode: str, current_revision_id: str | None,
                      created_at: str) -> dict[str, Any]:
        async def _insert() -> dict[str, Any]:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    return await self._insert_row_async(conn, "systems", {
                        "id": system_id,
                        "workspace_id": workspace_id,
                        "name": name,
                        "mode": mode,
                        "current_revision_id": current_revision_id,
                        "created_at": created_at,
                    })

        return self._run(_insert())

    def insert_system_revision(self, *, system_id: str, revision_id: str,
                               revision: int, payload: dict[str, Any],
                               created_at: str, set_current: bool) -> dict[str, Any]:
        return self._run(
            self._insert_system_revision_async(
                system_id=system_id, revision_id=revision_id,
                revision=revision, payload=payload, created_at=created_at,
                set_current=set_current,
            )
        )

    async def _insert_system_revision_async(
        self, *, system_id: str, revision_id: str, revision: int,
        payload: dict[str, Any], created_at: str, set_current: bool,
    ) -> dict[str, Any]:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await self._insert_row_async(
                    conn, "system_revisions", {
                        "id": revision_id,
                        "system_id": system_id,
                        "revision": revision,
                        "state_summary": payload["stateSummary"],
                        "uncertainty": payload["uncertainty"],
                        "source_ref": payload["sourceRef"],
                        "recovery": payload["recovery"],
                        "graph": payload["graph"],
                        "created_at": created_at,
                    }
                )
                if set_current:
                    await conn.execute(
                        "UPDATE systems SET current_revision_id = $1 "
                        "WHERE id = $2",
                        revision_id, system_id,
                    )
                # PUB-05 normalized projection: graph → nodes/edges rows
                # (same transaction, same shared mapping as SQLite).
                parent = await conn.fetchrow(
                    "SELECT workspace_id FROM systems WHERE id = $1",
                    system_id,
                )
                if parent is not None:
                    workspace_id = parent["workspace_id"]
                    graph = payload["graph"] or {}
                    await self._insert_rows_async(
                        conn, "architecture_nodes", graph_node_rows(
                            workspace_id, system_id, revision_id,
                            graph, created_at,
                        )
                    )
                    await self._insert_rows_async(
                        conn, "architecture_edges", graph_edge_rows(
                            workspace_id, system_id, revision_id,
                            graph, created_at,
                        )
                    )
                    await self._insert_rows_async(
                        conn, "architecture_boundary_contracts",
                        graph_boundary_contract_rows(
                            workspace_id, system_id, revision_id,
                            graph, created_at,
                        )
                    )
                return row

    # -- evidence -------------------------------------------------------------------

    def list_evidence(self, scope: TenantScope, *, workspace_id: str | None,
                      system_id: str | None, kind: str | None,
                      status: str | None, cursor: str | None,
                      limit: int) -> Page:
        extra: list[tuple[str, Any]] = []
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra.append(("evidence.workspace_id = {n}", workspace_id))
        if system_id is not None:
            extra.append(("evidence.system_id = {n}", system_id))
        if kind is not None:
            extra.append(("evidence.kind = {n}", kind))
        if status is not None:
            extra.append(("evidence.status = {n}", status))

        async def _page() -> Page:
            async with self._pool.acquire() as conn:
                return await self._fetch_page_async(
                    conn, "evidence", scope, extra, cursor=cursor, limit=limit
                )

        return self._run(_page())

    def insert_evidence(self, *, workspace_id: str, evidence_id: str,
                        payload: dict[str, Any]) -> dict[str, Any]:
        return self._run(
            self._insert_evidence_async(
                workspace_id=workspace_id, evidence_id=evidence_id,
                payload=payload,
            )
        )

    async def _insert_evidence_async(self, *, workspace_id: str,
                                     evidence_id: str,
                                     payload: dict[str, Any]) -> dict[str, Any]:
        # Content-addressed evidence ids dedup identical ingestion (W4) —
        # an identical record already present is returned unchanged.
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetchrow(
                    "SELECT * FROM evidence WHERE id = $1", evidence_id
                )
                if existing is not None:
                    return self._row("evidence", existing)
                row = await self._insert_row_async(conn, "evidence", {
                    "id": evidence_id,
                    "workspace_id": workspace_id,
                    "system_id": payload.get("systemId"),
                    "kind": payload["kind"],
                    "status": payload["status"],
                    "provenance": payload["provenance"],
                    "timestamp": payload.get("timestamp"),
                    "source_revision": payload.get("sourceRevision"),
                    "related_system_state": payload.get("relatedSystemState"),
                    "confidence": payload.get("confidence"),
                    "artifact_ref": payload.get("artifactRef"),
                    "created_at": payload["createdAt"],
                    "result": payload.get("result"),
                })
                # PUB-05 normalized projection: artifact metadata row.
                artifact = evidence_artifact_row(
                    workspace_id, evidence_id, payload
                )
                if artifact is not None:
                    await self._insert_rows_async(
                        conn, "evidence_artifacts", [artifact]
                    )
                return row

    # -- hypotheses -------------------------------------------------------------------

    def list_hypotheses(self, scope: TenantScope, *, workspace_id: str | None,
                        cursor: str | None, limit: int) -> Page:
        extra: list[tuple[str, Any]] = []
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra.append(("hypotheses.workspace_id = {n}", workspace_id))

        async def _page() -> Page:
            async with self._pool.acquire() as conn:
                return await self._fetch_page_async(
                    conn, "hypotheses", scope, extra,
                    cursor=cursor, limit=limit,
                )

        return self._run(_page())

    def insert_hypothesis(self, *, workspace_id: str, hypothesis_id: str,
                          payload: dict[str, Any]) -> dict[str, Any]:
        async def _insert() -> dict[str, Any]:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    row = await self._insert_row_async(conn, "hypotheses", {
                        "id": hypothesis_id,
                        "workspace_id": workspace_id,
                        "statement": payload["statement"],
                        "causal": payload["causal"],
                        "evidence_refs": payload["evidenceRefs"],
                        "status": payload["status"],
                        "created_at": payload["createdAt"],
                    })
                    # PUB-05 normalized projection: causal claim row.
                    causal = causal_hypothesis_row(
                        workspace_id, hypothesis_id, payload
                    )
                    if causal is not None:
                        await self._insert_rows_async(
                            conn, "causal_hypotheses", [causal]
                        )
                    return row

        return self._run(_insert())

    # -- candidates --------------------------------------------------------------------

    def list_candidates(self, scope: TenantScope, *, workspace_id: str | None,
                        cursor: str | None, limit: int) -> Page:
        extra: list[tuple[str, Any]] = []
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra.append(("candidates.workspace_id = {n}", workspace_id))

        async def _page() -> Page:
            async with self._pool.acquire() as conn:
                return await self._fetch_page_async(
                    conn, "candidates", scope, extra,
                    cursor=cursor, limit=limit,
                )

        return self._run(_page())

    def insert_candidate(self, *, workspace_id: str, candidate_id: str,
                         payload: dict[str, Any]) -> dict[str, Any]:
        async def _insert() -> dict[str, Any]:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    row = await self._insert_row_async(conn, "candidates", {
                        "id": candidate_id,
                        "workspace_id": workspace_id,
                        "name": payload["name"],
                        "subgraph_replacement": payload["subgraphReplacement"],
                        "effects": payload["effects"],
                        "costs": payload["costs"],
                        "risks": payload["risks"],
                        "constraints": payload["constraints"],
                        "evidence_refs": payload["evidenceRefs"],
                        "reversibility": payload["reversibility"],
                        "evaluation": payload["evaluation"],
                        "created_at": payload["createdAt"],
                    })
                    # PUB-05 normalized projection: objectives + Pareto rows.
                    await self._insert_rows_async(
                        conn, "candidate_evaluations", candidate_evaluation_rows(
                            workspace_id, candidate_id,
                            payload["evaluation"] or {},
                        )
                    )
                    return row

        return self._run(_insert())

    def get_candidate(self, scope: TenantScope,
                      candidate_id: str) -> dict[str, Any] | None:
        async def _get() -> dict[str, Any] | None:
            async with self._pool.acquire() as conn:
                return await self._get_scoped_async(
                    conn, "candidates", scope, "id", candidate_id
                )

        return self._run(_get())

    # -- assurance ----------------------------------------------------------------------

    def list_assurance(self, scope: TenantScope, *, workspace_id: str | None,
                       candidate_id: str | None, cursor: str | None,
                       limit: int) -> Page:
        extra: list[tuple[str, Any]] = []
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra.append(("assurance_runs.workspace_id = {n}", workspace_id))
        if candidate_id is not None:
            extra.append(("assurance_runs.candidate_id = {n}", candidate_id))

        async def _page() -> Page:
            async with self._pool.acquire() as conn:
                return await self._fetch_page_async(
                    conn, "assurance_runs", scope, extra,
                    cursor=cursor, limit=limit,
                )

        return self._run(_page())

    def insert_assurance(self, *, workspace_id: str, assurance_id: str,
                         payload: dict[str, Any]) -> dict[str, Any]:
        async def _insert() -> dict[str, Any]:
            # The checks column carries the full assurance record (gates +
            # domain reconstruction payload) — identical to SQLite.
            checks_doc = {
                "gates": payload["checks"],
                "domain": payload.get("domain", {}),
            }
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    row = await self._insert_row_async(
                        conn, "assurance_runs", {
                            "id": assurance_id,
                            "workspace_id": workspace_id,
                            "candidate_id": payload["candidateId"],
                            "checks": checks_doc,
                            "verdict": payload["verdict"],
                            "created_at": payload["createdAt"],
                        }
                    )
                    # PUB-05 normalized projection: one row per gate.
                    await self._insert_rows_async(
                        conn, "assurance_results", assurance_result_rows(
                            workspace_id, assurance_id, payload["candidateId"],
                            checks_doc, payload["createdAt"],
                        )
                    )
                    return row

        return self._run(_insert())

    def get_assurance(self, scope: TenantScope,
                      assurance_id: str) -> dict[str, Any] | None:
        async def _get() -> dict[str, Any] | None:
            async with self._pool.acquire() as conn:
                return await self._get_scoped_async(
                    conn, "assurance_runs", scope, "id", assurance_id
                )

        return self._run(_get())

    # -- decisions / authorizations --------------------------------------------------------

    def list_decisions(self, scope: TenantScope, *, workspace_id: str | None,
                       cursor: str | None, limit: int) -> Page:
        extra: list[tuple[str, Any]] = []
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra.append(("decisions.workspace_id = {n}", workspace_id))

        async def _page() -> Page:
            async with self._pool.acquire() as conn:
                return await self._fetch_page_async(
                    conn, "decisions", scope, extra,
                    cursor=cursor, limit=limit,
                )

        return self._run(_page())

    def insert_decision(self, *, workspace_id: str, decision_id: str,
                        payload: dict[str, Any]) -> dict[str, Any]:
        async def _insert() -> dict[str, Any]:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    return await self._insert_row_async(conn, "decisions", {
                        "id": decision_id,
                        "workspace_id": workspace_id,
                        "action": payload["action"],
                        "rationale": payload["rationale"],
                        "evidence_refs": payload["evidenceRefs"],
                        "authority_snapshot": payload["authoritySnapshot"],
                        "expected_impact": payload["expectedImpact"],
                        "risk": payload["risk"],
                        "blast_radius": payload["blastRadius"],
                        "reversibility": payload["reversibility"],
                        "required_approvals": payload["requiredApprovals"],
                        "ask_payload": payload.get("askPayload"),
                        "created_at": payload["createdAt"],
                    })

        return self._run(_insert())

    def get_decision(self, scope: TenantScope,
                     decision_id: str) -> dict[str, Any] | None:
        async def _get() -> dict[str, Any] | None:
            async with self._pool.acquire() as conn:
                return await self._get_scoped_async(
                    conn, "decisions", scope, "id", decision_id
                )

        return self._run(_get())

    def list_authorizations(self, scope: TenantScope, *,
                            workspace_id: str | None,
                            cursor: str | None, limit: int) -> Page:
        extra: list[tuple[str, Any]] = []
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra.append(("authorizations.workspace_id = {n}", workspace_id))

        async def _page() -> Page:
            async with self._pool.acquire() as conn:
                return await self._fetch_page_async(
                    conn, "authorizations", scope, extra,
                    cursor=cursor, limit=limit,
                )

        return self._run(_page())

    def insert_authorization(self, *, workspace_id: str,
                             authorization_id: str,
                             payload: dict[str, Any]) -> dict[str, Any]:
        async def _insert() -> dict[str, Any]:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    return await self._insert_row_async(
                        conn, "authorizations", {
                            "id": authorization_id,
                            "workspace_id": workspace_id,
                            "decision_id": payload.get("decisionId"),
                            "principal": payload["principal"],
                            "scope": payload["scope"],
                            "decision": payload["decision"],
                            "created_at": payload["createdAt"],
                        }
                    )

        return self._run(_insert())

    # -- experiments / executions ------------------------------------------------------------

    def list_experiments(self, scope: TenantScope, *, workspace_id: str | None,
                         candidate_id: str | None, cursor: str | None,
                         limit: int) -> Page:
        extra: list[tuple[str, Any]] = []
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra.append(("experiments.workspace_id = {n}", workspace_id))
        if candidate_id is not None:
            extra.append(("experiments.candidate_id = {n}", candidate_id))

        async def _page() -> Page:
            async with self._pool.acquire() as conn:
                return await self._fetch_page_async(
                    conn, "experiments", scope, extra,
                    cursor=cursor, limit=limit,
                )

        return self._run(_page())

    def insert_experiment(self, *, workspace_id: str, experiment_id: str,
                          payload: dict[str, Any]) -> dict[str, Any]:
        async def _insert() -> dict[str, Any]:
            events_doc = {
                "events": payload["events"],
                "domain": payload.get("domain", {}),
            }
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    row = await self._insert_row_async(conn, "experiments", {
                        "id": experiment_id,
                        "workspace_id": workspace_id,
                        "candidate_id": payload["candidateId"],
                        "status": payload["status"],
                        "events": events_doc,
                        "created_at": payload["createdAt"],
                    })
                    # PUB-05 normalized projection: event log rows.
                    await self._insert_rows_async(
                        conn, "experiment_events", experiment_event_rows(
                            workspace_id, experiment_id, events_doc
                        )
                    )
                    return row

        return self._run(_insert())

    def get_experiment(self, scope: TenantScope,
                       experiment_id: str) -> dict[str, Any] | None:
        async def _get() -> dict[str, Any] | None:
            async with self._pool.acquire() as conn:
                return await self._get_scoped_async(
                    conn, "experiments", scope, "id", experiment_id
                )

        return self._run(_get())

    def list_executions(self, scope: TenantScope, *, workspace_id: str | None,
                        experiment_id: str | None, cursor: str | None,
                        limit: int) -> Page:
        extra: list[tuple[str, Any]] = []
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra.append(("executions.workspace_id = {n}", workspace_id))
        if experiment_id is not None:
            extra.append(("executions.experiment_id = {n}", experiment_id))

        async def _page() -> Page:
            async with self._pool.acquire() as conn:
                return await self._fetch_page_async(
                    conn, "executions", scope, extra,
                    cursor=cursor, limit=limit,
                )

        return self._run(_page())

    def insert_execution(self, *, workspace_id: str, execution_id: str,
                         payload: dict[str, Any]) -> dict[str, Any]:
        async def _insert() -> dict[str, Any]:
            # Content-addressed execution ids make re-dispatch of an
            # IDENTICAL governed request idempotent (directive §8).
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    existing = await conn.fetchrow(
                        "SELECT * FROM executions WHERE id = $1", execution_id
                    )
                    if existing is not None:
                        return self._row("executions", existing)
                    row = await self._insert_row_async(conn, "executions", {
                        "id": execution_id,
                        "workspace_id": workspace_id,
                        "experiment_id": payload.get("experimentId"),
                        "provider": payload["provider"],
                        "request_hash": payload["requestHash"],
                        "receipt": payload.get("receipt"),
                        "artifact_refs": payload["artifactRefs"],
                        "status": payload["status"],
                        "created_at": payload["createdAt"],
                    })
                    # PUB-05 normalized projection: request + receipt rows.
                    await self._insert_rows_async(
                        conn, "execution_requests", [
                            execution_request_row(
                                workspace_id, execution_id, payload
                            )
                        ]
                    )
                    receipt = execution_receipt_row(
                        workspace_id, execution_id, payload
                    )
                    if receipt is not None:
                        await self._insert_rows_async(
                            conn, "execution_receipts", [receipt]
                        )
                    return row

        return self._run(_insert())

    def get_execution(self, scope: TenantScope,
                      execution_id: str) -> dict[str, Any] | None:
        async def _get() -> dict[str, Any] | None:
            async with self._pool.acquire() as conn:
                return await self._get_scoped_async(
                    conn, "executions", scope, "id", execution_id
                )

        return self._run(_get())

    # -- learning / memory ---------------------------------------------------------------------

    def list_learning(self, scope: TenantScope, *, workspace_id: str | None,
                      cursor: str | None, limit: int) -> Page:
        extra: list[tuple[str, Any]] = []
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra.append(("learning_records.workspace_id = {n}", workspace_id))

        async def _page() -> Page:
            async with self._pool.acquire() as conn:
                return await self._fetch_page_async(
                    conn, "learning_records", scope, extra,
                    cursor=cursor, limit=limit,
                )

        return self._run(_page())

    def insert_learning(self, *, workspace_id: str, record_id: str,
                        payload: dict[str, Any]) -> dict[str, Any]:
        async def _insert() -> dict[str, Any]:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    return await self._insert_row_async(
                        conn, "learning_records", {
                            "id": record_id,
                            "workspace_id": workspace_id,
                            "context": payload["context"],
                            "candidate": payload["candidate"],
                            "predicted_effects": payload["predictedEffects"],
                            "actual_effects": payload["actualEffects"],
                            "uncertainty": payload["uncertainty"],
                            "verdict": payload["verdict"],
                            "lessons": payload["lessons"],
                            "created_at": payload["createdAt"],
                        }
                    )

        return self._run(_insert())

    def list_memory(self, scope: TenantScope, *, workspace_id: str | None,
                    cursor: str | None, limit: int) -> Page:
        extra: list[tuple[str, Any]] = []
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra.append(("memory_entries.workspace_id = {n}", workspace_id))

        async def _page() -> Page:
            async with self._pool.acquire() as conn:
                return await self._fetch_page_async(
                    conn, "memory_entries", scope, extra,
                    cursor=cursor, limit=limit,
                )

        return self._run(_page())

    def insert_memory(self, *, workspace_id: str, entry_id: str,
                      payload: dict[str, Any]) -> dict[str, Any]:
        async def _insert() -> dict[str, Any]:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    return await self._insert_row_async(
                        conn, "memory_entries", {
                            "id": entry_id,
                            "workspace_id": workspace_id,
                            "context": payload["context"],
                            "candidate": payload["candidate"],
                            "predicted_effects": payload["predictedEffects"],
                            "actual_effects": payload["actualEffects"],
                            "uncertainty": payload["uncertainty"],
                            "verdict": payload["verdict"],
                            "lessons": payload["lessons"],
                            "created_at": payload["createdAt"],
                        }
                    )

        return self._run(_insert())

    # -- jobs --------------------------------------------------------------------------------------

    def list_jobs(self, scope: TenantScope, *, workspace_id: str | None,
                  type_: str | None, cursor: str | None, limit: int) -> Page:
        extra: list[tuple[str, Any]] = []
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra.append(("jobs.tenant_id = {n}", workspace_id))
        if type_ is not None:
            extra.append(("jobs.type = {n}", type_))

        async def _page() -> Page:
            async with self._pool.acquire() as conn:
                return await self._fetch_page_async(
                    conn, "jobs", scope, extra, cursor=cursor, limit=limit
                )

        return self._run(_page())

    def get_job(self, scope: TenantScope, job_id: str) -> dict[str, Any] | None:
        async def _get() -> dict[str, Any] | None:
            async with self._pool.acquire() as conn:
                return await self._get_scoped_async(
                    conn, "jobs", scope, "id", job_id
                )

        return self._run(_get())

    def get_job_by_idempotency_key(self, scope: TenantScope,
                                   key: str) -> dict[str, Any] | None:
        async def _get() -> dict[str, Any] | None:
            async with self._pool.acquire() as conn:
                return await self._get_scoped_async(
                    conn, "jobs", scope, "idempotency_key", key
                )

        return self._run(_get())

    def insert_job(self, *, workspace_id: str, job_id: str,
                   payload: dict[str, Any]) -> dict[str, Any]:
        async def _insert() -> dict[str, Any]:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    return await self._insert_row_async(conn, "jobs", {
                        "id": job_id,
                        "tenant_id": workspace_id,
                        "type": payload["type"],
                        "requested_by": payload["requestedBy"],
                        "authority_snapshot": payload["authoritySnapshot"],
                        "input_hash": payload["inputHash"],
                        "source_revision": payload["sourceRevision"],
                        "provider": payload["provider"],
                        "status": payload["status"],
                        "started_at": payload.get("startedAt"),
                        "completed_at": payload.get("completedAt"),
                        "receipt": payload.get("receipt"),
                        "artifact_refs": payload["artifactRefs"],
                        "error_state": payload.get("errorState"),
                        "idempotency_key": payload.get("idempotencyKey"),
                        "created_at": payload["createdAt"],
                    })

        return self._run(_insert())

    def update_job(self, scope: TenantScope, job_id: str,
                   *, payload_patch: dict[str, Any]) -> dict[str, Any] | None:
        return self._run(
            self._update_job_async(scope, job_id, payload_patch)
        )

    async def _update_job_async(self, scope: TenantScope, job_id: str,
                                payload_patch: dict[str, Any]) -> dict[str, Any] | None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                current = await self._get_scoped_async(
                    conn, "jobs", scope, "id", job_id
                )
                if current is None:
                    return None
                cols = _JSON_COLUMNS["jobs"]
                assignments: list[str] = []
                params: list[Any] = []
                for key, value in payload_patch.items():
                    snake = _snake(key)
                    idx = len(params) + 1
                    assignments.append(f"{snake} = ${idx}")
                    params.append(
                        json.dumps(value, sort_keys=True)
                        if snake in cols else value
                    )
                if assignments:
                    params.append(job_id)
                    await conn.execute(
                        f"UPDATE jobs SET {', '.join(assignments)} "
                        f"WHERE id = ${len(params)}",
                        *params,
                    )
                row = await conn.fetchrow(
                    "SELECT * FROM jobs WHERE id = $1", job_id
                )
                return self._row("jobs", row) if row else None

    # -- audit (append-only; every mutation writes one row — S17) -----------------------------------

    def append_audit(self, *, tenant_id: str, actor: str, action: str,
                     target: str, meta: dict[str, Any], ts: str,
                     audit_id: str) -> dict[str, Any]:
        return self._run(
            self._append_audit_async(
                tenant_id=tenant_id, actor=actor, action=action,
                target=target, meta=meta, ts=ts, audit_id=audit_id,
            )
        )

    async def _append_audit_async(self, *, tenant_id: str, actor: str,
                                  action: str, target: str,
                                  meta: dict[str, Any], ts: str,
                                  audit_id: str) -> dict[str, Any]:
        # Audit events are append-only: repeated identical events are
        # distinct records — a sequence suffix keeps the caller-supplied
        # content id unique per write (identical to the SQLite adapter).
        meta_json = encode_row("audit_events", {"meta": meta})["meta"]
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                candidate_id = audit_id
                seq = 0
                while True:
                    row = await conn.fetchrow(
                        "INSERT INTO audit_events (id, tenant_id, actor, "
                        "action, target, meta, ts) VALUES ($1, $2, $3, $4, "
                        "$5, $6, $7) ON CONFLICT (id) DO NOTHING RETURNING *",
                        candidate_id, tenant_id, actor, action, target,
                        meta_json, ts,
                    )
                    if row is not None:
                        return self._row("audit_events", row)
                    candidate_id = f"{audit_id}-{seq:04d}"
                    seq += 1
                    if seq > 1000:  # pragma: no cover - defensive
                        raise ConflictError(
                            f"audit id {audit_id!r} exhausted its "
                            "disambiguation sequence"
                        )


def build_neon_persistence(database_url: str) -> NeonPostgresPersistence:
    """The Neon (PostgreSQL) adapter factory (PUB-05).

    Fail-closed: an invalid/missing DSN or a missing asyncpg driver aborts
    boot with a precise error — never a silent fallback to LOCAL SQLite.
    """
    return NeonPostgresPersistence(database_url)
