"""``/api/v1/experiments`` — thin routes; creation runs through the W8
domain constructor + entry assurance gate (only PASS enters READY)."""
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
from ..orchestration import assurance_row_to_result
from ..schemas.execution import (
    CreateExperimentRequestDTO,
    ExperimentDTO,
)
from ..schemas.common import CollectionEnvelope
from providers.neon.seam import TenantScope  # noqa: E402

router = APIRouter(tags=["experiments"])


@router.get("/experiments", response_model=CollectionEnvelope[ExperimentDTO])
def list_experiments(
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    candidate_id: str | None = Query(default=None, alias="candidateId"),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> dict:
    page = container.persistence.list_experiments(
        scope, workspace_id=workspace_id, candidate_id=candidate_id,
        cursor=cursor, limit=limit,
    )
    items = [_experiment_wire(row) for row in page.items]
    return {"items": items, "nextCursor": page.next_cursor}


@router.post("/experiments", response_model=ExperimentDTO)
def create_experiment(
    body: CreateExperimentRequestDTO,
    session: SessionIdentity = Depends(require_authenticated),
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    audit=Depends(audit_writer),
) -> dict:
    from ..dependencies.rate_limit import check_write_quota

    if not scope.allows(body.workspace_id):
        raise not_found("workspace not found")
    check_write_quota(container, session)
    candidate = container.persistence.get_candidate(
        scope, body.candidate_id
    )
    if candidate is None or candidate["workspace_id"] != body.workspace_id:
        raise not_found("candidate not found")
    assurance_row = container.persistence.get_assurance(
        scope, body.assurance_id
    )
    if assurance_row is None or assurance_row["workspace_id"] != body.workspace_id:
        raise not_found("assurance run not found")
    assurance = assurance_row_to_result(assurance_row)

    experiment_id = f"exp-{body.candidate_id}"
    dom = assurance_row["checks"]["domain"]
    rollback_ref = (
        f"rollback://{body.workspace_id}/{body.candidate_id}/v1"
    )
    from sos.experimentation import Experiment, ExperimentMode, ExperimentState
    from sos.experimentation import StopCondition

    experiment = Experiment(
        id=experiment_id,
        candidate_id=body.candidate_id,
        assurance_result_id=assurance.id,
        base_graph_id=dom.get("baseGraphId", ""),
        base_graph_revision=dom.get("baseGraphRevision", ""),
        provenance_revision=dom.get("provenanceRevision", ""),
        mode=ExperimentMode.CANARY,
        scope=("candidate",),
        observation_window=(now_iso(), now_iso()),
        success_criteria=(
            "objectives move in their predicted directions within the "
            "observation window",
        ),
        stop_conditions=(
            StopCondition(
                name="error-rate", threshold=0.01, metric="error-rate"
            ),
        ),
        rollback_ref=rollback_ref,
        traceability=assurance.traceability,
        state=ExperimentState.PLANNED,
    )
    row = container.persistence.insert_experiment(
        workspace_id=body.workspace_id, experiment_id=experiment_id,
        payload={
            "candidateId": body.candidate_id,
            "status": experiment.state.value,
            "events": [
                {
                    "at": now_iso(), "type": "created",
                    "detail": (
                        f"experiment created for candidate {body.candidate_id} "
                        f"bound to assurance {assurance.id} "
                        f"({assurance.status.value})"
                    ),
                },
            ],
            "domain": {
                "assuranceResultId": assurance.id,
                "baseGraphId": dom.get("baseGraphId", ""),
                "baseGraphRevision": dom.get("baseGraphRevision", ""),
                "provenanceRevision": dom.get("provenanceRevision", ""),
                "mode": experiment.mode.value,
                "scope": list(experiment.scope),
                "observationWindow": list(experiment.observation_window),
                "successCriteria": list(experiment.success_criteria),
                "stopConditions": [
                    {"name": s.name, "threshold": s.threshold,
                     "metric": s.metric}
                    for s in experiment.stop_conditions
                ],
                "rollbackRef": rollback_ref,
                "containmentPolicyRef": None,
            },
            "createdAt": now_iso(),
        },
    )
    # Truthfulness note: a non-PASS assurance leaves the experiment in
    # PLANNED — only a PASS assurance can enter executable states (the W8
    # entry gate, enforced by sos.experimentation when transitions happen);
    # the created event records the binding verdict verbatim.
    audit(
        tenant_id=body.workspace_id, actor=session.display,
        action="experiment.created", target=f"experiment/{experiment_id}",
        meta={
            "candidateId": body.candidate_id,
            "assuranceId": assurance.id,
            "assuranceVerdict": assurance.status.value,
        },
        ts=now_iso(),
    )
    return _experiment_wire(row)


@router.get("/experiments/{experiment_id}", response_model=ExperimentDTO)
def get_experiment(
    experiment_id: str,
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
) -> dict:
    row = container.persistence.get_experiment(scope, experiment_id)
    if row is None:
        raise not_found("experiment not found")
    return _experiment_wire(row)


def _experiment_wire(row: dict) -> dict:
    events_doc = row["events"] if isinstance(row["events"], dict) else {}
    return {
        "id": row["id"],
        "workspaceId": row["workspace_id"],
        "candidateId": row["candidate_id"],
        "status": row["status"],
        "events": events_doc.get("events", []),
        "createdAt": row["created_at"],
    }
