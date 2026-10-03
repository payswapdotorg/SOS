"""Database layer for the Public Deployment Overlay (PUB-01; PUB-05 added
the Postgres dialect, the async migration runner and the shared mapping).

``migrations/`` — numbered, forward-creatable, REVERSIBLE schema migrations
(SQL files, applied by ``db/runner.py``). The SAME migration set runs on
SQLite (verbatim) and PostgreSQL/Neon (deterministic dialect translation:
JSON columns → JSONB, REAL → DOUBLE PRECISION).

``mapping.py`` — the single domain-object ↔ row mapping authority shared by
BOTH persistence adapters (JSON-column registry, tenant-table registry,
decomposition/reassembly of the normalized §11 entity rows, deterministic
row ids, identical JSON serialization on both backends).

``seeds/`` — deterministic demo seed data.

The ``sos`` package (``src/``) is NEVER imported from here except in the
demo seed's domain-object construction, which is mapping only.
"""
