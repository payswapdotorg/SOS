"""PUB-07 — the artifact transport routes (LOCAL app, TestClient).

Acceptance targets (contract §D PUB-07): upload/download endpoints
authenticated, tenant-scoped, rate-limited; signed-URL expiry/scope at the
HTTP boundary; size-limit rejection (slot AND redemption); audit events
for artifact operations; the OpenAPI snapshot stays byte-identical (the
routes are schema-excluded — the PUB-04 post-§7 precedent). Hermetic:
LOCAL adapters on tmp dirs, no network, no env, no credentials.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

fastapi = pytest.importorskip(
    "fastapi",
    reason=(
        "PUB-01 API tests require the 'api' dependency group "
        "(pyproject [project.optional-dependencies].api)"
    ),
)

REPO_ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(REPO_ROOT / "src"), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from fastapi.testclient import TestClient  # noqa: E402

from services.api.testing import make_client, make_settings, login  # noqa: E402
from services.api.main import create_app  # noqa: E402
from providers.r2 import layout  # noqa: E402
from providers.r2.local import LocalFsArtifactStore  # noqa: E402
from providers.r2.cloud import build_r2_artifact_store  # noqa: E402
import test_pub07_r2_adapter as r2test  # noqa: E402  (house style: sibling module)

DEMO_WS = "ws-demo"
DEMO_SYSTEM = "sys-demo-example-api"
CONTENT = b"route-level artifact bytes"
HASH = hashlib.sha256(CONTENT).hexdigest()

FROZEN_OPENAPI_SHA256 = (
    "6469732c4b6488d08cc5cbebad31fa57b59aec7dd693b909ea147a56ec6c40ba"
)


def _slot(client: TestClient, **overrides) -> dict:
    body = {
        "workspaceId": DEMO_WS,
        "systemId": DEMO_SYSTEM,
        "category": "evidence",
        "contextId": "ev-route-1",
        "sha256": HASH,
        "sizeBytes": len(CONTENT),
        "contentType": "application/octet-stream",
    }
    body.update(overrides)
    response = client.post("/api/v1/artifacts/uploads", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _upload(client: TestClient, **overrides) -> dict:
    slot = _slot(client, **overrides)
    put = client.put(
        slot["url"], content=CONTENT,
        headers={"content-type": "application/octet-stream"},
    )
    assert put.status_code == 201, put.text
    assert put.json()["sha256"] == HASH
    return slot


# -- authentication + tenant boundaries --------------------------------------


def test_slots_require_authentication(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        anon = client.post("/api/v1/artifacts/uploads", json={})
        assert anon.status_code == 401
        assert anon.json()["error"]["code"] == "UNAUTHENTICATED"
        anon_dl = client.post("/api/v1/artifacts/downloads", json={"key": "x"})
        assert anon_dl.status_code == 401
        # the byte endpoint is token-authenticated, not session-authenticated
        no_token = client.put("/api/v1/artifacts/object", content=b"x")
        assert no_token.status_code == 403


def test_upload_requires_workspace_membership(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client, "alice")
        # alice is NOT a member of the demo workspace (readable, not mutable)
        response = client.post("/api/v1/artifacts/uploads", json={
            "workspaceId": DEMO_WS, "systemId": DEMO_SYSTEM,
            "category": "evidence", "contextId": "ev-x", "sha256": HASH,
            "sizeBytes": len(CONTENT),
        })
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


def test_upload_requires_a_system_inside_the_workspace(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        response = client.post("/api/v1/artifacts/uploads", json={
            "workspaceId": DEMO_WS, "systemId": "sys-not-in-this-workspace",
            "category": "evidence", "contextId": "ev-x", "sha256": HASH,
            "sizeBytes": len(CONTENT),
        })
        assert response.status_code == 404


def test_cross_tenant_download_is_404_not_403(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        # store a real artifact owned by ANOTHER tenant (bytes present)
        store: LocalFsArtifactStore = client.app.state.container.artifacts
        foreign = store.put(
            "ws-bob", "sys-bob-1", category="evidence", context_id="ev-bob",
            subcategory="", content=b"bob private bytes",
            content_type="application/octet-stream",
        )
        login(client, "alice")
        response = client.post(
            "/api/v1/artifacts/downloads", json={"key": foreign.key},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


def test_download_reads_are_scope_allowed_for_the_demo_workspace(
    tmp_path: Path,
) -> None:
    """Downloads are READS: any authenticated user whose scope includes the
    demo workspace (everyone) may fetch demo artifacts — exactly the
    evidence read surface (uploads still require membership, S21)."""
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        slot = _upload(client)
        # alice (a non-member) can mint a download URL for the demo artifact
        login(client, "alice")
        response = client.post(
            "/api/v1/artifacts/downloads", json={"key": slot["key"]},
        )
        assert response.status_code == 200, response.text
        got = client.get(response.json()["url"])
        assert got.status_code == 200
        assert got.content == CONTENT


# -- upload-slot validation -----------------------------------------------------


def test_upload_slot_validation(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        base = {
            "workspaceId": DEMO_WS, "systemId": DEMO_SYSTEM,
            "category": "evidence", "contextId": "ev-v", "sha256": HASH,
            "sizeBytes": len(CONTENT),
        }
        # missing required fields
        for missing in ("workspaceId", "systemId", "contextId", "sha256",
                        "sizeBytes"):
            body = {k: v for k, v in base.items() if k != missing}
            response = client.post("/api/v1/artifacts/uploads", json=body)
            assert response.status_code == 422, missing
        # malformed inputs
        for overrides in (
            {"sha256": "nothex"},
            {"sizeBytes": 0},
            {"sizeBytes": "ten"},
            {"category": "nope"},
            {"category": "evidence", "subcategory": "logs"},
            {"category": "executions"},  # executions need a subcategory
            {"contentType": "not-a-media-type"},
            {"filename": "a/b.txt"},
        ):
            body = {**base, **overrides}
            response = client.post("/api/v1/artifacts/uploads", json=body)
            assert response.status_code == 422, overrides
            assert response.json()["error"]["code"] == "VALIDATION"


def test_upload_slot_rejects_oversize_with_the_artifact_cap(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path, rate_artifact_max_mb=1) as client:
        login(client, "demo-owner")
        response = client.post("/api/v1/artifacts/uploads", json={
            "workspaceId": DEMO_WS, "systemId": DEMO_SYSTEM,
            "category": "evidence", "contextId": "ev-big", "sha256": HASH,
            "sizeBytes": (1 * 1024 * 1024) + 1,
        })
        assert response.status_code == 413
        body = response.json()["error"]
        assert body["code"] == "PAYLOAD_TOO_LARGE"
        assert body["details"]["maxArtifactMb"] == 1


# -- the full round-trip ---------------------------------------------------------


def test_upload_download_round_trip_with_metadata_and_audits(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        slot = _upload(client)
        assert slot["key"] == (
            f"tenants/{DEMO_WS}/systems/{DEMO_SYSTEM}/evidence/ev-route-1/"
            f"{HASH}"
        )
        assert slot["method"] == "PUT"
        assert slot["maxBytes"] == 50 * 1024 * 1024
        assert slot["store"]["mode"] == "local"
        assert slot["store"]["demo"] is True
        assert slot["url"].startswith("/api/v1/artifacts/object?token=")

        dl = client.post(
            "/api/v1/artifacts/downloads", json={"key": slot["key"]},
        )
        assert dl.status_code == 200, dl.text
        dl_body = dl.json()
        assert dl_body["method"] == "GET"
        got = client.get(dl_body["url"])
        assert got.status_code == 200
        assert got.content == CONTENT
        assert got.headers["content-type"].startswith("application/octet-stream")
        assert got.headers["etag"] == f'"{HASH}"'
        assert got.headers["x-artifact-key"] == slot["key"]

        # every artifact operation left an audit trail (S17)
        detail = client.get(f"/api/v1/workspaces/{DEMO_WS}").json()
        actions = {e["action"] for e in detail["recentActivity"]}
        assert {
            "artifact.upload_authorized", "artifact.upload_completed",
            "artifact.download_authorized", "artifact.download_served",
        } <= actions


def test_redemption_does_not_need_a_session(tmp_path: Path) -> None:
    """The grant — not the browser session — authorizes the transfer
    (exactly like an R2 presigned URL)."""
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        slot = _upload(client)
        url = slot["url"]
    with TestClient(client.app) as stranger:  # no session cookie at all
        put = stranger.put(url, content=CONTENT)
        assert put.status_code == 201
        dl = stranger.post("/api/v1/artifacts/downloads", json={"key": slot["key"]})
        assert dl.status_code == 401  # slot minting still needs a session


def test_seed_evidence_artifact_refs_are_honestly_missing(tmp_path: Path) -> None:
    """The demo seed records receipt artifactRefs WITHOUT storing bytes
    (references only); the download surface reports the honest missing
    state instead of fabricating content."""
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        evidence = client.get(
            "/api/v1/evidence", params={"workspaceId": DEMO_WS, "limit": 100},
        ).json()["items"]
        with_ref = [e for e in evidence if e.get("artifactRef")]
        assert with_ref, "the demo seed carries artifactRef evidence"
        response = client.post(
            "/api/v1/artifacts/downloads",
            json={"key": with_ref[0]["artifactRef"]},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


# -- redemption guards ------------------------------------------------------------


def test_content_address_mismatch_is_rejected(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        slot = _slot(client)
        put = client.put(slot["url"], content=b"not the addressed bytes")
        assert put.status_code == 422
        assert put.json()["error"]["code"] == "VALIDATION"
        assert "content address mismatch" in put.json()["error"]["message"]


def test_expired_tampered_and_mode_confused_tokens(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        slot = _upload(client)

        store: LocalFsArtifactStore = client.app.state.container.artifacts
        # expired grant (ttl in the past)
        expired = store.signed_url(
            slot["key"], ttl_seconds=-1, mode="put", actor="user-x",
        )
        put = client.put(
            f"/api/v1/artifacts/object?token={expired}", content=CONTENT,
        )
        assert put.status_code == 403

        # tampered signature
        good_url = slot["url"]
        tampered = good_url[:-6] + "aaaaaa"
        put = client.put(tampered, content=CONTENT)
        assert put.status_code == 403

        # mode confusion: a GET grant cannot PUT
        dl = client.post(
            "/api/v1/artifacts/downloads", json={"key": slot["key"]},
        ).json()
        put = client.put(dl["url"], content=CONTENT)
        assert put.status_code == 403
        # and a PUT grant cannot GET
        got = client.get(slot["url"])
        assert got.status_code == 403


def test_forged_demo_key_tokens_fail_under_a_real_signing_key(
    tmp_path: Path,
) -> None:
    """With SOS_SESSION_SECRET wired (the non-LOCAL posture), tokens minted
    with the PUBLIC demo key material are refused — the production
    signing-key wiring resists the known-demo-key forgery."""
    with make_client(tmp_path, session_secret="x" * 32) as client:
        login(client, "demo-owner")
        key = layout.build_key(
            DEMO_WS, DEMO_SYSTEM, category="evidence", context_id="ev-forged",
            subcategory="", content_hash=HASH, filename="",
        )
        attacker = LocalFsArtifactStore(tmp_path / "attacker-store")
        forged = attacker.signed_url(key, ttl_seconds=600, mode="put")
        put = client.put(
            f"/api/v1/artifacts/object?token={forged}", content=CONTENT,
        )
        assert put.status_code == 403


# -- size limits at the HTTP boundary ------------------------------------------


def test_redemption_enforces_the_artifact_cap(tmp_path: Path) -> None:
    with make_client(tmp_path, rate_artifact_max_mb=1) as client:
        login(client, "demo-owner")
        big = b"x" * ((1 * 1024 * 1024) + 16)
        slot = _slot(
            client,
            contextId="ev-cap",
            sha256=hashlib.sha256(b"1").hexdigest(),
            sizeBytes=1,
        )
        put = client.put(slot["url"], content=big)
        assert put.status_code == 413
        body = put.json()["error"]
        assert body["code"] == "PAYLOAD_TOO_LARGE"
        assert body["details"]["maxArtifactMb"] == 1


def test_s16_generic_cap_exempts_only_the_artifact_path(tmp_path: Path) -> None:
    """Artifact transfers may exceed the GENERIC JSON body cap up to the
    artifact cap; every other request keeps the generic cap."""
    payload = b"x" * (1 * 1024 * 1024 + 64)  # > 1MB generic cap
    with make_client(
        tmp_path, rate_artifact_max_mb=2, rate_body_max_mb=1,
    ) as client:
        login(client, "demo-owner")
        slot = _slot(
            client,
            contextId="ev-s16",
            sha256=hashlib.sha256(payload).hexdigest(),
            sizeBytes=len(payload),
        )
        put = client.put(slot["url"], content=payload)
        assert put.status_code == 201, put.text
        # the generic cap still guards the rest of the surface
        missions = client.post(
            "/api/v1/missions",
            content=b'{"workspaceId": "' + DEMO_WS.encode() + b'", "junk": "' +
                    payload + b'"}',
            headers={"content-type": "application/json"},
        )
        assert missions.status_code == 413
        assert missions.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


# -- rate limiting (§13 bounded writes) -----------------------------------------


def test_upload_slots_consume_the_write_bucket(tmp_path: Path) -> None:
    with make_client(tmp_path, rate_write_per_min=2) as client:
        login(client, "demo-owner")
        first = client.post("/api/v1/artifacts/uploads", json={
            "workspaceId": DEMO_WS, "systemId": DEMO_SYSTEM,
            "category": "evidence", "contextId": "ev-rl-1", "sha256": HASH,
            "sizeBytes": len(CONTENT),
        })
        second = client.post("/api/v1/artifacts/uploads", json={
            "workspaceId": DEMO_WS, "systemId": DEMO_SYSTEM,
            "category": "evidence", "contextId": "ev-rl-2", "sha256": HASH,
            "sizeBytes": len(CONTENT),
        })
        third = client.post("/api/v1/artifacts/uploads", json={
            "workspaceId": DEMO_WS, "systemId": DEMO_SYSTEM,
            "category": "evidence", "contextId": "ev-rl-3", "sha256": HASH,
            "sizeBytes": len(CONTENT),
        })
        assert first.status_code == 200
        assert second.status_code == 200
        assert third.status_code == 429
        assert third.json()["error"]["code"] == "RATE_LIMITED"


# -- R2 mode: presigned URLs on the same routes ---------------------------------


def test_r2_mode_serves_presigned_urls_and_refuses_local_tokens(
    tmp_path: Path,
) -> None:
    transport = r2test.ScriptedR2()
    r2_store = build_r2_artifact_store(
        "https://acct-example.r2.cloudflarestorage.com",
        "AKIDEXAMPLE0123456789",
        "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "sos-public-artifacts",
        transport=transport,
    )
    app = create_app(make_settings(tmp_path), artifacts=r2_store)
    with TestClient(app) as client:
        login(client, "demo-owner")
        slot = _slot(client, contextId="ev-r2-mode")
        assert slot["store"] == {
            "mode": "r2", "implementation": "r2-s3-sigv4", "demo": False,
        }
        assert slot["url"].startswith(
            "https://acct-example.r2.cloudflarestorage.com/sos-public-artifacts/"
        )
        assert "X-Amz-Signature=" in slot["url"]
        # the R2 secret never reaches the client surface
        assert "wJalrXUtnFEMI" not in slot["url"]
        # LOCAL tokens are not redeemable in R2 mode (the transfer goes to
        # R2 directly; the API's object endpoint refuses foreign grants)
        put = client.put(
            f"/api/v1/artifacts/object?token={slot['url']}", content=CONTENT,
        )
        assert put.status_code == 403


# -- the frozen OpenAPI snapshot stays byte-identical ---------------------------


def test_openapi_snapshot_unchanged_by_pub07(tmp_path: Path) -> None:
    import json

    with make_client(tmp_path) as client:
        spec = client.get("/api/v1/openapi.json").json()
    assert not [p for p in spec["paths"] if "artifact" in p]
    canon = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    assert digest == FROZEN_OPENAPI_SHA256
