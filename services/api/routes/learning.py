"""``/api/v1/learning`` and ``/api/v1/memory`` — thin read routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..container import ApiContainer
from ..dependencies import get_container, tenant_scope
from ..schemas.execution import LearningRecordDTO, MemoryEntryDTO
from ..schemas.common import CollectionEnvelope
from providers.neon.seam import TenantScope  # noqa: E402

router = APIRouter(tags=["learning"])


@router.get("/learning", response_model=CollectionEnvelope[LearningRecordDTO])
def list_learning(
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> dict:
    page = container.persistence.list_learning(
        scope, workspace_id=workspace_id, cursor=cursor, limit=limit
    )
    items = [_record_wire(row) for row in page.items]
    return {"items": items, "nextCursor": page.next_cursor}


@router.get("/memory", response_model=CollectionEnvelope[MemoryEntryDTO])
def list_memory(
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> dict:
    page = container.persistence.list_memory(
        scope, workspace_id=workspace_id, cursor=cursor, limit=limit
    )
    items = [_record_wire(row) for row in page.items]
    return {"items": items, "nextCursor": page.next_cursor}


def _record_wire(row: dict) -> dict:
    return {
        "id": row["id"],
        "workspaceId": row["workspace_id"],
        "context": row["context"],
        "candidate": row["candidate"],
        "predictedEffects": row["predicted_effects"],
        "actualEffects": row["actual_effects"],
        "uncertainty": row["uncertainty"],
        "verdict": row["verdict"],
        "lessons": row["lessons"],
        "createdAt": row["created_at"],
    }
