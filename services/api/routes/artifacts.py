"""``/api/v1/artifacts`` — the PUB-07 evidence/artifact transport routes.

Directive §12 + contract §D PUB-07: signed upload/download URLs
(time-bounded, scoped to the exact object key), tenant-scoped artifact
transfers with size limits, audit events for every artifact operation.
The deterministic §12 key layout and the content-addressed stores live in
``providers/r2`` (LOCAL filesystem / R2 S3 SigV4 — same seam, same keys).

Flow (identical wire shape on both adapters):

1. ``POST /artifacts/uploads`` — an authenticated member of the target
   workspace requests an upload slot for (workspace, system, category,
   contextId[, subcategory], sha256, sizeBytes). The API validates the
   size against ``SOS_RATE_ARTIFACT_MAX_MB`` (413 PAYLOAD_TOO_LARGE),
   builds the content-addressed §12 key and returns a SIGNED, time-bounded
   put URL — R2: a SigV4 presigned PUT (the client uploads directly to
   the private bucket; the R2 secret never reaches the browser); LOCAL:
   an HMAC token redeemed at ``/artifacts/object`` (same semantics).
2. ``PUT /artifacts/object?token=…`` — the LOCAL token redemption: the
   grant authorizes exactly ONE key for ``put`` until it expires; the
   bytes' sha256 MUST equal the key's content address (content
   addressing closes the substitution hole); the artifact size cap is
   enforced here (the generic S16 request-body cap exempts this path —
   the artifact-specific cap applies instead).
3. ``POST /artifacts/downloads`` — an authenticated member requests a
   signed get URL for an existing §12 key (the key's tenant must be in
   the caller's scope — cross-tenant keys are 404, never 403-leaking).
4. ``GET /artifacts/object?token=…`` — the LOCAL get redemption.

All four routes are ``include_in_schema=False``: they extend the frozen
directive §7 wire surface beyond its listed set, and the PUB-01 OpenAPI
snapshot must stay byte-identical (the PUB-04 precedent for
post-§7 endpoints; documented in ``docs/deployment/artifacts.md``).

No SOS decision logic lives here — artifact transport only. Evidence
semantics (kinds, truth states, promotion) stay in ``src/sos`` and the
governed flows that create evidence rows; ``evidence_artifacts`` metadata
rows are projected at evidence insert (PUB-05 mapping) from the
``artifactRef`` these keys populate.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse

from ..auth.csrf import enforce_mutation_csrf
from ..auth.session import SessionIdentity
from ..container import ApiContainer
from ..dependencies import (
    audit_writer,
    ensure_workspace_access,
    get_container,
    now_iso,
    require_authenticated,
    require_workspace_membership,
    tenant_scope,
)
from ..dependencies.rate_limit import (
    ARTIFACT_OBJECT_PATH,
    check_write_quota,
)
from ..errors import (
    ApiError,
    CODE_FORBIDDEN,
    CODE_PAYLOAD_TOO_LARGE,
    not_found,
    validation,
)
from providers.r2 import layout
from providers.r2.seam import (
    ArtifactSignatureError,
    ArtifactTooLarge,
)
from providers.neon.seam import TenantScope  # noqa: E402

router = APIRouter(tags=["artifacts"])

# Signed-URL lifetimes (PUB-07 constants — disclosed in the checkpoint;
# short by design: a client that misses the window requests a fresh slot,
# and no long-lived transfer authority is ever outstanding).
UPLOAD_URL_TTL_SECONDS = 600
DOWNLOAD_URL_TTL_SECONDS = 300

_MAX_CONTENT_TYPE = 255
_SHA256_HEX = frozenset("0123456789abcdef")


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(c in _SHA256_HEX for c in value)


def _artifact_cap_bytes(container: ApiContainer) -> int:
    return container.settings.rate_artifact_max_mb * 1024 * 1024


def _payload_too_large(max_mb: int) -> ApiError:
    return ApiError(
        status_code=413,
        code=CODE_PAYLOAD_TOO_LARGE,
        message="artifact exceeds the upload size limit",
        details={"maxArtifactMb": max_mb},
    )


def _store_label(container: ApiContainer) -> dict[str, Any]:
    store = container.artifacts
    return {
        "mode": store.mode,
        "implementation": store.implementation,
        "demo": store.mode == "local",
    }


async def _json_body(request: Request) -> dict[str, Any]:
    raw = await request.body()
    try:
        parsed = json.loads(raw or b"{}")
    except ValueError as exc:
        raise validation(f"request body must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise validation("request body must be a JSON object")
    return parsed


def _forbidden(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            "error": {
                "code": CODE_FORBIDDEN,
                "message": message,
                "details": None,
            }
        },
    )


@router.post("/artifacts/uploads", include_in_schema=False)
async def request_upload_slot(
    request: Request,
    scope: TenantScope = Depends(tenant_scope),
    session: SessionIdentity = Depends(require_authenticated),
    container: ApiContainer = Depends(get_container),
    audit=Depends(audit_writer),
) -> dict:
    body = await _json_body(request)
    enforce_mutation_csrf(request, session)

    workspace_id = str(body.get("workspaceId") or "").strip()
    system_id = str(body.get("systemId") or "").strip()
    category = str(body.get("category") or "").strip()
    context_id = str(body.get("contextId") or "").strip()
    subcategory = str(body.get("subcategory") or "").strip()
    filename = str(body.get("filename") or "").strip()
    sha256 = str(body.get("sha256") or "").strip().lower()
    content_type = (
        str(body.get("contentType") or "").strip()
        or "application/octet-stream"
    )
    raw_size = body.get("sizeBytes")

    if not workspace_id:
        raise validation("workspaceId is required")
    if not system_id:
        raise validation(
            "systemId is required (the §12 key layout is system-scoped)"
        )
    if not context_id:
        raise validation("contextId is required (the §12 layout context)")
    if not _is_sha256(sha256):
        raise validation(
            "sha256 must be exactly 64 lowercase hex characters (the "
            "content address for the content-addressed §12 key)"
        )
    if not isinstance(raw_size, int) or isinstance(raw_size, bool):
        raise validation(
            "sizeBytes must be an integer (the exact artifact byte count)"
        )
    if raw_size < 1:
        raise validation("sizeBytes must be >= 1")
    if raw_size > _artifact_cap_bytes(container):
        raise _payload_too_large(container.settings.rate_artifact_max_mb)
    if len(content_type) > _MAX_CONTENT_TYPE or "/" not in content_type:
        raise validation(
            f"contentType must be a media type (max {_MAX_CONTENT_TYPE} chars)"
        )
    if filename and ("/" in filename or "\\" in filename):
        raise validation("filename must be a bare name (no path separators)")

    # Tenant boundary: membership in the target workspace (S5/S21) and a
    # system that exists INSIDE it (the §12 key is system-scoped).
    require_workspace_membership(container, session, workspace_id)
    system_row = container.persistence.get_system(scope, system_id)
    if system_row is None or str(system_row["workspace_id"]) != workspace_id:
        raise not_found("system not found")

    try:
        key = layout.build_key(
            workspace_id,
            system_id,
            category=category,
            context_id=context_id,
            subcategory=subcategory,
            content_hash=sha256,
            filename=filename,
        )
    except layout.InvalidArtifactKey as exc:
        raise validation(f"unlawful artifact key: {exc}") from exc

    check_write_quota(container, session)

    store = container.artifacts
    if store.mode == "local":
        token = store.signed_url(
            key, ttl_seconds=UPLOAD_URL_TTL_SECONDS, mode="put",
            actor=str(session.user_id),
        )
        # The LOCAL redemption endpoint (this API) — a relative URL, the
        # same-origin rule as every other client-facing URL. The token is
        # percent-encoded: it contains its own ``?sig=`` segment.
        url = (
            f"{ARTIFACT_OBJECT_PATH}?token="
            f"{urllib.parse.quote(token, safe='')}"
        )
    else:
        url = store.signed_url(
            key, ttl_seconds=UPLOAD_URL_TTL_SECONDS, mode="put"
        )
    expires_at = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + UPLOAD_URL_TTL_SECONDS)
    )
    audit(
        tenant_id=workspace_id,
        actor=session.display,
        action="artifact.upload_authorized",
        target=f"artifact/{key}",
        meta={
            "category": category,
            "contextId": context_id,
            "systemId": system_id,
            "sizeBytes": raw_size,
            "sha256": sha256,
            "ttlSeconds": UPLOAD_URL_TTL_SECONDS,
        },
        ts=now_iso(),
    )
    return {
        "key": key,
        "method": "PUT",
        "url": url,
        "expiresAt": expires_at,
        "maxBytes": _artifact_cap_bytes(container),
        "store": _store_label(container),
    }


@router.post("/artifacts/downloads", include_in_schema=False)
async def request_download_slot(
    request: Request,
    scope: TenantScope = Depends(tenant_scope),
    session: SessionIdentity = Depends(require_authenticated),
    container: ApiContainer = Depends(get_container),
    audit=Depends(audit_writer),
) -> dict:
    body = await _json_body(request)
    enforce_mutation_csrf(request, session)
    key = str(body.get("key") or "").strip()
    if not key:
        raise validation("key is required (the §12 artifact key)")
    try:
        parts = layout.parse_key(key)
    except layout.InvalidArtifactKey as exc:
        raise validation(f"unlawful artifact key: {exc}") from exc

    # Tenant boundary: a download is a READ — the key's tenant must be in
    # the caller's scope (member workspaces + the demo workspace, exactly
    # the evidence read surface); cross-tenant keys are 404 (existence
    # never leaks). Uploads, by contrast, require MEMBERSHIP (S21).
    ensure_workspace_access(scope, parts.tenant_id)
    if not container.artifacts.exists(key):
        raise not_found("artifact not found")

    store = container.artifacts
    if store.mode == "local":
        token = store.signed_url(
            key, ttl_seconds=DOWNLOAD_URL_TTL_SECONDS, mode="get",
            actor=str(session.user_id),
        )
        url = (
            f"{ARTIFACT_OBJECT_PATH}?token="
            f"{urllib.parse.quote(token, safe='')}"
        )
    else:
        url = store.signed_url(
            key, ttl_seconds=DOWNLOAD_URL_TTL_SECONDS, mode="get"
        )
    expires_at = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ",
        time.gmtime(time.time() + DOWNLOAD_URL_TTL_SECONDS),
    )
    audit(
        tenant_id=parts.tenant_id,
        actor=session.display,
        action="artifact.download_authorized",
        target=f"artifact/{key}",
        meta={"ttlSeconds": DOWNLOAD_URL_TTL_SECONDS},
        ts=now_iso(),
    )
    return {
        "key": key,
        "method": "GET",
        "url": url,
        "expiresAt": expires_at,
        "store": _store_label(container),
    }


# The redemption route is declared RELATIVE (the /api/v1 prefix comes
# from the router assembly); ARTIFACT_OBJECT_PATH is the FULL request
# path used for URL building and the middleware's S16 exemption.
_OBJECT_ROUTE_PATH = "/artifacts/object"


@router.api_route(
    _OBJECT_ROUTE_PATH, methods=["GET", "PUT"], include_in_schema=False
)
async def artifact_object(
    request: Request,
    container: ApiContainer = Depends(get_container),
    token: str = Query(default=""),
    audit=Depends(audit_writer),
) -> Response:
    """The LOCAL signed-URL redemption endpoint (byte transfer).

    The grant — not a browser session — authorizes the transfer (exactly
    like an R2 presigned URL): time-bounded, scoped to ONE key and ONE
    mode, HMAC-signed by the store. Sessions/CSRF do not apply (no
    ambient cookie authority is consulted); the per-IP/anonymous
    middleware buckets still apply, and the artifact-specific size cap
    (not the generic S16 body cap) bounds uploads here.
    """
    if not token:
        return _forbidden("missing signed-artifact token")
    try:
        grant = container.artifacts.resolve_grant(token, now=time.time())
    except ArtifactSignatureError as exc:
        # One honest code for every grant failure — no oracle about WHICH
        # check failed (signature, expiry or scope).
        return _forbidden("invalid or expired signed-artifact token")

    if request.method == "PUT":
        if grant.mode != "put":
            return _forbidden("grant does not authorize uploads")
        return await _redeem_put(request, container, grant, audit)
    if grant.mode != "get":
        return _forbidden("grant does not authorize downloads")
    return _redeem_get(container, grant, audit)


async def _redeem_put(
    request: Request,
    container: ApiContainer,
    grant: Any,
    audit: Any,
) -> Response:
    max_bytes = _artifact_cap_bytes(container)
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit():
        if int(content_length) > max_bytes:
            raise _payload_too_large(container.settings.rate_artifact_max_mb)
    content = await request.body()
    if len(content) > max_bytes:
        raise _payload_too_large(container.settings.rate_artifact_max_mb)
    if not content:
        raise validation("artifact body is empty")
    content_hash = hashlib.sha256(content).hexdigest()
    if content_hash != layout.key_content_hash(grant.key):
        raise validation(
            "content address mismatch: the uploaded bytes hash to "
            f"{content_hash} but the authorized key addresses "
            f"{layout.key_content_hash(grant.key)}"
        )
    content_type = (
        request.headers.get("content-type") or "application/octet-stream"
    )
    try:
        stored = container.artifacts.put_by_key(
            grant.key, content, content_type
        )
    except ArtifactTooLarge as exc:
        raise _payload_too_large(
            container.settings.rate_artifact_max_mb
        ) from exc
    except layout.InvalidArtifactKey as exc:
        raise validation(f"unlawful artifact key: {exc}") from exc
    audit(
        tenant_id=layout.parse_key(grant.key).tenant_id,
        actor=grant.actor or "signed-artifact-token",
        action="artifact.upload_completed",
        target=f"artifact/{grant.key}",
        meta={"sha256": stored.sha256, "size": stored.size},
        ts=now_iso(),
    )
    return JSONResponse(
        status_code=201,
        content={
            "key": stored.key,
            "sha256": stored.sha256,
            "size": stored.size,
        },
    )


def _redeem_get(container: ApiContainer, grant: Any, audit: Any) -> Response:
    head = container.artifacts.head(grant.key)
    if head is None:
        raise not_found("artifact not found")
    content = container.artifacts.get(grant.key)
    audit(
        tenant_id=layout.parse_key(grant.key).tenant_id,
        actor=grant.actor or "signed-artifact-token",
        action="artifact.download_served",
        target=f"artifact/{grant.key}",
        meta={"size": head.size},
        ts=now_iso(),
    )
    return Response(
        content=content,
        media_type=head.content_type,
        headers={
            # The ETag is the served bytes' sha256 — for content-addressed
            # keys (every PUB-07 write) it equals the key's address.
            "ETag": f'"{hashlib.sha256(content).hexdigest()}"',
            "X-Artifact-Key": grant.key,
        },
    )
