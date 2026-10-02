#!/usr/bin/env python3
"""Cloudflare R2 provisioning/verification script — SOS Public Deployment (PUB-03).

Operator-executed (directive §3 R2 lane, §12 artifact layout, §20
environments). Idempotent BY CONSTRUCTION: it only VERIFIES (existence,
read/write/delete, private posture) — bucket creation stays a documented
console/CLI step (see infra/r2/README.md), so this script never needs to
"undo" anything.

Reads (operator shell — reusing the APPLICATION names from
infra/environment.example on purpose: verify exactly what you wire):

  SOS_R2_ENDPOINT            https://<account>.r2.cloudflarestorage.com
  SOS_R2_ACCESS_KEY_ID       R2 API token → Access Key ID
  SOS_R2_SECRET_ACCESS_KEY   R2 API token → Secret Access Key
  SOS_R2_BUCKET              bucket name (PRIVATE — security gate S3)
  SOS_R2_REGION              optional — sigv4 region (default: auto; R2 also accepts us-east-1)

What it does:
  1. HeadBucket (signed) — bucket exists + credentials valid;
  2. PutObject/GetObject/DeleteObject round-trip on a ``_setup-probe/…``
     key — the account can actually read/write (not just list);
  3. ANONYMOUS GetObject on the same key (no signature) — MUST be rejected
     with 401/403. This is the security-gate S3 private-bucket assertion.

Honesty notes:
  * The sigv4 signer is stdlib-only and carries an OFFLINE known-answer
    test against the documented AWS Signature Version 4 example vector
    (``--selftest``) — run it anywhere, no credentials needed.
  * Live verification needs operator credentials; ``--dry-run`` runs fully
    offline. ``--aws-cli`` mode shells out to the ``aws`` CLI as a robust
    alternative if the operator prefers it.

Usage:
  python3 infra/r2/setup.py --selftest           # offline sigv4 known-answer test
  python3 infra/r2/setup.py --dry-run            # offline plan
  python3 infra/r2/setup.py                      # verify (needs the four SOS_R2_* vars)
  python3 infra/r2/setup.py --aws-cli            # same checks via the aws CLI
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import hmac
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import uuid

R2_REGION_DEFAULT = "auto"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
TIMEOUT_SECONDS = 30

# The documented AWS SigV4 example vector (Signature Version 4 signing
# process — example): parameters and expected signature, used by --selftest.
_AWS_EXAMPLE = {
    "secret": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
    "method": "GET",
    "uri": "/",
    "query": "",
    "headers": {"host": "example.amazonaws.com", "x-amz-date": "20150830T123600Z"},
    "payload_hash": EMPTY_SHA256,
    "amzdate": "20150830T123600Z",
    "date": "20150830",
    "region": "us-east-1",
    "service": "service",
    "expected_signature": "5fa00fa31553b73ebf1942676e86291e8372ff2a2260956d9b8aae1d763fbf31",
}


# ---------------------------------------------------------------------------
# SigV4 (stdlib implementation, parameterized by service so the AWS example
# vector can verify it offline)
# ---------------------------------------------------------------------------

def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _uri_encode(value: str) -> str:
    # S3 rule: encode per RFC3986 but PRESERVE '/' (each path segment
    # encoded once; never double-encode).
    return urllib.request.quote(value, safe="/-_.~")


def canonical_request(method: str, uri: str, query: str,
                      headers: dict[str, str], payload_hash: str) -> str:
    sorted_headers = {k.lower(): v.strip() for k, v in headers.items()}
    header_lines = "".join(f"{k}:{sorted_headers[k]}\n" for k in sorted(sorted_headers))
    signed_headers = ";".join(sorted(sorted_headers))
    return (
        f"{method}\n{_uri_encode(uri)}\n{query}\n"
        f"{header_lines}\n{signed_headers}\n{payload_hash}"
    )


def string_to_sign(amzdate: str, date: str, region: str, service: str,
                   creq: str) -> str:
    scope = f"{date}/{region}/{service}/aws4_request"
    return f"AWS4-HMAC-SHA256\n{amzdate}\n{scope}\n{hashlib.sha256(creq.encode()).hexdigest()}"


def sign_request(*, secret: str, method: str, uri: str, query: str,
                 headers: dict[str, str], payload_hash: str, amzdate: str,
                 date: str, region: str, service: str = "s3") -> str:
    creq = canonical_request(method, uri, query, headers, payload_hash)
    sts = string_to_sign(amzdate, date, region, service, creq)
    k_date = _hmac(f"AWS4{secret}".encode(), date)
    k_region = _hmac(k_date, region)
    k_service = _hmac(k_region, service)
    k_signing = _hmac(k_service, "aws4_request")
    return hmac.new(k_signing, sts.encode(), hashlib.sha256).hexdigest()


def authorization_header(access_key: str, signature: str, amzdate: str,
                         date: str, region: str, service: str,
                         signed_headers: list[str]) -> str:
    scope = f"{date}/{region}/{service}/aws4_request"
    return (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
        f"SignedHeaders={';'.join(sorted(signed_headers))}, Signature={signature}"
    )


def _selftest() -> int:
    ex = _AWS_EXAMPLE
    signature = sign_request(
        secret=ex["secret"], method=ex["method"], uri=ex["uri"],
        query=ex["query"], headers=ex["headers"],
        payload_hash=ex["payload_hash"], amzdate=ex["amzdate"],
        date=ex["date"], region=ex["region"], service=ex["service"],
    )
    if signature != ex["expected_signature"]:
        print(f"SELFTEST FAILED: sigv4 signature {signature} != {ex['expected_signature']}")
        return 1
    if _uri_encode("tenants/t-1/systems/s-2/evidence/a b+c~d.json") != \
            "tenants/t-1/systems/s-2/evidence/a%20b%2Bc~d.json":
        print("SELFTEST FAILED: S3 uri-encoding policy wrong")
        return 1
    print("selftest: OK (AWS SigV4 known-answer vector, S3 uri-encoding policy)")
    return 0


# ---------------------------------------------------------------------------
# S3-compatible request helper (signed or anonymous)
# ---------------------------------------------------------------------------

def s3_request(endpoint: str, bucket: str, key: str, *, method: str,
               access_key: str, secret_key: str, region: str,
               body: bytes = b"", anonymous: bool = False) -> tuple[int, bytes]:
    """Issue a path-style S3 request; returns (status, body).

    ``key=""`` addresses the bucket itself (HeadBucket).
    """
    now = _dt.datetime.now(_dt.timezone.utc)
    amzdate = now.strftime("%Y%m%dT%H%M%SZ")
    date = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()
    uri = f"/{bucket}" + (f"/{key}" if key else "")
    host = urllib.request.urlparse(endpoint).netloc
    headers = {
        "host": host,
        "x-amz-date": amzdate,
        "x-amz-content-sha256": payload_hash,
    }
    if not anonymous:
        signature = sign_request(
            secret=secret_key, method=method, uri=uri, query="",
            headers=headers, payload_hash=payload_hash, amzdate=amzdate,
            date=date, region=region,
        )
        headers["Authorization"] = authorization_header(
            access_key, signature, amzdate, date, region, "s3",
            list(headers.keys()),
        )
    if body:
        headers["Content-Length"] = str(len(body))
    req = urllib.request.Request(
        f"{endpoint.rstrip('/')}{uri}", data=body if body else None,
        method=method, headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except urllib.error.URLError as exc:
        raise SystemExit(f"R2 endpoint unreachable ({endpoint}): {exc.reason}") from exc


# ---------------------------------------------------------------------------
# Verification steps
# ---------------------------------------------------------------------------

def verify_stdlib(endpoint: str, bucket: str, access_key: str, secret_key: str,
                  region: str) -> None:
    status, body = s3_request(endpoint, bucket, "", method="HEAD",
                              access_key=access_key, secret_key=secret_key,
                              region=region)
    if status != 200:
        raise SystemExit(f"HeadBucket failed ({status}): {body[:300]!r} — check endpoint/bucket/keys")
    print(f"[ok] HeadBucket 200 — bucket exists, credentials valid ({bucket})")

    probe_key = f"_setup-probe/{uuid.uuid4().hex}.txt"
    probe_body = b"sos-pub-03 r2 setup verification probe\n"
    status, body = s3_request(endpoint, bucket, probe_key, method="PUT",
                              access_key=access_key, secret_key=secret_key,
                              region=region, body=probe_body)
    if status != 200:
        raise SystemExit(f"PutObject failed ({status}): {body[:300]!r}")
    status, body = s3_request(endpoint, bucket, probe_key, method="GET",
                              access_key=access_key, secret_key=secret_key,
                              region=region)
    if status != 200 or body != probe_body:
        raise SystemExit(f"GetObject round-trip failed ({status}): {body[:300]!r}")
    print("[ok] Put/Get round-trip verified on _setup-probe/ key")

    # Security gate S3: private-by-default — an ANONYMOUS read must be
    # rejected. A 200 here means the bucket (or the object) is public: STOP.
    status, body = s3_request(endpoint, bucket, probe_key, method="GET",
                              access_key="", secret_key="", region=region,
                              anonymous=True)
    if status in (401, 403):
        print(f"[ok] anonymous read rejected ({status}) — private posture (security gate S3)")
    else:
        raise SystemExit(
            f"SECURITY FAILURE: anonymous GetObject returned {status} — the bucket is "
            "publicly readable. Fix the bucket policy before wiring SOS_R2_BUCKET."
        )

    status, body = s3_request(endpoint, bucket, probe_key, method="DELETE",
                              access_key=access_key, secret_key=secret_key,
                              region=region)
    if status != 204:
        raise SystemExit(f"DeleteObject failed ({status}): {body[:300]!r}")
    print("[ok] probe object deleted — bucket left clean")


def verify_aws_cli(endpoint: str, bucket: str) -> None:
    """Same verification via the aws CLI (operator-preferred alternative)."""
    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["aws", *args, "--endpoint-url", endpoint],
                              capture_output=True, text=True)

    r = run("s3api", "head-bucket", "--bucket", bucket)
    if r.returncode != 0:
        raise SystemExit(f"aws s3api head-bucket failed: {r.stderr.strip()[:300]}")
    print(f"[ok] HeadBucket (aws-cli) — {bucket}")

    probe_key = f"_setup-probe/{uuid.uuid4().hex}.txt"
    r = run("s3api", "put-object", "--bucket", bucket, "--key", probe_key,
            "--body", "/dev/stdin")
    if r.returncode != 0:
        # /dev/stdin trick is environment-dependent; fall back to a temp file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as fh:
            fh.write(b"sos-pub-03 r2 setup verification probe\n")
            path = fh.name
        r = run("s3api", "put-object", "--bucket", bucket, "--key", probe_key,
                "--body", path)
        os.unlink(path)
        if r.returncode != 0:
            raise SystemExit(f"aws s3api put-object failed: {r.stderr.strip()[:300]}")
    print("[ok] put-object probe (aws-cli)")

    import tempfile
    with tempfile.NamedTemporaryFile(delete=False) as fh:
        path = fh.name
    r = run("s3api", "get-object", "--bucket", bucket, "--key", probe_key, path)
    got = open(path, "rb").read() if r.returncode == 0 else b""
    os.unlink(path)
    if r.returncode != 0 or got != b"sos-pub-03 r2 setup verification probe\n":
        raise SystemExit(f"aws s3api get-object failed: {r.stderr.strip()[:300]}")
    print("[ok] get-object round-trip (aws-cli)")

    # Anonymous probe: curl without credentials must be rejected (gate S3).
    r = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
         f"{endpoint.rstrip('/')}/{bucket}/{probe_key}"],
        capture_output=True, text=True,
    )
    if r.stdout.strip() in ("401", "403"):
        print(f"[ok] anonymous read rejected ({r.stdout.strip()}) — private posture (aws-cli mode, gate S3)")
    else:
        raise SystemExit(f"SECURITY FAILURE: anonymous read returned {r.stdout.strip()} — bucket is public")

    r = run("s3api", "delete-object", "--bucket", bucket, "--key", probe_key)
    if r.returncode != 0:
        raise SystemExit(f"aws s3api delete-object failed: {r.stderr.strip()[:300]}")
    print("[ok] probe deleted (aws-cli) — bucket left clean")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Idempotent R2 verification for the SOS public deployment (PUB-03).")
    parser.add_argument("--dry-run", action="store_true",
                        help="plan only; no network calls")
    parser.add_argument("--aws-cli", action="store_true",
                        help="verify via the aws CLI instead of the stdlib signer")
    parser.add_argument("--selftest", action="store_true",
                        help="offline sigv4 known-answer test and exit")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    endpoint = os.environ.get("SOS_R2_ENDPOINT", "").strip()
    access_key = os.environ.get("SOS_R2_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("SOS_R2_SECRET_ACCESS_KEY", "").strip()
    bucket = os.environ.get("SOS_R2_BUCKET", "").strip()
    region = os.environ.get("SOS_R2_REGION", "").strip() or R2_REGION_DEFAULT

    if args.dry_run:
        print("[dry-run] verification plan (no network calls):")
        print(f"  HeadBucket          → {endpoint or '<SOS_R2_ENDPOINT>'} / {bucket or '<SOS_R2_BUCKET>'}")
        print("  Put/Get/Delete      → _setup-probe/<uuid>.txt round-trip")
        print("  ANONYMOUS GetObject → must be rejected 401/403 (security gate S3)")
        print("  (bucket creation itself is a documented console/CLI step — see infra/r2/README.md)")
        return 0

    if not (endpoint and bucket and (args.aws_cli or (access_key and secret_key))):
        raise SystemExit(
            "need SOS_R2_ENDPOINT, SOS_R2_BUCKET and SOS_R2_ACCESS_KEY_ID/SOS_R2_SECRET_ACCESS_KEY "
            "(or --aws-cli for CLI-based verification)"
        )

    if args.aws_cli:
        verify_aws_cli(endpoint, bucket)
    else:
        verify_stdlib(endpoint, bucket, access_key, secret_key, region)

    print("\n--- Operator wiring (already correct — copy into the Render dashboard) ---")
    print(f"SOS_R2_ENDPOINT = {endpoint}")
    print(f"SOS_R2_BUCKET   = {bucket}")
    print(f"(+ SOS_R2_ACCESS_KEY_ID / SOS_R2_SECRET_ACCESS_KEY as dashboard secrets)")
    print("\nNotes:")
    print("  * Key layout is deterministic and tenant-scoped (directive §12):")
    print("    tenants/<tenantId>/systems/<systemId>/{revisions|recovery|evidence|")
    print("    experiments|executions}/<content-hash-named objects>")
    print("  * PUB-07 (Worker C) owns the artifact adapter + signed URL semantics;")
    print("    this script owns infrastructure verification only.")
    print("  * Buckets stay PRIVATE; public access only via time-bounded signed")
    print("    URLs (security gates S3/S4).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
