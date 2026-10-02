"""The provider-neutral coordination seam: locks, idempotency keys,
rate-limit buckets (directive §8/§13; PUB-06 adds the Upstash Redis adapter
with identical semantics)."""
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
    """An acquired mutual-exclusion lock (context manager)."""

    key: str

    def release(self) -> None: ...

    def __enter__(self) -> "LockHandle": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...


class CoordinationPort(Protocol):
    """Locks, idempotency keys and rate-limit buckets behind one seam."""

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
        """Fixed-window counter for one directive §13 bucket."""
