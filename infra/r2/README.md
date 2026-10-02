# Cloudflare R2 — evidence/artifact storage (PUB-03 setup runbook)

Operator runbook for durable artifact storage (directive §3 R2 lane, §12
artifact layout, §20 environments). R2 free tier: 10 GB-month storage, 1M
Class A ops/month, 10M Class B ops/month, free egress.

**What R2 holds:** source snapshots, evidence bundles, execution logs,
reports, replay artifacts, screenshots/attachments, architecture exports,
test output, large JSON bundles, downloadable audit packages — under the
deterministic key layout. **All buckets PRIVATE by default; public access
only via time-bounded signed URLs (security gates S3/S4).** Artifact bytes
NEVER go in Postgres (directive §3/§11).

## Ownership boundaries (contract lanes)

| Concern | Owner |
|---|---|
| Infrastructure verification (this runbook + `setup.py`) | PUB-03 (Worker C) |
| Artifact adapter, key layout enforcement, signed URLs (`providers/r2/**`) | PUB-07 (Worker C) |
| `SOS_R2_*` naming | `infra/environment.example` (naming authority) |

## Operator steps

1. Create the bucket (choose one; all idempotent by name):
   - **Console:** dash.cloudflare.com → R2 Object Storage → Create bucket →
     name `sos-public-artifacts` → keep **public access DISABLED**.
   - **wrangler:** `wrangler r2 bucket create sos-public-artifacts`
   - **aws CLI:** `aws s3api create-bucket --bucket sos-public-artifacts \
     --endpoint-url https://<account>.r2.cloudflarestorage.com`
2. Create R2 API credentials: R2 → Manage R2 API Tokens → Create API token
   → Object Read & Write, scope = the bucket only. Note the
   **Access Key ID** and **Secret Access Key**.
3. Verify (this is the script's whole job — it never creates anything):

   ```bash
   export SOS_R2_ENDPOINT='https://<account>.r2.cloudflarestorage.com'
   export SOS_R2_ACCESS_KEY_ID='<key id>'
   export SOS_R2_SECRET_ACCESS_KEY='<secret>'
   export SOS_R2_BUCKET='sos-public-artifacts'
   python3 infra/r2/setup.py
   ```

   Expected output — four checks, all real:
   - `[ok] HeadBucket 200` — bucket exists, credentials valid
   - `[ok] Put/Get round-trip` — the account can actually write/read
   - `[ok] anonymous read rejected (403)` — **private posture, gate S3**
     (the script FAILS if the bucket answers an unsigned read)
   - `[ok] probe object deleted` — no residue left behind

   Alternative: `python3 infra/r2/setup.py --aws-cli` (same checks via the
   aws CLI against the R2 endpoint).
4. Copy the four `SOS_R2_*` values into the **Render dashboard**.
5. Offline checks (what CI/sandbox can honestly run):

   ```bash
   python3 infra/r2/setup.py --selftest   # AWS SigV4 known-answer vector, no network
   python3 infra/r2/setup.py --dry-run    # plan printout, no network
   ```

## Deterministic key layout (directive §12 — enforced by PUB-07, restated here)

```text
tenants/{tenantId}/systems/{systemId}/revisions/…    immutable revision bundles
tenants/{tenantId}/systems/{systemId}/recovery/…     brownfield recovery outputs
tenants/{tenantId}/systems/{systemId}/evidence/…     evidence bundles (bytes)
tenants/{tenantId}/systems/{systemId}/experiments/…  experiment artifacts
tenants/{tenantId}/systems/{systemId}/executions/…   execution logs/receipts
```

Object names are content-hash addressed; database rows (`evidence_artifacts`)
carry the metadata and point at these keys. The setup probe deliberately
writes only under `_setup-probe/`, never under the governed layout.

## Free-tier budget notes

- 10 GB-month storage is ample for Stage A/B demo evidence; enforce the
  `SOS_RATE_ARTIFACT_MAX_MB` cap (50 MB) on Render — the upload endpoint
  and store enforce it (S15).
- Class A ops (writes/lists) are the scarce resource at 1M/month; the job
  layer batches artifact writes (PUB-06/07 design).
- Never enable a public `r2.dev` subdomain on this bucket — public access
  is signed-URL-only by design.
