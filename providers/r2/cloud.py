"""R2 (S3-compatible) cloud adapter — FAIL-CLOSED placeholder (PUB-07 pending).

PUB-07 implements the artifact-store seam over Cloudflare R2 (private bucket,
time-bounded key-scoped signed URLs, size limits). Selecting
``SOS_ARTIFACTS=r2`` before PUB-07 lands aborts startup with a precise
message — never a silent fallback (fail-closed config).
"""
from __future__ import annotations


class R2AdapterUnavailable(Exception):
    """Raised when the PUB-07 R2 adapter is selected before it exists."""


def build_r2_artifact_store(endpoint: str, access_key_id: str,
                            secret_access_key: str,
                            bucket: str):  # pragma: no cover - PUB-07
    del endpoint, access_key_id, secret_access_key, bucket
    raise R2AdapterUnavailable(
        "SOS_ARTIFACTS=r2 selects the Cloudflare R2 adapter, which is "
        "implemented by PUB-07 (not yet merged). Refusing to boot: no silent "
        "fallback to the LOCAL filesystem store is permitted. Use "
        "SOS_ARTIFACTS=local for LOCAL mode."
    )
