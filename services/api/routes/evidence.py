"""``/api/v1/evidence`` and ``/api/v1/hypotheses`` — thin read routes.

Evidence filtering by kind/status uses the EXACT wire vocabulary; truth
states pass through verbatim (no silent conversion)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..container import ApiContainer
from ..dependencies import get_container, tenant_scope
from ..errors import validation
from ..orchestration import WIRE_EVIDENCE_KINDS
from ..schemas.common import CollectionEnvelope
from ..schemas.evidence import EvidenceDTO, HypothesisDTO
from providers.neon.seam import TenantScope  # noqa: E402

router = APIRouter(tags=["evidence"])


@router.get("/evidence", response_model=CollectionEnvelope[EvidenceDTO])
def list_evidence(
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    system_id: str | None = Query(default=None, alias="systemId"),
    kind: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> dict:
    if kind is not None and kind not in WIRE_EVIDENCE_KINDS:
        raise validation(
            f"unknown evidence kind {kind!r}; expected one of "
            + ", ".join(WIRE_EVIDENCE_KINDS)
        )
    if status is not None and status not in {
        "SUCCESS", "EMPTY", "FAILED", "UNKNOWN", "UNSUPPORTED", "UNAVAILABLE",
    }:
        raise validation(f"unknown truth state {status!r}")
    page = container.persistence.list_evidence(
        scope, workspace_id=workspace_id, system_id=system_id, kind=kind,
        status=status, cursor=cursor, limit=limit,
    )
    return {"items": list(page.items), "nextCursor": page.next_cursor}


@router.get(
    "/hypotheses", response_model=CollectionEnvelope[HypothesisDTO]
)
def list_hypotheses(
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> dict:
    page = container.persistence.list_hypotheses(
        scope, workspace_id=workspace_id, cursor=cursor, limit=limit
    )
    return {"items": list(page.items), "nextCursor": page.next_cursor}
