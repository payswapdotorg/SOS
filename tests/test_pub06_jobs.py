"""PUB-06 — the job layer: idempotency (same key → one job), the status
lifecycle, orchestration locks (concurrent dispatch → single execution),
the bounded/jittered/disclosed retry policy, timeouts, crash rescue, the
worker sweep, and the LOCAL↔PUBLIC execution split. Hermetic (LOCAL
adapters, tmp dirs, no network)."""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any

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

from fastapi.testclient import TestClient  # noqa: E402

from providers.neon.seam import TenantScope  # noqa: E402
from services.api.errors import ApiError  # noqa: E402
from services.api.jobs import (  # noqa: E402
    JobPermanentError,
    JobRetryableError,
    JobService,
    JobTimeoutError,
)
from services.api.jobs.service import RetryPolicy  # noqa: E402
from services.api.schemas.execution import CreateJobRequestDTO  # noqa: E402
from services.api.testing import login, make_client, make_settings  # noqa: E402

DEMO_WS = "ws-demo"
FIXTURE_REPO = "https://github.com/sos-demo/example-api"


def _scope_for(workspace: str = DEMO_WS) -> TenantScope:
    return TenantScope(workspace_ids=frozenset({workspace}))


def _recovery_body(key: str, **overrides: Any) -> CreateJobRequestDTO:
    return CreateJobRequestDTO(
        workspace_id=DEMO_WS,
        type="system_recovery",
        repository_url=overrides.pop("repository_url", FIXTURE_REPO),
        ref=overrides.pop("ref", None),
        idempotency_key=key,
    )


def _make_service(
    container: Any,
    *,
    operations: dict[str, Any] | None = None,
    sleeps: list[float] | None = None,
    jitter_zero: bool = True,
) -> JobService:
    return JobService(
        container,
        operations=operations,
        sleep=(sleeps.append if sleeps is not None else (lambda s: None)),
        jitter=(lambda upper: 0.0 if jitter_zero else None) if jitter_zero
        else None,
    )


# ---------------------------------------------------------------------------
# Retry policy shape (bounded, jittered, disclosed)
# ---------------------------------------------------------------------------

def test_retry_policy_backoff_is_bounded_and_exponential() -> None:
    policy = RetryPolicy(
        max_attempts=4, backoff_base_seconds=1, backoff_max_seconds=10
    )
    assert [policy.backoff_for(a) for a in (1, 2, 3, 4, 5)] == [
        1.0, 2.0, 4.0, 8.0, 10.0  # capped at max
    ]
    disclosed = policy.describe()
    assert disclosed["maxAttempts"] == 4
    assert "full jitter" in disclosed["backoff"]
    assert disclosed["timeoutSeconds"] == policy.timeout_seconds


# ---------------------------------------------------------------------------
# Route-level: lifecycle + idempotency (LOCAL inline executor)
# ---------------------------------------------------------------------------

