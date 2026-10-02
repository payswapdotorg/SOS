"""The provider-neutral artifact-store seam (directive §12).

Key layout (deterministic, content-hashed):

``tenants/{tenantId}/systems/{systemId}/revisions/{revisionId}`` |
``.../recovery/{jobId}`` | ``.../evidence/{evidenceId}`` |
``.../experiments/{experimentId}`` | ``.../executions/{executionId}/logs`` |
``/reports`` | ``/receipts`` | ``/bundles`` — with the content hash as the
object filename. Signed URLs (time-bounded, scoped to the exact object key)
are produced via :meth:`ArtifactStorePort.signed_url`; LOCAL mode signs with a
clearly-labeled demo key (PUB-07 hardens with real R2 signing).
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

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def signed_url(self, key: str, *, ttl_seconds: int, mode: str) -> str:
        """A time-bounded, key-scoped signed URL (or LOCAL equivalent)."""

    def resolve_signed_url(self, token: str, *, now: float) -> tuple[str, str]:
        """Validate a signed token → (key, mode); raise on expiry/scope error."""
