"""Upstash Redis cloud adapter — FAIL-CLOSED placeholder (PUB-06 pending).

The PUB-06 adapter implements the same coordination semantics over Upstash
Redis (locks, idempotency keys, directive §13 rate-limit buckets). Selecting
``SOS_COORDINATION=upstash`` before PUB-06 lands aborts startup with a
precise message — never a silent fallback (fail-closed config).
"""
from __future__ import annotations


class UpstashAdapterUnavailable(Exception):
    """Raised when the PUB-06 Upstash adapter is selected before it exists."""


def build_upstash_coordination(redis_url: str):  # pragma: no cover - PUB-06
    raise UpstashAdapterUnavailable(
        "SOS_COORDINATION=upstash selects the Upstash Redis adapter, which is "
        "implemented by PUB-06 (not yet merged). Refusing to boot: no silent "
        "fallback to the LOCAL in-process adapter is permitted. Use "
        "SOS_COORDINATION=local for LOCAL mode."
    )
