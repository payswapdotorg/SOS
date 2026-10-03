"""The PUB-06 job/coordination layer (directive §8, §13; contract §D PUB-06).

Modules:

- :mod:`services.api.jobs.service` — the :class:`JobService`: idempotent
  job creation (durable unique index + coordination fast path), the
  queued → running → succeeded/failed status lifecycle guarded by
  orchestration locks, and the bounded/jittered/disclosed retry policy.
- :mod:`services.api.jobs.dispatchers` — the provider dispatcher's bounded
  local operations: ``system_recovery`` (the W3 recovery pipeline) and
  ``experiment_execution`` (handoff to the governed W11 execution seam).
- :mod:`services.api.jobs.worker` — the worker entrypoint (a SEPARATE
  process from the API in PUBLIC mode; an in-process bounded executor
  serves LOCAL mode and deterministic tests).
- :mod:`services.api.jobs.callbacks` — the replay-protected signed-callback
  validation primitive (directive §16-A PUB-06 "callback validation"); the
  provider-facing callback ENDPOINT is PUB-08's surface.
"""
from __future__ import annotations

from .service import (
    JobPermanentError,
    JobRetryableError,
    JobService,
    JobTimeoutError,
    RetryPolicy,
)
from .dispatchers import BUILT_IN_OPERATIONS

__all__ = [
    "JobPermanentError",
    "JobRetryableError",
    "JobService",
    "JobTimeoutError",
    "RetryPolicy",
    "BUILT_IN_OPERATIONS",
]