def test_route_recovery_job_full_lifecycle_inline(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        response = client.post(
            "/api/v1/jobs",
            json={
                "workspaceId": DEMO_WS, "type": "system_recovery",
                "repositoryUrl": FIXTURE_REPO, "ref": "staging",
                "idempotencyKey": "route-life-1",
            },
        )
        assert response.status_code == 200, response.text
        job = response.json()
        # directive §8 fields, exactly, on the wire
        for field in (
            "id", "tenantId", "type", "requestedBy", "authoritySnapshot",
            "inputHash", "sourceRevision", "provider", "status", "startedAt",
            "completedAt", "receipt", "artifactRefs", "errorState",
        ):
            assert field in job, field
        assert job["status"] == "succeeded"
        assert job["type"] == "system_recovery"
        assert job["provider"] == "local"
        assert len(job["sourceRevision"]) == 40  # pinned immutable commit
        assert job["receipt"]["fixture"] is True
        assert job["startedAt"] and job["completedAt"]
        # the queued → running → succeeded lifecycle left audit evidence
        detail = client.get("/api/v1/jobs").json()
        assert job["id"] in {row["id"] for row in detail["items"]}
        fetched = client.get(f"/api/v1/jobs/{job['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["status"] == "succeeded"


def test_route_idempotent_replays_return_same_job_no_duplicates(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        payload = {
            "workspaceId": DEMO_WS, "type": "system_recovery",
            "repositoryUrl": FIXTURE_REPO, "idempotencyKey": "route-idem-1",
        }
        ids = [
            client.post("/api/v1/jobs", json=payload).json()["id"]
            for _ in range(3)
        ]
        assert ids[0] == ids[1] == ids[2]
        jobs = [
            j for j in client.get("/api/v1/jobs?type=system_recovery").json()
            ["items"]
            if j["id"] == ids[0]
        ]
        assert len(jobs) == 1
        # one recovery evidence record for that idempotency key
        evidence = [
            e for e in client.get("/api/v1/evidence").json()["items"]
            if e["id"] == f"ev-{ids[0]}"
        ]
        assert len(evidence) == 1


def test_route_execution_job_handoff_to_execution_seam(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        response = client.post(
            "/api/v1/jobs",
            json={
                "workspaceId": DEMO_WS, "type": "experiment_execution",
                "experimentId": "exp-demo-cache",
                "idempotencyKey": "route-exec-1",
            },
        )
        assert response.status_code == 200, response.text
        job = response.json()
        assert job["status"] == "succeeded"
        assert job["provider"] == "demo"
        assert job["receipt"]["demo"] is True
        assert job["receipt"]["outcome"]["state"] == "SUCCESS"


def test_route_truthful_failure_is_a_job_state_not_an_error(
    tmp_path: Path,
) -> None:
    """A job whose operation fails truthfully records ``failed`` with the
    disclosed retry policy — never a fake success, never a masked error."""
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        response = client.post(
            "/api/v1/jobs",
            json={
                "workspaceId": DEMO_WS, "type": "system_recovery",
                "repositoryUrl": "https://github.com/sos-demo/no-such-repo",
                "idempotencyKey": "route-fail-1",
            },
        )
        assert response.status_code == 200, response.text
        job = response.json()
        assert job["status"] == "failed"
        assert job["errorState"]
        assert "not available" in job["errorState"]
        # the retry policy is disclosed on the failed job
        assert "maxAttempts" in job["errorState"]
        fetched = client.get(f"/api/v1/jobs/{job['id']}")
        assert fetched.json()["status"] == "failed"


def test_route_requires_explicit_pinned_inputs(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        response = client.post(
            "/api/v1/jobs",
            json={
                "workspaceId": DEMO_WS, "type": "system_recovery",
                "idempotencyKey": "route-no-repo-1",
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION"
        response = client.post(
            "/api/v1/jobs",
            json={
                "workspaceId": DEMO_WS, "type": "experiment_execution",
                "idempotencyKey": "route-no-exp-1",
            },
        )
        assert response.status_code == 422


def test_anonymous_job_creation_rejected(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/v1/jobs",
            json={
                "workspaceId": DEMO_WS, "type": "system_recovery",
                "repositoryUrl": FIXTURE_REPO,
            },
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"


# ---------------------------------------------------------------------------
# Service-level: retry, timeout, locks, rescue, input loss (injected ops)
# ---------------------------------------------------------------------------

class _OpRecorder:
    def __init__(self, outcomes: list[Any] | None = None):
        self.calls = 0
        self.outcomes = outcomes or []

    def __call__(self, container, scope, row, session, job_input):
        self.calls += 1
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return {
            "status": "succeeded", "receipt": {"demo": True},
            "artifactRefs": [], "errorState": None,
        }


def _service_with(container, recorder, **kwargs):
    return JobService(
        container,
        operations={"system_recovery": recorder},
        sleep=kwargs.pop("sleeps", []).append if "sleeps" in kwargs
        else (lambda seconds: None),
        **kwargs,
    )


def _container(tmp_path: Path) -> Any:
    app = make_client(tmp_path).app
    return app.state.container


def test_retry_recovers_within_bounded_attempts(tmp_path: Path) -> None:
    container = _container(tmp_path)
    sleeps: list[float] = []
    recorder = _OpRecorder(
        [
            JobRetryableError("transient provider trouble"),
            JobRetryableError("another transient failure"),
        ]
    )
    service = JobService(
        container,
        operations={"system_recovery": recorder},
        sleep=sleeps.append,
        jitter=lambda upper: upper,  # observe the raw backoff schedule
    )
    created, row = service.create_job(
        scope=_scope_for(), session=_stub_session(container),
        body=_recovery_body("retry-recover-1"), audit=None,
    )
    assert created and row["status"] == "queued"
    final = service.execute_job(
        scope=_scope_for(), job_row=row, session=_stub_session(container)
    )
    assert final["status"] == "succeeded"
    assert recorder.calls == 3  # two failures + the successful third attempt
    # jittered backoffs were applied between attempts (0-jitter in test)
    assert sleeps == [1.0, 2.0]  # base 1s: 2^(attempt-1) = 1, 2


def test_retry_bound_stops_at_max_attempts_and_discloses_policy(
    tmp_path: Path,
) -> None:
    container = _container(tmp_path)
    recorder = _OpRecorder(
        [JobRetryableError("always failing") for _ in range(10)]
    )
    service = JobService(
        container, operations={"system_recovery": recorder},
        sleep=lambda seconds: None, jitter=lambda upper: 0.0,
    )
    _, row = service.create_job(
        scope=_scope_for(), session=_stub_session(container),
        body=_recovery_body("retry-bound-1"), audit=None,
    )
    final = service.execute_job(
        scope=_scope_for(), job_row=row, session=_stub_session(container)
    )
    assert final["status"] == "failed"
    assert recorder.calls == 3  # default max_attempts = 3
    error = str(final["error_state"])
    assert "failed after 3 attempt(s)" in error
    assert "maxAttempts" in error  # the policy is disclosed on the wire


def test_permanent_failures_do_not_retry(tmp_path: Path) -> None:
    container = _container(tmp_path)
    recorder = _OpRecorder([JobPermanentError("governed rejection")])
    service = JobService(
        container, operations={"system_recovery": recorder},
        sleep=lambda seconds: None,
    )
    _, row = service.create_job(
        scope=_scope_for(), session=_stub_session(container),
        body=_recovery_body("perm-fail-1"), audit=None,
    )
    final = service.execute_job(
        scope=_scope_for(), job_row=row, session=_stub_session(container)
    )
    assert final["status"] == "failed"
    assert recorder.calls == 1
    assert "governed rejection" in str(final["error_state"])


def test_timeout_is_bounded_and_retried_then_failed(tmp_path: Path) -> None:
    container = _container(tmp_path)

    def _slow(container, scope, row, session, job_input):
        time.sleep(5.0)  # far beyond the injected timeout bound
        return {"status": "succeeded"}

    service = JobService(
        container, operations={"system_recovery": _slow},
        sleep=lambda seconds: None, jitter=lambda upper: 0.0,
        run_bounded=lambda fn, *, args, timeout_seconds: (
            time.sleep(min(0.05, timeout_seconds)),
            (_ for _ in ()).throw(
                JobTimeoutError(
                    f"operation exceeded its {timeout_seconds}s time bound"
                )
            ),
        )[1],
    )
    _, row = service.create_job(
        scope=_scope_for(), session=_stub_session(container),
        body=_recovery_body("timeout-1"), audit=None,
    )
    started = time.monotonic()
    final = service.execute_job(
        scope=_scope_for(), job_row=row, session=_stub_session(container)
    )
    elapsed = time.monotonic() - started
    assert elapsed < 2.0  # bounded: never waits for the 5s operation
    assert final["status"] == "failed"
    assert "time bound" in str(final["error_state"])


def test_default_run_bounded_enforces_timeout(tmp_path: Path) -> None:
    from services.api.jobs.service import _default_run_bounded

    def _slow():
        time.sleep(1.0)

    started = time.monotonic()
    with pytest.raises(JobTimeoutError):
        _default_run_bounded(_slow, args=(), timeout_seconds=0.1)
    assert time.monotonic() - started < 0.5

    def _fast(value):
        return value * 2

    assert _default_run_bounded(
        _fast, args=(21,), timeout_seconds=5.0
    ) == 42


def test_concurrent_dispatch_executes_exactly_once(tmp_path: Path) -> None:
    """The orchestration-lock acceptance test: concurrent claims of the
    same queued job → the operation runs EXACTLY once; every claimant
    observes the same terminal row."""
    container = _container(tmp_path)
    active = []
    executions = []

    def _counting(container, scope, row, session, job_input):
        active.append(1)
        executions.append(1)
        assert len(active) == 1  # genuinely single-threaded execution
        time.sleep(0.15)  # hold the lease long enough for the race
        active.pop()
        return {
            "status": "succeeded", "receipt": {"demo": True},
            "artifactRefs": [], "errorState": None,
        }

    service = JobService(
        container, operations={"system_recovery": _counting},
        sleep=lambda seconds: None,
    )
    _, row = service.create_job(
        scope=_scope_for(), session=_stub_session(container),
        body=_recovery_body("lock-race-1"), audit=None,
    )
    results: list[dict] = []
    errors: list[BaseException] = []

    def _claimant():
        try:
            results.append(
                service.execute_job(
                    scope=_scope_for(), job_row=row,
                    session=_stub_session(container),
                )
            )
        except BaseException as exc:  # noqa: BLE001 - recorded, asserted
            errors.append(exc)

    threads = [threading.Thread(target=_claimant) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not errors, errors
    assert executions, "the job must have executed"
    assert len(executions) == 1  # single execution under the lock
    ids = {str(r["id"]) for r in results}
    assert ids == {str(row["id"])}
    # every claimant observed a truthful lifecycle row (the losers see
    # the in-flight state; none fabricated an outcome)
    assert {r["status"] for r in results} <= {
        "queued", "running", "succeeded"
    }
    # and the durable row reaches the terminal state exactly once
    final_row = container.persistence.get_job(_scope_for(), str(row["id"]))
    assert final_row["status"] == "succeeded"


def test_second_execute_call_is_a_noop_after_terminal(tmp_path: Path) -> None:
    container = _container(tmp_path)
    recorder = _OpRecorder()
    service = JobService(
        container, operations={"system_recovery": recorder},
        sleep=lambda seconds: None,
    )
    _, row = service.create_job(
        scope=_scope_for(), session=_stub_session(container),
        body=_recovery_keyed("terminal-1"), audit=None,
    )
    first = service.execute_job(
        scope=_scope_for(), job_row=row, session=_stub_session(container)
    )
    second = service.execute_job(
        scope=_scope_for(), job_row=first, session=_stub_session(container)
    )
    assert first["status"] == second["status"] == "succeeded"
    assert recorder.calls == 1  # no re-execution of terminal jobs


def _recovery_keyed(key: str) -> CreateJobRequestDTO:
    return _recovery_body(key)


def test_stale_running_rescue_requeues_then_fails(tmp_path: Path) -> None:
    container = _container(tmp_path)
    recorder = _OpRecorder()
    service = JobService(
        container, operations={"system_recovery": recorder},
        sleep=lambda seconds: None, jitter=lambda upper: 0.0,
    )
    _, row = service.create_job(
        scope=_scope_for(), session=_stub_session(container),
        body=_recovery_body("rescue-1"), audit=None,
    )
    # simulate a crashed executor: status running, attempts partway to the
    # bound, lease gone (the in-process lock was never taken for this row).
    # The input must survive in the coordination state (as it would after a
    # real crash — only the lease is lost, not the TTL-bounded state).
    import json as _json

    state = _json.loads(
        container.coordination.job_state_get(str(row["id"])) or "{}"
    )
    state["attempts"] = 1
    container.persistence.update_job(
        _scope_for(), str(row["id"]), payload_patch={"status": "running"}
    )
    container.coordination.job_state_put(
        str(row["id"]), _json.dumps(state), ttl_seconds=3600
    )
    running = container.persistence.get_job(_scope_for(), str(row["id"]))
    rescued = service.rescue_stale_running(
        scope=_scope_for(), job_row=running
    )
    assert rescued is not None
    assert rescued["status"] == "queued"  # attempts remain → requeue
    assert "requeued after lease expiry" in str(rescued["error_state"])
    # requeued → executable again
    final = service.execute_job(
        scope=_scope_for(), job_row=rescued,
        session=_stub_session(container),
    )
    assert final["status"] == "succeeded"
    # exhausted attempts → terminal abandoned
    _, row2 = service.create_job(
        scope=_scope_for(), session=_stub_session(container),
        body=_recovery_body("rescue-2"), audit=None,
    )
    container.persistence.update_job(
        _scope_for(), str(row2["id"]), payload_patch={"status": "running"}
    )
    container.coordination.job_state_put(
        str(row2["id"]), '{"attempts": 3}', ttl_seconds=3600
    )
    running2 = container.persistence.get_job(_scope_for(), str(row2["id"]))
    abandoned = service.rescue_stale_running(
        scope=_scope_for(), job_row=running2
    )
    assert abandoned is not None
    assert abandoned["status"] == "failed"
    assert "abandoned" in str(abandoned["error_state"])


def test_lost_job_input_fails_truthfully(tmp_path: Path) -> None:
    container = _container(tmp_path)
    recorder = _OpRecorder()
    service = JobService(
        container, operations={"system_recovery": recorder},
        sleep=lambda seconds: None,
    )
    _, row = service.create_job(
        scope=_scope_for(), session=_stub_session(container),
        body=_recovery_body("input-lost-1"), audit=None,
    )
    # simulate coordination-plane loss of the ephemeral job state
    container.coordination._job_state.clear()
    final = service.execute_job(
        scope=_scope_for(), job_row=row, session=_stub_session(container)
    )
    assert final["status"] == "failed"
    assert "input is unavailable" in str(final["error_state"])
    assert recorder.calls == 0  # nothing executed without the input


def test_execute_skips_when_lock_is_held_by_another_executor(
    tmp_path: Path,
) -> None:
    container = _container(tmp_path)
    started = threading.Event()
    release = threading.Event()

    def _blocking(container, scope, row, session, job_input):
        started.set()
        release.wait(timeout=5)
        return {
            "status": "succeeded", "receipt": {}, "artifactRefs": [],
            "errorState": None,
        }

    service = JobService(
        container, operations={"system_recovery": _blocking},
        sleep=lambda seconds: None,
    )
    _, row = service.create_job(
        scope=_scope_for(), session=_stub_session(container),
        body=_recovery_body("lock-held-1"), audit=None,
    )
    outcome: dict = {}

    def _executor():
        outcome["row"] = service.execute_job(
            scope=_scope_for(), job_row=row, session=_stub_session(container)
        )

    thread = threading.Thread(target=_executor)
    thread.start()
    assert started.wait(timeout=5)
    # while the first executor holds the lease, a second claim is a no-op
    skipped = service.execute_job(
        scope=_scope_for(), job_row=row, session=_stub_session(container)
    )
    assert skipped["status"] == "running"  # observed, not executed
    release.set()
    thread.join(timeout=10)
    assert outcome["row"]["status"] == "succeeded"


# ---------------------------------------------------------------------------
# The worker (mode-independent sweep) + the PUBLIC enqueue-only split
# ---------------------------------------------------------------------------

def test_worker_sweep_executes_queued_jobs(tmp_path: Path) -> None:
    from services.api.jobs.worker import run_worker_once

    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        container = client.app.state.container
        # enqueue without the inline executor (service-level, as the worker
        # would see them after an enqueue-only API process)
        service = JobService(container)
        _, row = service.create_job(
            scope=_scope_for(), session=_stub_session(container),
            body=_recovery_body("worker-sweep-1"), audit=None,
        )
        assert row["status"] == "queued"
        summary = run_worker_once(container)
        assert summary["succeeded"] == 1
        assert summary["executed"] == 1
        final = container.persistence.get_job(_scope_for(), str(row["id"]))
        assert final["status"] == "succeeded"
        # terminal jobs leave the pending registry
        assert (DEMO_WS, str(row["id"])) not in (
            container.coordination.pending_jobs()
        )


def test_public_env_enqueues_only_then_worker_executes(
    tmp_path: Path,
) -> None:
    """The execution split: SOS_ENV=public never executes jobs in the API
    process (POST returns the queued DTO); the worker completes them."""
    from services.api.jobs.worker import run_worker_once

    settings = make_settings(
        tmp_path, env="public", session_secret="x" * 40
    )
    from services.api.main import create_app

    app = create_app(settings)
    with TestClient(app) as client:
        # stub login is refused outside LOCAL: set the deterministic stub
        # session cookie directly (the session resolution stays server-side)
        client.cookies.set("sos_session", "stub-session:user-demo-owner")
        response = client.post(
            "/api/v1/jobs",
            json={
                "workspaceId": DEMO_WS, "type": "system_recovery",
                "repositoryUrl": FIXTURE_REPO,
                "idempotencyKey": "public-enqueue-1",
            },
        )
        assert response.status_code == 200, response.text
        job = response.json()
        assert job["status"] == "queued"  # enqueued, NOT executed inline
        assert job["startedAt"] is None
        container = client.app.state.container
        summary = run_worker_once(container)
        assert summary["succeeded"] == 1
        fetched = client.get(f"/api/v1/jobs/{job['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["status"] == "succeeded"
        assert len(fetched.json()["sourceRevision"]) == 40


def test_worker_sweep_rescues_stale_running(tmp_path: Path) -> None:
    from services.api.jobs.worker import run_worker_once

    container = _container(tmp_path)
    service = JobService(container)
    _, row = service.create_job(
        scope=_scope_for(), session=_stub_session(container),
        body=_recovery_body("worker-rescue-1"), audit=None,
    )
    container.persistence.update_job(
        _scope_for(), str(row["id"]), payload_patch={"status": "running"}
    )
    container.coordination.job_state_put(
        str(row["id"]), '{"attempts": 3}', ttl_seconds=3600
    )
    summary = run_worker_once(container)
    assert summary["failed"] == 1  # abandoned at the attempt bound
    final = container.persistence.get_job(_scope_for(), str(row["id"]))
    assert final["status"] == "failed"
    assert "abandoned" in str(final["error_state"])


# ---------------------------------------------------------------------------
# Audit trail (every mutation carries an audit event — §C.2)
# ---------------------------------------------------------------------------

def test_job_mutations_are_audited(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        container = client.app.state.container
        response = client.post(
            "/api/v1/jobs",
            json={
                "workspaceId": DEMO_WS, "type": "system_recovery",
                "repositoryUrl": FIXTURE_REPO,
                "idempotencyKey": "audit-1",
            },
        )
        job_id = response.json()["id"]
        activity = client.get(
            f"/api/v1/workspaces/{DEMO_WS}"
        ).json()["recentActivity"]
        actions = {
            (event["action"], event["target"])
            for event in activity
        }
        assert ("job.created", f"job/{job_id}") in actions
        assert ("job.started", f"job/{job_id}") in actions
        assert ("job.completed", f"job/{job_id}") in actions


# ---------------------------------------------------------------------------
# Callback validation primitive (directive §16-A; the endpoint is PUB-08)
# ---------------------------------------------------------------------------

def test_callback_validation_accepts_and_replays_reject() -> None:
    from services.api.jobs.callbacks import (
        CallbackRejected,
        sign_callback_envelope,
        verify_signed_callback,
    )
    from providers.upstash.local import InProcessCoordination

    coordination = InProcessCoordination()
    secret = "callback-secret-value"
    timestamp = str(int(time.time()))
    body = '{"jobId": "job-x", "outcome": "SUCCESS"}'
    signature = sign_callback_envelope(
        secret=secret, timestamp=timestamp, nonce="nonce-1", body=body
    )
    payload = verify_signed_callback(
        secret=secret, timestamp=timestamp, nonce="nonce-1",
        signature=signature, body=body, coordination=coordination,
    )
    assert payload["jobId"] == "job-x"
    # replay: same nonce rejected even with a fresh valid signature
    with pytest.raises(CallbackRejected) as excinfo:
        verify_signed_callback(
            secret=secret, timestamp=timestamp, nonce="nonce-1",
            signature=signature, body=body, coordination=coordination,
        )
    assert "replay" in str(excinfo.value)


def test_callback_validation_rejects_tampered_expired_unconfigured() -> None:
    from services.api.jobs.callbacks import (
        CallbackRejected,
        sign_callback_envelope,
        verify_signed_callback,
    )
    from providers.upstash.local import InProcessCoordination

    coordination = InProcessCoordination()
    secret = "callback-secret-value"
    body = '{"jobId": "job-y"}'
    timestamp = str(int(time.time()))
    signature = sign_callback_envelope(
        secret=secret, timestamp=timestamp, nonce="n", body=body
    )
    # tampered body → signature mismatch
    with pytest.raises(CallbackRejected, match="signature"):
        verify_signed_callback(
            secret=secret, timestamp=timestamp, nonce="n",
            signature=signature, body='{"jobId": "tampered"}',
            coordination=coordination,
        )
    # expired timestamp → outside the window
    old = str(int(time.time()) - 3600)
    old_signature = sign_callback_envelope(
        secret=secret, timestamp=old, nonce="n2", body=body
    )
    with pytest.raises(CallbackRejected, match="window"):
        verify_signed_callback(
            secret=secret, timestamp=old, nonce="n2",
            signature=old_signature, body=body, coordination=coordination,
        )
    # no callback secret configured → fail-closed
    with pytest.raises(CallbackRejected, match="not configured"):
        verify_signed_callback(
            secret=None, timestamp=timestamp, nonce="n3",
            signature=signature, body=body, coordination=coordination,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _StubSession:
    """A minimal authenticated session for service-level calls."""

    authenticated = True
    user_id = "user-demo-owner"

    @property
    def display(self) -> str:
        return "demo-owner(user-demo-owner)"


def _stub_session(container: Any) -> _StubSession:
    return _StubSession()


def test_apierror_rate_limited_is_retryable(tmp_path: Path) -> None:
    """A RATE_LIMITED dispatch trip retries after the backoff (a quota is
    transient); other API errors are permanent job failures."""
    container = _container(tmp_path)
    recorder = _OpRecorder(
        [ApiError(status_code=429, code="RATE_LIMITED", message="slow down")]
    )
    service = JobService(
        container, operations={"system_recovery": recorder},
        sleep=lambda seconds: None, jitter=lambda upper: 0.0,
    )
    _, row = service.create_job(
        scope=_scope_for(), session=_stub_session(container),
        body=_recovery_body("rate-retry-1"), audit=None,
    )
    final = service.execute_job(
        scope=_scope_for(), job_row=row, session=_stub_session(container)
    )
    assert final["status"] == "succeeded"
    assert recorder.calls == 2

    recorder2 = _OpRecorder(
        [ApiError(status_code=404, code="NOT_FOUND", message="gone")]
    )
    service2 = JobService(
        container, operations={"system_recovery": recorder2},
        sleep=lambda seconds: None,
    )
    _, row2 = service2.create_job(
        scope=_scope_for(), session=_stub_session(container),
        body=_recovery_body("rate-perm-1"), audit=None,
    )
    final2 = service2.execute_job(
        scope=_scope_for(), job_row=row2, session=_stub_session(container)
    )
    assert final2["status"] == "failed"
    assert recorder2.calls == 1
