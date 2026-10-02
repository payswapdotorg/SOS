"""``/api/v1/workspaces`` — thin routes (contract §C.4)."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..auth.session import SessionIdentity
from ..container import ApiContainer
from ..dependencies import (
    audit_writer,
    cursor_param,
    get_container,
    now_iso,
    require_authenticated,
    tenant_scope,
)
from ..errors import conflict, not_found, validation
from ..schemas.common import CollectionEnvelope
from ..schemas.workspace import WorkspaceDetailDTO, WorkspaceDTO
from providers.neon.local import ConflictError as SlugConflict  # noqa: E402
from providers.neon.seam import TenantScope  # noqa: E402

router = APIRouter(tags=["workspaces"])

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=3, max_length=64, pattern=_SLUG_RE.pattern)


@router.get("/workspaces", response_model=CollectionEnvelope[WorkspaceDTO])
def list_workspaces(
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Depends(cursor_param),
) -> dict:
    page = container.persistence.list_workspaces(
        scope, cursor=cursor, limit=limit
    )
    return {"items": list(page.items), "nextCursor": page.next_cursor}


@router.post("/workspaces", response_model=WorkspaceDTO)
def create_workspace(
    body: CreateWorkspaceRequest,
    session: SessionIdentity = Depends(require_authenticated),
    container: ApiContainer = Depends(get_container),
    audit=Depends(audit_writer),
) -> dict:
    from ..dependencies.rate_limit import check_write_quota

    check_write_quota(container, session)
    workspace_id = f"ws-{body.slug}"
    try:
        row = container.persistence.create_workspace(
            workspace_id=workspace_id,
            name=body.name,
            slug=body.slug,
            owner_user_id=str(session.user_id),
            is_demo=False,
            created_at=now_iso(),
        )
    except SlugConflict as exc:
        raise conflict(str(exc)) from exc
    audit(
        tenant_id=str(row["id"]), actor=session.display,
        action="workspace.created", target=f"workspace/{row['id']}",
        meta={"name": body.name, "slug": body.slug}, ts=now_iso(),
    )
    return row


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceDetailDTO)
def get_workspace(
    workspace_id: str,
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
) -> dict:
    row = container.persistence.get_workspace(scope, workspace_id)
    if row is None:
        raise not_found("workspace not found")
    activity = container.persistence.list_workspace_activity(
        scope, workspace_id, limit=50
    )
    return {**row, "recentActivity": list(activity)}
