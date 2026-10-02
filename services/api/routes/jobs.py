"""``/api/v1/jobs`` — thin routes. Idempotency keys dedup duplicate POSTs
(coordination seam); job types: system_recovery (W3 recovery at a pinned
ref), experiment_execution (the governed W11 dispatch). Directive §8 job
fields exactly."""
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
from ..errors import not_found, validation
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
    cursor: str | None = Query(default=None),
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
    from ..dependencies.rate_limit import check_job_quota, check_write_quota

    if not scope.allows(body.workspace_id):
        raise not_found("workspace not found")
    check_write_quota(container, session)

    idempotency_key = body.idempotency_key or (
        f"{body.type}:{body.workspace_id}:"
        f"{body.experiment_id or ''}:{body.ref or ''}"
    )
    existing = container.persistence.get_job_by_idempotency_key(
        scope, idempotency_key
    )
    if existing is not None:
        # Idempotent replay: same key → same job, no duplicate side effects.
        return _job_wire(existing)

    check_job_quota(container, body.workspace_id, body.type)

    if body.type == "experiment_execution":
        row = _run_execution_job(
            container=container, scope=scope, session=session,
            workspace_id=body.workspace_id, experiment_id=body.experiment_id,
            idempotency_key=idempotency_key, audit=audit,
        )
        return _job_wire(row)
    if body.type == "system_recovery":
        row = _run_recovery_job(
            container=container, scope=scope, session=session,
            workspace_id=body.workspace_id, repository_url=body.repository_url,
            ref=body.ref, idempotency_key=idempotency_key, audit=audit,
        )
        return _job_wire(row)
    raise validation(f"unknown job type {body.type!r}")


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


# -- job runners (LOCAL bounded in-process execution; PUB-06 adds the
# separate worker process) -------------------------------------------------


def _run_execution_job(
    *,
    container: ApiContainer,
    scope: TenantScope,
    session: SessionIdentity,
    workspace_id: str,
    experiment_id: str | None,
    idempotency_key: str,
    audit,
) -> dict:
    if not experiment_id:
        raise validation(
            "experiment_execution jobs require experimentId"
        )
    from ..routes.executions import dispatch_execution
    from ..schemas.execution import DispatchExecutionRequestDTO

    execution = dispatch_execution(
        DispatchExecutionRequestDTO(
            experiment_id=experiment_id, intent=""
        ),
        session=session, scope=scope, container=container, audit=audit,
    )
    receipt = execution["receipt"] or {}
    job_id = "job-exec-" + str(execution["id"])
    row = container.persistence.insert_job(
        workspace_id=workspace_id, job_id=job_id,
        payload={
            "type": "experiment_execution",
            "requestedBy": session.user_id,
            "authoritySnapshot": {
                "principal": session.display,
                "provider": execution["provider"],
            },
            "inputHash": str(execution["requestHash"]),
            "sourceRevision": receipt.get("sourceRevision", ""),
            "provider": str(execution["provider"]),
            "status": (
                "succeeded"
                if receipt.get("outcome", {}).get("state") == "SUCCESS"
                else "failed"
            ),
            "startedAt": receipt.get("startedAt"),
            "completedAt": receipt.get("finishedAt"),
            "receipt": receipt,
            "artifactRefs": list(execution.get("artifactRefs") or []),
            "errorState": (
                None
                if receipt.get("outcome", {}).get("state") == "SUCCESS"
                else str(receipt.get("outcome", {}).get("detail") or "")
            ),
            "idempotencyKey": idempotency_key,
            "createdAt": now_iso(),
        },
    )
    audit(
        tenant_id=workspace_id, actor=session.display,
        action="job.completed", target=f"job/{job_id}",
        meta={"status": row["status"], "executionId": execution["id"]},
        ts=now_iso(),
    )
    return row


