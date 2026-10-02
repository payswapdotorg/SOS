"""PUB-01 — truth-state preservation end-to-end (S18): the six-state
vocabulary survives DB → API with no silent conversion; provider seams
returning UNKNOWN/UNAVAILABLE surface as that status; health reports
degraded truthfully under fault injection. Hermetic."""
from __future__ import annotations

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

from services.api.config import Settings  # noqa: E402
from services.api.main import create_app  # noqa: E402
from services.api.testing import login, make_client, make_settings  # noqa: E402

ALL_SIX = {
    "SUCCESS", "EMPTY", "FAILED", "UNKNOWN", "UNSUPPORTED", "UNAVAILABLE",
}


def test_all_six_truth_states_surface_verbatim(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/api/v1/evidence")
        statuses = {e["status"] for e in response.json()["items"]}
        assert statuses == ALL_SIX, (
            "the demo dataset exercises every truth state and none is "
            "converted en route"
        )
        # filter round-trips per state
        for status in sorted(ALL_SIX):
            response = client.get(f"/api/v1/evidence?status={status}")
            items = response.json()["items"]
            assert items, status
            assert all(e["status"] == status for e in items)


def test_unavailable_evidence_is_not_success_or_empty(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/api/v1/evidence?status=UNAVAILABLE")
        items = response.json()["items"]
        assert items
        for item in items:
            assert item["status"] == "UNAVAILABLE"
            assert item["provenance"]["availability"]
            # the explanatory detail is preserved (no silent conversion)
            assert item["result"]["detail"]


def test_simulated_execution_failures_surface_verbatim(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        # FAILED and UNKNOWN executions surface as that status — never as
        # empty collections or SUCCESS.
        response = client.post(
            "/api/v1/executions",
            json={"experimentId": "exp-demo-cache", "intent": "demo:fail"},
        )
        assert response.status_code == 200
        failed = response.json()
        assert failed["status"] == "FAILED"
        assert failed["receipt"]["outcome"]["state"] == "FAILED"
        assert failed["receipt"]["outcome"]["value"] is None
        assert failed["receipt"]["outcome"]["detail"]
        response = client.post(
            "/api/v1/executions",
            json={"experimentId": "exp-demo-cache", "intent": "demo:unknown"},
        )
        assert response.status_code == 200
        unknown = response.json()
        assert unknown["status"] == "UNKNOWN"
        assert unknown["receipt"]["outcome"]["state"] == "UNKNOWN"
        # and the receipt-derived evidence records carry the same states
        response = client.get("/api/v1/evidence")
        ev = next(
            e for e in response.json()["items"]
            if e["id"].startswith("ev-exec-")
        )


def test_unregistered_provider_surfaces_unavailable_verbatim(tmp_path: Path) -> None:
    """A missing execution provider yields the W11 truthful no-run receipt:
    status UNAVAILABLE end-to-end — never an empty response, never success
    (S18 fault injection at the seam)."""
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        client.app.state.container.execution_providers = {}
        response = client.post(
            "/api/v1/executions", json={"experimentId": "exp-demo-cache"}
        )
        assert response.status_code == 200
        execution = response.json()
        assert execution["status"] == "UNAVAILABLE"
        assert execution["receipt"]["outcome"]["state"] == "UNAVAILABLE"
        assert execution["receipt"]["outcome"]["value"] is None
        assert "no provider registered" in execution["receipt"]["outcome"]["detail"]


class _BrokenSeam:
    mode = "local"
    implementation = "broken-fixture"

    def health_check(self):
        from providers.neon.seam import SeamHealth

        return SeamHealth(status="FAILED", detail="fault-injected failure")

    def execute(self, request):  # pragma: no cover - fixture
        raise RuntimeError("broken provider fixture")

    def __getattr__(self, name):
        def _fail(*args, **kwargs):
            raise RuntimeError("broken coordination fixture")

        return _fail


def test_health_reports_degraded_truthfully(tmp_path: Path) -> None:
    """Fault injection: a broken seam reports degraded + its TRUE state —
    never a fake ok."""
    settings = make_settings(tmp_path)
    app = create_app(
        settings,
        coordination=_BrokenSeam(),
        seed=True,
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "degraded"
        assert body["checks"]["coordination"]["status"] == "FAILED"
        assert "fault-injected" in body["checks"]["coordination"]["detail"]
        # the healthy adapters still report SUCCESS (per-adapter truth)
        assert body["checks"]["persistence"]["status"] == "SUCCESS"
        assert body["checks"]["artifacts"]["status"] == "SUCCESS"
        assert body["checks"]["execution"]["status"] == "SUCCESS"
        # Protected (non-health) traffic fails CLOSED while the
        # coordination plane is down — 503 PROVIDER_UNAVAILABLE, never a
        # fake ok; only /api/v1/health answers truthfully in this state.
        response = client.get("/api/v1/providers/status/coordination")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"


class _FailingPersistence:
    """A persistence seam whose queries fail (fault injection)."""

    mode = "local"
    implementation = "failing-fixture"

    def health_check(self):
        from providers.neon.seam import SeamHealth

        return SeamHealth(status="FAILED", detail="database unreachable")

    def __getattr__(self, name):  # every seam call fails
        def _fail(*args, **kwargs):
            raise RuntimeError("persistence fixture failure")

        return _fail


def test_failing_persistence_degrades_health(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    app = create_app(settings, persistence=_FailingPersistence(), seed=False)
    with TestClient(app) as client:
        body = client.get("/api/v1/health").json()
        assert body["status"] == "degraded"
        assert body["checks"]["persistence"]["status"] == "FAILED"
