"""W10 — platform-neutral adapter contracts for SOS.

Defines a common adapter boundary for web, mobile, desktop, TV, cross-platform
and future supported surfaces. Adapters are contract/policy interfaces only —
no deployment, network, or side effects (C5, C6).

Architect review iteration 4 correction (finding A5): platform constraints are
modeled as an explicit, typed, construction-validated narrowing constraint
record (``PlatformPolicyConstraint``): a platform adapter may further restrict
``allowed_actions`` / ceilings of an already-authorized policy — like
``ContextualPolicy`` narrows W9 — but never widen. Widening and invalid
constraint data are rejected deterministically (C12); all validation is pure
and side-effect-free (C6).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any, TYPE_CHECKING

from .model import ModelValidationError, Traceability, DecisionAction

if TYPE_CHECKING:
    from .autonomy import AutonomyRequest, PolicyCeiling


# ---------------------------------------------------------------------------
# Frozen vocabulary
# ---------------------------------------------------------------------------


class PlatformSurface(str, Enum):
    """Supported platform surfaces (architecture §8)."""

    WEB = "web"
    MOBILE = "mobile"
    DESKTOP = "desktop"
    TV = "tv"
    CROSS_PLATFORM = "cross-platform"
    WEARABLE = "wearable"
    API = "api"
    EDGE = "edge"
    CLOUD = "cloud"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Adapter capability
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdapterCapability:
    """A single capability exposed by a platform adapter."""

    name: str
    supported: bool

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ModelValidationError("AdapterCapability.name is required")


# ---------------------------------------------------------------------------
# Platform adapter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlatformAdapter:
    """A platform-neutral adapter contract (C5).

    Exposes stable capability/compatibility contracts, platform identity metadata,
    and traceability without embedding semantic authority in any platform
    implementation.
    """

    id: str
    version: int
    surface: PlatformSurface
    capabilities: tuple[AdapterCapability, ...]
    traceability: Traceability

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not self.id.strip():
            raise ModelValidationError("PlatformAdapter.id is required")
        if self.version < 1:
            raise ModelValidationError("PlatformAdapter.version must be >= 1")
        if not isinstance(self.surface, PlatformSurface):
            raise ModelValidationError("PlatformAdapter.surface must be a PlatformSurface")
        if not self.capabilities:
            raise ModelValidationError("PlatformAdapter.capabilities is required")
        for c in self.capabilities:
            c.__post_init__()
        self.traceability.validate(require_value=True, require_context=True)

    def has_capability(self, name: str) -> bool:
        """Check if a capability is supported."""
        for c in self.capabilities:
            if c.name == name and c.supported:
                return True
        return False


# ---------------------------------------------------------------------------
# Adapter plan (side-effect-free validation result)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdapterPlan:
    """A side-effect-free adapter validation result (C6).

    ``compatible`` indicates whether the adapter satisfies the required
    capabilities. No execution, deployment, or external side effect.
    """

    id: str
    adapter_id: str
    surface: PlatformSurface
    compatible: bool
    required_capabilities: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    traceability: Traceability

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", _plan_id(self))
        self.validate()

    def validate(self) -> None:
        if not self.adapter_id.strip():
            raise ModelValidationError("AdapterPlan.adapter_id is required")
        if not isinstance(self.surface, PlatformSurface):
            raise ModelValidationError("AdapterPlan.surface must be a PlatformSurface")
        self.traceability.validate(require_value=True, require_context=True)


def _plan_id(p: AdapterPlan) -> str:
    material = "|".join([p.adapter_id, p.surface.value, str(p.compatible), ",".join(p.required_capabilities)])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"adapter-plan-{digest}"


# ---------------------------------------------------------------------------
# Adapter validation (deterministic, side-effect-free)
# ---------------------------------------------------------------------------


def validate_adapter(
    adapter: PlatformAdapter,
    *,
    required_capabilities: tuple[str, ...] = (),
) -> AdapterPlan:
    """Validate an adapter against required capabilities (C6, C9).

    Pure function: no side effects, no network, no deployment. Capability-set
    validation only — the explicit narrowing of an already-authorized policy
    against platform constraints is modeled separately by
    ``PlatformPolicyConstraint`` / ``constrain_policy`` (A5, C7).
    Returns an ``AdapterPlan`` with ``compatible`` indicating whether all
    required capabilities are supported.
    """
    adapter.validate()
    missing: list[str] = []
    for cap in required_capabilities:
        if not adapter.has_capability(cap):
            missing.append(cap)
    compatible = len(missing) == 0
    return AdapterPlan(
        id="",
        adapter_id=adapter.id,
        surface=adapter.surface,
        compatible=compatible,
        required_capabilities=tuple(required_capabilities),
        missing_capabilities=tuple(missing),
        traceability=adapter.traceability,
    )


# ---------------------------------------------------------------------------
# Platform policy narrowing constraints (A5, C7)
# ---------------------------------------------------------------------------


_BLAST_ORDER: dict[str, int] = {"none": 0, "limited": 1, "service": 2, "system": 3, "organization": 4}


def _blast_rank(level: str) -> int:
    return _BLAST_ORDER.get(level, 0)


@dataclass(frozen=True)
class PlatformPolicyConstraint:
    """A typed platform narrowing constraint over an already-authorized W9 policy (A5, C7).

    Platform/adapter constraints may further restrict an authorized policy —
    like ``ContextualPolicy`` narrows W9 — but never widen it:

    - ``narrowed_allowed_actions`` must be a non-empty subset of the authorized
      ``source_policy.allowed_actions`` (real W1 ``DecisionAction`` members);
    - ``narrowed_ceilings`` must be stricter than or equal to the authorized
      ``source_policy.ceilings``: risk ceiling no higher, blast radius no
      wider, reversibility not relaxed, confidence floor no lower, human
      approval for ACT never waived.

    Construction-validated: widening or invalid constraint data raises
    ``ModelValidationError`` deterministically (C12). Pure data + validation
    only — no execution, network, or external side effects (C6).
    """

    id: str
    version: int
    adapter_id: str
    source_policy: "AutonomyRequest"
    narrowed_allowed_actions: tuple[Any, ...]
    narrowed_ceilings: "PolicyCeiling"
    traceability: Traceability

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not self.id.strip():
            raise ModelValidationError("PlatformPolicyConstraint.id is required")
        if self.version < 1:
            raise ModelValidationError("PlatformPolicyConstraint.version must be >= 1")
        if not self.adapter_id.strip():
            raise ModelValidationError("PlatformPolicyConstraint.adapter_id is required")
        if not self.narrowed_allowed_actions:
            raise ModelValidationError("PlatformPolicyConstraint.narrowed_allowed_actions is required")
        # C12: every narrowed action must be a real W1 DecisionAction member.
        for a in self.narrowed_allowed_actions:
            if not isinstance(a, DecisionAction):
                raise ModelValidationError(
                    f"PlatformPolicyConstraint.narrowed_allowed_actions contains a non-DecisionAction value: {a!r}"
                )
        self.source_policy.validate()
        source_set = set(self.source_policy.allowed_actions)
        for a in self.narrowed_allowed_actions:
            if a not in source_set:
                raise ModelValidationError(
                    f"PlatformPolicyConstraint cannot expand allowed_actions: {a} not in source policy"
                )
        sc = self.source_policy.ceilings
        nc = self.narrowed_ceilings
        if nc.max_risk > sc.max_risk:
            raise ModelValidationError(
                f"PlatformPolicyConstraint cannot relax max_risk: {nc.max_risk} > {sc.max_risk}"
            )
        if _blast_rank(nc.max_blast_radius) > _blast_rank(sc.max_blast_radius):
            raise ModelValidationError(
                f"PlatformPolicyConstraint cannot widen max_blast_radius: {nc.max_blast_radius} > {sc.max_blast_radius}"
            )
        if sc.require_reversible and not nc.require_reversible:
            raise ModelValidationError("PlatformPolicyConstraint cannot relax require_reversible")
        if nc.min_confidence < sc.min_confidence:
            raise ModelValidationError(
                f"PlatformPolicyConstraint cannot lower min_confidence: {nc.min_confidence} < {sc.min_confidence}"
            )
        if sc.require_human_approval_for_act and not nc.require_human_approval_for_act:
            raise ModelValidationError("PlatformPolicyConstraint cannot waive human approval")
        self.traceability.validate(require_value=True, require_context=True)


def constrain_policy(
    adapter: PlatformAdapter,
    *,
    source_policy: "AutonomyRequest",
    narrowed_allowed_actions: tuple[Any, ...],
    narrowed_ceilings: "PolicyCeiling",
    constraint_id: str,
    version: int = 1,
    traceability: Traceability | None = None,
) -> PlatformPolicyConstraint:
    """Build the platform narrowing constraint for ``adapter`` over an authorized policy (A5, C7).

    Pure, deterministic, side-effect-free (C6): validates the adapter, then
    returns the construction-validated ``PlatformPolicyConstraint``. Widening
    or invalid constraint data raises ``ModelValidationError`` (C12). The
    adapter's capabilities/metadata remain non-authoritative — only the
    narrowing constraint may restrict, never grant, authority (C7).
    """
    adapter.validate()
    return PlatformPolicyConstraint(
        id=constraint_id,
        version=version,
        adapter_id=adapter.id,
        source_policy=source_policy,
        narrowed_allowed_actions=tuple(narrowed_allowed_actions),
        narrowed_ceilings=narrowed_ceilings,
        traceability=traceability if traceability is not None else adapter.traceability,
    )
