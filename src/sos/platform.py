"""W10 — platform-neutral adapter contracts for SOS.

Defines a common adapter boundary for web, mobile, desktop, TV, cross-platform
and future supported surfaces. Adapters are contract/policy interfaces only —
no deployment, network, or side effects (C5, C6).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .model import ModelValidationError, Traceability


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

    Pure function: no side effects, no network, no deployment.
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