def _run_recovery_job(
    *,
    container: ApiContainer,
    scope: TenantScope,
    session: SessionIdentity,
    workspace_id: str,
    repository_url: str | None,
    ref: str | None,
    idempotency_key: str,
    audit,
) -> dict:
    if not repository_url:
        raise validation(
            "system_recovery jobs require repositoryUrl (recovery pins the "
            "exact revision — never 'latest')"
        )
    from ..orchestration import run_system_recovery
    from ..routes.systems import _graph_wire
    from providers.github.local import (
        UnknownCommitError,
        UnknownRepositoryError,
    )
    from sos.model import TruthState, TruthfulValue
    from sos.evidence import EvidenceProvenance
    from ..orchestration import (
        DEMO_TRACEABILITY,
        build_evidence_record,
        evidence_domain_to_wire,
    )

    job_id = "job-recovery-" + (idempotency_key.replace(":", "-"))
    try:
        commit, recovery, state = run_system_recovery(
            github=container.github, repository_url=repository_url,
            ref=ref, fallback_revision=None,
            traceability=DEMO_TRACEABILITY,
        )
    except UnknownRepositoryError as exc:
        raise validation(str(exc)) from exc
    except UnknownCommitError as exc:
        raise validation(str(exc)) from exc

    system_id = "sys-" + _slugish_url(repository_url)
    revision_id = f"{system_id}-rev1"
    existing_system = container.persistence.get_system(scope, system_id)
    if existing_system is None:
        container.persistence.insert_system(
            workspace_id=workspace_id, system_id=system_id,
            name=repository_url.rsplit("/", 1)[-1] or system_id,
            mode="brownfield", current_revision_id=None,
            created_at=now_iso(),
        )
    container.persistence.insert_system_revision(
        system_id=system_id, revision_id=revision_id, revision=1,
        payload={
            "stateSummary": (
                f"Recovered at pinned commit {commit.sha[:12]} via the W3 "
                f"recovery pipeline ({len(state.architecture.nodes)} nodes, "
                f"{len(state.architecture.edges)} edges)."
            ),
            "uncertainty": {
                "state": state.architecture.uncertainty.state.value,
                "reason": state.architecture.uncertainty.reason,
                "confidence": state.architecture.uncertainty.confidence,
            },
            "sourceRef": {
                "kind": "github",
                "url": repository_url,
                "revision": commit.sha,
                "immutable": True,
                "fixture": True,
            },
            "recovery": {"jobId": job_id, "status": "succeeded"},
            "graph": _graph_wire(state.architecture),
        },
        created_at=now_iso(), set_current=True,
    )
    evidence = build_evidence_record(
        kind="source_revision",
        source_ref="architecture-recovery",
        subject_ref=system_id,
        result=TruthfulValue(
            TruthState.SUCCESS,
            {
                "revision": commit.sha,
                "filesClassified": len(recovery.inventory.files),
                "nodesRecovered": len(state.architecture.nodes),
            },
            "system state recovered from the pinned commit",
        ),
        provenance=EvidenceProvenance(
            source="architecture-recovery",
            observed_subject=system_id,
            timestamp=now_iso(),
            environment=None,
            implementation_revision=commit.sha,
        ),
        traceability=DEMO_TRACEABILITY,
        evidence_id=f"ev-{job_id}",
        timestamp=now_iso(),
    )
    container.persistence.insert_evidence(
        workspace_id=workspace_id, evidence_id=f"ev-{job_id}",
        payload=evidence_domain_to_wire(
            evidence, evidence_id=f"ev-{job_id}",
            workspace_id=workspace_id, system_id=system_id,
            created_at=now_iso(),
        ),
    )
    row = container.persistence.insert_job(
        workspace_id=workspace_id, job_id=job_id,
        payload={
            "type": "system_recovery",
            "requestedBy": session.user_id,
            "authoritySnapshot": {
                "principal": session.display, "workspaceRole": "member",
            },
            "inputHash": commit.sha[:16],
            "sourceRevision": commit.sha,
            "provider": "local",
            "status": "succeeded",
            "startedAt": now_iso(),
            "completedAt": now_iso(),
            "receipt": {
                "performedBy": "sos.recovery.recover_repository",
                "fixture": True,
                "revision": commit.sha,
                "systemRevisionId": revision_id,
                "filesClassified": len(recovery.inventory.files),
                "nodesRecovered": len(state.architecture.nodes),
            },
            "artifactRefs": [],
            "errorState": None,
            "idempotencyKey": idempotency_key,
            "createdAt": now_iso(),
        },
    )
    audit(
        tenant_id=workspace_id, actor=session.display,
        action="job.completed", target=f"job/{job_id}",
        meta={"status": "succeeded", "systemRevisionId": revision_id},
        ts=now_iso(),
    )
    return row


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


def _slugish_url(url: str) -> str:
    import re as _re

    tail = url.rstrip("/").rsplit("/", 1)[-1] or "repo"
    slug = _re.sub(r"[^a-z0-9]+", "-", tail.lower()).strip("-")
    return (slug or "repo")[:48]
