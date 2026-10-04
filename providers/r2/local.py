"""LOCAL artifact adapter: content-addressed local-FS store with the exact
directive §12 key layout (PUB-01; hardened by PUB-07).

PUB-07 hardening (all inside the ``providers/r2/**`` surface):

- **size limits enforced in the store** (``max_bytes`` construction bound;
  directive §13 "Artifact uploads: size-limited", SECURITY S15) — on the
  layout-built ``put`` AND the redemption ``put_by_key``;
- **path-traversal defense**: every read/write path goes through
  :func:`providers.r2.layout.parse_key`, which accepts ONLY the exact
  governed §12 layout (no separator tricks, no ``..`` segments);
- **content-address verification** on ``put_by_key`` (the signed-URL
  redemption path): the bytes' sha256 MUST equal the key's hash segment —
  a put-scoped token cannot store content under a different address;
- **richer signed-URL grants**: tokens now bind the requesting ``actor``
  (audit accountability at redemption) — ``resolve_grant`` returns the
  full grant; ``resolve_signed_url`` keeps the PUB-01 shape.

Signing key material: LOCAL mode signs with a clearly-labeled deterministic
DEMO key (``NOT A SECRET`` — the LOCAL/fixture posture); non-LOCAL
deployments running the local filesystem store pass real key material via
``signing_key`` (the app factory wires ``SOS_SESSION_SECRET`` — see
``services/api.main._build_adapters``). PUB-07's R2 adapter
(:mod:`providers.r2.cloud`) signs real S3 SigV4 presigned URLs on the same
seam.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any

from . import layout
from .layout import (  # noqa: F401  (re-exported: PUB-01 import sites)
    CATEGORIES,
    EXECUTION_SUBCATEGORIES,
    InvalidArtifactKey,
)
from .seam import (
    ArtifactHead,
    ArtifactSignatureError,
    ArtifactTooLarge,
    SeamHealth,
    SignedGrant,
    StoredArtifact,
)

_DEMO_KEY_MATERIAL = b"sos-local-demo-artifact-signing-key (NOT A SECRET)"

_DEFAULT_CONTENT_TYPE = "application/octet-stream"


class LocalFsArtifactStore:
    """The LOCAL implementation of the artifact-store seam."""

    mode = "local"
    implementation = "local-fs"

    def __init__(
        self,
        root: str | Path,
        *,
        signing_key: bytes | None = None,
        max_bytes: int | None = None,
    ):
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._signing_key = signing_key or _DEMO_KEY_MATERIAL
        self._max_bytes = max_bytes

    # -- layout ---------------------------------------------------------

    def build_key(
        self,
        tenant_id: str,
        system_id: str,
        *,
        category: str,
        context_id: str,
        subcategory: str,
        content_hash: str,
        filename: str,
    ) -> str:
        """The deterministic §12 key (single authority: providers.r2.layout)."""
        return layout.build_key(
            tenant_id,
            system_id,
            category=category,
            context_id=context_id,
            subcategory=subcategory,
            content_hash=content_hash,
            filename=filename,
        )

    # -- seam surface ----------------------------------------------------

    def health_check(self) -> SeamHealth:
        try:
            probe = self._root / ".health-probe"
            probe.write_bytes(b"ok")
            probe.unlink()
            return SeamHealth(
                status="SUCCESS",
                detail=f"local artifact store writable at {self._root}",
            )
        except OSError as exc:
            return SeamHealth(
                status="FAILED", detail=f"local artifact store unusable: {exc}"
            )

    def _enforce_size(self, content: bytes) -> None:
        if self._max_bytes is not None and len(content) > self._max_bytes:
            raise ArtifactTooLarge(
                f"artifact is {len(content)} bytes; the store limit is "
                f"{self._max_bytes} bytes (SOS_RATE_ARTIFACT_MAX_MB)"
            )

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
        self._enforce_size(content)
        content_hash = hashlib.sha256(content).hexdigest()
        key = layout.build_key(
            tenant_id,
            system_id,
            category=category,
            context_id=context_id,
            subcategory=subcategory,
            content_hash=content_hash,
            filename=filename,
        )
        return self._write_content_addressed(
            key, content, content_type, content_hash
        )

    def put_by_key(
        self, key: str, content: bytes, content_type: str,
    ) -> StoredArtifact:
        """Store at an already-built §12 key, verifying the content address.

        This is the signed-upload-URL redemption path: a put grant scoped
        to ``key`` can only ever land bytes whose sha256 IS the key's
        address — content addressing closes the substitution hole. Keys
        whose object name is not the 64-hex content address (legacy
        read-only surface) are refused here.
        """
        self._enforce_size(content)
        addressed_hash = layout.key_content_hash(key)
        content_hash = hashlib.sha256(content).hexdigest()
        if content_hash != addressed_hash:
            raise layout.InvalidArtifactKey(
                "content address mismatch: bytes hash to "
                f"{content_hash} but the key addresses "
                f"{addressed_hash}"
            )
        return self._write_content_addressed(
            key, content, content_type, content_hash
        )

    def _write_content_addressed(
        self, key: str, content: bytes, content_type: str,
        content_hash: str,
    ) -> StoredArtifact:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(content)
        meta = {
            "contentType": content_type or _DEFAULT_CONTENT_TYPE,
            "size": len(content),
            "createdAt": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            ),
        }
        meta_path = path.with_name(path.name + ".meta.json")
        if not meta_path.exists():
            meta_path.write_text(
                json.dumps(meta, sort_keys=True), encoding="utf-8"
            )
        return StoredArtifact(key=key, sha256=content_hash, size=len(content))

    def _resolve(self, key: str) -> Path:
        """The filesystem path for ``key`` — validated §12 layout only."""
        layout.parse_key(key)  # the traversal defense
        return self._root / key

    def get(self, key: str) -> bytes:
        path = self._resolve(key)
        if not path.is_file():
            raise KeyError(f"artifact not found: {key}")
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        try:
            return self._resolve(key).is_file()
        except layout.InvalidArtifactKey:
            return False

    def head(self, key: str) -> ArtifactHead | None:
        path = self._resolve(key)
        if not path.is_file():
            return None
        content_type = _DEFAULT_CONTENT_TYPE
        meta_path = path.with_name(path.name + ".meta.json")
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                content_type = str(
                    meta.get("contentType") or _DEFAULT_CONTENT_TYPE
                )
            except ValueError:
                pass  # honest default; the bytes remain readable
        return ArtifactHead(
            key=key, size=path.stat().st_size, content_type=content_type
        )

    # -- signed URL equivalents -------------------------------------------

    def signed_url(
        self,
        key: str,
        *,
        ttl_seconds: int,
        mode: str,
        actor: str = "",
    ) -> str:
        if mode not in ("get", "put"):
            raise ValueError(f"unknown signed-url mode '{mode}'")
        layout.parse_key(key)  # only governed keys get grants
        expiry = int(time.time()) + ttl_seconds
        payload = json.dumps(
            {"key": key, "mode": mode, "exp": expiry, "actor": actor},
            sort_keys=True,
        ).encode("utf-8")
        body = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
        sig = hmac.new(
            self._signing_key, body.encode("ascii"), hashlib.sha256
        ).hexdigest()
        return f"sos-local-artifact://{body}?sig={sig}"

    def resolve_grant(self, token: str, *, now: float) -> SignedGrant:
        if not token.startswith("sos-local-artifact://"):
            raise ArtifactSignatureError("not a local signed artifact token")
        rest = token[len("sos-local-artifact://"):]
        body, _, query = rest.partition("?")
        if not query.startswith("sig="):
            raise ArtifactSignatureError("missing signature")
        sig = query[4:]
        expected = hmac.new(
            self._signing_key, body.encode("ascii"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise ArtifactSignatureError("signature mismatch")
        padded = body + "=" * (-len(body) % 4)
        try:
            payload: dict[str, Any] = json.loads(
                base64.urlsafe_b64decode(padded.encode("ascii"))
            )
        except (ValueError, UnicodeDecodeError) as exc:
            raise ArtifactSignatureError(f"malformed token body: {exc}") from exc
        key = str(payload["key"])
        mode = str(payload["mode"])
        if mode not in ("get", "put"):
            raise ArtifactSignatureError(f"unknown grant mode '{mode}'")
        expires_at = int(payload["exp"])
        if float(expires_at) < now:
            raise ArtifactSignatureError("signed URL expired")
        try:
            layout.parse_key(key)
        except layout.InvalidArtifactKey as exc:
            raise ArtifactSignatureError(
                f"grant key is not a lawful §12 key: {exc}"
            ) from exc
        return SignedGrant(
            key=key,
            mode=mode,
            actor=str(payload.get("actor") or ""),
            expires_at=expires_at,
        )

    def resolve_signed_url(self, token: str, *, now: float) -> tuple[str, str]:
        grant = self.resolve_grant(token, now=now)
        return grant.key, grant.mode
