"""PUB-05 — LOCAL (SQLite) ↔ Neon (PostgreSQL) PARITY: the same migration
set, the same mapping, the same deterministic demo seed, the same seam
behavior — verified against a REAL PostgreSQL (LOCAL ``pg``; CI Postgres
when reachable). Runs wherever asyncpg + a Postgres are available and skips
cleanly otherwise (truthful skip reasons, never a fabricated pass).

Parity dimensions (all asserted SQLite == PostgreSQL):
  - every entity collection (row-for-row, field-for-field);
  - every single-resource getter;
  - the deterministic demo seed (identical content, idempotent re-run);
  - tenant scoping (cross-tenant ids yield zero rows on BOTH backends);
  - truth-state preservation (the six states surface verbatim);
  - cursor pagination (identical opaque cursors, identical pages);
  - filters (workspace/system/kind/status/candidate/experiment/type);
  - dedup semantics (evidence + execution content-addressed ids);
  - conflict semantics (duplicate workspace slug);
  - the normalized §11 tables (identical row counts, doc↔rows equivalence);
  - the FastAPI control plane booting on the Neon adapter (integration)."""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

fastapi = pytest.importorskip(
    "fastapi",
    reason="PUB-05 API integration requires the 'api' dependency group",
)

REPO_ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(REPO_ROOT / "src"), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from providers.neon.seam import TenantScope  # noqa: E402

_PG_PROBES = (
    "postgresql://postgres:postgres@127.0.0.1:5432/postgres",
    "postgresql://postgres@127.0.0.1:54329/postgres",
)

ALL_SIX = {
    "SUCCESS", "EMPTY", "FAILED", "UNKNOWN", "UNSUPPORTED", "UNAVAILABLE",
}


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


def _swap_db(base: str, db: str) -> str:
    prefix, rest = base.split("://", 1)
    if "@" in rest:
        creds, host_part = rest.split("@", 1)
        host, _ = host_part.split("/", 1)
        return f"{prefix}://{creds}@{host}/{db}"
    host, _ = rest.split("/", 1)
    return f"{prefix}://{host}/{db}"


@pytest.fixture(scope="module")
def pg_dsn() -> str:
    pytest.importorskip(
        "asyncpg",
        reason="Postgres parity requires asyncpg (the Neon adapter driver)",
    )
    dsn = _discover_pg_dsn()
    if dsn is None:
        pytest.skip(
            "no Postgres reachable (SOS_TEST_DATABASE_URL unset and no "
            "LOCAL pg on the probe ports) — parity is verified only where "
            "a real backend exists (contract §D PUB-05 acceptance)"
        )
    return dsn


@pytest.fixture(scope="module")
def pg_seeded(pg_dsn: str):
    """A module-scoped seeded Neon adapter + the matching seeded SQLite
    adapter (same migration set, same seed) for the parity assertions."""
    from db.seeds.demo_seed import seed_demo
    from providers.neon.cloud import NeonPostgresPersistence
    from providers.neon.local import LocalSqlitePersistence

    asyncpg = pytest.importorskip("asyncpg")
    database = f"sos_pub05_parity_{uuid.uuid4().hex[:10]}"

    async def _recreate() -> None:
        admin = await asyncpg.connect(pg_dsn)
        try:
            await admin.execute(
                f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'
            )
            await admin.execute(f'CREATE DATABASE "{database}"')
        finally:
            await admin.close()

    asyncio.run(_recreate())

    sqlite_path = Path(
        __import__("tempfile").gettempdir()
    ) / f"{database}.sqlite3"
    sqlite = LocalSqlitePersistence(str(sqlite_path))
    sqlite.migrate()
    seed_demo(sqlite)

    dsn = _swap_db(pg_dsn, database)
    neon = NeonPostgresPersistence(dsn)
    neon.migrate()
    seed_demo(neon)

    yield sqlite, neon, dsn

    sqlite.close()
    neon.close()
    sqlite_path.unlink(missing_ok=True)

    async def _drop() -> None:
        admin = await asyncpg.connect(pg_dsn)
        try:
            await admin.execute(
                f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'
            )
        finally:
            await admin.close()

    asyncio.run(_drop())


