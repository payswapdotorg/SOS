"""``/api/v1/missions`` — thin routes; journey validation through the W1
domain authority (``services.api.orchestration``)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..auth.session import SessionIdentity
from ..container import ApiContainer
from ..dependencies import (
    audit_writer,
    get_container,
    now_iso,
    require_authenticated,
    tenant_scope,
)
from ..errors import not_found
from ..orchestration import validate_mission_journey
from ..schemas.common import CollectionEnvelope
from ..schemas.mission import (
    CreateMissionRequestDTO,
    MissionDTO,
    MissionRevisionDTO,
    ProposeMissionRevisionRequestDTO,
)
from providers.neon.seam import TenantScope  # noqa: E402

router = APIRouter(tags=["missions"])


@router.get("/missions", response_model=CollectionEnvelope[MissionDTO])
def list_missions(
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> dict:
    page = container.persistence.list_missions(
        scope, workspace_id=workspace_id, cursor=cursor, limit=limit
    )
    items = []
    for row in page.items:
        items.append(_with_current_revision(container, scope, row))
    return {"items": items, "nextCursor": page.next_cursor}


@router.post("/missions", response_model=MissionDTO)
def create_mission(
    body: CreateMissionRequestDTO,
    session: SessionIdentity = Depends(require_authenticated),
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    audit=Depends(audit_writer),
) -> dict:
    from ..dependencies.rate_limit import check_write_quota

    if not scope.allows(body.workspace_id):
        raise not_found("workspace not found")
    check_write_quota(container, session)
    validate_mission_journey(
        goals=body.goals, outcomes=body.outcomes,
        stakeholders=body.stakeholders, measures=body.measures,
        constraints=body.constraints, preferences=body.preferences,
    )
    mission_id = "mission-" + _slugish(body.title)
    revision_id = f"{mission_id}-r1"
    row = container.persistence.insert_mission(
        workspace_id=body.workspace_id, mission_id=mission_id,
        title=body.title, status="DRAFT",
        current_revision_id=None, created_at=now_iso(),
    )
    revision = container.persistence.insert_mission_revision(
        mission_id=mission_id, revision_id=revision_id, revision=1,
        payload={
            "goals": body.goals, "outcomes": body.outcomes,
            "stakeholders": body.stakeholders, "measures": body.measures,
            "constraints": body.constraints,
            "preferences": body.preferences,
            "approval": {
                "state": "pending", "requestedBy": session.user_id,
                "decidedBy": None, "decidedAt": None,
            },
        },
        created_at=now_iso(), set_current=True,
    )
    audit(
        tenant_id=body.workspace_id, actor=session.display,
        action="mission.created", target=f"mission/{mission_id}",
        meta={"title": body.title, "revision": 1}, ts=now_iso(),
    )
    return _with_current_revision(container, scope, {**row}, revision)


@router.get("/missions/{mission_id}", response_model=MissionDTO)
def get_mission(
    mission_id: str,
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
) -> dict:
    row = container.persistence.get_mission(scope, mission_id)
    if row is None:
        raise not_found("mission not found")
    return _with_current_revision(container, scope, row)


@router.get(
    "/missions/{mission_id}/revisions",
    response_model=CollectionEnvelope[MissionRevisionDTO],
)
def list_mission_revisions(
    mission_id: str,
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> dict:
    page = container.persistence.list_mission_revisions(
        scope, mission_id, cursor=cursor, limit=limit
    )
    return {"items": list(page.items), "nextCursor": page.next_cursor}


@router.post(
    "/missions/{mission_id}/revisions", response_model=MissionRevisionDTO
)
def propose_mission_revision(
    mission_id: str,
    body: ProposeMissionRevisionRequestDTO,
    session: SessionIdentity = Depends(require_authenticated),
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    audit=Depends(audit_writer),
) -> dict:
    from ..dependencies.rate_limit import check_write_quota

    mission = container.persistence.get_mission(scope, mission_id)
    if mission is None:
        raise not_found("mission not found")
    check_write_quota(container, session)
    validate_mission_journey(
        goals=body.goals, outcomes=body.outcomes,
        stakeholders=body.stakeholders, measures=body.measures,
        constraints=body.constraints, preferences=body.preferences,
    )
    existing = container.persistence.list_mission_revisions(
        scope, mission_id, cursor=None, limit=100
    )
    next_revision = len(existing.items) + 1
    revision_id = f"{mission_id}-r{next_revision}"
    row = container.persistence.insert_mission_revision(
        mission_id=mission_id, revision_id=revision_id,
        revision=next_revision,
        payload={
            "goals": body.goals, "outcomes": body.outcomes,
            "stakeholders": body.stakeholders, "measures": body.measures,
            "constraints": body.constraints,
            "preferences": body.preferences,
            "approval": {
                "state": "pending", "requestedBy": session.user_id,
                "decidedBy": None, "decidedAt": None,
            },
        },
        created_at=now_iso(), set_current=body.set_current,
    )
    audit(
        tenant_id=str(mission["workspace_id"]), actor=session.display,
        action="mission.revision.proposed",
        target=f"mission-revision/{revision_id}",
        meta={"revision": next_revision}, ts=now_iso(),
    )
    return row


def _with_current_revision(
    container: ApiContainer, scope: TenantScope, row: dict,
    revision: dict | None = None,
) -> dict:
    if revision is None and row.get("current_revision_id"):
        revision = container.persistence.get_mission_revision(
            scope, str(row["current_revision_id"])
        )
    return {**row, "currentRevision": revision}


def _slugish(title: str) -> str:
    import re as _re

    slug = _re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return (slug or "untitled")[:48]
