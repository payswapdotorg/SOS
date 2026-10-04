"""PUB-07 — the LOCAL artifact store + the deterministic §12 key layout.

Acceptance targets (contract §D PUB-07): LOCAL artifact store round-trip;
key-layout determinism; signed-URL expiry/scope; size-limit rejection.
Hermetic: no network, no env, no credentials.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(REPO_ROOT / "src"), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from providers.r2 import layout  # noqa: E402
from providers.r2.local import LocalFsArtifactStore  # noqa: E402
from providers.r2.seam import (  # noqa: E402
    ArtifactSignatureError,
    ArtifactTooLarge,
)

CONTENT = b"evidence bundle payload \x00\x01\x02"
HASH = hashlib.sha256(CONTENT).hexdigest()
OTHER = b"different bytes entirely"
OTHER_HASH = hashlib.sha256(OTHER).hexdigest()


# -- key-layout determinism (directive §12) --------------------------------


def test_key_layout_is_the_directive_shape() -> None:
    key = layout.build_key(
        "ws-demo", "sys-1", category="evidence", context_id="ev-1",
        subcategory="", content_hash=HASH, filename="",
    )
    assert key == (
        f"tenants/ws-demo/systems/sys-1/evidence/ev-1/{HASH}"
    )
    exec_key = layout.build_key(
        "ws-demo", "sys-1", category="executions", context_id="exec-9",
        subcategory="receipts", content_hash=HASH, filename="r.json",
    )
    assert exec_key == (
        f"tenants/ws-demo/systems/sys-1/executions/exec-9/receipts/"
        f"{HASH}-r.json"
    )


def test_key_layout_is_deterministic_and_content_addressed() -> None:
    first = layout.build_key(
        "ws-demo", "sys-1", category="revisions", context_id="rev-1",
        subcategory="", content_hash=HASH, filename="",
    )
    second = layout.build_key(
        "ws-demo", "sys-1", category="revisions", context_id="rev-1",
        subcategory="", content_hash=HASH, filename="",
    )
    assert first == second
    # different content → different address; different context → different key
    assert layout.build_key(
        "ws-demo", "sys-1", category="revisions", context_id="rev-1",
        subcategory="", content_hash=OTHER_HASH, filename="",
    ) != first
    assert layout.build_key(
        "ws-demo", "sys-1", category="revisions", context_id="rev-2",
        subcategory="", content_hash=HASH, filename="",
    ) != first


def test_key_layout_vocabulary_is_enforced() -> None:
    with pytest.raises(layout.InvalidArtifactKey):
        layout.build_key(
            "ws-demo", "sys-1", category="nope", context_id="ev-1",
            subcategory="", content_hash=HASH, filename="",
        )
    with pytest.raises(layout.InvalidArtifactKey):
        layout.build_key(  # subcategory only lawful for executions
            "ws-demo", "sys-1", category="evidence", context_id="ev-1",
            subcategory="logs", content_hash=HASH, filename="",
        )
    with pytest.raises(layout.InvalidArtifactKey):
        layout.build_key(  # executions REQUIRE a lawful subcategory
            "ws-demo", "sys-1", category="executions", context_id="exec-1",
            subcategory="", content_hash=HASH, filename="",
        )
    with pytest.raises(layout.InvalidArtifactKey):
        layout.build_key(  # content hash must be 64 lowercase hex
            "ws-demo", "sys-1", category="evidence", context_id="ev-1",
            subcategory="", content_hash="deadbeef", filename="",
        )


def test_key_layout_rejects_traversal_segments() -> None:
    for bad_tenant in ("..", "a/b", "a\\b", ".", "a\x00b"):
        with pytest.raises(layout.InvalidArtifactKey):
            layout.build_key(
                bad_tenant, "sys-1", category="evidence", context_id="ev-1",
                subcategory="", content_hash=HASH, filename="",
            )
    for bad_name in ("../x", "a/b"):
        with pytest.raises(layout.InvalidArtifactKey):
            layout.build_key(
                "ws-demo", "sys-1", category="evidence", context_id="ev-1",
                subcategory="", content_hash=HASH, filename=bad_name,
            )


def test_parse_key_round_trip_and_rejections() -> None:
    key = layout.build_key(
        "ws-demo", "sys-1", category="recovery", context_id="job-7",
        subcategory="", content_hash=HASH, filename="out.json",
    )
    parts = layout.parse_key(key)
    assert parts.tenant_id == "ws-demo"
    assert parts.system_id == "sys-1"
    assert parts.category == "recovery"
    assert parts.context_id == "job-7"
    assert parts.subcategory == ""
    assert parts.content_hash == HASH
    assert parts.filename == "out.json"
    assert parts.key == key  # deterministic rebuild

    exec_parts = layout.parse_key(layout.build_key(
        "t", "s", category="executions", context_id="e", subcategory="logs",
        content_hash=HASH, filename="",
    ))
    assert exec_parts.subcategory == "logs"

    # seed-style object names (short-hash + ".json") are lawful TREE keys
    # (read surface) but NOT content-addressed (write surface refuses them)
    seed_style = f"tenants/ws-demo/systems/sys-1/evidence/ev-1/{HASH[:16]}.json"
    legacy = layout.parse_key(seed_style)
    assert legacy.name == f"{HASH[:16]}.json"
    assert legacy.content_hash == ""
    with pytest.raises(layout.InvalidArtifactKey):
        layout.key_content_hash(seed_style)

    for bad in (
        "", "tenants/ws-demo", f"tenants/ws-demo/systems/sys-1/x/ev-1/{HASH}",
        f"notenants/ws-demo/systems/sys-1/evidence/ev-1/{HASH}",
        f"tenants/../systems/sys-1/evidence/ev-1/{HASH}",
        f"tenants/ws-demo/systems/sys-1/evidence/ev-1/",
        f"tenants/ws-demo/systems/sys-1/executions/ev-1/{HASH}",  # no sub
        f"tenants/ws-demo/systems/sys-1/executions/ev-1/nope/{HASH}",
    ):
        with pytest.raises(layout.InvalidArtifactKey):
            layout.parse_key(bad)


# -- LOCAL store round-trip --------------------------------------------------


def test_local_store_round_trip(tmp_path: Path) -> None:
    store = LocalFsArtifactStore(tmp_path)
    stored = store.put(
        "ws-demo", "sys-1", category="evidence", context_id="ev-1",
        subcategory="", content=CONTENT, content_type="application/json",
        filename="bundle.json",
    )
    assert stored.sha256 == HASH and stored.size == len(CONTENT)
    assert stored.key.endswith(f"{HASH}-bundle.json")
    assert store.exists(stored.key)
    assert store.get(stored.key) == CONTENT
    head = store.head(stored.key)
    assert head is not None
    assert head.size == len(CONTENT)
    assert head.content_type == "application/json"
    # idempotent re-put of identical content converges on the same key
    again = store.put(
        "ws-demo", "sys-1", category="evidence", context_id="ev-1",
        subcategory="", content=CONTENT, content_type="application/json",
        filename="bundle.json",
    )
    assert again.key == stored.key
    # a missing artifact is honestly missing
    assert store.head("tenants/ws-demo/systems/sys-1/evidence/ev-9/" + HASH) is None
    with pytest.raises(KeyError):
        store.get("tenants/ws-demo/systems/sys-1/evidence/ev-9/" + HASH)
    # traversal keys are refused, never resolved against the filesystem
    with pytest.raises(layout.InvalidArtifactKey):
        store.get(f"tenants/../escape/{HASH}")


def test_local_store_meta_sidecar(tmp_path: Path) -> None:
    store = LocalFsArtifactStore(tmp_path)
    stored = store.put(
        "ws-demo", "sys-1", category="experiments", context_id="exp-1",
        subcategory="", content=CONTENT, content_type="text/plain",
    )
    meta_path = tmp_path / stored.key
    assert (meta_path.with_name(meta_path.name + ".meta.json")).is_file()
    meta = json.loads(
        (meta_path.with_name(meta_path.name + ".meta.json")).read_text()
    )
    assert meta["contentType"] == "text/plain"
    assert meta["size"] == len(CONTENT)


def test_local_store_put_by_key_verifies_content_address(
    tmp_path: Path,
) -> None:
    store = LocalFsArtifactStore(tmp_path)
    key = layout.build_key(
        "ws-demo", "sys-1", category="evidence", context_id="ev-2",
        subcategory="", content_hash=HASH, filename="",
    )
    stored = store.put_by_key(key, CONTENT, "application/octet-stream")
    assert stored.key == key and stored.sha256 == HASH
    assert store.get(key) == CONTENT
    # bytes that do not match the key's address are refused
    with pytest.raises(layout.InvalidArtifactKey):
        store.put_by_key(key, OTHER, "application/octet-stream")
    # and the key itself must be a lawful §12 key
    with pytest.raises(layout.InvalidArtifactKey):
        store.put_by_key("tenants/../escape/" + HASH, CONTENT, "text/plain")


# -- size limits (S15) --------------------------------------------------------


def test_local_store_enforces_the_size_limit(tmp_path: Path) -> None:
    store = LocalFsArtifactStore(tmp_path, max_bytes=8)
    small = b"12345678"
    assert len(small) == 8  # exactly at the cap: allowed
    ok = store.put(
        "ws-demo", "sys-1", category="evidence", context_id="ev-1",
        subcategory="", content=small, content_type="text/plain",
    )
    assert store.get(ok.key) == small
    with pytest.raises(ArtifactTooLarge):
        store.put(
            "ws-demo", "sys-1", category="evidence", context_id="ev-1",
            subcategory="", content=b"123456789", content_type="text/plain",
        )
    key = layout.build_key(
        "ws-demo", "sys-1", category="evidence", context_id="ev-3",
        subcategory="",
        content_hash=hashlib.sha256(b"123456789").hexdigest(), filename="",
    )
    with pytest.raises(ArtifactTooLarge):
        store.put_by_key(key, b"123456789", "text/plain")


# -- signed URLs: expiry + scope ----------------------------------------------


def test_signed_url_expiry_and_scope(tmp_path: Path) -> None:
    store = LocalFsArtifactStore(tmp_path)
    key = layout.build_key(
        "ws-demo", "sys-1", category="evidence", context_id="ev-1",
        subcategory="", content_hash=HASH, filename="",
    )
    other_key = layout.build_key(
        "ws-bob", "sys-2", category="evidence", context_id="ev-1",
        subcategory="", content_hash=HASH, filename="",
    )
    token = store.signed_url(key, ttl_seconds=300, mode="put", actor="user-1")
    assert token.startswith("sos-local-artifact://")
    grant = store.resolve_grant(token, now=time.time())
    # scope: the grant names EXACTLY this key, mode and actor
    assert (grant.key, grant.mode, grant.actor) == (key, "put", "user-1")
    assert grant.expires_at >= int(time.time())
    # resolve_signed_url keeps the PUB-01 shape
    assert store.resolve_signed_url(token, now=time.time()) == (key, "put")

    # expiry: a ttl in the past is already expired
    stale = store.signed_url(key, ttl_seconds=-1, mode="get")
    with pytest.raises(ArtifactSignatureError, match="expired"):
        store.resolve_grant(stale, now=time.time())

    # tampered signature is refused
    body, _, sig = token.partition("?sig=")
    forged = f"{body}?sig={'0' * 64}"
    with pytest.raises(ArtifactSignatureError, match="signature"):
        store.resolve_grant(forged, now=time.time())

    # a token minted for ANOTHER key does not resolve to this one
    other_token = store.signed_url(other_key, ttl_seconds=300, mode="put")
    grant_other = store.resolve_grant(other_token, now=time.time())
    assert grant_other.key == other_key != key

    # unknown modes never mint; garbage never resolves
    with pytest.raises(ValueError):
        store.signed_url(key, ttl_seconds=10, mode="delete")
    with pytest.raises(ArtifactSignatureError):
        store.resolve_grant("sos-local-artifact://garbage?sig=zz", now=time.time())
    with pytest.raises(ArtifactSignatureError):
        store.resolve_grant("not-a-token", now=time.time())


def test_signed_url_key_must_be_a_lawful_key(tmp_path: Path) -> None:
    store = LocalFsArtifactStore(tmp_path)
    with pytest.raises(layout.InvalidArtifactKey):
        store.signed_url(
            f"tenants/../escape/{HASH}", ttl_seconds=10, mode="put"
        )


def test_cross_store_token_forgery_is_refused(tmp_path: Path) -> None:
    """Tokens signed with DIFFERENT key material never validate — the
    production wiring (session-secret signing outside LOCAL) is what makes
    the public demo key non-forgeable in PUBLIC deployments."""
    honest = LocalFsArtifactStore(tmp_path, signing_key=b"real-secret-key-32-bytes-aaaaaaaa")
    attacker = LocalFsArtifactStore(tmp_path / "attacker")
    key = layout.build_key(
        "ws-demo", "sys-1", category="evidence", context_id="ev-1",
        subcategory="", content_hash=HASH, filename="",
    )
    forged = attacker.signed_url(key, ttl_seconds=300, mode="put")
    with pytest.raises(ArtifactSignatureError):
        honest.resolve_grant(forged, now=time.time())
    # and the honest store's own tokens still work
    good = honest.signed_url(key, ttl_seconds=300, mode="put")
    assert honest.resolve_grant(good, now=time.time()).key == key


def test_local_store_health_is_truthful(tmp_path: Path) -> None:
    store = LocalFsArtifactStore(tmp_path)
    health = store.health_check()
    assert health.status == "SUCCESS"
    assert "local artifact store" in health.detail
