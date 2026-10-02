"""PUB-01 — DemoProvider tests: deterministic receipts, demo:true marking,
never a real-deployment claim; plus W11 substrate-contract parity through
the real authority gates. Hermetic."""
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

from sos.execution import (  # noqa: E402
    ExecutionActionScope,
    ExecutionContractError,
    ExecutionLifecycleState,
    ExecutionSubstrate,
)
from sos.model import TruthState  # noqa: E402

from execution.adapters.demo import (  # noqa: E402
    DEMO_PROVIDER_ID,
    DemoProvider,
    build_execution_registry,
)
from services.api.testing import login, make_client  # noqa: E402


def _demo_receipt(intent: str = "governed demo run"):
    provider = DemoProvider()
    request = _request(intent)
    substrate = ExecutionSubstrate(
        providers={DEMO_PROVIDER_ID: provider},
        known_decisions={},
        known_assurance={},
        known_experiments={},
    )
    # Bypass the authority registries for the raw provider test by calling
    # the provider directly (the substrate path is covered in the route
    # tests through the seeded governed chain).
    return provider.execute(request), request


def _request(intent: str):
    from sos.execution import ExecutionRequest, RollbackReference
    from sos.model import Traceability

    traceability = Traceability(
        constitution_ref="spec/constitution.md",
        mission_ref="mission:demo",
        value_model_ref="value-model:demo",
        context_ref="context:demo",
    )
    return ExecutionRequest(
        intent=intent,
        action_scope=ExecutionActionScope.DEPLOY,
        provider_id=DEMO_PROVIDER_ID,
        source_revision="a" * 40,
        provenance_revision="a" * 40,
        base_graph_id="arch-test",
        base_graph_revision="recovered-rev-test",
        environment="demo",
        w9_decision_id="autonomy-test",
        traceability=traceability,
        w7_assurance_id="assurance-test",
        w8_experiment_id="exp-test",
        rollback_reference=RollbackReference(
            reference="rollback://test",
            evidence_ids=("ev-test-recovery",),
            detail="test rollback path",
        ),
    )


def test_receipt_is_deterministic() -> None:
    first, _ = _demo_receipt()
    second, _ = _demo_receipt()
    assert first == second
    assert first.id == second.id
    assert first.started_at == second.started_at
    assert first.finished_at == second.finished_at


def test_receipt_explicitly_marked_demo_true() -> None:
    receipt, _ = _demo_receipt()
    outcome = receipt.outcome
    assert outcome.state == TruthState.SUCCESS
    value = outcome.value
    assert isinstance(value, dict)
    assert value["demo"] is True
    assert value["simulated"] is True
    for effect in receipt.side_effects:
        assert "demo:true" in effect.detail
    assert "never a real deployment" in outcome.detail.lower() or (
        "no real" in outcome.detail.lower()
    )


def test_receipt_never_claims_real_deployment() -> None:
    receipt, _ = _demo_receipt()
    blob = repr(receipt)
    assert "demo:true" in blob
    # the note explicitly denies real deployment
    assert "no real external deployment" in receipt.outcome.value["note"]


def test_simulated_failure_states_are_truthful_and_distinct() -> None:
    failed, _ = _demo_receipt("demo:fail")
    assert failed.lifecycle == ExecutionLifecycleState.FAILED
    assert failed.outcome.state == TruthState.FAILED
    assert failed.outcome.value is None  # non-SUCCESS carries no value
    assert failed.outcome.detail
    unknown, _ = _demo_receipt("demo:unknown")
    assert unknown.lifecycle == ExecutionLifecycleState.OUTCOME_UNKNOWN
    assert unknown.outcome.state == TruthState.UNKNOWN
    assert unknown.outcome.value is None
    assert failed.outcome.state != unknown.outcome.state


def test_provider_id_and_capabilities() -> None:
    provider = DemoProvider()
    assert provider.provider_id == DEMO_PROVIDER_ID == "demo"
    assert build_execution_registry()[DEMO_PROVIDER_ID] is not None
    from sos.execution import ProviderCapability

    assert ProviderCapability.EXECUTE_DEPLOY in provider.capabilities


def test_demo_receipt_through_route_is_marked(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        login(client, "demo-owner")
        response = client.post(
            "/api/v1/executions", json={"experimentId": "exp-demo-cache"}
        )
        assert response.status_code == 200
        execution = response.json()
        assert execution["provider"] == "demo"
        assert execution["receipt"]["demo"] is True
        assert execution["receipt"]["outcome"]["value"]["demo"] is True


def test_substrate_rejects_unresolved_authority() -> None:
    """The W11 authority gates reject a forged decision id BEFORE any
    provider call (provider cannot self-authorize)."""
    substrate = ExecutionSubstrate(
        providers=build_execution_registry(),
        known_decisions={},
        known_assurance={},
        known_experiments={},
    )
    request = _request("forged authority")
    with pytest.raises(ExecutionContractError):
        substrate.submit(request)
