"""PUB-05 — the Neon adapter itself: fail-closed configuration, DSN
normalization, the sync-seam bridge over the async driver, concurrency and
lifecycle. The DSN/config tests run WITHOUT asyncpg (pure functions); the
driver-dependent tests run against a real Postgres when available."""
from __future__ import annotations

import asyncio
import os
import sys
import threading
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(REPO_ROOT / "src"), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from providers.neon.cloud import (  # noqa: E402
    NeonConfigError,
    NeonPostgresPersistence,
    NeonTimeoutError,
    _dsn_label,
    normalize_database_url,
)

# ---------------------------------------------------------------------------
# DSN validation / fail-closed configuration (no asyncpg required)
# ---------------------------------------------------------------------------


def test_normalize_accepts_all_postgres_dsn_forms() -> None:
    assert (
        normalize_database_url("postgresql://u:p@host/db?sslmode=require")
        == "postgresql://u:p@host/db?sslmode=require"
    )
    assert (
        normalize_database_url("postgres://u:p@host/db")
        == "postgres://u:p@host/db"
    )
    # the SQLAlchemy-style driver suffix is accepted and stripped
    assert (
        normalize_database_url(
            "postgresql+asyncpg://u:p@host/db?sslmode=require"
        )
        == "postgresql://u:p@host/db?sslmode=require"
    )


@pytest.mark.parametrize("bad", [None, "", "None", "mysql://x/y", "host db"])
def test_invalid_dsn_fails_closed_with_precise_error(bad) -> None:
    """A missing/malformed DSN aborts boot fail-closed — never a silent
    fallback to the LOCAL SQLite adapter (SECURITY threat notes)."""
    with pytest.raises(NeonConfigError) as excinfo:
        normalize_database_url(bad)
    message = str(excinfo.value)
    assert "SOS_DATABASE_URL" in message
    assert "PUB-05" in message
    assert "fail-closed" in message


def test_dsn_label_never_leaks_credentials() -> None:
    label = _dsn_label("postgresql://user:supersecret@ep-x.neon.tech/db?sslmode=require")
    assert "supersecret" not in label
    assert "user" not in label
    assert label.endswith("/db")


def test_create_app_neon_without_dsn_fails_closed(tmp_path: Path) -> None:
    """The PUB-01 contract test's shape: selecting SOS_PERSISTENCE=neon
    without a valid DSN aborts app construction with a PUB-05-precise
    error (fail-closed; still true now the adapter EXISTS)."""
    pytest.importorskip(
        "fastapi",
        reason="create_app requires the 'api' dependency group",
    )
    from services.api.config import Settings
    from services.api.main import create_app

    settings = Settings(
        env="local",
        persistence_mode="neon",
        coordination_mode="local",
        artifacts_mode="local",
        execution_mode="demo",
        database_url=None,
        redis_url=None,
        r2_endpoint=None,
        r2_access_key_id=None,
        r2_secret_access_key=None,
        r2_bucket=None,
        apify_token=None,
        apify_actor_id=None,
        github_client_id=None,
        github_client_secret=None,
        session_secret=None,
        github_source_pat=None,
        job_callback_secret=None,
        api_base_url=None,
        web_base_url=None,
        rate_anon_per_min=1000,
        rate_user_per_min=1000,
        rate_write_per_min=1000,
        rate_job_per_hour=1000,
        rate_recovery_per_hour=1000,
        rate_artifact_max_mb=50,
        rate_body_max_mb=1,
        apify_max_concurrent=2,
        local_db_path=str(tmp_path / "api.sqlite3"),
        local_artifacts_dir=str(tmp_path / "artifacts"),
    )
    with pytest.raises(Exception) as excinfo:
        create_app(settings)
    assert "PUB-05" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Driver-dependent tests (a real Postgres when reachable)
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


@pytest.fixture
def pg_dsn() -> str:
    pytest.importorskip("asyncpg", reason="requires the asyncpg driver")
    dsn = _discover_pg_dsn()
    if dsn is None:
        pytest.skip("no Postgres reachable (SOS_TEST_DATABASE_URL or LOCAL pg)")
    return dsn


@pytest.fixture
def neon_adapter(pg_dsn: str):
    asyncpg = pytest.importorskip("asyncpg")
    name = f"sos_pub05_adapter_{uuid.uuid4().hex[:10]}"

    async def _recreate() -> str:
        admin = await asyncpg.connect(pg_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            await admin.execute(f'CREATE DATABASE "{name}"')
        finally:
            await admin.close()
        prefix, rest = pg_dsn.split("://", 1)
        if "@" in rest:
            creds, host_part = rest.split("@", 1)
            host, _ = host_part.split("/", 1)
            return f"{prefix}://{creds}@{host}/{name}"
        host, _ = rest.split("/", 1)
        return f"{prefix}://{host}/{name}"

    dsn = asyncio.run(_recreate())
    adapter = NeonPostgresPersistence(dsn)
    adapter.migrate()
    try:
        yield adapter
    finally:
        adapter.close()

        async def _drop() -> None:
            admin = await asyncpg.connect(pg_dsn)
            try:
                await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            finally:
                await admin.close()

        asyncio.run(_drop())


def test_adapter_identity(neon_adapter) -> None:
    assert neon_adapter.mode == "neon"
    assert neon_adapter.implementation == "postgres-asyncpg"
    health = neon_adapter.health_check()
    assert health.status == "SUCCESS"


def test_sync_bridge_serves_concurrent_threads(neon_adapter) -> None:
    """The seam is SYNCHRONOUS (final since PUB-01) but every call bridges
    onto the single dedicated async loop — concurrent callers from multiple
    threads all get correct results (no cross-talk, no lost writes)."""
    from db.seeds.demo_seed import seed_demo

    seed_demo(neon_adapter)
    results: dict[int, int] = {}
    errors: list[Exception] = []

    def reader(index: int) -> None:
        try:
            for _ in range(5):
                page = neon_adapter.list_missions(
                    __import__("providers.neon.seam", fromlist=["TenantScope"])
                    .TenantScope(workspace_ids=frozenset({"ws-demo"})),
                    workspace_id=None, cursor=None, limit=10,
                )
                results[index] = results.get(index, 0) + len(page.items)
        except Exception as exc:  # pragma: no cover - failure surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=reader, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not errors, errors
    assert len(results) == 8
    assert all(count == 5 for count in results.values())  # 1 mission × 5 reads


def test_close_then_use_fails_closed(neon_adapter) -> None:
    adapter = neon_adapter
    adapter.close()
    with pytest.raises(NeonConfigError):
        adapter.get_user("user-demo-owner")
    # close is idempotent
    adapter.close()


def test_timeout_is_truthful_not_silent(neon_adapter) -> None:
    """A bridged call that exceeds its timeout raises NeonTimeoutError —
    truthful failure, never a hang (and never a fabricated result)."""
    class _Slow(NeonPostgresPersistence):  # type: ignore[misc]
        def __init__(self) -> None:  # fixture: no pool
            self._db_label = "slow"
            self._call_timeout = 0.05
            self._closed = False

    slow = _Slow()

    async def _forever() -> int:
        await asyncio.sleep(30)
        return 1

    with pytest.raises(NeonTimeoutError):
        slow._loop_runner = __import__(
            "providers.neon.cloud", fromlist=["_LoopRunner"]
        )._LoopRunner("slow-fixture")
        try:
            slow._run(_forever())
        finally:
            slow._loop_runner.close()
