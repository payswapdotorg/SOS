"""The PUB-06 job worker entrypoint (directive §8; contract §D PUB-06).

PUBLIC mode: a SEPARATE process from the API — the API only enqueues
(POST /jobs returns the ``queued`` DTO; zero job execution in the API
process), and this worker claims queued jobs through the orchestration
locks and runs them to terminal states with the bounded retry policy:

    PYTHONPATH=../.. python3 -m services.api.jobs.worker --poll 5

LOCAL mode: an in-process bounded executor serves tests (the API executes
jobs inline after creation), and this module's :func:`run_worker_once` is
the deterministic sweep used by the test suite (and by any operator who
wants to drive a LOCAL queue manually).

The worker never executes arbitrary user repository code (directive
§16-A): its operations are the bounded dispatchers
(:mod:`services.api.jobs.dispatchers`) — recovery via the frozen W3
pipeline and execution via the governed W11 seam.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

# Bootstrap the repo layout (src/ for ``sos``, repo root for
# ``services``/``providers``) so the module also runs uninstalled, exactly
# like ``services.api.testing`` does for the test suite.
_REPO_ROOT = Path(__file__).resolve().parents[3]
for _entry in (str(_REPO_ROOT / "src"), str(_REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)


def build_worker_container(settings: Any) -> Any:
    """The worker's composition root.

    Mirrors ``services.api.main._build_adapters`` selection-by-selection
    (deliberately NOT importing that module — importing it would execute
    the API app factory at import time and boot the API lifecycle inside
    the worker process). Keep the two aligned; both fail CLOSED on cloud
    modes without their credentials (no silent LOCAL fallback).
    """
    from services.api.container import ApiContainer

    if settings.persistence_mode == "local":
        from providers.neon.local import LocalSqlitePersistence

        persistence = LocalSqlitePersistence(settings.local_db_path)
    else:
        from providers.neon.cloud import build_neon_persistence

        persistence = build_neon_persistence(str(settings.database_url))

    if settings.coordination_mode == "local":
        from providers.upstash.local import InProcessCoordination

        coordination = InProcessCoordination()
    else:
        from providers.upstash.cloud import build_upstash_coordination

        coordination = build_upstash_coordination(str(settings.redis_url))

    if settings.artifacts_mode == "local":
        from providers.r2.local import LocalFsArtifactStore

        artifacts = LocalFsArtifactStore(
            settings.local_artifacts_dir,
            signing_key=(
                settings.session_secret.encode("utf-8")
                if settings.session_secret else None
            ),
            max_bytes=settings.rate_artifact_max_mb * 1024 * 1024,
        )
    else:
        from providers.r2.cloud import build_r2_artifact_store

        artifacts = build_r2_artifact_store(
            str(settings.r2_endpoint), str(settings.r2_access_key_id),
            str(settings.r2_secret_access_key), str(settings.r2_bucket),
            max_bytes=settings.rate_artifact_max_mb * 1024 * 1024,
        )

    if settings.execution_mode == "demo":
        from execution.adapters.demo import build_execution_registry

        execution_providers = build_execution_registry()
    else:
        from services.api.config import ConfigError

        raise ConfigError(
            "SOS_EXECUTION=apify selects the Apify bounded-execution "
            "adapter, which is implemented by PUB-08 (not yet merged). "
            "Refusing to boot the worker: no silent fallback to "
            "DemoProvider is permitted. Use SOS_EXECUTION=demo."
        )

    if settings.github_source_pat:
        from providers.github.cloud import build_github_cloud_source

        github = build_github_cloud_source(str(settings.github_source_pat))
    else:
        from providers.github.local import LocalFixtureGitHubSource

        github = LocalFixtureGitHubSource()

    return ApiContainer(
        settings=settings,
        persistence=persistence,
        coordination=coordination,
        artifacts=artifacts,
        execution_providers=execution_providers,
        github=github,
    )


def run_worker_once(
    container: Any, *, service: Any = None, limit: int = 10
) -> dict[str, int]:
    """One deterministic worker sweep over the pending-job registry.

    - ``queued`` jobs → claim + execute to a terminal state;
    - ``running`` jobs → rescue when the lease expired (requeue within the
      bounded attempt budget, else terminal ``failed``/abandoned);
    - terminal/unknown jobs → drop their pending registration.

    Job discovery comes from the coordination plane's pending registry
    (directive §3 "short-lived job state"); each job is then read through
    the tenant-scoped persistence seam with the registry-recorded tenant —
    the worker never widens a tenant scope beyond that one workspace.
    """
    from providers.neon.seam import TenantScope

    from .service import JobService

    coordination = container.coordination
    service = service or JobService(container)
    summary = {
        "scanned": 0, "executed": 0, "succeeded": 0, "failed": 0,
        "requeued": 0, "skipped": 0,
    }
    seen: set[str] = set()
    for tenant_id, job_id in coordination.pending_jobs():
        if job_id in seen:
            continue  # re-registration duplicates: one pass per job
        if len(seen) >= limit:
            break
        seen.add(job_id)
        summary["scanned"] += 1
        scope = TenantScope(workspace_ids=frozenset({tenant_id}))
        row = container.persistence.get_job(scope, job_id)
        if row is None:
            # The durable row is gone (deleted workspace cascade): the
            # registration is stale — drop it truthfully.
            coordination.pending_job_remove(tenant_id, job_id)
            summary["skipped"] += 1
            continue
        status = str(row["status"])
        if status == "queued":
            final = service.execute_job(scope=scope, job_row=row)
            summary["executed"] += 1
            final_status = str(final["status"]) if final else "unknown"
            if final_status == "succeeded":
                summary["succeeded"] += 1
            elif final_status == "failed":
                summary["failed"] += 1
            else:
                # Still queued/running: another executor holds the lease.
                summary["skipped"] += 1
        elif status == "running":
            rescued = service.rescue_stale_running(scope=scope, job_row=row)
            if rescued is None:
                summary["skipped"] += 1  # live lease — leave it alone
            elif str(rescued["status"]) == "queued":
                summary["requeued"] += 1
            else:
                summary["failed"] += 1
        else:
            coordination.pending_job_remove(tenant_id, job_id)
            summary["skipped"] += 1
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m services.api.jobs.worker",
        description="The SOS public-deployment job worker (PUB-06).",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="run one sweep and exit (default: poll forever)",
    )
    parser.add_argument(
        "--poll", type=float, default=2.0, metavar="SECONDS",
        help="seconds between sweeps in loop mode (default: 2.0)",
    )
    parser.add_argument(
        "--limit", type=int, default=10, metavar="N",
        help="max jobs per sweep (default: 10)",
    )
    args = parser.parse_args(argv)

    from services.api.config import load_settings

    settings = load_settings()
    container = build_worker_container(settings)
    # Migrations are idempotent; the worker shares the API's database and
    # never seeds (seeding is the API's deterministic-boot responsibility).
    container.persistence.migrate()

    health = container.coordination.health_check()
    print(
        f"sos-job-worker: mode={settings.env} "
        f"persistence={container.persistence.mode} "
        f"coordination={container.coordination.mode} "
        f"(health: {health.status})",
        flush=True,
    )

    if args.once:
        summary = run_worker_once(container, limit=args.limit)
        print(f"sweep: {summary}", flush=True)
        return 0

    while True:
        try:
            summary = run_worker_once(container, limit=args.limit)
            if summary["scanned"]:
                print(f"sweep: {summary}", flush=True)
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001 - the worker stays up
            # One failing sweep never kills the worker (jobs stay queued
            # truthfully); the error is reported, not swallowed as success.
            print(
                f"sweep error (jobs remain durably queued): "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )
        try:
            time.sleep(max(0.1, args.poll))
        except KeyboardInterrupt:
            print("sos-job-worker: stopped", flush=True)
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
