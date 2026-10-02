"""Coordination seam (provider-neutral) — PUB-01.

The seam lives in the ``upstash`` package because Upstash Redis is the cloud
coordination provider of the overlay (directive §3); the interface is
provider-neutral. The LOCAL implementation is in-process (locks, idempotency
keys, rate-limit buckets — identical semantics to the Upstash adapter that
arrives with PUB-06). Redis is NEVER the primary event store: jobs stay
durable in the persistence layer; coordination state is ephemeral.
"""
from .seam import CoordinationPort, LockHandle, RateDecision, SeamHealth

__all__ = ["CoordinationPort", "LockHandle", "RateDecision", "SeamHealth"]
