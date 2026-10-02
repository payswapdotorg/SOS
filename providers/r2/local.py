"""LOCAL artifact adapter: content-addressed local-FS store with the exact
directive §12 key layout (PUB-01). Signed-URL equivalents are HMAC tokens
(time-bounded, scoped to the exact object key) signed with the configured key
material — a clearly-labeled deterministic DEMO key in LOCAL mode; PUB-07
replaces this with real R2 signed URLs on the same seam."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any

from .seam import SeamHealth, StoredArtifact

# Directive §12 layout categories (binding).
CATEGORIES = frozenset({
    "revisions", "recovery", "evidence", "experiments", "executions",
})
EXECUTION_SUBCATEGORIES = frozenset({"logs", "reports", "receipts", "bundles"})

_DEMO_KEY_MATERIAL = b"sos-local-demo-artifact-signing-key (NOT A SECRET)"


class ArtifactSignatureError(Exception):
    """A signed-URL token is invalid, expired, or scope-mismatched."""


class LocalFsArtifactStore:
    """The LOCAL implementation of the artifact-store seam."""

    mode = "local"
    implementation = "local-fs"

    def __init__(self, root: str | Path, *, signing_key: bytes | None = None):
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._signing_key = signing_key or _DEMO_KEY_MATERIAL

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
        if category not in CATEGORIES:
            raise ValueError(f"unknown artifact category '{category}'")
        parts = [f"tenants/{tenant_id}", f"systems/{system_id}"]
        if category == "executions":
            if subcategory not in EXECUTION_SUBCATEGORIES:
                raise ValueError(
                    f"unknown execution artifact subcategory '{subcategory}'"
                )
            parts.append(f"{category}/{context_id}/{subcategory}")
        else:
            if subcategory:
                raise ValueError(
                    f"subcategory is only lawful for executions, got "
                    f"'{subcategory}'"
                )
            parts.append(f"{category}/{context_id}")
        name = f"{content_hash}"
        if filename:
            name += f"-{filename}"
        return "/".join(parts) + "/" + name

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
        content_hash = hashlib.sha256(content).hexdigest()
        key = self.build_key(
            tenant_id,
            system_id,
            category=category,
            context_id=context_id,
            subcategory=subcategory,
            content_hash=content_hash,
            filename=filename,
        )
        path = self._root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(content)
        meta = {
            "contentType": content_type,
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

    def get(self, key: str) -> bytes:
        path = self._root / key
        if not path.is_file():
            raise KeyError(f"artifact not found: {key}")
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return (self._root / key).is_file()

    # -- signed URL equivalents -------------------------------------------

    def signed_url(self, key: str, *, ttl_seconds: int, mode: str) -> str:
        if mode not in ("get", "put"):
            raise ValueError(f"unknown signed-url mode '{mode}'")
        expiry = int(time.time()) + ttl_seconds
        payload = json.dumps(
            {"key": key, "mode": mode, "exp": expiry}, sort_keys=True
        ).encode("utf-8")
        body = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
        sig = hmac.new(
            self._signing_key, body.encode("ascii"), hashlib.sha256
        ).hexdigest()
        return f"sos-local-artifact://{body}?sig={sig}"

    def resolve_signed_url(self, token: str, *, now: float) -> tuple[str, str]:
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
        if float(payload["exp"]) < now:
            raise ArtifactSignatureError("signed URL expired")
        return str(payload["key"]), str(payload["mode"])
