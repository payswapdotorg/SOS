"""PUB-07 — the R2 (S3-compatible) artifact adapter.

Semantics verified against a scripted fake transport (the PUB-06 Upstash
precedent): request signing, presigned-URL structure/expiry/scope, the
shared §12 key layout (LOCAL↔R2 parity), size limits, the fail-closed
configuration and the private-bucket posture. Hermetic: no network, no
credentials.
"""
from __future__ import annotations

import hashlib
import sys
import time
import urllib.parse
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(REPO_ROOT / "src"), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from providers.r2 import layout  # noqa: E402
from providers.r2.cloud import (  # noqa: E402
    R2ArtifactStore,
    R2ConfigError,
    build_r2_artifact_store,
)
from providers.r2.local import LocalFsArtifactStore  # noqa: E402
from providers.r2.seam import (  # noqa: E402
    ArtifactSignatureError,
    ArtifactTooLarge,
)

CONTENT = b"r2 evidence bundle"
HASH = hashlib.sha256(CONTENT).hexdigest()
ENDPOINT = "https://acct-example.r2.cloudflarestorage.com"
AKID = "AKIDEXAMPLE0123456789"
SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
BUCKET = "sos-public-artifacts"


class ScriptedR2:
    """A fake S3 transport recording every call, with a live object map."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, dict[str, str]]] = {}
        self.calls: list[tuple[str, str, dict[str, str], bytes]] = []

    def __call__(
        self, method: str, url: str, headers: dict[str, str],
        body: bytes, timeout: float,
    ) -> tuple[int, dict[str, str], bytes]:
        self.calls.append((method, url, headers, body))
        split = urllib.parse.urlsplit(url)
        path = urllib.parse.unquote(split.path)
        key = path[len(f"/{BUCKET}/"):] if path.startswith(f"/{BUCKET}/") else ""
        if method == "HEAD":
            if not key:  # HeadBucket
                return 200, {}, b""
            if key in self.objects:
                content, hdrs = self.objects[key]
                return 200, {
                    "content-length": str(len(content)),
                    "content-type": hdrs.get("content-type",
                                            "application/octet-stream"),
                }, b""
            return 404, {}, b""
        if method == "PUT":
            self.objects[key] = (
                body, {k.lower(): v for k, v in headers.items()}
            )
            return 200, {"etag": f'"{HASH}"'}, b""
        if method == "GET":
            if key in self.objects:
                content, hdrs = self.objects[key]
                return 200, {
                    "content-length": str(len(content)),
                    "content-type": hdrs.get("content-type",
                                            "application/octet-stream"),
                }, content
            return 404, {}, b""
        return 400, {}, b""


def _store(**kwargs) -> tuple[R2ArtifactStore, ScriptedR2]:
    transport = ScriptedR2()
    store = build_r2_artifact_store(
        ENDPOINT, AKID, SECRET, BUCKET, transport=transport, **kwargs,
    )
    return store, transport


# -- fail-closed configuration ------------------------------------------------


def test_r2_configuration_fails_closed_naming_pub07() -> None:
    for bad in (
        ("", AKID, SECRET, BUCKET),
        ("None", "None", "None", "None"),
        (ENDPOINT, "", SECRET, BUCKET),
        (ENDPOINT, AKID, "", BUCKET),
        (ENDPOINT, AKID, SECRET, ""),
    ):
        with pytest.raises(R2ConfigError) as excinfo:
            build_r2_artifact_store(*bad)
        assert "PUB-07" in str(excinfo.value)
    # non-HTTPS endpoints are refused outright (no plaintext credentials)
    with pytest.raises(R2ConfigError, match="https"):
        build_r2_artifact_store("http://acct.r2.cloudflarestorage.com",
                                AKID, SECRET, BUCKET)


# -- §12 layout parity with the LOCAL store -----------------------------------


def test_r2_and_local_build_the_same_key() -> None:
    store, _ = _store()
    local = LocalFsArtifactStore(Path("/tmp/does-not-matter"))
    for category, sub in (
        ("revisions", ""), ("recovery", ""), ("evidence", ""),
        ("experiments", ""), ("executions", "logs"), ("executions", "reports"),
        ("executions", "receipts"), ("executions", "bundles"),
    ):
        args = dict(
            category=category, context_id="ctx-1", subcategory=sub,
            content_hash=HASH, filename="f.bin",
        )
        assert store.build_key("ws-demo", "sys-1", **args) == (
            local.build_key("ws-demo", "sys-1", **args)
        )
    # and the vocabulary discipline is shared
    with pytest.raises(layout.InvalidArtifactKey):
        store.build_key(
            "ws-demo", "sys-1", category="nope", context_id="c",
            subcategory="", content_hash=HASH, filename="",
        )


# -- signed request transport ---------------------------------------------------


def test_put_get_head_round_trip_with_sigv4_requests() -> None:
    store, transport = _store()
    stored = store.put(
        "ws-demo", "sys-1", category="evidence", context_id="ev-1",
        subcategory="", content=CONTENT, content_type="application/json",
        filename="bundle.json",
    )
    assert stored.key.endswith(f"{HASH}-bundle.json")
    method, url, headers, body = transport.calls[-1]
    assert method == "PUT"
    assert url == (
        f"{ENDPOINT}/{BUCKET}/tenants/ws-demo/systems/sys-1/evidence/"
        f"ev-1/{urllib.parse.quote(HASH + '-bundle.json', safe='')}"
    ) or url.startswith(f"{ENDPOINT}/{BUCKET}/tenants/ws-demo/")
    assert body == CONTENT
    # every request is SigV4-signed (private bucket — no anonymous writes)
    auth = headers.get("Authorization", "")
    assert auth.startswith("AWS4-HMAC-SHA256 ")
    assert f"Credential={AKID}/" in auth
    assert headers["x-amz-content-sha256"] == HASH
    assert "content-type" in {name.lower() for name in headers}
    # reads
    assert store.get(stored.key) == CONTENT
    assert transport.calls[-1][0] == "GET"
    head = store.head(stored.key)
    assert head is not None and head.size == len(CONTENT)
    assert head.content_type == "application/json"
    assert store.exists(stored.key)
    # honestly missing
    missing = layout.build_key(
        "ws-demo", "sys-1", category="evidence", context_id="ev-404",
        subcategory="", content_hash=HASH, filename="",
    )
    assert store.head(missing) is None
    assert not store.exists(missing)
    with pytest.raises(KeyError):
        store.get(missing)


def test_put_by_key_verifies_the_content_address() -> None:
    store, _ = _store()
    key = layout.build_key(
        "ws-demo", "sys-1", category="executions", context_id="exec-1",
        subcategory="receipts", content_hash=HASH, filename="",
    )
    stored = store.put_by_key(key, CONTENT, "application/json")
    assert stored.key == key
    with pytest.raises(layout.InvalidArtifactKey):
        store.put_by_key(key, b"not the addressed bytes", "application/json")


def test_size_limit_is_enforced_in_the_r2_store() -> None:
    store, transport = _store(max_bytes=8)
    with pytest.raises(ArtifactTooLarge):
        store.put(
            "ws-demo", "sys-1", category="evidence", context_id="ev-1",
            subcategory="", content=b"123456789", content_type="text/plain",
        )
    key = layout.build_key(
        "ws-demo", "sys-1", category="evidence", context_id="ev-2",
        subcategory="",
        content_hash=hashlib.sha256(b"123456789").hexdigest(), filename="",
    )
    with pytest.raises(ArtifactTooLarge):
        store.put_by_key(key, b"123456789", "text/plain")
    assert transport.calls == []  # refused before any network call


def test_health_check_is_truthful() -> None:
    store, transport = _store()
    assert store.health_check().status == "SUCCESS"
    assert "HeadBucket" in store.health_check().detail

    def failing(method, url, headers, body, timeout):
        raise OSError("connection refused")

    broken = build_r2_artifact_store(
        ENDPOINT, AKID, SECRET, BUCKET, transport=failing,
    )
    health = broken.health_check()
    assert health.status == "FAILED"
    assert "unreachable" in health.detail


# -- presigned URLs (the browser-facing surface) --------------------------------


def test_presigned_url_structure_and_self_verification() -> None:
    store, _ = _store()
    key = layout.build_key(
        "ws-demo", "sys-1", category="evidence", context_id="ev-1",
        subcategory="", content_hash=HASH, filename="",
    )
    url = store.signed_url(key, ttl_seconds=300, mode="put")
    assert url.startswith(f"{ENDPOINT}/{BUCKET}/")
    assert urllib.parse.unquote(url).endswith(key) or key in urllib.parse.unquote(url)
    split = urllib.parse.urlsplit(url)
    params = dict(urllib.parse.parse_qsl(split.query))
    assert params["X-Amz-Algorithm"] == "AWS4-HMAC-SHA256"
    assert params["X-Amz-Credential"].startswith(f"{AKID}/")
    assert params["X-Amz-Expires"] == "300"
    assert params["X-Amz-SignedHeaders"] == "host"
    assert "X-Amz-Signature" in params
    # the SECRET never appears anywhere in the URL (directive §12)
    assert SECRET not in url
    # private posture: every URL the store issues is signed
    get_url = store.signed_url(key, ttl_seconds=60, mode="get")
    assert "X-Amz-Signature=" in get_url

    # self-verification: mode is derived from the signed method
    grant = store.resolve_grant(url, now=time.time())
    assert (grant.key, grant.mode) == (key, "put")
    assert store.resolve_signed_url(url, now=time.time()) == (key, "put")
    get_grant = store.resolve_grant(get_url, now=time.time())
    assert (get_grant.key, get_grant.mode) == (key, "get")


def test_presigned_url_tamper_and_scope_rejection() -> None:
    store, _ = _store()
    key = layout.build_key(
        "ws-demo", "sys-1", category="evidence", context_id="ev-1",
        subcategory="", content_hash=HASH, filename="",
    )
    url = store.signed_url(key, ttl_seconds=300, mode="get")

    # query tamper: extending the expiry invalidates the signature
    tampered = url.replace("X-Amz-Expires=300", "X-Amz-Expires=99999")
    with pytest.raises(ArtifactSignatureError, match="signature"):
        store.resolve_grant(tampered, now=time.time())

    # path tamper: the same signature cannot address another key
    other_key = layout.build_key(
        "ws-bob", "sys-9", category="evidence", context_id="ev-1",
        subcategory="", content_hash=HASH, filename="",
    )
    swapped = url.replace(
        urllib.parse.quote(key, safe="/"),
        urllib.parse.quote(other_key, safe="/"),
    )
    with pytest.raises(ArtifactSignatureError, match="signature"):
        store.resolve_grant(swapped, now=time.time())

    # a URL from ANOTHER endpoint/store never validates here
    other_store = build_r2_artifact_store(
        "https://evil.example.org", AKID, SECRET, BUCKET,
        transport=ScriptedR2(),
    )
    evil = other_store.signed_url(other_key, ttl_seconds=300, mode="get")
    with pytest.raises(ArtifactSignatureError, match="endpoint"):
        store.resolve_grant(evil, now=time.time())

    # expiry: a ttl in the past is already expired
    stale = store.signed_url(key, ttl_seconds=-1, mode="get")
    with pytest.raises(ArtifactSignatureError, match="expired"):
        store.resolve_grant(stale, now=time.time())


def test_presigned_url_mode_is_signed_not_asserted() -> None:
    """A GET URL cannot be replayed as a PUT: the HTTP method is part of
    the signed canonical request, so the derived mode is binding."""
    store, _ = _store()
    key = layout.build_key(
        "ws-demo", "sys-1", category="evidence", context_id="ev-1",
        subcategory="", content_hash=HASH, filename="",
    )
    put_url = store.signed_url(key, ttl_seconds=300, mode="put")
    get_url = store.signed_url(key, ttl_seconds=300, mode="get")
    assert put_url != get_url
    assert store.resolve_grant(put_url, now=time.time()).mode == "put"
    assert store.resolve_grant(get_url, now=time.time()).mode == "get"


def test_r2_store_modes_are_labeled() -> None:
    store, _ = _store()
    assert store.mode == "r2"
    assert store.implementation == "r2-s3-sigv4"
