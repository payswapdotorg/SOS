"""Artifact-store seam (provider-neutral) — PUB-01; R2 adapter PUB-07.

The seam lives in the ``r2`` package because Cloudflare R2 is the cloud
artifact store of the overlay (directive §3/§12); the interface is
provider-neutral. The LOCAL implementation is a content-addressed local-FS
store and the R2 implementation is the S3 SigV4 adapter — BOTH with the
SAME deterministic key layout (directive §12, single authority:
:mod:`providers.r2.layout`). Artifact bytes never live in the database;
the DB stores metadata + artifact refs only (`evidence_artifacts` rows
point at these keys).
"""
from .local import LocalFsArtifactStore
from .seam import (
    ArtifactHead,
    ArtifactSignatureError,
    ArtifactStorePort,
    ArtifactTooLarge,
    SeamHealth,
    SignedGrant,
    StoredArtifact,
)

__all__ = [
    "ArtifactHead",
    "ArtifactSignatureError",
    "ArtifactStorePort",
    "ArtifactTooLarge",
    "LocalFsArtifactStore",
    "SeamHealth",
    "SignedGrant",
    "StoredArtifact",
]
