"""GET /api/v1/health — truthful readiness per adapter (contract §C.1).

A LOCAL deployment reports the local adapters; a failing adapter reports its
TRUE state — never a fake ok. ``degraded`` is reported when any check is not
SUCCESS."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..container import ApiContainer
from ..dependencies import get_container
from ..schemas.execution import HealthResponseDTO

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponseDTO)
def health(container: ApiContainer = Depends(get_container)) -> dict:
    checks = container.health_checks()
    all_ok = all(c["status"] == "SUCCESS" for c in checks.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "checks": checks,
    }
