"""``/api/v1/jobs`` — thin routes over the PUB-06 job/coordination layer.

POST /jobs: idempotent creation (duplicate keys return the SAME job, no
duplicate side effects — durable unique index + coordination fast path);
job types: system_recovery (W3 recovery at a pinned ref) and
experiment_execution (the governed W11 dispatch). Directive §8 job fields
exactly.

Execution split (directive §8 / contract §D PUB-06): LOCAL mode runs the
in-process bounded executor inline (deterministic tests); preview/public
enqueues ONLY — the separate worker process
(``python3 -m services.api.jobs.worker``) claims jobs through the
orchestration locks and applies the bounded/jittered retry policy. The
lifecycle: ``queued`` → ``running`` → ``succeeded`` | ``failed``; truthful
non-SUCCESS outcomes are terminal results, never retried into fake
success.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..auth.session import SessionIdentity
from ..container import ApiContainer
from ..dependencies import (
    audit_writer,
    cursor_param,
    get_container,
    require_authenticated,
    require_workspace_membership,
    tenant_scope,
)
from ..errors import not_found, validation
from ..jobs import JobService
from ..schemas.execution import CreateJobRequestDTO, JobDTO
from ..schemas.common import CollectionEnvelope
from providers.neon.seam import TenantScope  # noqa: E402

router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_model=CollectionEnvelope[JobDTO])
def list_jobs(
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    type_: str | None = Query(default=None, alias="type"),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Depends(cursor_param),
) -> dict:
    page = container.persistence.list_jobs(
        scope, workspace_id=workspace_id, type_=type_,
        cursor=cursor, limit=limit,
    )
    items = [_job_wire(row) for row in page.items]
    return {"items": items, "nextCursor": page.next_cursor}


@router.post("/jobs", response_model=JobDTO)
def create_job(
    body: CreateJobRequestDTO,
    session: SessionIdentity = Depends(require_authenticated),
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    audit=Depends(audit_writer),
) -> dict:
    from ..dependencies.rate_limit import check_write_quota

    if not scope.allows(body.workspace_id):
        raise not_found("workspace not found")
    require_workspace_membership(container, session, body.workspace_id)
    check_write_quota(container, session)

    # Route-level input validation (thin controller, §C.4): the job layer
    # assumes a well-formed input and records failures as job states.
    if body.type == "experiment_execution" and not body.experiment_id:
        raise validation("experiment_execution jobs require experimentId")
    if body.type == "system_recovery" and not body.repository_url:
        raise validation(
            "system_recovery jobs require repositoryUrl (recovery pins the "
            "exact revision — never 'latest')"
        )

    service = JobService(container)
    created, row = service.create_job(
        scope=scope, session=session, body=body, audit=audit
    )
    # LOCAL mode: the in-process bounded executor (tests/dev). PUBLIC and
    # preview: enqueue only — zero job execution in the API process.
    if (
        container.settings.env == "local"
        and str(row.get("status")) == "queued"
    ):
        row = service.execute_job(
            scope=scope, job_row=row, session=session, audit=audit
        )
    return _job_wire(row)


@router.get("/jobs/{job_id}", response_model=JobDTO)
def get_job(
    job_id: str,
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
) -> dict:
    row = container.persistence.get_job(scope, job_id)
    if row is None:
        raise not_found("job not found")
    return _job_wire(row)


def _job_wire(row: dict) -> dict:
    return {
        "id": row["id"],
        "tenantId": row["tenant_id"],
        "type": row["type"],
        "requestedBy": row["requested_by"],
        "authoritySnapshot": row["authority_snapshot"],
        "inputHash": row["input_hash"],
        "sourceRevision": row["source_revision"],
        "provider": row["provider"],
        "status": row["status"],
        "startedAt": row["started_at"],
        "completedAt": row["completed_at"],
        "receipt": row["receipt"],
        "artifactRefs": row["artifact_refs"],
        "errorState": row["error_state"],
        "createdAt": row["created_at"],
    }
