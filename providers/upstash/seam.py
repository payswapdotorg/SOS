"""The provider-neutral coordination seam: locks, idempotency keys,
rate-limit buckets, ephemeral job state and the pending-job registry
(directive §8/§13; PUB-06 adds the Upstash Redis adapter with identical
semantics).

Binding design rules (directive §3 "Upstash Redis — coordination plane"):

- Redis is NEVER the primary event store: durable job truth lives in the
  persistence seam (SQLite/Neon ``jobs`` table). Everything on THIS seam is
  ephemeral coordination (locks, idempotency fast-paths, fixed-window
  counters, short-lived job state, the pending-job registry) — bounded by
  TTLs, safe to lose (worst case: re-drive, never a status lie).
- LOCAL (in-process) and PUBLIC (Upstash Redis) implementations carry
  IDENTICAL semantics: same fixed-window alignment (epoch buckets), same
  decision fields, same lock mutual exclusion, same idempotency first-write
  semantics. The PUB-06 parity suite asserts this.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType
from typing import Protocol


@dataclass(frozen=True)
class SeamHealth:
    status: str  # a sos.model.TruthState value, reported verbatim
    detail: str


@dataclass(frozen=True)
class RateDecision:
    """The verdict of one rate-limit check (directive §13 buckets)."""

    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


class LockHandle(Protocol):
    """An acquired-or-not mutual-exclusion lock (context manager).

    ``acquired`` is False when the lock was already held: the caller MUST
    check it and skip the guarded section (orchestration-lock semantics —
    concurrent dispatch of the same key executes exactly once).
    """

    key: str
    acquired: bool

    def release(self) -> None: ...

    def __enter__(self) -> "LockHandle": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...


class CoordinationPort(Protocol):
    """Locks, idempotency keys, rate-limit buckets, ephemeral job state and
    the pending-job registry behind one seam."""

    mode: str
    implementation: str

    def health_check(self) -> SeamHealth: ...

    def acquire_lock(self, key: str, *, ttl_seconds: float) -> LockHandle: ...

    def idempotency_remember(self, key: str, value: str) -> bool:
        """Record ``key -> value``; return True the FIRST time only."""

    def idempotency_lookup(self, key: str) -> str | None: ...

    def rate_limit(
        self, bucket: str, key: str, *, limit: int, window_seconds: int
    ) -> RateDecision:
        """Fixed-window counter for one directive §13 bucket.

        Window alignment is EPOCH-aligned (``floor(now / window)``) on BOTH
        implementations so LOCAL and Upstash decide identically for the same
        wall clock and counter state.
        """

    # -- ephemeral job state (directive §3: "short-lived job state") -------
    # Durable job truth (status, receipt, error) lives in the persistence
    # seam's ``jobs`` table; these keys only carry retry bookkeeping that is
    # safe to lose (worst case: bounded re-execution, never a status lie).

    def job_state_get(self, job_id: str) -> str | None:
        """The stored JSON blob for ``job_id`` (or None when absent/expired)."""

    def job_state_set(self, job_id: str, value: str,
                      *, ttl_seconds: float) -> bool:
        """Create state for ``job_id`` only if absent (NX); True when created."""

    def job_state_put(self, job_id: str, value: str,
                      *, ttl_seconds: float) -> None:
        """Unconditionally write state for ``job_id`` and refresh its TTL."""

    # -- pending-job registry (directive §3: "duplicate-job suppression" /
    # "polling state"; the worker's job-discovery queue) -------------------
    # Ephemeral driver only: if this registry is lost, queued jobs remain
    # truthfully ``queued`` in the database and are re-driven on idempotent
    # replay (POST /jobs with the same key re-registers them).

    def pending_job_add(self, tenant_id: str, job_id: str,
                        *, ttl_seconds: float) -> None:
        """Register ``(tenant_id, job_id)`` as pending for the worker."""

    def pending_job_remove(self, tenant_id: str, job_id: str) -> None:
        """Drop one pending registration (job reached a terminal state)."""

    def pending_jobs(self) -> list[tuple[str, str]]:
        """Snapshot of pending ``[(tenant_id, job_id), ...]`` (may contain
        duplicates after re-registration; consumers deduplicate by job id)."""
