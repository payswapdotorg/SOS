# SOS Public Deployment — Evidence/Artifact Layer (PUB-07)

The PUB-07 artifact layer: the provider-neutral artifact-store seam
(`providers/r2`) with two implementations — the LOCAL content-addressed
filesystem store and the Cloudflare R2 (S3-compatible) adapter — plus the
authenticated, tenant-scoped, rate-limited upload/download endpoints on
`services/api`. Directive §12 is the layout law; SECURITY S3/S4/S15 are the
posture law (private buckets, signed URLs, size limits).

## The deterministic key layout (directive §12)

```text
tenants/{tenantId}/systems/{systemId}/
  revisions/{revisionId}/…     immutable revision bundles
  recovery/{jobId}/…           brownfield recovery outputs
  evidence/{evidenceId}/…      evidence bundles (bytes)
  experiments/{experimentId}/… experiment artifacts
  executions/{executionId}/
    logs/ reports/ receipts/ bundles/
```

Single layout authority: `providers/r2/layout.py` (`build_key` /
`parse_key`). Both adapters mint and validate the SAME keys — an artifact
addressed by a key is addressable identically on either backend.

- **Object names are content-addressed on every PUB-07 write**: exactly
  `{sha256}` or `{sha256}-{filename}` (the hash IS the address).
- **Read paths accept any SAFE object name** under the governed tree:
  directive §12 says "use content hashes whenever possible", and the
  pre-PUB-07 demo seed already records short-hash receipt references
  (`{16-hex}.json`). Those keys are lawful tree keys whose bytes are
  honestly absent (a download reports 404, never fabricated content);
  the write path (`key_content_hash`) refuses them.
- **Traversal defense**: every read/write path validates the full tree
  shape (`parse_key`) — no separator tricks, no `..` segments, exact
  depth and category vocabulary. The LOCAL store resolves ONLY validated
  keys against the filesystem.

## Metadata in the DB, bytes in the store (never in Postgres)

`evidence_artifacts` rows (migration 0006, PUB-05) carry the metadata and
point at these keys; they are projected at evidence insert from the
payload's `artifactRef` (`db/mapping.py`). Governed flows that produce
artifacts (execution receipts via `POST /executions`, recovery jobs)
store the bytes through the seam and set `artifactRef` on the evidence
row — the DB↔store wiring. PUB-07 adds the transport surface so those
bytes can be PUT and RETRIEVED under signed, scoped, size-limited
authority.

## The transfer flow (identical wire shape on both adapters)

```text
1. POST /api/v1/artifacts/uploads      (session + membership + write
   {workspaceId, systemId, category,    bucket + CSRF + size check)
    contextId, subcategory?, filename?,
    contentType?, sizeBytes, sha256}
        ↓ returns
   {key, method:"PUT", url, expiresAt, maxBytes, store}

2. PUT url  (the artifact bytes)
   - R2: a SigV4 presigned PUT — the client uploads DIRECTLY to the
     private bucket (Render's free-tier API never proxies the bytes);
   - LOCAL: /api/v1/artifacts/object?token=… — an HMAC grant redeemed
     by the API (same semantics: one key, one mode, time-bounded).

3. POST /api/v1/artifacts/downloads {key}   (session + read-scope)
        ↓ returns {key, method:"GET", url, expiresAt, store}

4. GET url  (the artifact bytes, stored content type, sha256 ETag)
```

**Content addressing closes the substitution hole**: the bytes' sha256
MUST equal the key's hash segment (422 `VALIDATION` otherwise) — a put
grant scoped to one key can never land different content under it.

**Signed-URL properties** (both adapters, tested):

- time-bounded: 600 s (upload) / 300 s (download); expiry → 403;
- scoped to the exact object key: any path/query tamper breaks the
  signature (R2 SigV4 canonical request; LOCAL HMAC over the grant body);
- scoped to one mode: the HTTP method is part of the signature — a GET
  grant cannot PUT and vice versa;
