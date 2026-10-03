"""The PUB-06 JobService — the job model's lifecycle, idempotency, locks and
retry policy (directive §8, contract §D PUB-06).

Binding semantics:

- **Durable truth lives in the persistence seam** (``jobs`` table — the
  directive §8 fields exactly; unique partial index on ``idempotency_key``).
  Redis (Upstash) holds ONLY ephemeral coordination: the duplicate-
  suppression fast path, orchestration locks (TTL-bounded leases), attempt
  bookkeeping, the job input for not-yet-started jobs and the pending-job
  registry. Losing the coordination plane never produces a status lie: jobs
  stay queued (re-driven on idempotent replay) or fail truthfully.
- **Idempotency** (duplicate POST /jobs → same job, no duplicate side
  effects): the DB unique index is authoritative; the coordination
  ``idempotency_remember`` fast path suppresses concurrent duplicates before
  they reach the DB, and deterministic job/evidence ids (derived from the
  idempotency key) keep repeated side effects insert-conflict-free.
- **Orchestration locks**: claiming a job takes
  ``sos:lock:job:{id}`` (SET NX EX — TTL-bounded lease). Concurrent
  dispatches/claims of the same job execute exactly once: the loser sees
  ``acquired=False`` and skips. The lock is efficiency; the status-guarded
  transition under the lock is correctness.
- **Retry policy (bounded, jittered, disclosed)**: at most
  ``job_max_attempts`` attempts; backoff = ``min(job_backoff_max_seconds,
  job_backoff_base_seconds * 2**(attempt-1))`` with FULL jitter (the sleep
  is uniform in ``[0, backoff]``); every attempt is time-bounded by
  ``job_timeout_seconds``. The policy is disclosed on every failed job's
  ``error_state`` and in ``docs/deployment/jobs.md``.
- **Status lifecycle**: ``queued`` (created, awaiting dispatch) →
  ``running`` (claimed under lock) → ``succeeded`` | ``failed`` (terminal,
  with receipt/error state). Truthful non-SUCCESS provider outcomes (FAILED/
  UNKNOWN/UNAVAILABLE receipts) are terminal RESULTS, not retryable
  infrastructure failures — they are never retried into a fake success.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from ..config import Settings

# Fallback actor label used when no session is available (worker path).
WORKER_ACTOR = "job-worker"

Operation = Callable[..., dict[str, Any]]


class JobError(Exception):
    """Base class for job-layer failures."""

    retryable: bool = False


class JobPermanentError(JobError):
    """A failure that retrying cannot fix (validation, governed rejection,
    conflict). The job terminates as ``failed`` immediately."""

    retryable = False


class JobRetryableError(JobError):
    """An explicitly retryable failure (transient provider trouble)."""

    retryable = True


class JobTimeoutError(JobError):
    """The operation exceeded its time bound (retryable, bounded by the
    attempt count — never unbounded waiting)."""

    retryable = True


@dataclass(frozen=True)
class RetryPolicy:
    """Directive §8 retry policy: bounded, jittered, disclosed."""

    max_attempts: int = 3
    backoff_base_seconds: int = 1
    backoff_max_seconds: int = 30
    timeout_seconds: int = 60
    lease_seconds: int = 600

    @classmethod
    def from_settings(cls, settings: Settings) -> "RetryPolicy":
        return cls(
            max_attempts=max(1, settings.job_max_attempts),
            backoff_base_seconds=max(0, settings.job_backoff_base_seconds),
            backoff_max_seconds=max(0, settings.job_backoff_max_seconds),
            timeout_seconds=max(1, settings.job_timeout_seconds),
            lease_seconds=max(1, settings.job_lease_seconds),
        )

    def backoff_for(self, attempt: int) -> float:
        """Exponential backoff for ``attempt`` (1-based), capped."""
        exponent = max(0, attempt - 1)
        raw = float(self.backoff_base_seconds) * (2 ** exponent)
        return min(float(self.backoff_max_seconds), raw)

    def describe(self) -> dict[str, Any]:
        """The disclosed policy (recorded on failed jobs + docs)."""
        return {
            "maxAttempts": self.max_attempts,
            "backoffBaseSeconds": self.backoff_base_seconds,
            "backoffMaxSeconds": self.backoff_max_seconds,
            "backoff": "min(max, base * 2^(attempt-1)), full jitter",
            "timeoutSeconds": self.timeout_seconds,
            "leaseSeconds": self.lease_seconds,
        }


def _default_run_bounded(
    fn: Callable[..., Any], *, args: tuple, timeout_seconds: float
) -> Any:
    """Run ``fn`` with a time bound on a daemon thread.

    The bound covers the WAITING side (the caller never blocks past the
    bound; the job then fails/ retries honestly). A timed-out operation's
    thread cannot be force-killed — it is a daemon thread that dies with
    the process, and any late side effect surfaces as a conflict on the
    next attempt (truth states preserved, never a silent success).
    """
    box: dict[str, Any] = {}
    done = threading.Event()

    def _target() -> None:
        try:
            box["result"] = fn(*args)
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            box["error"] = exc
        finally:
            done.set()

    thread = threading.Thread(
        target=_target, daemon=True, name="sos-job-operation"
    )
    thread.start()
    if not done.wait(timeout_seconds):
        raise JobTimeoutError(
            f"operation exceeded its {timeout_seconds}s time bound"
        )
    if "error" in box:
        raise box["error"]
    return box["result"]


def _default_jitter(upper: float) -> float:
    """Full jitter: uniform random in ``[0, upper]`` (directive §8: jittered)."""
    return random.uniform(0.0, upper) if upper > 0 else 0.0


def _slugish(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-")
    return (slug or "job")[:48]


def job_id_for(job_type: str, idempotency_key: str) -> str:
    """Deterministic job id derived from the idempotency key (stable side
    effects across idempotent replays: evidence ids are derived from it)."""
    prefix = "job-recovery" if job_type == "system_recovery" else "job-exec"
    return f"{prefix}-{_slugish(idempotency_key)}"


def canonical_input_hash(body: dict[str, Any]) -> str:
    """The §8 ``input_hash``: a stable hash of the canonical job input."""
    material = json.dumps(
        {
            "type": body.get("type"),
            "workspaceId": body.get("workspace_id"),
            "experimentId": body.get("experiment_id"),
            "repositoryUrl": body.get("repository_url"),
            "ref": body.get("ref"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


class JobService:
    """The job lifecycle service (one instance per container; stateless)."""

    def __init__(
        self,
        container: Any,
        *,
        operations: dict[str, Operation] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float], float] = _default_jitter,
        run_bounded: Callable[..., Any] = _default_run_bounded,
        now_iso: Callable[[], str] | None = None,
    ) -> None:
        from ..dependencies import now_iso as _now_iso

        self._container = container
        self.settings: Settings = container.settings
        self.policy = RetryPolicy.from_settings(container.settings)
        from .dispatchers import BUILT_IN_OPERATIONS

        self._operations: dict[str, Operation] = dict(
            BUILT_IN_OPERATIONS if operations is None else operations
        )
        self._sleep = sleep
        self._jitter = jitter
        self._run_bounded = run_bounded
        self._now = now_iso or _now_iso

    # -- creation (idempotent) ----------------------------------------------

    def create_job(
        self,
        *,
        scope: Any,
        session: Any,
        body: Any,
        audit: Callable[..., Any] | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """Create a job (idempotent): returns ``(created, job_row)``.

        Duplicate POSTs with the same key return the SAME job row with no
        duplicate side effects. Quotas: the job-type (§13) and provider
        (§13) buckets are consumed only for jobs that are actually created
        (replays never consume them — PUB-01 semantics preserved).
        """
        persistence = self._container.persistence
        coordination = self._container.coordination
        workspace_id = body.workspace_id
        idempotency_key = body.idempotency_key or (
            f"{body.type}:{workspace_id}:"
            f"{body.experiment_id or ''}:{body.ref or ''}"
        )
        job_id = job_id_for(body.type, idempotency_key)

        # 1. Durable replay check (the jobs.idempotency_key unique index is
        #    the authoritative dedup; this is the fast path for replays).
        existing = persistence.get_job_by_idempotency_key(
            scope, idempotency_key
        )
        if existing is not None:
            # Re-drive: a queued job whose pending registration was lost
            # (ephemeral coordination plane) is re-registered on replay.
            if existing["status"] == "queued":
                coordination.pending_job_add(
                    workspace_id, str(existing["id"]),
                    ttl_seconds=self._registry_ttl(),
                )
            return False, existing

        provider = self._provider_for(body.type)

        # 2. Directive §13 expensive-job quota (per workspace per hour).
        from ..dependencies.rate_limit import check_job_quota

        check_job_quota(self._container, workspace_id, body.type)

        # 3. Directive §13 provider bucket (per provider per minute).
        from ..dependencies.rate_limit import check_provider_quota

        check_provider_quota(self._container, provider)

        # 4. Coordination duplicate-suppression fast path (concurrent
        #    same-key POSTs before the row exists).
        remembered = coordination.idempotency_remember(
            f"job:{workspace_id}:{idempotency_key}", job_id
        )
        if not remembered:
            in_flight = self._await_in_flight_row(scope, idempotency_key)
            if in_flight is not None:
                return False, in_flight
            # No row after the window: fall through — the DB unique index
            # arbitrates authoritatively.

        # 5. Ephemeral job input + attempt state (directive §3 "short-lived
        #    job state"): the worker reads the input from the coordination
        #    plane; the durable row keeps exactly the directive §8 fields.
        input_blob = json.dumps(
            {
                "input": {
                    "workspaceId": workspace_id,
                    "type": body.type,
                    "experimentId": body.experiment_id,
                    "repositoryUrl": body.repository_url,
                    "ref": body.ref,
                },
                "attempts": 0,
            },
            sort_keys=True,
        )
        coordination.job_state_put(job_id, input_blob, ttl_seconds=self._registry_ttl())

        # 6. Durable insert (status queued — the lifecycle starts here).
        payload = {
            "type": body.type,
            "requestedBy": session.user_id,
            "authoritySnapshot": self._authority_snapshot(session, provider),
            "inputHash": canonical_input_hash(body.model_dump()),
            "sourceRevision": body.ref or "",
            "provider": provider,
            "status": "queued",
            "startedAt": None,
            "completedAt": None,
            "receipt": None,
            "artifactRefs": [],
            "errorState": None,
            "idempotencyKey": idempotency_key,
            "createdAt": self._now(),
        }
        try:
            row = persistence.insert_job(
                workspace_id=workspace_id, job_id=job_id, payload=payload
            )
        except Exception:
            # Concurrent creator won the unique index race: replay.
            winner = persistence.get_job_by_idempotency_key(
                scope, idempotency_key
            )
            if winner is not None:
                return False, winner
            raise

        coordination.pending_job_add(
            workspace_id, job_id, ttl_seconds=self._registry_ttl()
        )
        if audit is not None:
            audit(
                tenant_id=workspace_id, actor=session.display,
                action="job.created", target=f"job/{job_id}",
                meta={
                    "type": body.type, "status": "queued",
                    "idempotencyKey": idempotency_key, "provider": provider,
                },
                ts=self._now(),
            )
        return True, row

    # -- claim + execute (the lifecycle) -------------------------------------

    def execute_job(
        self,
        *,
        scope: Any,
        job_row: dict[str, Any] | Any,
        session: Any = None,
        audit: Callable[..., Any] | None = None,
    ) -> dict[str, Any]:
        """Claim + run one job to a terminal state under the orchestration
        lock, applying the bounded retry policy. Returns the final row.

        Safe to call concurrently for the same job (lock + status guard →
        exactly one execution; the other callers see the same final row).
        """
        persistence = self._container.persistence
        coordination = self._container.coordination
        job_id = str(job_row["id"])
        tenant_id = str(job_row["tenant_id"])

        current = persistence.get_job(scope, job_id)
        if current is None or current["status"] != "queued":
            return current if current is not None else dict(job_row)

        lock = coordination.acquire_lock(
            f"job:{job_id}", ttl_seconds=self.policy.lease_seconds
        )
        if not lock.acquired:
            # Another executor holds the lease: this dispatch is a no-op.
            return persistence.get_job(scope, job_id) or dict(job_row)
        with lock:
            current = persistence.get_job(scope, job_id)
            if current is None or current["status"] != "queued":
                return current if current is not None else dict(job_row)
            actor = self._actor_for(current, session)
            current = persistence.update_job(
                scope, job_id,
                payload_patch={
                    "status": "running",
                    "startedAt": current.get("started_at") or self._now(),
                },
            )
            if audit is not None:
                audit(
                    tenant_id=tenant_id, actor=actor,
                    action="job.started", target=f"job/{job_id}",
                    meta={"status": "running"}, ts=self._now(),
                )
            return self._run_with_retry(
                scope=scope, row=current, session=session, audit=audit,
                actor=actor,
            )

    def _run_with_retry(
        self,
        *,
        scope: Any,
        row: dict[str, Any],
        session: Any,
        audit: Callable[..., Any] | None,
        actor: str,
    ) -> dict[str, Any]:
        persistence = self._container.persistence
        coordination = self._container.coordination
        job_id = str(row["id"])
        tenant_id = str(row["tenant_id"])
        job_type = str(row["type"])
        operation = self._operations.get(job_type)
        if operation is None:
            return self._terminal(
                scope=scope, row=row, actor=actor, audit=audit,
                status="failed",
                error_state=(
                    f"no provider-dispatch operation registered for job "
                    f"type {job_type!r}"
                ),
            )

        state = self._read_state(job_id)
        attempts_used = int(state.get("attempts") or 0)
        input_payload = state.get("input")
        operation_session = session or _job_session(row)

        last_error: str = ""
        attempt = attempts_used
        while attempt < self.policy.max_attempts:
            attempt += 1
            self._write_state(job_id, state, attempts=attempt)
            try:
                if input_payload is None:
                    raise JobPermanentError(
                        "job input is unavailable (coordination state "
                        "expired or lost) — re-submit the job with the "
                        "same idempotency key to re-drive it"
                    )
                patch = self._run_bounded(
                    operation,
                    args=(
                        self._container, scope, row, operation_session,
                        input_payload,
                    ),
                    timeout_seconds=self.policy.timeout_seconds,
                )
                return self._terminal(
                    scope=scope, row=row, actor=actor, audit=audit,
                    patch=patch,
                )
            except JobPermanentError as exc:
                return self._terminal(
                    scope=scope, row=row, actor=actor, audit=audit,
                    status="failed", error_state=str(exc),
                    attempts=attempt,
                )
            except Exception as exc:  # noqa: BLE001 - bounded retry loop
                retryable = getattr(exc, "retryable", None)
                if retryable is None:
                    code = getattr(exc, "code", None)
                    retryable = code == "RATE_LIMITED"
                last_error = f"{type(exc).__name__}: {exc}"
                if not retryable or attempt >= self.policy.max_attempts:
                    break
                backoff = self.policy.backoff_for(attempt)
                self._sleep(self._jitter(backoff))

        return self._terminal(
            scope=scope, row=row, actor=actor, audit=audit, status="failed",
            error_state=(
                f"failed after {attempt} attempt(s); last error: "
                f"{last_error or 'unknown'}"
            ),
            attempts=attempt,
        )

    # -- crash recovery (stale running jobs) ----------------------------------

    def rescue_stale_running(
        self, *, scope: Any, job_row: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Recover a ``running`` job whose lease expired (executor crashed).

        - attempts remaining → requeue (status ``queued``, re-registered
          pending; the next worker pass re-claims it);
        - attempts exhausted → terminal ``failed`` ("abandoned").
        Returns the updated row, or None when the job is still leased.
        """
        persistence = self._container.persistence
        coordination = self._container.coordination
        job_id = str(job_row["id"])
        tenant_id = str(job_row["tenant_id"])
        if job_row.get("status") != "running":
            return None
        lock = coordination.acquire_lock(
            f"job:{job_id}", ttl_seconds=self.policy.lease_seconds
        )
        if not lock.acquired:
            return None  # a live executor still holds the lease
        with lock:
            current = persistence.get_job(scope, job_id)
            if current is None or current["status"] != "running":
                return current
            state = self._read_state(job_id)
            attempts = int(state.get("attempts") or 0)
            if attempts >= self.policy.max_attempts:
                row = persistence.update_job(
                    scope, job_id,
                    payload_patch={
                        "status": "failed",
                        "completedAt": self._now(),
                        "errorState": (
                            f"abandoned: lease expired after {attempts} "
                            "attempt(s) (retry policy: "
                            f"{json.dumps(self.policy.describe())})"
                        ),
                    },
                )
                coordination.pending_job_remove(tenant_id, job_id)
                return row
            row = persistence.update_job(
                scope, job_id,
                payload_patch={
                    "status": "queued",
                    "errorState": (
                        f"requeued after lease expiry (attempt {attempts} "
                        "of the bounded retry policy)"
                    ),
                },
            )
            coordination.pending_job_add(
                tenant_id, job_id, ttl_seconds=self._registry_ttl()
            )
            return row

    # -- helpers ---------------------------------------------------------------

    def _terminal(
        self,
        *,
        scope: Any,
        row: dict[str, Any],
        actor: str,
        audit: Callable[..., Any] | None,
        patch: dict[str, Any] | None = None,
        status: str | None = None,
        error_state: str | None = None,
        attempts: int | None = None,
    ) -> dict[str, Any]:
        """Apply the terminal transition (succeeded|failed) + bookkeeping."""
        persistence = self._container.persistence
        coordination = self._container.coordination
        job_id = str(row["id"])
        tenant_id = str(row["tenant_id"])
        final_status = (
            status or (patch or {}).get("status") or "failed"
        )
        if final_status not in ("succeeded", "failed"):
            final_status = "failed"
        final_patch: dict[str, Any] = dict(patch or {})
        final_patch["status"] = final_status
        final_patch["completedAt"] = self._now()
        if final_status == "failed":
            detail = error_state or final_patch.get("errorState") or ""
            if attempts is not None:
                detail = (
                    f"{detail}; " if detail else ""
                ) + (
                    f"retry policy (bounded, jittered, disclosed): "
                    f"{json.dumps(self.policy.describe())}"
                )
            final_patch["errorState"] = detail or "job failed"
        else:
            final_patch.setdefault("errorState", None)
        updated = persistence.update_job(
            scope, job_id, payload_patch=final_patch
        )
        coordination.pending_job_remove(tenant_id, job_id)
        if audit is not None:
            audit(
                tenant_id=tenant_id, actor=actor,
                action=(
                    "job.completed" if final_status == "succeeded"
                    else "job.failed"
                ),
                target=f"job/{job_id}",
                meta={
                    "status": final_status,
                    "attempts": attempts,
                    "errorState": final_patch.get("errorState"),
                },
                ts=self._now(),
            )
        return updated or dict(row)

    def _await_in_flight_row(
        self, scope: Any, idempotency_key: str
    ) -> dict[str, Any] | None:
        """Briefly poll for a concurrently-created job row (the winner of
        the idempotency race inserts it within milliseconds)."""
        persistence = self._container.persistence
        for _ in range(10):
            row = persistence.get_job_by_idempotency_key(
                scope, idempotency_key
            )
            if row is not None:
                return row
            self._sleep(0.01)
        return None

    def _provider_for(self, job_type: str) -> str:
        if job_type == "system_recovery":
            return "local"
        return self.settings.execution_mode

    def _authority_snapshot(self, session: Any, provider: str) -> dict:
        if provider == "local":
            return {
                "principal": session.display, "workspaceRole": "member",
            }
        return {"principal": session.display, "provider": provider}

    def _actor_for(self, row: dict[str, Any], session: Any) -> str:
        if session is not None and getattr(session, "display", None):
            return session.display
        snapshot = row.get("authority_snapshot") or {}
        principal = snapshot.get("principal")
        if principal:
            return f"{principal} (via job worker)"
        return WORKER_ACTOR

    def _read_state(self, job_id: str) -> dict[str, Any]:
        raw = self._container.coordination.job_state_get(job_id)
        if raw is None:
            return {}
        try:
            state = json.loads(raw)
            return state if isinstance(state, dict) else {}
        except ValueError:
            return {}

    def _write_state(
        self, job_id: str, state: dict[str, Any], *, attempts: int
    ) -> None:
        merged = dict(state)
        merged["attempts"] = attempts
        self._container.coordination.job_state_put(
            job_id, json.dumps(merged, sort_keys=True),
            ttl_seconds=self._registry_ttl(),
        )

    def _registry_ttl(self) -> float:
        # Input + pending bookkeeping must outlive the worst-case execution
        # window (lease) but stays strictly ephemeral (bounded TTL).
        return float(max(self.policy.lease_seconds * 4, 3600))


def _job_session(job_row: dict[str, Any]) -> Any:
    """Reconstruct the recorded authority for worker-side execution.

    The job's ``requested_by`` + ``authority_snapshot`` ARE the durable
    authority record (directive §8) — the worker executes under exactly
    that authority, never under a fabricated one.
    """
    from ..auth.session import SessionIdentity

    snapshot = job_row.get("authority_snapshot") or {}
    principal = str(
        snapshot.get("principal") or job_row.get("requested_by") or "worker"
    )
    login = principal.split("(", 1)[0].strip() or "worker"
    user = {"id": str(job_row["requested_by"]), "login": login}
    return SessionIdentity(
        user=user, stub=False, provider="job-authority-snapshot", token=None
    )
