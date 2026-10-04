"""R2 (S3-compatible) cloud adapter — the PUB-07 artifact store over
Cloudflare R2.

Implements the SAME provider-neutral seam as the LOCAL filesystem store
(:class:`providers.r2.local.LocalFsArtifactStore`), with the SAME
deterministic §12 key layout (single authority: :mod:`providers.r2.layout`)
— an artifact addressed by a key is addressable identically on either
backend (LOCAL↔PUBLIC parity; `evidence_artifacts` metadata rows point at
these keys).

Binding security posture (directive §12 / SECURITY S3, S4, S15):

- **private bucket by default**: the adapter exposes NO public-URL path —
  every object transfer is either a server-side SigV4-signed request or a
  time-bounded, key-scoped SigV4 PRESIGNED URL (GET or PUT). The R2
  secret never leaves the server; presigned URLs carry only the access
  key id + signature (the standard S3 pattern — never the secret);
- **signed URLs are scoped to the exact object key** (the key is part of
  the signed canonical request; any path or query tamper breaks the
  signature) and time-bounded (``X-Amz-Date`` + ``X-Amz-Expires``);
- **artifact size limits enforced in the store** (``max_bytes`` bound —
  directive §13 "Artifact uploads: size-limited");
- **content addressing on the redemption path**: ``put_by_key`` verifies
  the bytes' sha256 equals the key's hash segment.

Transport: the S3 REST API over HTTPS using ONLY the standard library
(``urllib.request``) — no new runtime dependency (the PUB-05/PUB-06
precedent keeps the frozen ``pyproject`` groups untouched). The transport
callable is injectable for deterministic tests (the PUB-07 adapter suite
runs request/presign semantics against a scripted fake transport — no
network, no credentials).

Misconfiguration (missing/``None`` credentials, non-HTTPS endpoint) aborts
boot FAIL-CLOSED with a message naming PUB-07 and the required
``SOS_R2_*`` variables — never a silent fallback to the LOCAL store.
"""
from __future__ import annotations

import calendar
import hashlib
import hmac
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from . import layout
from .seam import (
    ArtifactHead,
    ArtifactSignatureError,
    ArtifactTooLarge,
    SeamHealth,
    SignedGrant,
    StoredArtifact,
)

_REGION = "auto"  # the canonical Cloudflare R2 SigV4 region
_SERVICE = "s3"
_ALGORITHM = "AWS4-HMAC-SHA256"
_HTTP_TIMEOUT_SECONDS = 10.0

# (method, url, headers, body, timeout) -> (status, headers, body)
TransportFn = Callable[
    [str, str, dict[str, str], bytes, float],
    tuple[int, dict[str, str], bytes],
]


class R2ConfigError(Exception):
    """Raised when the R2 adapter configuration is missing/invalid."""


class R2UnavailableError(Exception):
    """Raised when the R2 endpoint cannot be reached or errors."""


def _uri_encode(value: str, *, encode_slash: bool = True) -> str:
    """RFC 3986 percent-encoding with S3's uppercase-hex convention."""
    safe = "" if encode_slash else "/"
    return urllib.parse.quote(value, safe=safe)


def _amz_date(now: float | None = None) -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))


def _scope_date(amz_date: str) -> str:
    return amz_date[:8]


def _signing_key(secret: str, date: str, region: str) -> bytes:
    k = hmac.new(("AWS4" + secret).encode("utf-8"), date.encode(), hashlib.sha256).digest()
    k = hmac.new(k, region.encode(), hashlib.sha256).digest()
    k = hmac.new(k, _SERVICE.encode(), hashlib.sha256).digest()
    return hmac.new(k, b"aws4_request", hashlib.sha256).digest()


def _signature(secret: str, date: str, region: str, string_to_sign: str) -> str:
    key = _signing_key(secret, _scope_date(date), region)
    return hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()


