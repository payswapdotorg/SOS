"""W11 — provider-neutral execution substrate for SOS (first bounded slice).

Promotes the PREP-W11 contract into production code: the semantic boundary

```
ExecutionRequest -> ExecutionProvider (port) -> ExecutionReceipt -> Evidence
```

where SOS remains the authority and providers only execute already-authorized
bounded requests (frozen W11 Work Order `spec/work-orders/W11-execution-
substrate.md`; reference design `docs/implementation/PREP-W11-EXECUTION-
SUBSTRATE-DESIGN.md`).

Design invariants (frozen by the Work Order, enforced by the promoted tests in
``tests/test_w11_execution.py``):

- W9 authorization is **mechanically required**: an ``ExecutionRequest`` is
  unconstructible without a non-empty ``w9_decision_id``; submit resolves the
  reference against caller-supplied registries (SOS-owned state, never
  provider-supplied); ASK cannot authorize; the request must run under the
  EXACT W9 decision references; the request's graph/revision/provenance chain
  must match the W7/W8 chain the decision was made on (C1, C2);
- no provider can authorize itself: a decision issued under a provider-owned
  policy is rejected before any provider call (C1);
- capability is **not** authorization: a fully-authorized request without
  provider capability yields a truthful no-run ``OUTCOME_UNSUPPORTED`` receipt,
  never a rejection of the request's validity (C3);
- receipt provenance is exact: revision / environment / workspace / provider /
  timestamps are echoed verbatim; receipt ids are content-addressed and
  deterministic (no uuid, no wall clock) (C4);
- outcomes stay distinct: FAILED / UNKNOWN / UNAVAILABLE / UNSUPPORTED are
  pairwise distinct; EMPTY is not a lawful execution outcome; no-run receipts
  cannot claim side effects; terminal lifecycle and outcome must agree (C5);
- rollback is governed: DEPLOY requests require a bounded ``RollbackReference``
  bound to the W8 experiment rollback chain; OBSERVE needs none; rollback
  execution itself is W9-authorized like any other request (C6);
- the substrate is single-threaded, clock-free, and deterministic: deadlines
  and timestamps are caller- or provider-supplied data; identical inputs
  produce identical results with zero network dependence (C8);
- requests/receipts round-trip through the W1 ``JsonModelStore``; receipts
  convert verbatim (observed, not inferred) into W4 evidence via
  ``receipt_to_w4_evidence``; UNAVAILABLE may never render as success
  downstream (C9, exclusions);
- this module contains only the port protocol, the capability enum, the
  contract types, and the core dispatcher: concrete provider adapters live
  outside ``src/sos/`` or are injected as port objects (C7, C10, port
  boundary). No provider names, SDKs, transports, or credentials appear here.

Authority reuse (referenced, never duplicated): W1 truth/traceability/
validation/persistence, W7 ``AssuranceResult`` (non-authorizing), W8
``Experiment`` rollback chain, W9 ``AutonomyDecision`` state, W4 evidence
assembly. The error type ``ExecutionContractError`` subclasses the W1
``ModelValidationError`` family (no competing error authority).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable, TYPE_CHECKING

from .model import ModelValidationError, Traceability, TruthState, TruthfulValue
from .assurance import AssuranceStatus
from .autonomy import AutonomyDecisionState
from .evidence import Evidence, EvidenceKind, EvidenceProvenance, _build_evidence

if TYPE_CHECKING:
    from .assurance import AssuranceResult
    from .autonomy import AutonomyDecision
    from .experimentation import Experiment


# ---------------------------------------------------------------------------
# Error authority (anchored in the W1 validation-error family)
# ---------------------------------------------------------------------------


class ExecutionContractError(ModelValidationError):
    """Raised when the execution contract is violated at a boundary.

    Subclasses the W1 ``ModelValidationError`` family per the frozen W11 Work
    Order (required outcome 2): no competing error authority is introduced.
    """


# ---------------------------------------------------------------------------
# Frozen contract vocabulary
# ---------------------------------------------------------------------------


class ExecutionActionScope(str, Enum):
    """One bounded execution verb per request."""

    DEPLOY = "deploy"
    ROLLBACK = "rollback"
    OBSERVE = "observe"


class ProviderCapability(str, Enum):
    """Mechanical provider facts — NEVER authorization."""

    EXECUTE_DEPLOY = "execute-deploy"
    EXECUTE_ROLLBACK = "execute-rollback"
    EXECUTE_OBSERVE = "execute-observe"
    ISOLATED_WORKSPACE = "isolated-workspace"
    REVISION_PINNING = "revision-pinning"
    LOG_CAPTURE = "log-capture"
    SIDE_EFFECT_REPORT = "side-effect-report"
    ENVIRONMENT_ISOLATION = "environment-isolation"


class ExecutionLifecycleState(str, Enum):
    """Governed execution lifecycle (W9/W8 transition-contract style)."""

    REQUESTED = "requested"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    OUTCOME_UNKNOWN = "outcome-unknown"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    ROLLING_BACK = "rolling-back"
    ROLLED_BACK = "rolled-back"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Frozen lifecycle transition table (governed state machine)
# ---------------------------------------------------------------------------

_VALID_LIFECYCLE_TRANSITIONS: dict[ExecutionLifecycleState, frozenset[ExecutionLifecycleState]] = {
    ExecutionLifecycleState.REQUESTED: frozenset({
        ExecutionLifecycleState.DISPATCHED, ExecutionLifecycleState.REJECTED,
    }),
    ExecutionLifecycleState.DISPATCHED: frozenset({
        ExecutionLifecycleState.RUNNING, ExecutionLifecycleState.SUCCEEDED,
        ExecutionLifecycleState.FAILED, ExecutionLifecycleState.OUTCOME_UNKNOWN,
        ExecutionLifecycleState.UNAVAILABLE, ExecutionLifecycleState.UNSUPPORTED,
    }),
    ExecutionLifecycleState.RUNNING: frozenset({
        ExecutionLifecycleState.SUCCEEDED, ExecutionLifecycleState.FAILED,
        ExecutionLifecycleState.OUTCOME_UNKNOWN, ExecutionLifecycleState.ROLLING_BACK,
    }),
    ExecutionLifecycleState.SUCCEEDED: frozenset({ExecutionLifecycleState.ROLLING_BACK}),
    ExecutionLifecycleState.FAILED: frozenset({ExecutionLifecycleState.ROLLING_BACK}),
    ExecutionLifecycleState.OUTCOME_UNKNOWN: frozenset({
        ExecutionLifecycleState.ROLLING_BACK, ExecutionLifecycleState.OUTCOME_UNKNOWN,
    }),
    ExecutionLifecycleState.ROLLING_BACK: frozenset({
        ExecutionLifecycleState.ROLLED_BACK, ExecutionLifecycleState.OUTCOME_UNKNOWN,
    }),
    ExecutionLifecycleState.UNAVAILABLE: frozenset(),
    ExecutionLifecycleState.UNSUPPORTED: frozenset(),
    ExecutionLifecycleState.ROLLED_BACK: frozenset(),
    ExecutionLifecycleState.REJECTED: frozenset(),
}


def validate_lifecycle_transition(
    from_state: ExecutionLifecycleState,
    to_state: ExecutionLifecycleState,
) -> None:
    """Validate a lifecycle transition against the governed machine."""
    if not isinstance(from_state, ExecutionLifecycleState):
        raise ExecutionContractError(f"from_state must be an ExecutionLifecycleState, got {from_state!r}")
    if not isinstance(to_state, ExecutionLifecycleState):
        raise ExecutionContractError(f"to_state must be an ExecutionLifecycleState, got {to_state!r}")
    if to_state not in _VALID_LIFECYCLE_TRANSITIONS.get(from_state, frozenset()):
        raise ExecutionContractError(
            f"invalid execution lifecycle transition: {from_state.value} -> {to_state.value}"
        )


# Scope -> required mechanical capability (checked separately from authorization).
_SCOPE_REQUIRED_CAPABILITY: dict[ExecutionActionScope, ProviderCapability] = {
    ExecutionActionScope.DEPLOY: ProviderCapability.EXECUTE_DEPLOY,
    ExecutionActionScope.ROLLBACK: ProviderCapability.EXECUTE_ROLLBACK,
    ExecutionActionScope.OBSERVE: ProviderCapability.EXECUTE_OBSERVE,
}

# Scope -> W9 decision states that may authorize it (frozen by the Work Order:
# OBSERVE accepts GATHER_EVIDENCE or ACT; DEPLOY requires ACT; ROLLBACK requires
# ROLLBACK; ASK and REJECT authorize nothing).
_SCOPE_AUTHORIZING_STATES: dict[ExecutionActionScope, frozenset[AutonomyDecisionState]] = {
    ExecutionActionScope.DEPLOY: frozenset({AutonomyDecisionState.ACT}),
    ExecutionActionScope.ROLLBACK: frozenset({AutonomyDecisionState.ROLLBACK}),
    ExecutionActionScope.OBSERVE: frozenset({
        AutonomyDecisionState.GATHER_EVIDENCE, AutonomyDecisionState.ACT,
    }),
}

# Lifecycles in which execution may have run (side effects / changed revisions
# / rollback references are lawful); no-run terminals enforce the opposite.
_RAN_TERMINAL = frozenset({
    ExecutionLifecycleState.SUCCEEDED, ExecutionLifecycleState.FAILED,
    ExecutionLifecycleState.ROLLED_BACK,
})
_RAN_STATES = _RAN_TERMINAL | frozenset({
    ExecutionLifecycleState.RUNNING, ExecutionLifecycleState.OUTCOME_UNKNOWN,
    ExecutionLifecycleState.ROLLING_BACK,
})
_NO_RUN_STATES = frozenset({
    ExecutionLifecycleState.UNAVAILABLE, ExecutionLifecycleState.UNSUPPORTED,
})


# ---------------------------------------------------------------------------
# Side effects
# ---------------------------------------------------------------------------


class SideEffectKind(str, Enum):
    """Typed side-effect classifications."""

    FILE_CHANGE = "file-change"
    SERVICE_STATE = "service-state"
    NETWORK_CALL = "network-call"
    EXTERNAL_STATE = "external-state"


@dataclass(frozen=True)
class SideEffect:
    """One typed, observed side effect of an execution."""

    kind: SideEffectKind
    target: str
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SideEffectKind):
            raise ExecutionContractError("SideEffect.kind must be a SideEffectKind")
        if not self.target.strip():
            raise ExecutionContractError("SideEffect.target is required")
        if not self.detail.strip():
            raise ExecutionContractError("SideEffect.detail is required")


# ---------------------------------------------------------------------------
# Governed rollback reference
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RollbackReference:
    """A governed rollback/recovery reference bound to the W8 rollback path.

    Rollback exists ONLY as this reference — never free-form narrative. The
    ``reference`` must equal the W8 experiment's ``rollback_ref`` (validated at
    submit, mirroring SOS-W9-F12), and ``evidence_ids`` must reference W4
    recovery evidence.
    """

    reference: str
    evidence_ids: tuple[str, ...]
    detail: str

    def __post_init__(self) -> None:
        if not self.reference.strip():
            raise ExecutionContractError("RollbackReference.reference is required")
        if not self.evidence_ids:
            raise ExecutionContractError("RollbackReference.evidence_ids is required (recovery evidence)")
        if not self.detail.strip():
            raise ExecutionContractError("RollbackReference.detail is required")


# ---------------------------------------------------------------------------
# Execution request
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionRequest:
    """A provider-neutral execution request (W9-authorized, exactly pinned).

    The W9 authorization reference is REQUIRED: a request without one cannot
    even be constructed (Work Order required outcome 3). Provenance is exact —
    no "latest" resolution.
    """

    intent: str
    action_scope: ExecutionActionScope
    provider_id: str
    source_revision: str
    provenance_revision: str
    base_graph_id: str
    base_graph_revision: str
    environment: str
    w9_decision_id: str
    traceability: Traceability
    w7_assurance_id: str = ""
    w8_experiment_id: str | None = None
    w8_promotion_ref: str | None = None
    workspace_ref: str | None = None
    rollback_reference: RollbackReference | None = None
    id: str = ""

    def __post_init__(self) -> None:
        self.validate()
        if not self.id:
            object.__setattr__(self, "id", _request_id(self))

    def validate(self) -> None:
        if not isinstance(self.action_scope, ExecutionActionScope):
            raise ExecutionContractError("ExecutionRequest.action_scope must be an ExecutionActionScope")
        if not self.intent.strip():
            raise ExecutionContractError("ExecutionRequest.intent is required")
        if not self.provider_id.strip():
            raise ExecutionContractError("ExecutionRequest.provider_id is required")
        for name, value in (
            ("source_revision", self.source_revision),
            ("provenance_revision", self.provenance_revision),
            ("base_graph_id", self.base_graph_id),
            ("base_graph_revision", self.base_graph_revision),
            ("environment", self.environment),
        ):
            if not value.strip():
                raise ExecutionContractError(f"ExecutionRequest.{name} is required (exact provenance)")
        # Required outcome 3: no request exists without a W9 authorization
        # reference — the type is unconstructible without it.
        if not self.w9_decision_id.strip():
            raise ExecutionContractError(
                "ExecutionRequest.w9_decision_id is required: an execution request cannot bypass W9 authority"
            )
        if self.workspace_ref is not None and not self.workspace_ref.strip():
            raise ExecutionContractError("ExecutionRequest.workspace_ref must be non-empty when supplied")
        if self.action_scope == ExecutionActionScope.DEPLOY:
            if not self.w7_assurance_id.strip():
                raise ExecutionContractError("DEPLOY scope requires a W7 assurance reference")
            if not (self.w8_experiment_id or "").strip():
                raise ExecutionContractError("DEPLOY scope requires a W8 experiment reference")
        if self.action_scope == ExecutionActionScope.ROLLBACK:
            if not (self.w8_experiment_id or "").strip():
                raise ExecutionContractError("ROLLBACK scope requires a W8 experiment reference")
        if self.action_scope in (ExecutionActionScope.DEPLOY, ExecutionActionScope.ROLLBACK):
            # Invariant §13.10: bounded rollback path for every automated change.
            if self.rollback_reference is None:
                raise ExecutionContractError(
                    f"{self.action_scope.value} scope requires a governed rollback reference"
                )
        if self.action_scope == ExecutionActionScope.OBSERVE and self.rollback_reference is not None:
            raise ExecutionContractError("OBSERVE scope must not carry a rollback reference")
        self.traceability.validate(require_value=True, require_context=True)


def _request_id(r: ExecutionRequest) -> str:
    """Content-addressed identity (no uuid, no wall clock)."""
    material = "|".join([
        r.intent, r.action_scope.value, r.provider_id,
        r.source_revision, r.provenance_revision, r.base_graph_id,
        r.base_graph_revision, r.environment, r.workspace_ref or "",
        r.w9_decision_id, r.w7_assurance_id, r.w8_experiment_id or "",
        r.w8_promotion_ref or "",
        _rollback_material(r.rollback_reference),
    ])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"exec-request-{digest}"


def _rollback_material(rb: RollbackReference | None) -> str:
    if rb is None:
        return ""
    return f"{rb.reference};{','.join(rb.evidence_ids)};{rb.detail}"


# ---------------------------------------------------------------------------
# Execution receipt
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionReceipt:
    """The truthful outcome of one execution with exact provenance.

    Outcomes reuse the W1 truth vocabulary (no competing truth authority):
    FAILED / UNKNOWN / UNAVAILABLE / UNSUPPORTED stay distinct, EMPTY is not a
    lawful execution outcome, and non-SUCCESS outcomes require an explanatory
    detail. No-run terminals (UNAVAILABLE / UNSUPPORTED) cannot claim
    timestamps, side effects, changed revisions, stream refs, or rollback
    references — "unavailable rendered as successful data" is unconstructible.
    """

    request_id: str
    provider_id: str
    action_scope: ExecutionActionScope
    lifecycle: ExecutionLifecycleState
    outcome: TruthfulValue[Any]
    w9_decision_id: str
    source_revision: str
    provenance_revision: str
    base_graph_id: str
    base_graph_revision: str
    environment: str
    started_at: str | None
    finished_at: str | None
    side_effects: tuple[SideEffect, ...] = ()
    stdout_ref: str | None = None
    stderr_ref: str | None = None
    log_ref: str | None = None
    changed_revisions: tuple[str, ...] = ()
    rollback_reference: RollbackReference | None = None
    w7_assurance_id: str | None = None
    id: str = ""

    def __post_init__(self) -> None:
        self.validate()
        if not self.id:
            object.__setattr__(self, "id", _receipt_id(self))

    def validate(self) -> None:
        if not self.request_id.strip():
            raise ExecutionContractError("ExecutionReceipt.request_id is required")
        if not self.provider_id.strip():
            raise ExecutionContractError("ExecutionReceipt.provider_id is required")
        if not isinstance(self.action_scope, ExecutionActionScope):
            raise ExecutionContractError("ExecutionReceipt.action_scope must be an ExecutionActionScope")
        if not isinstance(self.lifecycle, ExecutionLifecycleState):
            raise ExecutionContractError("ExecutionReceipt.lifecycle must be an ExecutionLifecycleState")
        if not isinstance(self.outcome, TruthfulValue):
            raise ExecutionContractError("ExecutionReceipt.outcome must be a TruthfulValue (W1 truth authority)")
        self.outcome.validate()
        if self.outcome.state == TruthState.EMPTY:
            raise ExecutionContractError("EMPTY is not a lawful execution outcome (observation-capture state)")
        if not self.w9_decision_id.strip():
            raise ExecutionContractError("ExecutionReceipt.w9_decision_id echo is required")
        if self.w7_assurance_id is not None and not self.w7_assurance_id.strip():
            raise ExecutionContractError("ExecutionReceipt.w7_assurance_id must be non-empty when supplied")
        for name, value in (
            ("source_revision", self.source_revision),
            ("provenance_revision", self.provenance_revision),
            ("base_graph_id", self.base_graph_id),
            ("base_graph_revision", self.base_graph_revision),
            ("environment", self.environment),
        ):
            if not value.strip():
                raise ExecutionContractError(f"ExecutionReceipt.{name} is required (exact provenance)")
        for name, value in (
            ("stdout_ref", self.stdout_ref), ("stderr_ref", self.stderr_ref), ("log_ref", self.log_ref),
        ):
            if value is not None and not value.strip():
                raise ExecutionContractError(f"ExecutionReceipt.{name} must be non-empty when supplied")
        # Terminal lifecycle <-> outcome alignment: the machine state and the
        # truth state agree; distinct outcomes stay distinct.
        _TERMINAL_OUTCOME: dict[ExecutionLifecycleState, TruthState] = {
            ExecutionLifecycleState.SUCCEEDED: TruthState.SUCCESS,
            ExecutionLifecycleState.FAILED: TruthState.FAILED,
            ExecutionLifecycleState.OUTCOME_UNKNOWN: TruthState.UNKNOWN,
            ExecutionLifecycleState.UNAVAILABLE: TruthState.UNAVAILABLE,
            ExecutionLifecycleState.UNSUPPORTED: TruthState.UNSUPPORTED,
            ExecutionLifecycleState.ROLLED_BACK: TruthState.SUCCESS,
        }
        expected = _TERMINAL_OUTCOME.get(self.lifecycle)
        if expected is not None and self.outcome.state != expected:
            raise ExecutionContractError(
                f"terminal lifecycle {self.lifecycle.value} requires outcome {expected.value}, "
                f"got {self.outcome.state.value}"
            )
        if self.lifecycle in _NO_RUN_STATES:
            if self.started_at is not None or self.finished_at is not None:
                raise ExecutionContractError(
                    f"{self.lifecycle.value} is a no-run terminal: timestamps are forbidden (nothing executed)"
                )
            if self.side_effects:
                raise ExecutionContractError(
                    f"{self.lifecycle.value} is a no-run terminal: side effects are forbidden (nothing executed)"
                )
            if self.changed_revisions:
                raise ExecutionContractError(
                    f"{self.lifecycle.value} is a no-run terminal: changed revisions are forbidden (nothing executed)"
                )
            if self.rollback_reference is not None:
                raise ExecutionContractError(
                    f"{self.lifecycle.value} is a no-run terminal: rollback references are forbidden (nothing executed)"
                )
            if any(ref is not None for ref in (self.stdout_ref, self.stderr_ref, self.log_ref)):
                raise ExecutionContractError(
                    f"{self.lifecycle.value} is a no-run terminal: stream references are forbidden (nothing executed)"
                )
        else:
            if self.lifecycle in _RAN_TERMINAL and (not (self.started_at or "").strip() or not (self.finished_at or "").strip()):
                raise ExecutionContractError(
                    f"{self.lifecycle.value} requires both started_at and finished_at (exact time provenance)"
                )
            if self.lifecycle in _RAN_STATES and not (self.started_at or "").strip():
                raise ExecutionContractError(
                    f"{self.lifecycle.value} requires started_at (exact time provenance)"
                )
            if (self.side_effects or self.changed_revisions) and self.lifecycle not in _RAN_STATES:
                raise ExecutionContractError(
                    "side effects / changed revisions are only lawful once execution has run"
                )
            if self.action_scope == ExecutionActionScope.OBSERVE and self.rollback_reference is not None:
                raise ExecutionContractError("OBSERVE-scope receipts must not carry a rollback reference")
            if (
                self.action_scope in (ExecutionActionScope.DEPLOY, ExecutionActionScope.ROLLBACK)
                and self.lifecycle in _RAN_STATES
                and self.rollback_reference is None
            ):
                raise ExecutionContractError(
                    f"{self.action_scope.value}-scope receipt in {self.lifecycle.value} requires the governed rollback reference"
                )
        if self.lifecycle == ExecutionLifecycleState.ROLLED_BACK and (
            self.rollback_reference is None or not self.rollback_reference.evidence_ids
        ):
            raise ExecutionContractError(
                "ROLLED_BACK requires a governed rollback reference with recovery evidence"
            )


def _receipt_id(r: ExecutionReceipt) -> str:
    """Content-addressed identity (no uuid, no wall clock)."""
    material = "|".join([
        r.request_id, r.provider_id, r.action_scope.value, r.lifecycle.value,
        r.outcome.state.value, str(r.outcome.value), str(r.outcome.detail),
        r.w9_decision_id, r.w7_assurance_id or "",
        r.source_revision, r.provenance_revision, r.base_graph_id,
        r.base_graph_revision, r.environment,
        r.started_at or "", r.finished_at or "",
        ";".join(f"{s.kind.value}:{s.target}" for s in r.side_effects),
        r.stdout_ref or "", r.stderr_ref or "", r.log_ref or "",
        ",".join(r.changed_revisions),
        _rollback_material(r.rollback_reference),
    ])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"exec-receipt-{digest}"


# ---------------------------------------------------------------------------
# Provider port (the ONLY provider-facing surface in core)
# ---------------------------------------------------------------------------


@runtime_checkable
class ExecutionProviderPort(Protocol):
    """The provider-neutral port: capability facts + one execution behavior.

    The port deliberately exposes NO method that grants, mints, or upgrades
    authorization. Authorization exists only as W9 decisions referenced by
    requests (architecture §12: execution mechanisms are not intent authority).
    Concrete provider adapters live outside ``src/sos/`` (or are injected as
    port objects, as the test stub providers are).
    """

    provider_id: str
    capabilities: frozenset[ProviderCapability]

    def execute(self, request: ExecutionRequest) -> ExecutionReceipt: ...


class ProviderUnavailableSignal(Exception):
    """A provider signaling it could not be engaged (nothing executed)."""


# ---------------------------------------------------------------------------
# Core dispatcher (single-threaded, clock-free, deterministic)
# ---------------------------------------------------------------------------


class ExecutionSubstrate:
    """The core-side dispatcher: authority gates, then truthful outcomes.

    Authority gates (W9 resolution, scope state, provider-not-authorizer,
    request/decision reference equality, W7 PASS chain, W8 experiment chain,
    rollback binding) raise ``ExecutionContractError`` and reject the request
    BEFORE any provider call. Capability and availability outcomes produce
    truthful receipts instead — distinct failure classes, never conflated.

    All registries (providers, known decisions, assurance results, experiments)
    are caller-supplied: SOS-owned state, never provider-supplied. One
    substrate instance is single-threaded; core logic consults no clock and no
    network — deadlines and timestamps are caller/provider data.
    """

    def __init__(
        self,
        *,
        providers: dict[str, ExecutionProviderPort],
        known_decisions: dict[str, AutonomyDecision],
        known_assurance: dict[str, AssuranceResult] | None = None,
        known_experiments: dict[str, Experiment] | None = None,
    ):
        self._providers = dict(providers)
        self._known_decisions = dict(known_decisions)
        self._known_assurance = dict(known_assurance) if known_assurance is not None else None
        self._known_experiments = dict(known_experiments) if known_experiments is not None else None

    def submit(self, request: ExecutionRequest) -> ExecutionReceipt:
        request.validate()
        self._validate_authorization(request)
        provider = self._providers.get(request.provider_id)
        if provider is None:
            return self._no_run_receipt(
                request,
                lifecycle=ExecutionLifecycleState.UNAVAILABLE,
                detail=f"no provider registered under id '{request.provider_id}'",
            )
        required = _SCOPE_REQUIRED_CAPABILITY[request.action_scope]
        if required not in provider.capabilities:
            return self._no_run_receipt(
                request,
                lifecycle=ExecutionLifecycleState.UNSUPPORTED,
                detail=(
                    f"provider '{request.provider_id}' lacks capability '{required.value}' "
                    f"for scope '{request.action_scope.value}'"
                ),
            )
        try:
            receipt = provider.execute(request)
        except ProviderUnavailableSignal as exc:
            return self._no_run_receipt(
                request, lifecycle=ExecutionLifecycleState.UNAVAILABLE, detail=str(exc),
            )
        receipt.validate()
        self._verify_receipt_provenance(request, receipt)
        return receipt

    # --- authority gates ---------------------------------------------------

    def _validate_authorization(self, request: ExecutionRequest) -> None:
        # Gate 1: the W9 reference must resolve — forged ids never dispatch.
        decision = self._known_decisions.get(request.w9_decision_id)
        if decision is None:
            raise ExecutionContractError(
                f"unresolved W9 authorization reference '{request.w9_decision_id}'; request rejected"
            )
        # Gate 2: the decision state must authorize this scope (ASK and REJECT
        # authorize nothing).
        allowed = _SCOPE_AUTHORIZING_STATES[request.action_scope]
        if decision.state not in allowed:
            raise ExecutionContractError(
                f"W9 decision state {decision.state.value} does not authorize scope "
                f"{request.action_scope.value}; request rejected"
            )
        # Gate 3: a provider can never authorize its own execution (C1).
        if decision.policy_id == request.provider_id:
            raise ExecutionContractError(
                f"execution provider '{request.provider_id}' cannot authorize its own execution "
                f"(authorizing policy '{decision.policy_id}' is provider-owned); request rejected"
            )
        # Gate 4: the request must run under the EXACT decision references.
        if request.w7_assurance_id and request.w7_assurance_id != decision.assurance_id:
            raise ExecutionContractError(
                "request.w7_assurance_id does not match the W9 decision's assurance binding; request rejected"
            )
        if request.w8_experiment_id is not None and request.w8_experiment_id != decision.experiment_id:
            raise ExecutionContractError(
                "request.w8_experiment_id does not match the W9 decision's experiment binding; request rejected"
            )
        if request.w8_promotion_ref is not None and request.w8_promotion_ref != decision.promotion_id:
            raise ExecutionContractError(
                "request.w8_promotion_ref does not match the W9 decision's promotion binding; request rejected"
            )
        # Gates 5-7: W7 PASS + exact chain, W8 experiment chain, rollback binding.
        if request.action_scope in (ExecutionActionScope.DEPLOY, ExecutionActionScope.ROLLBACK):
            if self._known_experiments is None:
                raise ExecutionContractError(
                    "cannot verify the W8 experiment chain: no known_experiments registry supplied"
                )
            experiment = self._known_experiments.get(request.w8_experiment_id or "")
            if experiment is None:
                raise ExecutionContractError(
                    f"unresolved W8 experiment reference '{request.w8_experiment_id}'; request rejected"
                )
            if request.action_scope == ExecutionActionScope.DEPLOY:
                if self._known_assurance is None:
                    raise ExecutionContractError(
                        "cannot verify the W7 assurance chain: no known_assurance registry supplied"
                    )
                assurance = self._known_assurance.get(request.w7_assurance_id)
                if assurance is None:
                    raise ExecutionContractError(
                        f"unresolved W7 assurance reference '{request.w7_assurance_id}'; request rejected"
                    )
                # W8 entry-gate principle: only PASS assurance enters executable states.
                if assurance.status != AssuranceStatus.PASS:
                    raise ExecutionContractError(
                        f"W7 assurance status is {assurance.status.value}, not PASS; request rejected"
                    )
                if (
                    request.base_graph_id != assurance.base_graph_id
                    or request.base_graph_revision != assurance.base_graph_revision
                    or request.provenance_revision != assurance.provenance_revision
                ):
                    raise ExecutionContractError(
                        "request does not match the W7 assurance graph/revision/provenance chain; request rejected"
                    )
                if experiment.assurance_result_id != request.w7_assurance_id:
                    raise ExecutionContractError(
                        "W8 experiment is not bound to the exact W7 assurance; request rejected"
                    )
            if (
                request.base_graph_id != experiment.base_graph_id
                or request.base_graph_revision != experiment.base_graph_revision
                or request.provenance_revision != experiment.provenance_revision
            ):
                raise ExecutionContractError(
                    "request does not match the W8 experiment graph/revision/provenance chain; request rejected"
                )
            # SOS-W9-F12 style binding: the rollback reference names the
            # experiment's governed rollback path.
            if request.rollback_reference.reference != experiment.rollback_ref:
                raise ExecutionContractError(
                    f"rollback reference '{request.rollback_reference.reference}' does not match "
                    f"the W8 experiment's rollback_ref '{experiment.rollback_ref}'; request rejected"
                )

    def _verify_receipt_provenance(self, request: ExecutionRequest, receipt: ExecutionReceipt) -> None:
        checks = (
            ("request_id", receipt.request_id, request.id),
            ("provider_id", receipt.provider_id, request.provider_id),
            ("action_scope", receipt.action_scope, request.action_scope),
            ("w9_decision_id", receipt.w9_decision_id, request.w9_decision_id),
            ("source_revision", receipt.source_revision, request.source_revision),
            ("provenance_revision", receipt.provenance_revision, request.provenance_revision),
            ("base_graph_id", receipt.base_graph_id, request.base_graph_id),
            ("base_graph_revision", receipt.base_graph_revision, request.base_graph_revision),
            ("environment", receipt.environment, request.environment),
        )
        for name, got, expected in checks:
            if got != expected:
                raise ExecutionContractError(
                    f"receipt provenance mismatch on {name}: got {got!r}, expected {expected!r}"
                )

    def _no_run_receipt(
        self, request: ExecutionRequest, *, lifecycle: ExecutionLifecycleState, detail: str,
    ) -> ExecutionReceipt:
        return ExecutionReceipt(
            request_id=request.id,
            provider_id=request.provider_id,
            action_scope=request.action_scope,
            lifecycle=lifecycle,
            outcome=TruthfulValue(
                TruthState.UNAVAILABLE if lifecycle == ExecutionLifecycleState.UNAVAILABLE
                else TruthState.UNSUPPORTED,
                None, detail,
            ),
            w9_decision_id=request.w9_decision_id,
            w7_assurance_id=request.w7_assurance_id or None,
            source_revision=request.source_revision,
            provenance_revision=request.provenance_revision,
            base_graph_id=request.base_graph_id,
            base_graph_revision=request.base_graph_revision,
            environment=request.environment,
            started_at=None, finished_at=None,
        )


# ---------------------------------------------------------------------------
# Receipt -> W4 evidence binding (observed, not inferred)
# ---------------------------------------------------------------------------


def receipt_to_w4_evidence(receipt: ExecutionReceipt, *, traceability: Traceability) -> Evidence:
    """Convert a receipt into a W4 evidence record (observed, not inferred).

    Reuses the real W4 evidence assembly authority (``_build_evidence`` — the
    package-internal constructor of the W4 authority, referenced here so the
    content-addressed evidence identity is computed by exactly one algorithm):
    DEPLOY receipts become ``deployment`` evidence, ROLLBACK receipts become
    ``rollback`` evidence, and the receipt's truth state is preserved verbatim.
    Availability is the evidence's own capture state (SUCCESS = the receipt was
    captured), which W4 keeps distinct from the observed result state — an
    UNAVAILABLE execution can never render as success downstream.
    """
    receipt.validate()
    kind = (
        EvidenceKind.ROLLBACK
        if receipt.action_scope == ExecutionActionScope.ROLLBACK
        else EvidenceKind.DEPLOYMENT
    )
    return _build_evidence(
        kind=kind,
        source_ref=receipt.provider_id,
        subject_ref=receipt.base_graph_id,
        result=TruthfulValue(receipt.outcome.state, receipt.outcome.value, receipt.outcome.detail),
        provenance=EvidenceProvenance(
            source=receipt.provider_id,
            observed_subject=receipt.base_graph_id,
            timestamp=receipt.finished_at,
            environment=receipt.environment,
            implementation_revision=receipt.source_revision,
        ),
        traceability=traceability,
        timestamp=receipt.finished_at,
        environment=receipt.environment,
        confidence=None,
        availability=TruthState.SUCCESS,
    )
