"""Persistence seam (provider-neutral) — PUB-01; Neon adapter landed PUB-05.

The seam interface lives in the ``neon`` package because Neon is the cloud
persistence provider of the Public Deployment Overlay (directive §3); the
interface itself is provider-neutral: the LOCAL implementation
(:class:`~providers.neon.local.LocalSqlitePersistence`) serves SQLite via the
``db/``-managed schema, and the cloud implementation
(:class:`~providers.neon.cloud.NeonPostgresPersistence`) serves PostgreSQL
(Neon) via the asyncpg driver. PUB-05 added the full relational mapping
(``db/mapping.py`` — the single mapping authority shared by BOTH adapters)
and the normalized §11 entity tables; the wire-shaped seam rows are
identical across backends (proven by the PUB-05 parity suite).
"""
from .seam import ConflictError, Page, PersistencePort, SeamHealth, TenantScope

__all__ = [
    "ConflictError",
    "Page",
    "PersistencePort",
    "SeamHealth",
    "TenantScope",
]
