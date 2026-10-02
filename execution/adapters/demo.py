"""DemoProvider — the LOCAL execution substrate adapter (PUB-01, PUB-08 parity target).

Implements the W11 provider port by importing ``sos.execution`` types
(immutable core — never edited). Contract rules honored verbatim:

- deterministic: no uuid, no wall clock — receipt ids are content-addressed
  (the W11 algorithm), and synthetic timestamps are derived deterministically
  from the request id;
- receipts are explicitly marked ``demo:true`` in the outcome value AND in
  every side-effect detail AND in the serialized receipt payload — a demo
  execution NEVER claims a real external deployment (directive §9);
- provenance is echoed exactly (request/receipt equality is verified by the
  substrate, not by this adapter);
- truthful outcomes only: the demo run genuinely "succeeds" at simulating;
  failures are simulated as failures with distinct truth states when the
  intent names them (``demo:fail``, ``demo:unknown``), never converted.
"""
from __future__ import annotations

import hashlib
import time

from sos.execution import (
    ExecutionActionScope,
    ExecutionLifecycleState,
    ExecutionReceipt,
    ExecutionRequest,
    ProviderCapability,
    RollbackReference,
    SideEffect,
    SideEffectKind,
)
from sos.model import TruthState, TruthfulValue

DEMO_PROVIDER_ID = "demo"

# The demo provider is "always available" (directive §9) and truthfully
# reports full mechanical capabilities (simulation of deploy/rollback/observe
# with log capture and side-effect reporting). Capability is NEVER
# authorization (W11 invariant; the substrate enforces the authority gates).
DEMO_CAPABILITIES = frozenset({
    ProviderCapability.EXECUTE_DEPLOY,
    ProviderCapability.EXECUTE_ROLLBACK,
    ProviderCapability.EXECUTE_OBSERVE,
    ProviderCapability.ISOLATED_WORKSPACE,
    ProviderCapability.REVISION_PINNING,
    ProviderCapability.LOG_CAPTURE,
    ProviderCapability.SIDE_EFFECT_REPORT,
    ProviderCapability.ENVIRONMENT_ISOLATION,
})

# Synthetic time base for deterministic demo timestamps (clearly fake epoch).
_DEMO_RUN_SECONDS = 42


def _demo_timestamps(request: ExecutionRequest) -> tuple[str, str]:
    """Deterministic synthetic started/finished pair derived from the request
    id (content-addressed) — no wall clock anywhere."""
    digest = hashlib.sha256(request.id.encode("utf-8")).digest()
    offset = int.from_bytes(digest[:4], "big")
    base_seconds = 1_774_000_000  # 2026-04-01T00:00:00Z
    start = base_seconds + (offset % 3_600)
    end = start + _DEMO_RUN_SECONDS + (offset % 60)
    return (
        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start)),
        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(end)),
    )


class DemoProvider:
    """The always-available demo execution provider (simulation only)."""

    provider_id = DEMO_PROVIDER_ID
    capabilities = DEMO_CAPABILITIES

    def execute(self, request: ExecutionRequest) -> ExecutionReceipt:
        started_at, finished_at = _demo_timestamps(request)
        scope = request.action_scope

        # Intent-named simulated failure modes — truthful, distinct states.
        if request.intent == "demo:fail":
            outcome = TruthfulValue(
                TruthState.FAILED,
                {"demo": True, "simulated": "failure"},
                "DemoProvider simulated a FAILED outcome at the caller's "
                "explicit request; no real deployment was attempted",
            )
            lifecycle = ExecutionLifecycleState.FAILED
        elif request.intent == "demo:unknown":
            outcome = TruthfulValue(
                TruthState.UNKNOWN,
                {"demo": True, "simulated": "unknown-outcome"},
                "DemoProvider simulated an UNKNOWN outcome at the caller's "
                "explicit request; the true result of the simulated run was "
                "not observable",
            )
            lifecycle = ExecutionLifecycleState.OUTCOME_UNKNOWN
        else:
            outcome = TruthfulValue(
                TruthState.SUCCESS,
                {
                    "demo": True,
                    "simulated": True,
                    "actionScope": scope.value,
                    "deployedRevisions": (),
                    "note": (
                        "DemoProvider simulated execution only; no real "
                        "external deployment was performed and none is claimed"
                    ),
                },
                "DemoProvider simulated a successful bounded execution "
                "(demo:true; never a real deployment)",
            )
            lifecycle = ExecutionLifecycleState.SUCCEEDED

        side_effects = (
            SideEffect(
                kind=SideEffectKind.SERVICE_STATE,
                target=f"demo-sandbox:{request.environment}",
                detail=(
                    "demo:true; simulated service-state transition inside the "
                    "in-process demo sandbox (no external system touched)"
                ),
            ),
            SideEffect(
                kind=SideEffectKind.NETWORK_CALL,
                target="demo-sandbox-internal",
                detail=(
                    "demo:true; simulated internal call inside the demo "
                    "sandbox (no external network call performed)"
                ),
            ),
        )

        # No-run states never carry side effects (W11) — only ran states do.
        if lifecycle in (ExecutionLifecycleState.FAILED,
                         ExecutionLifecycleState.OUTCOME_UNKNOWN):
            side_effects = side_effects[:1]

        changed_revisions: tuple[str, ...] = ()
        if lifecycle == ExecutionLifecycleState.SUCCEEDED and scope in (
            ExecutionActionScope.DEPLOY, ExecutionActionScope.ROLLBACK
        ):
            changed_revisions = (request.source_revision,)

        rollback_echo: RollbackReference | None = None
        if (
            scope in (ExecutionActionScope.DEPLOY, ExecutionActionScope.ROLLBACK)
            and request.rollback_reference is not None
            and lifecycle in (
                ExecutionLifecycleState.SUCCEEDED,
                ExecutionLifecycleState.FAILED,
                ExecutionLifecycleState.OUTCOME_UNKNOWN,
                ExecutionLifecycleState.ROLLING_BACK,
            )
        ):
            rollback_echo = request.rollback_reference

        return ExecutionReceipt(
            request_id=request.id,
            provider_id=DEMO_PROVIDER_ID,
            action_scope=scope,
            lifecycle=lifecycle,
            outcome=outcome,
            w9_decision_id=request.w9_decision_id,
            source_revision=request.source_revision,
            provenance_revision=request.provenance_revision,
            base_graph_id=request.base_graph_id,
            base_graph_revision=request.base_graph_revision,
            environment=request.environment,
            started_at=started_at,
            finished_at=finished_at,
            side_effects=side_effects,
            stdout_ref=None,
            stderr_ref=None,
            log_ref=(
                f"demo-logs://{request.id}/run.log"
                if lifecycle != ExecutionLifecycleState.FAILED else None
            ),
            changed_revisions=changed_revisions,
            rollback_reference=rollback_echo,
            w7_assurance_id=request.w7_assurance_id or None,
        )


def build_execution_registry(provider: DemoProvider | None = None):
    """The provider dispatch table wired at API startup (PUB-08 adds Apify)."""
    return {DEMO_PROVIDER_ID: provider or DemoProvider()}
