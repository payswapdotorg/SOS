"""Artifact-store seam (provider-neutral) — PUB-01.

The seam lives in the ``r2`` package because Cloudflare R2 is the cloud
artifact store of the overlay (directive §3/§12); the interface is
provider-neutral. The LOCAL implementation is a content-addressed local-FS
store with the SAME deterministic key layout (directive §12); PUB-07 adds the
R2 (S3-compatible) adapter. Artifact bytes never live in the database; the DB
stores metadata + artifact refs only.
"""
from .local import LocalFsArtifactStore
from .seam import ArtifactStorePort, SeamHealth, StoredArtifact

__all__ = ["ArtifactStorePort", "LocalFsArtifactStore", "SeamHealth", "StoredArtifact"]
