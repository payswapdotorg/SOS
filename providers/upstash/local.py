"""LOCAL coordination adapter: in-process locks, idempotency keys and
rate-limit buckets (PUB-01). Identical semantics to the PUB-06 Upstash
adapter; suitable for LOCAL mode and deterministic tests."""
from __future__ import annotations

import threading
import time

from .seam import LockHandle, RateDecision, SeamHealth


class _InProcessLock:
    """A non-reentrant mutual-exclusion lock released on context exit."""

    def __init__(self, key: str, acquired: bool):
        self.key = key
        self.acquired = acquired

    def release(self) -> None:
        if self.acquired:
            self.acquired = False

    def __enter__(self) -> "_InProcessLock":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class InProcessCoordination:
    """The LOCAL implementation of the coordination seam (thread-safe)."""

    mode = "local"
    implementation = "in-process"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        self._idempotency: dict[str, str] = {}
        # (bucket, key) -> (window_start, count)
        self._windows: dict[tuple[str, str], tuple[float, int]] = {}

    def health_check(self) -> SeamHealth:
        return SeamHealth(status="SUCCESS", detail="in-process coordination ok")

    def acquire_lock(self, key: str, *, ttl_seconds: float) -> LockHandle:
        del ttl_seconds  # in-process locks live no longer than the process
        with self._lock:
            lock = self._locks.setdefault(key, threading.Lock())
            acquired = lock.acquire(blocking=False)
            return _InProcessLock(key, acquired)  # type: ignore[return-value]

    def idempotency_remember(self, key: str, value: str) -> bool:
        with self._lock:
            if key in self._idempotency:
                return False
            self._idempotency[key] = value
            return True

    def idempotency_lookup(self, key: str) -> str | None:
        with self._lock:
            return self._idempotency.get(key)

    def rate_limit(
        self, bucket: str, key: str, *, limit: int, window_seconds: int
    ) -> RateDecision:
        now = time.monotonic()
        with self._lock:
            window_start, count = self._windows.get((bucket, key), (now, 0))
            if now - window_start >= window_seconds:
                window_start, count = now, 0
            count += 1
            self._windows[(bucket, key)] = (window_start, count)
            allowed = count <= limit
            retry_after = 0
            if not allowed:
                elapsed = now - window_start
                retry_after = max(1, int(window_seconds - elapsed) + 1)
            return RateDecision(
                allowed=allowed,
                limit=limit,
                remaining=max(0, limit - count),
                retry_after_seconds=retry_after,
            )