class R2ArtifactStore:
    """The Cloudflare R2 implementation of the artifact-store seam."""

    mode = "r2"
    implementation = "r2-s3-sigv4"

    def __init__(
        self,
        *,
        endpoint: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        max_bytes: int | None = None,
        region: str = _REGION,
        transport: TransportFn | None = None,
    ):
        self._endpoint = endpoint.rstrip("/")
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._bucket = bucket
        self._max_bytes = max_bytes
        self._region = region
        self._transport = transport or _urllib_transport
        self._base = f"{self._endpoint}/{_uri_encode(bucket, encode_slash=False)}"

    # -- layout -----------------------------------------------------------

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

    # -- seam surface ------------------------------------------------------

    def health_check(self) -> SeamHealth:
        try:
            status, _, _ = self._request("HEAD", self._base, b"", {})
            if 200 <= status < 300:
                return SeamHealth(
                    status="SUCCESS",
                    detail=(
                        f"R2 bucket '{self._bucket}' reachable at "
                        f"{self._endpoint} (HeadBucket {status})"
                    ),
                )
            return SeamHealth(
                status="FAILED",
                detail=f"R2 HeadBucket answered HTTP {status}",
            )
        except Exception as exc:  # truthful health, never a raise
            return SeamHealth(
                status="FAILED", detail=f"R2 endpoint unreachable: {exc}"
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
        return self._put_object(key, content, content_type, content_hash)

    def put_by_key(
        self, key: str, content: bytes, content_type: str,
    ) -> StoredArtifact:
        """Store at an already-built §12 key, verifying the content address
        (the signed-upload-URL redemption path — identical semantics to the
        LOCAL store; legacy non-addressed names are refused)."""
        self._enforce_size(content)
        addressed_hash = layout.key_content_hash(key)
        content_hash = hashlib.sha256(content).hexdigest()
        if content_hash != addressed_hash:
            raise layout.InvalidArtifactKey(
                "content address mismatch: bytes hash to "
                f"{content_hash} but the key addresses "
                f"{addressed_hash}"
            )
        return self._put_object(key, content, content_type, content_hash)

    def _put_object(
        self, key: str, content: bytes, content_type: str, content_hash: str,
    ) -> StoredArtifact:
        url = f"{self._base}/{_uri_encode(key, encode_slash=False)}"
        headers = {"Content-Type": content_type or "application/octet-stream"}
        self._request("PUT", url, content, headers)
        return StoredArtifact(key=key, sha256=content_hash, size=len(content))

    def get(self, key: str) -> bytes:
        layout.parse_key(key)
        url = f"{self._base}/{_uri_encode(key, encode_slash=False)}"
        status, _, body = self._request("GET", url, b"", {})
        if status == 404:
            raise KeyError(f"artifact not found: {key}")
        return body

    def exists(self, key: str) -> bool:
        return self.head(key) is not None

    def head(self, key: str) -> ArtifactHead | None:
        layout.parse_key(key)
        url = f"{self._base}/{_uri_encode(key, encode_slash=False)}"
        status, headers, _ = self._request("HEAD", url, b"", {})
        if status == 404:
            return None
        size = int(headers.get("content-length", "0") or 0)
        return ArtifactHead(
            key=key,
            size=size,
            content_type=headers.get("content-type", "application/octet-stream"),
        )

    # -- signed URLs (S3 SigV4 presigned) -----------------------------------

    def signed_url(self, key: str, *, ttl_seconds: int, mode: str) -> str:
        """A time-bounded, key-scoped SigV4 presigned URL (GET or PUT).

        The URL carries ONLY the access key id and the signature — the R2
        SECRET is never embedded (directive §12); tampering with the path
        or any query parameter invalidates the signature, and the URL
        expires at ``X-Amz-Date + X-Amz-Expires``.
        """
        if mode not in ("get", "put"):
            raise ValueError(f"unknown signed-url mode '{mode}'")
        layout.parse_key(key)
        method = "GET" if mode == "get" else "PUT"
        amz_date = _amz_date()
        scope = (
            f"{_scope_date(amz_date)}/{self._region}/{_SERVICE}/aws4_request"
        )
        query = {
            "X-Amz-Algorithm": _ALGORITHM,
            "X-Amz-Credential": f"{self._access_key_id}/{scope}",
            "X-Amz-Date": amz_date,
            "X-Amz-Expires": str(int(ttl_seconds)),
            "X-Amz-SignedHeaders": "host",
        }
        canonical_query = "&".join(
            f"{_uri_encode(k)}={_uri_encode(v)}"
            for k, v in sorted(query.items())
        )
        host = urllib.parse.urlsplit(self._endpoint).netloc
        canonical_request = "\n".join((
            method,
            f"/{_uri_encode(self._bucket, encode_slash=False)}"
            f"/{_uri_encode(key, encode_slash=False)}",
            canonical_query,
            f"host:{host}",
            "",
            "host",
            "UNSIGNED-PAYLOAD",
        ))
        string_to_sign = "\n".join((
            _ALGORITHM,
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ))
        signature = _signature(
            self._secret_access_key, amz_date, self._region, string_to_sign
        )
        return (
            f"{self._base}/{_uri_encode(key, encode_slash=False)}"
            f"?{canonical_query}&X-Amz-Signature={signature}"
        )

    def resolve_grant(self, token: str, *, now: float) -> SignedGrant:
        """Locally verify one of OUR presigned URLs → the full grant.

        Recomputes the SigV4 signature from the URL as presented (any path
        or query tamper breaks it), checks the expiry window, and derives
        the transfer mode from the signed method (GET vs PUT signatures
        differ — a GET URL cannot be replayed as a PUT and vice versa).
        """
        parts = urllib.parse.urlsplit(token)
        if parts.scheme != "https":
            raise ArtifactSignatureError("presigned URL must be https")
        if parts.netloc != urllib.parse.urlsplit(self._endpoint).netloc:
            raise ArtifactSignatureError(
                "presigned URL host does not match this store's endpoint"
            )
        query_pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        params = dict(query_pairs)
        required = {
            "X-Amz-Algorithm", "X-Amz-Credential", "X-Amz-Date",
            "X-Amz-Expires", "X-Amz-SignedHeaders", "X-Amz-Signature",
        }
        if not required.issubset(params):
            raise ArtifactSignatureError("presigned URL is missing parameters")
        if params["X-Amz-Algorithm"] != _ALGORITHM:
            raise ArtifactSignatureError("unknown signing algorithm")
        if params["X-Amz-SignedHeaders"] != "host":
            raise ArtifactSignatureError("only host-signed URLs are issued")
        signature = params["X-Amz-Signature"]
        # Rebuild the canonical query EXACTLY as issued (sorted, encoded).
        issued = {k: v for k, v in query_pairs if k != "X-Amz-Signature"}
        canonical_query = "&".join(
            f"{_uri_encode(k)}={_uri_encode(v)}"
            for k, v in sorted(issued.items())
        )
        path = urllib.parse.unquote(parts.path)
        prefix = f"/{self._bucket}/"
        if not path.startswith(prefix):
            raise ArtifactSignatureError("presigned URL is not bucket-scoped")
        key = path[len(prefix):]
        try:
            layout.parse_key(key)
        except layout.InvalidArtifactKey as exc:
            raise ArtifactSignatureError(
                f"grant key is not a lawful §12 key: {exc}"
            ) from exc
        host = urllib.parse.urlsplit(self._endpoint).netloc
        for method, mode in (("GET", "get"), ("PUT", "put")):
            canonical_request = "\n".join((
                method,
                urllib.parse.quote(
                    f"/{self._bucket}/{key}", safe="/"
                ),
                canonical_query,
                f"host:{host}",
                "",
                "host",
                "UNSIGNED-PAYLOAD",
            ))
            amz_date = params["X-Amz-Date"]
            scope = "/".join(params["X-Amz-Credential"].split("/")[1:])
            string_to_sign = "\n".join((
                _ALGORITHM,
                amz_date,
                scope,
                hashlib.sha256(
                    canonical_request.encode("utf-8")
                ).hexdigest(),
            ))
            expected = _signature(
                self._secret_access_key, amz_date, self._region, string_to_sign
            )
            if hmac.compare_digest(signature, expected):
                # X-Amz-Date is UTC — timegm, never the local-zone mktime.
                expires_at = (
                    calendar.timegm(
                        time.strptime(amz_date, "%Y%m%dT%H%M%SZ")
                    )
                    + int(params["X-Amz-Expires"])
                )
                if expires_at < now:
                    raise ArtifactSignatureError("presigned URL expired")
                return SignedGrant(
                    key=key, mode=mode, actor="", expires_at=int(expires_at),
                )
        raise ArtifactSignatureError("signature mismatch")

    def resolve_signed_url(self, token: str, *, now: float) -> tuple[str, str]:
        grant = self.resolve_grant(token, now=now)
        return grant.key, grant.mode

    # -- signed request transport -------------------------------------------

    def _request(
        self,
        method: str,
        url: str,
        body: bytes,
        headers: dict[str, str],
    ) -> tuple[int, dict[str, str], bytes]:
        """One server-side SigV4-signed S3 REST call."""
        amz_date = _amz_date()
        payload_hash = hashlib.sha256(body).hexdigest()
        split = urllib.parse.urlsplit(url)
        host = split.netloc
        all_headers = {
            **headers,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        # Canonical headers: lowercase names, sorted, one trailing \n each.
        canonical_headers = "".join(
            f"{name}:{str(all_headers[name]).strip()}\n"
            for name in sorted(all_headers)
        )
        signed_headers = ";".join(sorted(all_headers))
        canonical_query = ""
        if split.query:
            pairs = urllib.parse.parse_qsl(
                split.query, keep_blank_values=True
            )
            canonical_query = "&".join(
                f"{_uri_encode(k)}={_uri_encode(v)}" for k, v in sorted(pairs)
            )
        scope = (
            f"{_scope_date(amz_date)}/{self._region}/{_SERVICE}/aws4_request"
        )
        canonical_request = "\n".join((
            method,
            urllib.parse.quote(split.path, safe="/"),
            canonical_query,
            canonical_headers,
            signed_headers,
            payload_hash,
        ))
        string_to_sign = "\n".join((
            _ALGORITHM,
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ))
        signature = _signature(
            self._secret_access_key, amz_date, self._region, string_to_sign
        )
        request_headers = {
            **all_headers,
            "Authorization": (
                f"{_ALGORITHM} Credential={self._access_key_id}/{scope}, "
                f"SignedHeaders={signed_headers}, Signature={signature}"
            ),
        }
        try:
            return self._transport(
                method, url, request_headers, body, _HTTP_TIMEOUT_SECONDS
            )
        except urllib.error.HTTPError as exc:  # pragma: no cover - transport
            body_bytes = exc.read() if exc.fp else b""
            return exc.code, dict(exc.headers.items()), body_bytes
        except Exception as exc:
            raise R2UnavailableError(
                f"R2 request failed ({method} {split.path}): {exc}"
            ) from exc


def _urllib_transport(
    method: str, url: str, headers: dict[str, str], body: bytes, timeout: float,
) -> tuple[int, dict[str, str], bytes]:
    """The default stdlib HTTPS transport (injectable in tests)."""
    request = urllib.request.Request(
        url, data=body if body else None, method=method
    )
    for name, value in headers.items():
        request.add_header(name, value)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return (
            response.status,
            {k.lower(): v for k, v in response.headers.items()},
            response.read(),
        )


def build_r2_artifact_store(
    endpoint: str,
    access_key_id: str,
    secret_access_key: str,
    bucket: str,
    *,
    max_bytes: int | None = None,
    transport: TransportFn | None = None,
) -> R2ArtifactStore:
    """Validate the configuration FAIL-CLOSED and build the R2 store.

    ``SOS_ARTIFACTS=r2`` without complete, well-formed ``SOS_R2_*``
    credentials aborts with a precise error naming PUB-07 — never a
    silent fallback to the LOCAL filesystem store.
    """
    problems: list[str] = []
    for name, value in (
        ("SOS_R2_ENDPOINT", endpoint),
        ("SOS_R2_ACCESS_KEY_ID", access_key_id),
        ("SOS_R2_SECRET_ACCESS_KEY", secret_access_key),
        ("SOS_R2_BUCKET", bucket),
    ):
        if not isinstance(value, str) or not value.strip() or value == "None":
            problems.append(name)
    endpoint_ok = False
    if (
        isinstance(endpoint, str)
        and endpoint.strip()
        and endpoint != "None"
    ):
        split = urllib.parse.urlsplit(endpoint.strip())
        endpoint_ok = (
            split.scheme == "https" and bool(split.netloc)
        )
        if not endpoint_ok:
            raise R2ConfigError(
                "SOS_R2_ENDPOINT must be an https:// URL (the R2 S3 API "
                "endpoint, https://<account>.r2.cloudflarestorage.com) for "
                "the PUB-07 R2 artifact adapter — fail-closed"
            )
    if problems:
        raise R2ConfigError(
            "SOS_ARTIFACTS=r2 (the PUB-07 R2 artifact layer) requires "
            + ", ".join(problems)
            + " (private bucket — SECURITY S3); refusing to boot: no silent "
            "fallback to the LOCAL filesystem store is permitted"
        )
    return R2ArtifactStore(
        endpoint=endpoint.strip(),
        access_key_id=access_key_id.strip(),
        secret_access_key=secret_access_key.strip(),
        bucket=bucket.strip(),
        max_bytes=max_bytes,
        transport=transport,
    )
