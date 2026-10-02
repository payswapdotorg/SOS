"""Database layer for the Public Deployment Overlay (PUB-01).

``migrations/`` — numbered, forward-creatable, REVERSIBLE schema migrations
(SQL files, applied by ``db/runner.py``). SQLite-compatible now; the
Postgres-compatible DDL strategy is documented in
``docs/deployment/database.md`` (PUB-05 finalizes Postgres).

``seeds/`` — deterministic demo seed data.

The ``sos`` package (``src/``) is NEVER imported from here except in the
demo seed's domain-object construction, which is mapping only.
"""