def _norm(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _norm(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_norm(v) for v in value]
    return value


SCOPE = TenantScope(workspace_ids=frozenset({"ws-demo", "ws-alice", "ws-bob"}))
FOREIGN = TenantScope(workspace_ids=frozenset({"ws-other"}))

COLLECTIONS = {
    "workspaces": lambda a: a.list_workspaces(SCOPE, cursor=None, limit=100).items,
    "missions": lambda a: a.list_missions(
        SCOPE, workspace_id=None, cursor=None, limit=100).items,
    "mission_revisions": lambda a: a.list_mission_revisions(
        SCOPE, "mission-demo-1", cursor=None, limit=100).items,
    "systems": lambda a: a.list_systems(
        SCOPE, workspace_id=None, cursor=None, limit=100).items,
    "evidence": lambda a: a.list_evidence(
        SCOPE, workspace_id=None, system_id=None, kind=None, status=None,
        cursor=None, limit=100).items,
    "hypotheses": lambda a: a.list_hypotheses(
        SCOPE, workspace_id=None, cursor=None, limit=100).items,
    "candidates": lambda a: a.list_candidates(
        SCOPE, workspace_id=None, cursor=None, limit=100).items,
    "assurance": lambda a: a.list_assurance(
        SCOPE, workspace_id=None, candidate_id=None, cursor=None, limit=100).items,
    "decisions": lambda a: a.list_decisions(
        SCOPE, workspace_id=None, cursor=None, limit=100).items,
    "authorizations": lambda a: a.list_authorizations(
        SCOPE, workspace_id=None, cursor=None, limit=100).items,
    "experiments": lambda a: a.list_experiments(
        SCOPE, workspace_id=None, candidate_id=None, cursor=None, limit=100).items,
    "executions": lambda a: a.list_executions(
        SCOPE, workspace_id=None, experiment_id=None, cursor=None, limit=100).items,
    "learning": lambda a: a.list_learning(
        SCOPE, workspace_id=None, cursor=None, limit=100).items,
    "memory": lambda a: a.list_memory(
        SCOPE, workspace_id=None, cursor=None, limit=100).items,
    "jobs": lambda a: a.list_jobs(
        SCOPE, workspace_id=None, type_=None, cursor=None, limit=100).items,
}


@pytest.mark.parametrize("entity", sorted(COLLECTIONS))
def test_collection_parity(pg_seeded, entity: str) -> None:
    sqlite, neon, _ = pg_seeded
    sqlite_rows = [_norm(r) for r in COLLECTIONS[entity](sqlite)]
    neon_rows = [_norm(r) for r in COLLECTIONS[entity](neon)]
    assert sqlite_rows == neon_rows, (
        f"{entity}: SQLite and PostgreSQL rows diverged — first difference "
        "reported by pytest is the exact field at fault"
    )
    assert sqlite_rows, f"{entity}: the demo dataset must be non-empty"


def test_single_resource_getters_parity(pg_seeded) -> None:
    sqlite, neon, _ = pg_seeded
    assurance_id = COLLECTIONS["assurance"](sqlite)[0]["id"]
    decision_id = COLLECTIONS["decisions"](sqlite)[0]["id"]
    job_id = COLLECTIONS["jobs"](sqlite)[0]["id"]
    getters = {
        "mission": lambda a: a.get_mission(SCOPE, "mission-demo-1"),
        "mission_revision": lambda a: a.get_mission_revision(
            SCOPE, "mission-demo-1-r2"),
        "workspace": lambda a: a.get_workspace(SCOPE, "ws-demo"),
        "system": lambda a: a.get_system(SCOPE, "sys-demo-example-api"),
        "system_revision": lambda a: a.get_system_revision(
            SCOPE, "sysrev-demo-2"),
        "candidate": lambda a: a.get_candidate(SCOPE, "cand-demo-cache"),
        "assurance": lambda a: a.get_assurance(SCOPE, assurance_id),
        "decision": lambda a: a.get_decision(SCOPE, decision_id),
        "experiment": lambda a: a.get_experiment(SCOPE, "exp-demo-cache"),
        "execution": lambda a: a.get_execution(SCOPE, "exec-demo-1"),
        "job": lambda a: a.get_job(SCOPE, job_id),
    }
    for name, getter in getters.items():
        assert _norm(getter(sqlite)) == _norm(getter(neon)), name


def test_users_and_membership_parity(pg_seeded) -> None:
    sqlite, neon, _ = pg_seeded
    assert _norm(sqlite.get_user("user-demo-owner")) == _norm(
        neon.get_user("user-demo-owner")
    )
    assert _norm(sqlite.get_user("missing-user")) is None
    assert _norm(neon.get_user("missing-user")) is None
    assert [
        _norm(r) for r in sqlite.workspaces_for_user("user-alice")
    ] == [_norm(r) for r in neon.workspaces_for_user("user-alice")]
    assert _norm(sqlite.demo_workspace()) == _norm(neon.demo_workspace())


def test_workspace_activity_parity(pg_seeded) -> None:
    sqlite, neon, _ = pg_seeded
    sqlite_rows = [_norm(r) for r in sqlite.list_workspace_activity(
        SCOPE, "ws-demo", limit=10
    )]
    neon_rows = [_norm(r) for r in neon.list_workspace_activity(
        SCOPE, "ws-demo", limit=10
    )]
    assert sqlite_rows == neon_rows
    assert sqlite_rows, "the demo audit trail must be non-empty"


def test_seed_idempotent_on_postgres(pg_seeded) -> None:
    sqlite, neon, _ = pg_seeded
    from db.seeds.demo_seed import seed_demo

    assert neon.is_seeded() is True
    result = seed_demo(neon)
    assert result["seeded"] is False  # the demo workspace already exists
    # and the content is unchanged (no duplicate rows)
    assert len(COLLECTIONS["evidence"](neon)) == len(
        COLLECTIONS["evidence"](sqlite)
    )


def test_tenant_scoping_zero_rows_both_backends(pg_seeded) -> None:
    """SECURITY S5 parity: a foreign TenantScope yields zero rows / None on
    BOTH backends — the adapter, not the route, owns the scope filter."""
    sqlite, neon, _ = pg_seeded
    for adapter in (sqlite, neon):
        assert adapter.get_mission(FOREIGN, "mission-demo-1") is None
        assert adapter.get_system(FOREIGN, "sys-demo-example-api") is None
        assert adapter.get_workspace(FOREIGN, "ws-demo") is None
        assert adapter.get_candidate(FOREIGN, "cand-demo-cache") is None
        assert adapter.get_experiment(FOREIGN, "exp-demo-cache") is None
        assert adapter.get_execution(FOREIGN, "exec-demo-1") is None
        assert adapter.get_job(FOREIGN, "job-demo-recovery-1") is None
        page = adapter.list_evidence(
            FOREIGN, workspace_id=None, system_id=None, kind=None,
            status=None, cursor=None, limit=100,
        )
        assert page.items == () and page.next_cursor is None
        page = adapter.list_missions(
            FOREIGN, workspace_id=None, cursor=None, limit=100
        )
        assert page.items == ()
        # a workspace-scoped query for an unallowed workspace: empty page
        page = adapter.list_evidence(
            SCOPE, workspace_id="ws-other", system_id=None, kind=None,
            status=None, cursor=None, limit=100,
        )
        assert page.items == ()
        assert adapter.list_workspace_activity(
            FOREIGN, "ws-demo", limit=10
        ) == ()


def test_truth_states_surface_verbatim_on_postgres(pg_seeded) -> None:
    sqlite, neon, _ = pg_seeded
    for adapter in (sqlite, neon):
        items = COLLECTIONS["evidence"](adapter)
        assert {e["status"] for e in items} == ALL_SIX
        # filter round-trips per state
        for status in sorted(ALL_SIX):
            page = adapter.list_evidence(
                SCOPE, workspace_id=None, system_id=None, kind=None,
                status=status, cursor=None, limit=50,
            )
            assert page.items, status
            assert all(e["status"] == status for e in page.items)


def test_cursor_pagination_parity(pg_seeded) -> None:
    sqlite, neon, _ = pg_seeded
    for limit in (3, 5, 7):
        seen: dict[str, list[str]] = {"sqlite": [], "neon": []}
        for name, adapter in (("sqlite", sqlite), ("neon", neon)):
            cursor: str | None = None
            while True:
                page = adapter.list_evidence(
                    SCOPE, workspace_id=None, system_id=None, kind=None,
                    status=None, cursor=cursor, limit=limit,
                )
                seen[name].extend(e["id"] for e in page.items)
                if page.next_cursor is None:
                    break
                cursor = page.next_cursor
        assert seen["sqlite"] == seen["neon"], (
            f"paginated evidence ids diverged at limit={limit}"
        )
        assert len(seen["sqlite"]) == len(COLLECTIONS["evidence"](sqlite))
        assert len(set(seen["sqlite"])) == len(seen["sqlite"])  # no dupes


def test_filters_parity(pg_seeded) -> None:
    sqlite, neon, _ = pg_seeded
    cases = [
        dict(workspace_id="ws-demo"),
        dict(kind="runtime_observation"),
        dict(status="UNAVAILABLE"),
        dict(system_id="sys-demo-example-api"),
    ]
    for case in cases:
        defaults = {"workspace_id": None, "system_id": None, "kind": None,
                    "status": None, "cursor": None, "limit": 50}
        sqlite_rows = [_norm(r) for r in sqlite.list_evidence(
            SCOPE, **{**defaults, **case},
        ).items]
        neon_rows = [_norm(r) for r in neon.list_evidence(
            SCOPE, **{**defaults, **case},
        ).items]
        assert sqlite_rows == neon_rows, case
        assert sqlite_rows, case


def test_candidate_experiment_job_filters_parity(pg_seeded) -> None:
    sqlite, neon, _ = pg_seeded
    assert [_norm(r) for r in sqlite.list_assurance(
        SCOPE, workspace_id=None, candidate_id="cand-demo-cache",
        cursor=None, limit=50,
    ).items] == [_norm(r) for r in neon.list_assurance(
        SCOPE, workspace_id=None, candidate_id="cand-demo-cache",
        cursor=None, limit=50,
    ).items]
    assert [_norm(r) for r in sqlite.list_experiments(
        SCOPE, workspace_id=None, candidate_id="cand-demo-cache",
        cursor=None, limit=50,
    ).items] == [_norm(r) for r in neon.list_experiments(
        SCOPE, workspace_id=None, candidate_id="cand-demo-cache",
        cursor=None, limit=50,
    ).items]
    assert [_norm(r) for r in sqlite.list_executions(
        SCOPE, workspace_id=None, experiment_id="exp-demo-cache",
        cursor=None, limit=50,
    ).items] == [_norm(r) for r in neon.list_executions(
        SCOPE, workspace_id=None, experiment_id="exp-demo-cache",
        cursor=None, limit=50,
    ).items]


def test_evidence_and_execution_dedup_parity(pg_seeded) -> None:
    """Content-addressed ids: identical re-ingestion returns the existing
    row unchanged on BOTH backends (no duplicate side effects)."""
    sqlite, neon, _ = pg_seeded
    original_sqlite = COLLECTIONS["evidence"](sqlite)[0]
    original_neon = COLLECTIONS["evidence"](neon)[0]
    payload = {
        "kind": original_sqlite["kind"],
        "status": original_sqlite["status"],
        "provenance": original_sqlite["provenance"],
        "timestamp": original_sqlite["timestamp"],
        "sourceRevision": original_sqlite["source_revision"],
        "relatedSystemState": original_sqlite["related_system_state"],
        "confidence": original_sqlite["confidence"],
        "artifactRef": original_sqlite["artifact_ref"],
        "createdAt": original_sqlite["created_at"],
        "result": original_sqlite["result"],
    }
    again_sqlite = sqlite.insert_evidence(
        workspace_id="ws-demo", evidence_id=original_sqlite["id"],
        payload=payload,
    )
    again_neon = neon.insert_evidence(
        workspace_id="ws-demo", evidence_id=original_neon["id"],
        payload=payload,
    )
    assert _norm(again_sqlite) == _norm(original_sqlite)
    assert _norm(again_neon) == _norm(original_neon)
    assert len(COLLECTIONS["evidence"](sqlite)) == len(
        COLLECTIONS["evidence"](neon)
    )


def test_workspace_slug_conflict_parity(pg_seeded) -> None:
    sqlite, neon, _ = pg_seeded
    from providers.neon.seam import ConflictError

    for adapter in (sqlite, neon):
        with pytest.raises(ConflictError):
            adapter.create_workspace(
                workspace_id=f"ws-{uuid.uuid4().hex[:8]}",
                name="Duplicate", slug="demo",
                owner_user_id="user-demo-owner", is_demo=False,
                created_at="2026-01-01T00:00:00Z",
            )


def test_update_job_parity(pg_seeded) -> None:
    """Job patch updates flow identically (JSON columns re-encoded)."""
    sqlite, neon, _ = pg_seeded
    job_id = next(
        j["id"] for j in COLLECTIONS["jobs"](sqlite)
        if j["status"] == "succeeded"
    )
    patch = {
        "status": "succeeded",
        "completedAt": "2026-05-23T17:00:00Z",
        "receipt": {"demo": True, "outcome": "SUCCESS"},
    }
    updated_sqlite = sqlite.update_job(SCOPE, job_id, payload_patch=patch)
    updated_neon = neon.update_job(SCOPE, job_id, payload_patch=patch)
    assert updated_sqlite is not None and updated_neon is not None
    assert _norm(updated_sqlite) == _norm(updated_neon)
    # scope miss: None on both
    assert sqlite.update_job(FOREIGN, job_id, payload_patch=patch) is None
    assert neon.update_job(FOREIGN, job_id, payload_patch=patch) is None


def test_append_audit_disambiguates_identical_ids_parity(pg_seeded) -> None:
    """Repeated identical audit events are distinct rows (suffix keeps the
    content id unique) — identical behavior on both backends."""
    sqlite, neon, _ = pg_seeded
    base = f"audit-parity-{uuid.uuid4().hex[:8]}"
    meta = {"demo": True, "n": 1}
    rows_sqlite = [
        sqlite.append_audit(
            tenant_id="ws-demo", actor="user:test", action="test.audit",
            target="test", meta=meta, ts="2026-01-01T00:00:00Z",
            audit_id=base,
        )
        for _ in range(3)
    ]
    rows_neon = [
        neon.append_audit(
            tenant_id="ws-demo", actor="user:test", action="test.audit",
            target="test", meta=meta, ts="2026-01-01T00:00:00Z",
            audit_id=base,
        )
        for _ in range(3)
    ]
    assert [r["id"] for r in rows_sqlite] == [r["id"] for r in rows_neon]
    assert [r["id"] for r in rows_sqlite] == [base, f"{base}-0000", f"{base}-0001"]
    assert all(_norm(r) == _norm(n) for r, n in zip(rows_sqlite, rows_neon))


def test_normalized_tables_parity(pg_seeded) -> None:
    """The normalized §11 tables carry identical row counts on both
    backends, and the JSON-heavy rows (execution receipts) are identical
    after the shared decode."""
    sqlite, neon, dsn = pg_seeded
    asyncpg = pytest.importorskip("asyncpg")

    tables = (
        "architecture_nodes", "architecture_edges",
        "architecture_boundary_contracts", "evidence_artifacts",
        "causal_hypotheses", "candidate_evaluations", "assurance_results",
        "experiment_events", "execution_requests", "execution_receipts",
    )

    async def _pg_rows(table: str) -> list[dict]:
        conn = await asyncpg.connect(dsn)
        try:
            return [dict(r) for r in await conn.fetch(
                f"SELECT * FROM {table} ORDER BY id"
            )]
        finally:
            await conn.close()

    from db.mapping import decode_row

    empty_allowed = {"architecture_boundary_contracts"}  # demo graphs carry none
    for table in tables:
        sqlite_count = sqlite._fetchone(
            f"SELECT COUNT(*) AS n FROM {table}"
        )["n"]
        pg_rows = asyncio.run(_pg_rows(table))
        assert sqlite_count == len(pg_rows), table
        if table not in empty_allowed:
            assert pg_rows, table

    # deep equality on the all-columnar execution receipt row
    sqlite_receipt = decode_row(
        "execution_receipts",
        dict(sqlite._fetchone(
            "SELECT * FROM execution_receipts WHERE "
            "execution_id = 'exec-demo-1'"
        )),
    )
    pg_receipt = None
    for row in asyncio.run(_pg_rows("execution_receipts")):
        decoded = decode_row("execution_receipts", row)
        if decoded["execution_id"] == "exec-demo-1":
            pg_receipt = decoded
    assert pg_receipt is not None
    assert _norm(sqlite_receipt) == _norm(pg_receipt)


def test_graph_doc_rows_equivalence_on_postgres(pg_seeded) -> None:
    """On PostgreSQL: the doc column (system_revisions.graph JSONB) equals
    the reassembly of the normalized architecture rows — the §11 relational
    projection IS the stored graph (mapping only, no interpretation)."""
    _, neon, dsn = pg_seeded
    asyncpg = pytest.importorskip("asyncpg")
    from db.mapping import decode_row, rows_to_graph

    async def _run() -> None:
        conn = await asyncpg.connect(dsn)
        try:
            for revision_id in ("sysrev-demo-1", "sysrev-demo-2"):
                doc = await conn.fetchval(
                    "SELECT graph FROM system_revisions WHERE id = $1",
                    revision_id,
                )
                node_rows = [
                    decode_row("architecture_nodes", dict(r)) for r in
                    await conn.fetch(
                        "SELECT * FROM architecture_nodes WHERE "
                        "system_revision_id = $1 ORDER BY position",
                        revision_id,
                    )
                ]
                edge_rows = [
                    decode_row("architecture_edges", dict(r)) for r in
                    await conn.fetch(
                        "SELECT * FROM architecture_edges WHERE "
                        "system_revision_id = $1 ORDER BY position",
                        revision_id,
                    )
                ]
                contract_rows = [
                    decode_row("architecture_boundary_contracts", dict(r))
                    for r in await conn.fetch(
                        "SELECT * FROM architecture_boundary_contracts "
                        "WHERE system_revision_id = $1 ORDER BY position",
                        revision_id,
                    )
                ]
                import json as _json

                assert rows_to_graph(node_rows, edge_rows, contract_rows) == (
                    _json.loads(doc)
                )
        finally:
            await conn.close()

    asyncio.run(_run())


def test_health_truthful_on_postgres(pg_seeded) -> None:
    _, neon, _ = pg_seeded
    health = neon.health_check()
    assert health.status == "SUCCESS"
    assert "postgres ok" in health.detail
    assert "asyncpg" in health.detail
    # truthful failure under a broken adapter (fail-closed, never a fake ok)
    from providers.neon.cloud import NeonPostgresPersistence

    class _Broken(NeonPostgresPersistence):  # type: ignore[misc]
        def __init__(self) -> None:  # bypass pool construction
            self._db_label = "broken"
            self._call_timeout = 5.0
            self._closed = True

        def _run(self, coro):  # force the failure path
            raise RuntimeError("connection gone")

    broken = _Broken()
    broken_health = broken.health_check()
    assert broken_health.status == "FAILED"
    assert "connection gone" in broken_health.detail


def test_control_plane_boots_on_neon_persistence(pg_dsn: str) -> None:
    """Integration: create_app with SOS_PERSISTENCE=neon boots the Neon
    adapter, migrates + seeds the demo dataset through the app factory and
    serves the /api/v1 surface over PostgreSQL (truthful health, anonymous
    demo reads, all six truth states)."""
    import tempfile

    from fastapi.testclient import TestClient

    from services.api.config import Settings
    from services.api.main import create_app

    asyncpg = pytest.importorskip("asyncpg")
    database = f"sos_pub05_boot_{uuid.uuid4().hex[:10]}"

    async def _recreate() -> None:
        admin = await asyncpg.connect(pg_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
            await admin.execute(f'CREATE DATABASE "{database}"')
        finally:
            await admin.close()

    asyncio.run(_recreate())
    dsn = _swap_db(pg_dsn, database)

    defaults: dict[str, Any] = {
        "env": "local",
        "persistence_mode": "neon",
        "coordination_mode": "local",
        "artifacts_mode": "local",
        "execution_mode": "demo",
        "database_url": dsn,
        "redis_url": None,
        "r2_endpoint": None,
        "r2_access_key_id": None,
        "r2_secret_access_key": None,
        "r2_bucket": None,
        "apify_token": None,
        "apify_actor_id": None,
        "github_client_id": None,
        "github_client_secret": None,
        "session_secret": None,
        "github_source_pat": None,
        "job_callback_secret": None,
        "api_base_url": None,
        "web_base_url": None,
        "rate_anon_per_min": 1000,
        "rate_user_per_min": 1000,
        "rate_write_per_min": 1000,
        "rate_job_per_hour": 1000,
        "rate_recovery_per_hour": 1000,
        "rate_artifact_max_mb": 50,
        "rate_body_max_mb": 1,
        "apify_max_concurrent": 2,
        "local_db_path": str(
            Path(tempfile.gettempdir()) / f"{database}.sqlite3"
        ),
        "local_artifacts_dir": str(
            Path(tempfile.gettempdir()) / f"{database}-artifacts"
        ),
    }
    app = create_app(Settings(**defaults))
    try:
        with TestClient(app) as client:
            health = client.get("/api/v1/health").json()
            assert health["status"] == "ok"
            assert health["checks"]["persistence"]["mode"] == "neon"
            assert health["checks"]["persistence"]["status"] == "SUCCESS"
            assert "postgres ok" in health["checks"]["persistence"]["detail"]

            response = client.get("/api/v1/evidence")
            assert response.status_code == 200
            items = response.json()["items"]
            assert {e["status"] for e in items} == ALL_SIX

            response = client.get("/api/v1/workspaces/ws-demo")
            assert response.status_code == 200
            assert response.json()["slug"] == "demo"

            response = client.get("/api/v1/systems/sys-demo-example-api")
            assert response.status_code == 200
            system = response.json()
            assert system["mode"] == "brownfield"
            assert system["currentRevision"]["graph"]["nodes"]

            response = client.get("/api/v1/missions")
            assert response.status_code == 200
            assert response.json()["items"]
    finally:
        app.state.container.persistence.close()

        async def _drop() -> None:
            admin = await asyncpg.connect(pg_dsn)
            try:
                await admin.execute(
                    f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'
                )
            finally:
                await admin.close()

        asyncio.run(_drop())
