"""Environment/config module (PUB-01) — fail-closed by construction.

Consumes the ``infra/environment.example`` names. LOCAL mode (all four mode
switches local/demo) boots with ZERO env vars. Every non-LOCAL mode requires
its provider credentials, and misconfiguration aborts with a precise error —
never an insecure default (SECURITY threat notes: fail-closed config).
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from typing import Mapping

VALID_ENVS = ("local", "preview", "public")
VALID_PERSISTENCE = ("local", "neon")
VALID_COORDINATION = ("local", "upstash")
VALID_ARTIFACTS = ("local", "r2")
VALID_EXECUTION = ("demo", "apify")


class ConfigError(Exception):
    """Raised when required configuration is missing or contradictory."""


@dataclass(frozen=True)
class Settings:
    """The validated runtime configuration (name authority: infra/environment.example)."""

    env: str
    persistence_mode: str
    coordination_mode: str
    artifacts_mode: str
    execution_mode: str
    database_url: str | None
    redis_url: str | None
    r2_endpoint: str | None
    r2_access_key_id: str | None
    r2_secret_access_key: str | None
    r2_bucket: str | None
    apify_token: str | None
    apify_actor_id: str | None
    github_client_id: str | None
    github_client_secret: str | None
    session_secret: str | None
    github_source_pat: str | None
    job_callback_secret: str | None
    api_base_url: str | None
    web_base_url: str | None
    rate_anon_per_min: int
    rate_user_per_min: int
    rate_write_per_min: int
    rate_job_per_hour: int
    rate_recovery_per_hour: int
    rate_artifact_max_mb: int
    rate_body_max_mb: int
    apify_max_concurrent: int
    local_db_path: str
    local_artifacts_dir: str


def _mode(environ: Mapping[str, str], name: str, default: str,
          valid: tuple[str, ...]) -> str:
    raw = environ.get(name, "").strip() or default
    if raw not in valid:
        raise ConfigError(
            f"{name}={raw!r} is invalid; expected one of "
            f"{', '.join(valid)} (fail-closed: no silent default)"
        )
    return raw


def _required(environ: Mapping[str, str], name: str, mode: str) -> str:
    value = environ.get(name, "").strip()
    if not value:
        raise ConfigError(
            f"{name} is REQUIRED when {mode} is selected (fail-closed: "
            "missing provider credentials must abort boot, never fall back)"
        )
    return value


def _positive_int(environ: Mapping[str, str], name: str, default: int) -> int:
    raw = environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name}={raw!r} is not an integer") from exc
    if value < 1:
        raise ConfigError(f"{name}={value} must be >= 1")
    return value


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Load and validate the runtime configuration.

    ``environ`` defaults to ``os.environ``. LOCAL mode requires zero
    variables; preview/public and cloud provider modes fail closed on
    missing REQUIRED values with precise errors.
    """
    env_map: Mapping[str, str] = os.environ if environ is None else environ

    env = _mode(env_map, "SOS_ENV", "local", VALID_ENVS)
    persistence = _mode(env_map, "SOS_PERSISTENCE", "local", VALID_PERSISTENCE)
    coordination = _mode(env_map, "SOS_COORDINATION", "local", VALID_COORDINATION)
    artifacts = _mode(env_map, "SOS_ARTIFACTS", "local", VALID_ARTIFACTS)
    execution = _mode(env_map, "SOS_EXECUTION", "demo", VALID_EXECUTION)

    database_url = env_map.get("SOS_DATABASE_URL", "").strip() or None
    if persistence == "neon" and not database_url:
        raise ConfigError(
            "SOS_PERSISTENCE=neon requires SOS_DATABASE_URL "
            "(postgresql+asyncpg://…, the Neon branch) — fail-closed"
        )
    redis_url = env_map.get("SOS_REDIS_URL", "").strip() or None
    if coordination == "upstash" and not redis_url:
        raise ConfigError(
            "SOS_COORDINATION=upstash requires SOS_REDIS_URL "
            "(rediss://…:6379, the Upstash instance) — fail-closed"
        )
    r2_endpoint = env_map.get("SOS_R2_ENDPOINT", "").strip() or None
    r2_access_key_id = env_map.get("SOS_R2_ACCESS_KEY_ID", "").strip() or None
    r2_secret = env_map.get("SOS_R2_SECRET_ACCESS_KEY", "").strip() or None
    r2_bucket = env_map.get("SOS_R2_BUCKET", "").strip() or None
    if artifacts == "r2" and not (
        r2_endpoint and r2_access_key_id and r2_secret and r2_bucket
    ):
        raise ConfigError(
            "SOS_ARTIFACTS=r2 requires SOS_R2_ENDPOINT, "
            "SOS_R2_ACCESS_KEY_ID, SOS_R2_SECRET_ACCESS_KEY and SOS_R2_BUCKET "
            "(private bucket — SECURITY S3) — fail-closed"
        )
    apify_token = env_map.get("SOS_APIFY_TOKEN", "").strip() or None
    apify_actor_id = env_map.get("SOS_APIFY_ACTOR_ID", "").strip() or None
    if execution == "apify" and not (apify_token and apify_actor_id):
        raise ConfigError(
            "SOS_EXECUTION=apify requires SOS_APIFY_TOKEN and "
            "SOS_APIFY_ACTOR_ID (the bounded execution actor, PUB-08) — "
            "fail-closed"
        )

    session_secret = env_map.get("SOS_SESSION_SECRET", "").strip() or None
    if env != "local" and not session_secret:
        raise ConfigError(
            f"SOS_ENV={env} requires SOS_SESSION_SECRET (32+ random bytes; "
            "sessions fail closed without it) — fail-closed"
        )
    if session_secret is not None and len(session_secret) < 32:
        raise ConfigError(
            "SOS_SESSION_SECRET must be at least 32 bytes — fail-closed"
        )

    return Settings(
        env=env,
        persistence_mode=persistence,
        coordination_mode=coordination,
        artifacts_mode=artifacts,
        execution_mode=execution,
        database_url=database_url,
        redis_url=redis_url,
        r2_endpoint=r2_endpoint,
        r2_access_key_id=r2_access_key_id,
        r2_secret_access_key=r2_secret,
        r2_bucket=r2_bucket,
        apify_token=apify_token,
        apify_actor_id=apify_actor_id,
        github_client_id=env_map.get("SOS_GITHUB_CLIENT_ID", "").strip() or None,
        github_client_secret=(
            env_map.get("SOS_GITHUB_CLIENT_SECRET", "").strip() or None
        ),
        session_secret=session_secret,
        github_source_pat=env_map.get("SOS_GITHUB_SOURCE_PAT", "").strip() or None,
        job_callback_secret=(
            env_map.get("SOS_JOB_CALLBACK_SECRET", "").strip() or None
        ),
        api_base_url=env_map.get("SOS_API_BASE_URL", "").strip() or None,
        web_base_url=env_map.get("SOS_WEB_BASE_URL", "").strip() or None,
        rate_anon_per_min=_positive_int(
            env_map, "SOS_RATE_ANON_PER_MIN", 60
        ),
        rate_user_per_min=_positive_int(
            env_map, "SOS_RATE_USER_PER_MIN", 240
        ),
        rate_write_per_min=_positive_int(
            env_map, "SOS_RATE_WRITE_PER_MIN", 30
        ),
        rate_job_per_hour=_positive_int(env_map, "SOS_RATE_JOB_PER_HOUR", 10),
        rate_recovery_per_hour=_positive_int(
            env_map, "SOS_RATE_RECOVERY_PER_HOUR", 2
        ),
        rate_artifact_max_mb=_positive_int(
            env_map, "SOS_RATE_ARTIFACT_MAX_MB", 50
        ),
        rate_body_max_mb=_positive_int(env_map, "SOS_RATE_BODY_MAX_MB", 1),
        apify_max_concurrent=_positive_int(
            env_map, "SOS_APIFY_MAX_CONCURRENT", 2
        ),
        local_db_path=(
            env_map.get("SOS_LOCAL_DB_PATH", "").strip()
            or os.path.join(
                tempfile.gettempdir(), "sos-api", "local.sqlite3"
            )
        ),
        local_artifacts_dir=(
            env_map.get("SOS_LOCAL_ARTIFACTS_DIR", "").strip()
            or os.path.join(
                tempfile.gettempdir(), "sos-api", "artifacts"
            )
        ),
    )
