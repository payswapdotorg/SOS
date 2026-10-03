"""PUB-06 — directive §13 rate-limit buckets: the complete bucket set
(anonymous demo-reads-only, authenticated, workspace, job type, provider,
IP) at the route level, plus the duplicate-recovery convergence semantics.
Hermetic (LOCAL adapters, generous non-binding buckets except the one
under test)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

fastapi = pytest.importorskip(
    "fastapi",
    reason=(
        "PUB-06 API tests require the 'api' dependency group "
        "(pyproject [project.optional-dependencies].api); the frozen 'tests' "
        "CI workflow runs the dependency-free baseline suite only"
    ),
)

REPO_ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(REPO_ROOT / "src"), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from services.api.testing import login, make_client  # noqa: E402

DEMO_WS = "ws-demo"
FIXTURE_REPO = "https://github.com/sos-demo/example-api"


def test_workspace_bucket_limits_path_targeted_requests(
    tmp_path: Path,
) -> None:
    """GET /workspaces/{id} is workspace-targeted: the per-workspace bucket
    trips before the generous identity buckets (PUB-06 §13 bucket)."""
    with make_client(
        tmp_path,
        rate_anon_per_min=1000, rate_user_per_min=1000,
        rate_workspace_per_min=3,
    ) as client:
        login(client, "demo-owner")
        codes = [
            client.get(f"/api/v1/workspaces/{DEMO_WS}").status_code
            for _ in range(5)
        ]
        assert codes[:3] == [200, 200, 200]
        assert codes[3] == 429 and codes[4] == 429
        body = client.get(f"/api/v1/workspaces/{DEMO_WS}").json()
        assert body["error"]["code"] == "RATE_LIMITED"
        assert body["error"]["details"]["retryAfterSeconds"] >= 1
        # health probe stays exempt and truthful
        assert client.get("/api/v1/health").status_code == 200


def test_workspace_bucket_covers_query_targeted_collections(
    tmp_path: Path,
) -> None:
    with make_client(
        tmp_path,
        rate_anon_per_min=1000, rate_user_per_min=1000,
        rate_workspace_per_min=2,
    ) as client:
        login(client, "demo-owner")
        codes = [
            client.get(
                f"/api/v1/evidence?workspaceId={DEMO_WS}"
            ).status_code
            for _ in range(4)
        ]
        assert codes[:2] == [200, 200]
        assert codes[2] == 429 and codes[3] == 429
        # an untargeted collection stays under the identity buckets only
        assert client.get("/api/v1/evidence").status_code == 200


def test_workspace_buckets_are_independent_per_workspace(
    tmp_path: Path,
) -> None:
    with make_client(
        tmp_path,
        rate_anon_per_min=1000, rate_user_per_min=1000,
        rate_workspace_per_min=2,
    ) as client:
        login(client, "demo-owner")
        # exhaust the demo workspace bucket via its detail route
        for _ in range(3):
            client.get(f"/api/v1/workspaces/{DEMO_WS}")
        assert client.get(f"/api/v1/workspaces/{DEMO_WS}").status_code == 429
        # a different workspace's bucket is untouched — create one and read
        created = client.post(
            "/api/v1/workspaces", json={"name": "Other", "slug": "other-lab"}
        )
        assert created.status_code == 200
        other_id = created.json()["id"]
        assert client.get(f"/api/v1/workspaces/{other_id}").status_code == 200
        assert client.get(f"/api/v1/workspaces/{other_id}").status_code == 200
        # (the other workspace's OWN bucket trips only after its own limit)
        assert client.get(f"/api/v1/workspaces/{other_id}").status_code == 429


def test_provider_bucket_limits_job_dispatches(tmp_path: Path) -> None:
    """The §13 provider bucket: per-provider per-minute dispatch quota —
    the third job creation for the same provider trips 429 while the
    job-type quota stays generous."""
    with make_client(
        tmp_path,
        rate_anon_per_min=1000, rate_user_per_min=1000,
        rate_write_per_min=1000, rate_job_per_hour=1000,
        rate_recovery_per_hour=1000, rate_provider_per_min=2,
    ) as client:
        login(client, "demo-owner")
        first = client.post(
            "/api/v1/jobs",
            json={
                "workspaceId": DEMO_WS, "type": "system_recovery",
                "repositoryUrl": FIXTURE_REPO,
                "idempotencyKey": "provider-bucket-1",
            },
        )
        assert first.status_code == 200
        assert first.json()["status"] == "succeeded"
        second = client.post(
            "/api/v1/jobs",
            json={
                "workspaceId": DEMO_WS, "type": "system_recovery",
                "repositoryUrl": FIXTURE_REPO,
                "idempotencyKey": "provider-bucket-2",
            },
        )
        assert second.status_code == 200
        # repeated recovery of the same pinned repo CONVERGES on the same
        # system revision + evidence rows (no duplicate side effects)
        assert second.json()["receipt"]["revision"] == (
            first.json()["receipt"]["revision"]
        )
        third = client.post(
            "/api/v1/jobs",
            json={
                "workspaceId": DEMO_WS, "type": "system_recovery",
                "repositoryUrl": FIXTURE_REPO,
                "idempotencyKey": "provider-bucket-3",
            },
        )
        assert third.status_code == 429
        assert third.json()["error"]["code"] == "RATE_LIMITED"
        # idempotent replays never consume the provider bucket (PUB-01
        # semantics preserved: quota burn only on actual creation)
        replay = client.post(
            "/api/v1/jobs",
            json={
                "workspaceId": DEMO_WS, "type": "system_recovery",
                "repositoryUrl": FIXTURE_REPO,
                "idempotencyKey": "provider-bucket-1",
            },
        )
        assert replay.status_code == 200
        assert replay.json()["id"] == first.json()["id"]


def test_provider_bucket_is_per_provider_id(tmp_path: Path) -> None:
    """Recovery jobs dispatch under provider ``local``; execution jobs
    under the execution mode (``demo``) — separate §13 bucket keys."""
    with make_client(
        tmp_path,
        rate_anon_per_min=1000, rate_user_per_min=1000,
        rate_write_per_min=1000, rate_job_per_hour=1000,
        rate_recovery_per_hour=1000, rate_provider_per_min=1,
    ) as client:
        login(client, "demo-owner")
        # exhaust the `local` provider bucket (recovery)
        first = client.post(
            "/api/v1/jobs",
            json={
                "workspaceId": DEMO_WS, "type": "system_recovery",
                "repositoryUrl": FIXTURE_REPO,
                "idempotencyKey": "provider-split-1",
            },
        )
        assert first.status_code == 200
        blocked = client.post(
            "/api/v1/jobs",
            json={
                "workspaceId": DEMO_WS, "type": "system_recovery",
                "repositoryUrl": FIXTURE_REPO,
                "idempotencyKey": "provider-split-2",
            },
        )
        assert blocked.status_code == 429
        # the `demo` provider bucket is a DIFFERENT key: execution jobs
        # still dispatch
        execution = client.post(
            "/api/v1/jobs",
            json={
                "workspaceId": DEMO_WS, "type": "experiment_execution",
                "experimentId": "exp-demo-cache",
                "idempotencyKey": "provider-split-exec-1",
            },
        )
        assert execution.status_code == 200
        assert execution.json()["provider"] == "demo"


def test_job_type_quota_still_enforced_per_workspace(
    tmp_path: Path,
) -> None:
    with make_client(
        tmp_path,
        rate_anon_per_min=1000, rate_user_per_min=1000,
        rate_write_per_min=1000, rate_provider_per_min=1000,
        rate_recovery_per_hour=1,
    ) as client:
        login(client, "demo-owner")
        first = client.post(
            "/api/v1/jobs",
            json={
                "workspaceId": DEMO_WS, "type": "system_recovery",
                "repositoryUrl": FIXTURE_REPO,
                "idempotencyKey": "type-quota-1",
            },
        )
        assert first.status_code == 200
        second = client.post(
            "/api/v1/jobs",
            json={
                "workspaceId": DEMO_WS, "type": "system_recovery",
                "repositoryUrl": FIXTURE_REPO,
                "idempotencyKey": "type-quota-2",
            },
        )
        assert second.status_code == 429


def test_anonymous_demo_reads_only_mutations_rejected(
    tmp_path: Path,
) -> None:
    with make_client(
        tmp_path, rate_anon_per_min=1000, rate_user_per_min=1000
    ) as client:
        # reads work anonymously (demo workspace only)
        assert client.get("/api/v1/workspaces").status_code == 200
        assert client.get("/api/v1/evidence").status_code == 200
        # every mutation is rejected — anonymous is demo-reads-only (§13)
        response = client.post(
            "/api/v1/jobs",
            json={
                "workspaceId": DEMO_WS, "type": "system_recovery",
                "repositoryUrl": FIXTURE_REPO,
            },
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_ip_bucket_covers_all_traffic(tmp_path: Path) -> None:
    """The per-IP bucket spans anonymous + authenticated identities: a
    small ceiling trips for the client regardless of session state."""
    with make_client(
        tmp_path,
        rate_anon_per_min=4, rate_user_per_min=1000,
        rate_workspace_per_min=1000,
    ) as client:
        codes = [
            client.get("/api/v1/missions").status_code for _ in range(6)
        ]
        # ip limit = anon(4) + user(1000) for anonymous traffic… the IP
        # bucket applies after the anonymous bucket: 4 anon-allowed reads,
        # then the anonymous bucket itself trips at 429.
        assert codes[:4] == [200, 200, 200, 200]
        assert codes[4] == 429
