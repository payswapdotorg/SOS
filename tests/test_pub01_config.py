"""PUB-01 — fail-closed configuration tests + LOCAL zero-env boot + rate
limiting (directive §13 buckets) + payload cap (S16). Hermetic."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

fastapi = pytest.importorskip(
    "fastapi",
    reason=(
        "PUB-01 API tests require the 'api' dependency group "
        "(pyproject [project.optional-dependencies].api)"
    ),
)

REPO_ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(REPO_ROOT / "src"), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from fastapi.testclient import TestClient  # noqa: E402

from services.api.config import ConfigError, load_settings  # noqa: E402
from services.api.main import create_app  # noqa: E402
from services.api.testing import login, make_client, make_settings  # noqa: E402


def test_local_mode_boots_with_zero_env(tmp_path: Path) -> None:
    settings = load_settings(environ={})
    assert settings.env == "local"
    assert settings.persistence_mode == "local"
    assert settings.coordination_mode == "local"
    assert settings.artifacts_mode == "local"
    assert settings.execution_mode == "demo"
    # the app factory builds and serves on LOCAL adapters with no env at all
    settings = make_settings(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/v1/health").json()["status"] == "ok"


@pytest.mark.parametrize(
    "environ,fragment",
    [
        ({"SOS_PERSISTENCE": "banana"}, "SOS_PERSISTENCE='banana'"),
        ({"SOS_ENV": "dev"}, "SOS_ENV='dev'"),
        ({"SOS_PERSISTENCE": "neon"}, "SOS_DATABASE_URL"),
        ({"SOS_COORDINATION": "upstash"}, "SOS_REDIS_URL"),
        (
            {"SOS_ARTIFACTS": "r2"},
            "SOS_R2_ENDPOINT",
        ),
        ({"SOS_EXECUTION": "apify"}, "SOS_APIFY_TOKEN"),
        ({"SOS_ENV": "public"}, "SOS_SESSION_SECRET"),
        ({"SOS_ENV": "preview"}, "SOS_SESSION_SECRET"),
        (
            {
                "SOS_ENV": "public",
                "SOS_SESSION_SECRET": "short",
            },
            "at least 32 bytes",
        ),
        ({"SOS_RATE_ANON_PER_MIN": "0"}, "must be >= 1"),
        ({"SOS_RATE_ANON_PER_MIN": "abc"}, "not an integer"),
    ],
)
def test_fail_closed_configuration(environ, fragment) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_settings(environ=environ)
    assert fragment in str(excinfo.value), str(excinfo.value)


def test_cloud_mode_selection_fails_closed_with_precise_error(
    tmp_path: Path,
) -> None:
    """Selecting PUB-05/06/07/08 cloud adapters before they exist aborts
    boot with a precise error — never a silent LOCAL fallback."""
    settings = make_settings(tmp_path, persistence_mode="neon")
    with pytest.raises(Exception) as excinfo:
        create_app(settings)
    assert "PUB-05" in str(excinfo.value)

    settings = make_settings(tmp_path, coordination_mode="upstash")
    with pytest.raises(Exception) as excinfo:
        create_app(settings)
    assert "PUB-06" in str(excinfo.value)

    settings = make_settings(tmp_path, artifacts_mode="r2")
    with pytest.raises(Exception) as excinfo:
        create_app(settings)
    assert "PUB-07" in str(excinfo.value)

    settings = make_settings(tmp_path, execution_mode="apify")
    with pytest.raises(Exception) as excinfo:
        create_app(settings)
    assert "PUB-08" in str(excinfo.value)


def test_anonymous_rate_limit_bucket(tmp_path: Path) -> None:
    with make_client(tmp_path, rate_anon_per_min=3) as client:
        # /api/v1/health is exempt (readiness probe); the bucket applies to
        # the read surface:
        codes = [
            client.get("/api/v1/workspaces").status_code for _ in range(5)
        ]
        assert codes[:3] == [200, 200, 200]
        assert codes[3] == 429 and codes[4] == 429
        body = client.get("/api/v1/workspaces").json()
        assert body["error"]["code"] == "RATE_LIMITED"
        assert body["error"]["details"]["retryAfterSeconds"] >= 1
        # the health probe still answers while rate limited
        assert client.get("/api/v1/health").status_code == 200


def test_user_rate_limit_bucket_distinct_from_anonymous(tmp_path: Path) -> None:
    app = make_client(tmp_path, rate_anon_per_min=2, rate_user_per_min=1000).app
    with TestClient(app) as authed:
        login(authed, "demo-owner")
        # a second, cookie-less client exhausts the ANONYMOUS bucket
        with TestClient(app) as anon:
            for _ in range(3):
                anon.get("/api/v1/workspaces")
            assert anon.get("/api/v1/workspaces").status_code == 429
        # the authenticated identity uses the USER bucket, not the anonymous
        # one, and is unaffected by the exhausted anonymous bucket
        assert authed.get("/api/v1/workspaces").status_code == 200


def test_write_bucket_limited(tmp_path: Path) -> None:
    with make_client(tmp_path, rate_write_per_min=1) as client:
        login(client, "demo-owner")
        first = client.post(
            "/api/v1/workspaces", json={"name": "A", "slug": "aaa-lab"}
        )
        assert first.status_code == 200
        second = client.post(
            "/api/v1/workspaces", json={"name": "B", "slug": "bbb-lab"}
        )
        assert second.status_code == 429
        assert second.json()["error"]["code"] == "RATE_LIMITED"


def test_job_type_quota_limited(tmp_path: Path) -> None:
    with make_client(tmp_path, rate_recovery_per_hour=1) as client:
        login(client, "demo-owner")
        first = client.post(
            "/api/v1/jobs",
            json={
                "workspaceId": "ws-demo", "type": "system_recovery",
                "repositoryUrl": "https://github.com/sos-demo/example-api",
                "idempotencyKey": "quota-1",
            },
        )
        assert first.status_code == 200
        second = client.post(
            "/api/v1/jobs",
            json={
                "workspaceId": "ws-demo", "type": "system_recovery",
                "repositoryUrl": "https://github.com/sos-demo/example-api",
                "idempotencyKey": "quota-2",
            },
        )
        assert second.status_code == 429


def test_job_idempotency_key_dedups(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        payload = {
            "workspaceId": "ws-demo", "type": "system_recovery",
            "repositoryUrl": "https://github.com/sos-demo/example-api",
            "ref": "staging", "idempotencyKey": "idem-key-9",
        }
        first = client.post("/api/v1/jobs", json=payload)
        assert first.status_code == 200
        second = client.post("/api/v1/jobs", json=payload)
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        # same-key retries create no duplicate side effects: one recovery
        # evidence record for that idempotency key
        response = client.get("/api/v1/jobs?type=system_recovery")
        ids = [j["id"] for j in response.json()["items"]]
        assert ids.count(first.json()["id"]) == 1


def test_body_size_cap_413(tmp_path: Path) -> None:
    with make_client(tmp_path, rate_body_max_mb=1) as client:
        login(client, "demo-owner")
        big = {"name": "x" * (2 * 1024 * 1024), "slug": "big-body-lab"}
        response = client.post(
            "/api/v1/workspaces", json=big,
            headers={"Content-Length": str(2 * 1024 * 1024 + 512)},
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