- the R2 SECRET never reaches the browser (presigned URLs carry only the
  access key id + signature — the standard S3 pattern).

## Private-bucket posture (SECURITY S3/S4)

- The R2 adapter exposes NO public-URL path: every transfer is either a
  server-side SigV4-signed request or a presigned URL. Never enable a
  public `r2.dev` subdomain on the bucket (see `infra/r2/README.md`).
- LOCAL redemption tokens are HMAC-signed with key material that is the
  clearly-labeled DEMO key in LOCAL mode only; non-LOCAL deployments
  running the local filesystem store sign with `SOS_SESSION_SECRET`
  (wired in `services.api.main._build_adapters` — the public demo key is
  therefore non-forgeable in preview/public).
- Redemption is token-authoritative, not session-authoritative (exactly
  like an S3 presigned URL): no ambient cookie authority is consulted,
  and the per-IP/anonymous middleware buckets still apply.

## Size limits (directive §13 "Artifact uploads: size-limited"; S15)

`SOS_RATE_ARTIFACT_MAX_MB` (default 50 MB) is enforced at EVERY layer:

1. the upload-slot request (`sizeBytes` pre-declaration → 413);
2. the redemption Content-Length pre-check AND the post-read length;
3. the stores themselves (`max_bytes` construction bound — defense in
   depth; also bounds system-flow writes such as execution receipts).

The generic request-body cap (`SOS_RATE_BODY_MAX_MB`, S16) exempts ONLY
`/api/v1/artifacts/object` — the artifact-specific cap applies there
instead; every other request keeps the generic cap.

## Tenant boundaries

- **Uploads require workspace MEMBERSHIP** (S21 — the demo workspace is
  mutable only by its members) and a system that exists INSIDE the
  workspace (the §12 key is system-scoped).
- **Downloads are READS**: the key's tenant must be in the caller's scope
  (member workspaces + the demo workspace — exactly the evidence read
  surface). Cross-tenant keys → 404 (existence never leaks).

## Audit events (S17)

Every artifact operation writes an `audit_events` row:

| action | when | actor |
|---|---|---|
| `artifact.upload_authorized` | slot issued | the session identity |
| `artifact.upload_completed` | LOCAL redemption stored bytes | the grant's bound actor |
| `artifact.download_authorized` | download URL issued | the session identity |
| `artifact.download_served` | LOCAL redemption served bytes | the grant's bound actor |

R2 presigned URLs carry no actor (the S3 pattern); issuance-side audit
covers accountability — the actual transfer is client↔R2, visible in R2
access logs (operator side). Disclosed.

## Rate limiting (directive §13)

Upload-slot requests consume the §13 **write bucket** (per authenticated
user per minute); the redemption endpoint stays under the per-IP and
anonymous middleware buckets; downloads are bounded by the user bucket.
Artifact size limits are the primary §13 artifact control.

## LOCAL ↔ R2 parity

The same §12 layout, the same seam interface, the same size caps, the
same audit actions; the only differences are the URL form (relative
token URL vs absolute presigned URL) and where bytes flow (through the
API in LOCAL vs direct-to-bucket in R2). The adapter suite runs the
request/presign semantics against a scripted fake transport — no
network, no credentials (the PUB-06 Upstash precedent).

## Known limitations (truthful)

- The demo seed records receipt `artifactRef`s WITHOUT storing bytes —
  downloads of those keys report honest 404s (references only).
- Live R2 I/O (real bucket round-trips) is verified at PUB-11 with
  operator-held credentials; `infra/r2/setup.py` remains the operator's
  bucket-verification tool, and `SOS_ARTIFACTS=r2` fails closed without
  complete `SOS_R2_*` configuration (never a silent LOCAL fallback).
- Artifact deletion/lifecycle (retention, GC of unreferenced objects) is
  outside PUB-07's slice (no such §7/§D surface).
