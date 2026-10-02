"""``/api/v1/candidates`` and ``/api/v1/assurance`` — thin read routes
(multi-objective rows; NO single authoritative score)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..container import ApiContainer
from ..dependencies import cursor_param, get_container, tenant_scope
from ..schemas.candidate import AssuranceRunDTO, CandidateDTO
from ..schemas.common import CollectionEnvelope
from providers.neon.seam import TenantScope  # noqa: E402

router = APIRouter(tags=["candidates"])


@router.get("/candidates", response_model=CollectionEnvelope[CandidateDTO])
def list_candidates(
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Depends(cursor_param),
) -> dict:
    page = container.persistence.list_candidates(
        scope, workspace_id=workspace_id, cursor=cursor, limit=limit
    )
    return {"items": list(page.items), "nextCursor": page.next_cursor}


@router.get("/assurance", response_model=CollectionEnvelope[AssuranceRunDTO])
def list_assurance(
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    candidate_id: str | None = Query(default=None, alias="candidateId"),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Depends(cursor_param),
) -> dict:
    page = container.persistence.list_assurance(
        scope, workspace_id=workspace_id, candidate_id=candidate_id,
        cursor=cursor, limit=limit,
    )
    items = []
    for row in page.items:
        checks = row["checks"]
        items.append({
            "id": row["id"],
            "workspaceId": row["workspace_id"],
            "candidateId": row["candidate_id"],
            "checks": checks.get("gates", []) if isinstance(checks, dict) else checks,
            "verdict": row["verdict"],
            "createdAt": row["created_at"],
        })
    return {"items": items, "nextCursor": page.next_cursor}
