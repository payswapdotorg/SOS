"""The provider-neutral artifact-store seam (directive §12).

Key layout (deterministic, content-hashed — single authority in
:mod:`providers.r2.layout`):

``tenants/{tenantId}/systems/{systemId}/revisions/{revisionId}`` |
``.../recovery/{jobId}`` | ``.../evidence/{evidenceId}`` |
``.../experiments/{experimentId}`` | ``.../executions/{executionId}/logs`` |
``/reports`` | ``/receipts`` | ``/bundles`` — with the content hash as the
object filename. Signed URLs (time-bounded, scoped to the exact object key)
are produced via :meth:`ArtifactStorePort.signed_url`; the LOCAL
implementation signs HMAC tokens (redeemed at the API's object endpoint),
the R2 implementation (PUB-07) produces real S3 SigV4 presigned URLs.

PUB-07 additions to the port (implemented by BOTH adapters):

- ``max_bytes`` construction bound — artifact size limits are enforced IN
  THE STORE (directive §13 "Artifact uploads: size-limited", SECURITY
  S15), on top of the route-level caps;
- :meth:`ArtifactStorePort.put_by_key` — store bytes at an ALREADY-BUILT
  §12 key, verifying the content address (the sha256 segment) — the
  redemption path for signed upload URLs;
- :meth:`ArtifactStorePort.head` — object metadata without the bytes;
- :meth:`ArtifactStorePort.resolve_grant` — the FULL signed-URL grant
  (key, mode, actor, expiry) for audit accountability at redemption.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SeamHealth:
    status: str  # a sos.model.TruthState value, reported verbatim
    detail: str


@dataclass(frozen=True)
class StoredArtifact:
    """Metadata for one stored artifact (bytes live in the store, not the DB)."""

    key: str
    sha256: str
    size: int


@dataclass(frozen=True)
class ArtifactHead:
    """Head metadata for one stored artifact (no bytes transferred)."""

    key: str
    size: int
    content_type: str


@dataclass(frozen=True)
class SignedGrant:
    """The validated content of one signed-URL token.

    ``mode`` is the transfer direction the URL authorizes (``get`` or
    ``put``); ``actor`` is the identity that requested the grant (bound
    into LOCAL tokens for audit accountability; R2 presigned URLs carry
    no actor — issuance-side audit covers those, disclosed in
    ``docs/deployment/artifacts.md``).
    """

    key: str
    mode: str  # "get" | "put"
    actor: str
    expires_at: int  # epoch seconds


class ArtifactTooLarge(Exception):
    """Artifact bytes exceed the store's configured size limit (S15)."""


class ArtifactHashMismatch(Exception):
    """Bytes do not match the content address (the §12 key's sha256)."""


class ArtifactSignatureError(Exception):
    """A signed-URL token is invalid, expired, or scope-mismatched."""


class ArtifactStorePort(Protocol):
    mode: str
    implementation: str

    def health_check(self) -> SeamHealth: ...

    def put(
        self,
        tenant_id: str,
        system_id: str,
        *,
        category: str,
        context_id: str,
        subcategory: str,
        content: bytes,
        content_type: str,
        filename: str = "",
    ) -> StoredArtifact:
        """Store ``content`` under the directive §12 layout, content-addressed."""

    def put_by_key(
        self, key: str, content: bytes, content_type: str,
    ) -> StoredArtifact:
        """Store ``content`` at an already-built §12 key, verifying the
        content address (sha256 segment) — the signed-URL redemption path."""

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def head(self, key: str) -> ArtifactHead | None:
        """Object metadata (size, content type); ``None`` when absent."""

    def signed_url(self, key: str, *, ttl_seconds: int, mode: str) -> str:
        """A time-bounded, key-scoped signed URL (or LOCAL equivalent)."""

    def resolve_signed_url(self, token: str, *, now: float) -> tuple[str, str]:
        """Validate a signed token → (key, mode); raise on expiry/scope error."""

    def resolve_grant(self, token: str, *, now: float) -> SignedGrant:
        """Validate a signed token → the full grant (key, mode, actor,
        expiry); raise :class:`ArtifactSignatureError` on any mismatch."""
