"""Neon (PostgreSQL) cloud adapter — FAIL-CLOSED placeholder (PUB-05 pending).

The seam interface is final for PUB-01 (``providers/neon/seam.py``); the Neon
implementation (PostgreSQL via an async driver, Neon serverless-compatible)
arrives with PUB-05. Selecting ``SOS_PERSISTENCE=neon`` before that lands is a
configuration error and aborts startup with a precise message — never an
insecure or silent fallback to the LOCAL adapter (SECURITY threat notes:
fail-closed config).
"""
from __future__ import annotations


class NeonAdapterUnavailable(Exception):
    """Raised when the PUB-05 Neon adapter is selected before it exists."""


def build_neon_persistence(database_url: str):  # pragma: no cover - PUB-05
    raise NeonAdapterUnavailable(
        "SOS_PERSISTENCE=neon selects the Neon (PostgreSQL) adapter, which is "
        "implemented by PUB-05 (not yet merged). Refusing to boot: no silent "
        "fallback to the LOCAL SQLite adapter is permitted. Use "
        "SOS_PERSISTENCE=local for LOCAL mode."
    )
