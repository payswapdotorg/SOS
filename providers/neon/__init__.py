"""Persistence seam (provider-neutral) — PUB-01.

The seam interface lives in the ``neon`` package because Neon is the cloud
persistence provider of the Public Deployment Overlay (directive §3); the
interface itself is provider-neutral: the LOCAL implementation
(:class:`~providers.neon.local.LocalSqlitePersistence`) serves SQLite via the
``db/``-managed schema, and the Neon cloud adapter arrives with PUB-05
(fail-closed placeholder until then). Full relational mapping is PUB-05; PUB-01
persists exactly the entity set needed to serve the ``/api/v1`` surface.
"""
from .seam import Page, PersistencePort, SeamHealth, TenantScope

__all__ = ["Page", "PersistencePort", "SeamHealth", "TenantScope"]
