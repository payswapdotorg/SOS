"""Deterministic test support for PUB-01 API tests (LOCAL adapters on
temporary directories; no network, no env)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
for _entry in (str(_REPO_ROOT / "src"), str(_REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from fastapi.testclient import TestClient  # noqa: E402

from services.api.config import Settings  # noqa: E402
from services.api.main import create_app  # noqa: E402
from providers.neon.local import LocalSqlitePersistence  # noqa: E402
from providers.upstash.local import InProcessCoordination  # noqa: E402
from providers.r2.local import LocalFsArtifactStore  # noqa: E402
from providers.github.local import LocalFixtureGitHubSource  # noqa: E402
from execution.adapters.demo import build_execution_registry  # noqa: E402


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    """LOCAL settings on temporary state dirs (zero env required)."""
    defaults: dict[str, Any] = {
        "env": "local",
        "persistence_mode": "local",
        "coordination_mode": "local",
        "artifacts_mode": "local",
        "execution_mode": "demo",
        "database_url": None,
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
        "local_db_path": str(tmp_path / "api.sqlite3"),
        "local_artifacts_dir": str(tmp_path / "artifacts"),
    }
    defaults.update(overrides)
    return Settings(**defaults)


def make_test_app(tmp_path: Path, **settings_overrides: Any) -> Any:
    """A fully LOCAL app (migrations + demo seed applied) on tmp dirs."""
    settings = make_settings(tmp_path, **settings_overrides)
    return create_app(settings)


def make_client(tmp_path: Path, **settings_overrides: Any):
    """A TestClient with the lifespan executed (migrated + seeded)."""
    app = make_test_app(tmp_path, **settings_overrides)
    return TestClient(app)


def login(client: TestClient, login_name: str) -> None:
    """Log in a deterministic LOCAL test identity (stub session cookie)."""
    response = client.post("/api/v1/auth/login", json={"login": login_name})
    assert response.status_code == 200, response.text
