"""LOCAL coordination adapter: in-process locks, idempotency keys,
rate-limit buckets, ephemeral job state and the pending-job registry
(PUB-01; PUB-06 aligned the fixed windows to EPOCH boundaries and added the
job-state/registry methods). Identical semantics to the PUB-06 Upstash Redis
adapter; suitable for LOCAL mode and deterministic tests."""
from __future__ import annotations

import threading
import time

from .seam import LockHandle, RateDecision, SeamHealth

# Pending-registry entries are pruned when older than this many seconds past
# their TTL refresh (opportunistic pruning keeps the dict bounded).
_PRUNE_MARGIN = 60.0


class _InProcessLock:
    """A non-reentrant mutual-exclusion lock released on context exit."""

    def __init__(self, key: str, acquired: bool, lock: threading.Lock):
        self.key = key
        self.acquired = acquired
        self._lock = lock

    def release(self) -> None:
        if self.acquired:
            self.acquired = False
            self._lock.release()

    def __enter__(self) -> "_InProcessLock":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class InProcessCoordination:
    """The LOCAL implementation of the coordination seam (thread-safe).

    Rate windows are EPOCH-aligned exactly like the Upstash adapter
    (``window_id = floor(wall_clock / window)``) so both implementations
    produce identical decisions for the same counter state.
    """

    mode = "local"
    implementation = "in-process"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        self._idempotency: dict[str, str] = {}
        # (bucket, key, window_id) -> count (epoch-aligned fixed windows)
        self._windows: dict[tuple[str, str, int], int] = {}
        # job_id -> (json_value, expires_at_monotonic)
        self._job_state: dict[str, tuple[str, float]] = {}
        # list of (tenant_id, job_id, expires_at_monotonic)
        self._pending: list[tuple[str, str, float]] = []

    def health_check(self) -> SeamHealth:
        return SeamHealth(status="SUCCESS", detail="in-process coordination ok")

    # -- locks --------------------------------------------------------------

    def acquire_lock(self, key: str, *, ttl_seconds: float) -> LockHandle:
        del ttl_seconds  # in-process locks live no longer than the process
        with self._lock:
            lock = self._locks.setdefault(key, threading.Lock())
            acquired = lock.acquire(blocking=False)
            return _InProcessLock(key, acquired, lock)  # type: ignore[return-value]

    # -- idempotency keys ---------------------------------------------------

    def idempotency_remember(self, key: str, value: str) -> bool:
        with self._lock:
            if key in self._idempotency:
                return False
            self._idempotency[key] = value
            return True

    def idempotency_lookup(self, key: str) -> str | None:
        with self._lock:
            return self._idempotency.get(key)

    # -- rate limiting (epoch-aligned fixed windows) -------------------------

    def rate_limit(
        self, bucket: str, key: str, *, limit: int, window_seconds: int
    ) -> RateDecision:
        now = time.time()
        window_id = int(now // window_seconds) if window_seconds >= 1 else 0
        with self._lock:
            self._prune_windows(now, window_seconds)
            counter_key = (bucket, key, window_id)
            count = self._windows.get(counter_key, 0) + 1
            self._windows[counter_key] = count
            allowed = count <= limit
            window_end = (window_id + 1) * window_seconds
            retry_after = 0
            if not allowed:
                retry_after = max(1, int(window_end - now) + 1)
            return RateDecision(
                allowed=allowed,
                limit=limit,
                remaining=max(0, limit - count),
                retry_after_seconds=retry_after,
            )

    def _prune_windows(self, now: float, window_seconds: int) -> None:
        """Drop closed windows so the counter dict stays bounded."""
        if len(self._windows) < 4096:
            return
        horizon = now - 2 * max(1, window_seconds)
        # Window identity encodes its start time only when window_ids are
        # comparable across buckets with the same window length; prune by a
        # conservative age estimate derived from the window id.
        stale = [
            k
            for k, _count in self._windows.items()
            if k[2] < int((horizon // max(1, window_seconds)))
        ]
        for key in stale:
            del self._windows[key]

    # -- ephemeral job state --------------------------------------------------

    def job_state_get(self, job_id: str) -> str | None:
        with self._lock:
            entry = self._job_state.get(job_id)
            if entry is None:
                return None
            value, expires_at = entry
            if time.monotonic() >= expires_at:
                del self._job_state[job_id]
                return None
            return value

    def job_state_set(self, job_id: str, value: str,
                      *, ttl_seconds: float) -> bool:
        with self._lock:
            entry = self._job_state.get(job_id)
            if entry is not None and time.monotonic() < entry[1]:
                return False
            self._job_state[job_id] = (
                value, time.monotonic() + max(0.0, ttl_seconds)
            )
            return True

    def job_state_put(self, job_id: str, value: str,
                      *, ttl_seconds: float) -> None:
        with self._lock:
            self._job_state[job_id] = (
                value, time.monotonic() + max(0.0, ttl_seconds)
            )

    # -- pending-job registry ---------------------------------------------------

    def pending_job_add(self, tenant_id: str, job_id: str,
                        *, ttl_seconds: float) -> None:
        expires_at = time.monotonic() + max(0.0, ttl_seconds)
        with self._lock:
            self._prune_pending()
            self._pending.append((tenant_id, job_id, expires_at))

    def pending_job_remove(self, tenant_id: str, job_id: str) -> None:
        with self._lock:
            self._pending = [
                entry
                for entry in self._pending
                if not (entry[0] == tenant_id and entry[1] == job_id)
            ]

    def pending_jobs(self) -> list[tuple[str, str]]:
        with self._lock:
            self._prune_pending()
            return [(tenant, job) for tenant, job, _ in self._pending]

    def _prune_pending(self) -> None:
        now = time.monotonic()
        self._pending = [e for e in self._pending if e[2] > now]
