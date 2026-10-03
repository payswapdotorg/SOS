"""The FastAPI app factory (PUB-01).

``create_app()`` wires the provider seams from validated ``Settings``
(LOCAL mode boots with ZERO env vars; cloud modes fail closed with precise
errors), applies migrations, loads the deterministic demo seed, installs the
rate-limiting middleware and the error-envelope handlers, and mounts the
``/api/v1`` router (openapi.json served at ``/api/v1/openapi.json``).

Run (LOCAL, zero env)::

    python3 -m uvicorn services.api.main:app --port 8099
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from . import container as container_module
from .config import ConfigError, Settings, load_settings
from .dependencies.rate_limit import RateLimitMiddleware
from .errors import install_error_handlers
from .routes import build_api_v1_router


def create_app(
    settings: Settings | None = None,
    *,
    persistence: Any = None,
    coordination: Any = None,
    artifacts: Any = None,
    execution_providers: dict[str, Any] | None = None,
    github: Any = None,
    seed: bool = True,
) -> FastAPI:
    """Build the control-plane app.

    Adapter overrides exist for deterministic tests and fault injection;
    production wiring comes strictly from the validated settings.
    """
    settings = settings or load_settings()

    app = FastAPI(
        title="SOS Public Deployment API",
        version="1.0.0-pub01",
        description=(
            "Control-plane adapter over the frozen SOS semantic core "
            "(`src/sos`). Thin routes: authenticate → tenant-authorize → "
            "validate → domain orchestration → persist → typed DTO. Truth "
            "states survive end-to-end (SUCCESS|EMPTY|FAILED|UNKNOWN|"
            "UNSUPPORTED|UNAVAILABLE). LOCAL mode runs entirely on local "
            "provider seams; receipts from the demo execution provider are "
            "always marked demo:true and never claim a real deployment."
        ),
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
    )

    built = _build_adapters(
        settings,
        persistence=persistence,
        coordination=coordination,
        artifacts=artifacts,
        execution_providers=execution_providers,
        github=github,
    )
    container = container_module.ApiContainer(
        settings=settings,
        persistence=built["persistence"],
        coordination=built["coordination"],
        artifacts=built["artifacts"],
        execution_providers=built["execution_providers"],
        github=built["github"],
    )
    app.state.container = container

    # Migrations + deterministic demo seed (idempotent) — BOTH persistence
    # backends (PUB-05: SQLite LOCAL and Neon PostgreSQL load the same demo
    # dataset through the same seam; a fresh Neon branch bootstraps exactly
    # like a fresh LOCAL database).
    if seed:
        container.persistence.migrate()
        if not container.persistence.is_seeded():
            from db.seeds.demo_seed import seed_demo

            container.persistence.seed_demo(seed_demo)

    app.add_middleware(RateLimitMiddleware, container=container)
    install_error_handlers(app)
    app.include_router(build_api_v1_router())

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {
            "name": "SOS Public Deployment API",
            "api": "/api/v1",
            "health": "/api/v1/health",
            "openapi": "/api/v1/openapi.json",
        }

    return app


def _build_adapters(
    settings: Settings,
    *,
    persistence: Any = None,
    coordination: Any = None,
    artifacts: Any = None,
    execution_providers: dict[str, Any] | None = None,
    github: Any = None,
) -> dict[str, Any]:
    # Persistence: LOCAL SQLite | Neon PostgreSQL (PUB-05: asyncpg adapter
    # on the same seam; fail-closed on invalid config — never a fallback).
    if persistence is not None:
        pass
    elif settings.persistence_mode == "local":
        from providers.neon.local import LocalSqlitePersistence

        persistence = LocalSqlitePersistence(settings.local_db_path)
    else:
        from providers.neon.cloud import build_neon_persistence

        persistence = build_neon_persistence(str(settings.database_url))

    # Coordination: LOCAL in-process | Upstash (fail-closed, PUB-06).
    if coordination is not None:
        pass
    elif settings.coordination_mode == "local":
        from providers.upstash.local import InProcessCoordination

        coordination = InProcessCoordination()
    else:
        from providers.upstash.cloud import build_upstash_coordination

        coordination = build_upstash_coordination(str(settings.redis_url))

    # Artifacts: LOCAL content-addressed FS | R2 (fail-closed, PUB-07).
    if artifacts is not None:
        pass
    elif settings.artifacts_mode == "local":
        from providers.r2.local import LocalFsArtifactStore

        artifacts = LocalFsArtifactStore(settings.local_artifacts_dir)
    else:
        from providers.r2.cloud import build_r2_artifact_store

        artifacts = build_r2_artifact_store(
            str(settings.r2_endpoint), str(settings.r2_access_key_id),
            str(settings.r2_secret_access_key), str(settings.r2_bucket),
        )

    # Execution: DemoProvider | Apify (fail-closed placeholder, PUB-08).
    if execution_providers is not None:
        pass
    elif settings.execution_mode == "demo":
        from execution.adapters.demo import build_execution_registry

        execution_providers = build_execution_registry()
    else:
        raise ConfigError(
            "SOS_EXECUTION=apify selects the Apify bounded-execution "
            "adapter, which is implemented by PUB-08 (not yet merged). "
            "Refusing to boot: no silent fallback to DemoProvider is "
            "permitted. Use SOS_EXECUTION=demo for LOCAL mode."
        )

    # GitHub source: LOCAL fixture | live (fail-closed, PUB-04+).
    if github is not None:
        pass
    elif settings.github_source_pat:
        from providers.github.cloud import build_github_cloud_source

        github = build_github_cloud_source(str(settings.github_source_pat))
    else:
        from providers.github.local import LocalFixtureGitHubSource

        github = LocalFixtureGitHubSource()

    return {
        "persistence": persistence,
        "coordination": coordination,
        "artifacts": artifacts,
        "execution_providers": execution_providers,
        "github": github,
    }


# Module-level app for ``python3 -m uvicorn services.api.main:app``: built at
# import time so a misconfigured environment aborts boot with the precise
# ConfigError (fail-closed) and LOCAL mode boots with zero env vars.
app = create_app()
