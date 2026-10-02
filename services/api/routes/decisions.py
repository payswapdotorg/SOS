"""``/api/v1/decisions`` and ``/api/v1/authorizations`` — thin read routes.
ASK stays ASK end-to-end (no silent ACT conversion)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..container import ApiContainer
from ..dependencies import cursor_param, get_container, tenant_scope
from ..schemas.candidate import AuthorizationDTO, DecisionDTO
from ..schemas.common import CollectionEnvelope
from providers.neon.seam import TenantScope  # noqa: E402

router = APIRouter(tags=["decisions"])


@router.get("/decisions", response_model=CollectionEnvelope[DecisionDTO])
def list_decisions(
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Depends(cursor_param),
) -> dict:
    page = container.persistence.list_decisions(
        scope, workspace_id=workspace_id, cursor=cursor, limit=limit
    )
    items = [_decision_wire(row) for row in page.items]
    return {"items": items, "nextCursor": page.next_cursor}


@router.get(
    "/authorizations", response_model=CollectionEnvelope[AuthorizationDTO]
)
def list_authorizations(
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Depends(cursor_param),
) -> dict:
    page = container.persistence.list_authorizations(
        scope, workspace_id=workspace_id, cursor=cursor, limit=limit
    )
    return {"items": list(page.items), "nextCursor": page.next_cursor}


def _decision_wire(row: dict) -> dict:
    return {
        "id": row["id"],
        "workspaceId": row["workspace_id"],
        "action": row["action"],
        "rationale": row["rationale"],
        "evidenceRefs": row["evidence_refs"],
        "authoritySnapshot": row["authority_snapshot"],
        "expectedImpact": row["expected_impact"],
        "risk": row["risk"],
        "blastRadius": row["blast_radius"],
        "reversibility": row["reversibility"],
        "requiredApprovals": row["required_approvals"],
        "askPayload": row["ask_payload"],
        "createdAt": row["created_at"],
    }
