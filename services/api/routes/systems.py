"""``/api/v1/systems`` — thin routes. Brownfield onboarding pins the EXACT
commit through the GitHub seam (S11: never "latest main") and runs the REAL
W3 recovery pipeline; greenfield creates the system shell for later
revision authoring."""
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
from ..orchestration import (
    DEMO_TRACEABILITY,
    build_evidence_record,
    evidence_domain_to_wire,
    run_system_recovery,
)
from ..schemas.common import CollectionEnvelope
from ..schemas.system import (
    CreateSystemRequestDTO,
    RecoveryRequestDTO,
    SystemDTO,
)
from providers.github.local import (  # noqa: E402
    UnknownCommitError,
    UnknownRepositoryError,
)
from providers.neon.seam import TenantScope  # noqa: E402
from sos.model import TruthState, TruthfulValue  # noqa: E402
from sos.evidence import EvidenceProvenance  # noqa: E402

router = APIRouter(tags=["systems"])


@router.get("/systems", response_model=CollectionEnvelope[SystemDTO])
def list_systems(
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> dict:
    page = container.persistence.list_systems(
        scope, workspace_id=workspace_id, cursor=cursor, limit=limit
    )
    items = [_with_current_revision(container, scope, row) for row in page.items]
    return {"items": items, "nextCursor": page.next_cursor}


@router.post("/systems", response_model=SystemDTO)
def create_system(
    body: CreateSystemRequestDTO,
    session: SessionIdentity = Depends(require_authenticated),
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    audit=Depends(audit_writer),
) -> dict:
    from ..dependencies.rate_limit import check_write_quota, check_job_quota

    if not scope.allows(body.workspace_id):
        raise not_found("workspace not found")
    check_write_quota(container, session)
    system_id = "sys-" + _slugish(body.name)
    if body.mode == "brownfield":
        if not body.repository_url:
            raise validation(
                "brownfield onboarding requires repositoryUrl (the immutable "
                "source reference is pinned at onboarding)"
            )
        check_job_quota(container, body.workspace_id, "system_recovery")
        try:
            row = _onboard_brownfield(
                container=container, scope=scope,
                workspace_id=body.workspace_id, system_id=system_id,
                name=body.name, repository_url=body.repository_url,
                ref=body.ref, actor=session.display,
            )
        except UnknownRepositoryError as exc:
            raise validation(str(exc)) from exc
        except UnknownCommitError as exc:
            raise validation(str(exc)) from exc
        audit(
            tenant_id=body.workspace_id, actor=session.display,
            action="system.onboarded", target=f"system/{system_id}",
            meta={
                "mode": "brownfield",
                "repositoryUrl": body.repository_url,
                "ref": body.ref,
            },
            ts=now_iso(),
        )
        return row
    row = container.persistence.insert_system(
        workspace_id=body.workspace_id, system_id=system_id,
        name=body.name, mode="greenfield",
        current_revision_id=None, created_at=now_iso(),
    )
    audit(
        tenant_id=body.workspace_id, actor=session.display,
        action="system.onboarded", target=f"system/{system_id}",
        meta={"mode": "greenfield"}, ts=now_iso(),
    )
    return row


@router.get("/systems/{system_id}", response_model=SystemDTO)
def get_system(
    system_id: str,
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
) -> dict:
    row = container.persistence.get_system(scope, system_id)
    if row is None:
        raise not_found("system not found")
    return _with_current_revision(container, scope, row)


@router.post("/systems/{system_id}/recovery")
def start_recovery(
    system_id: str,
    body: RecoveryRequestDTO,
    session: SessionIdentity = Depends(require_authenticated),
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    audit=Depends(audit_writer),
) -> dict:
    """Run a (bounded, LOCAL-synchronous) recovery job: pin the exact ref,
    recover the architecture through ``sos.recovery``, persist the new
    system revision + source evidence + job + audit event."""
    from ..dependencies.rate_limit import check_job_quota

    system = container.persistence.get_system(scope, system_id)
    if system is None:
        raise not_found("system not found")
    workspace_id = str(system["workspace_id"])
    check_job_quota(container, workspace_id, "system_recovery")

    current = None
    if system.get("current_revision_id"):
        current = container.persistence.get_system_revision(
            scope, str(system["current_revision_id"])
        )
    source_ref = (current or {}).get("source_ref") or {}
    repository_url = source_ref.get("url")
    if not repository_url:
        raise validation(
            "system carries no recorded source reference to recover from"
        )

    revision_number = _next_revision_number(container, scope, system_id)
    revision_id = f"{system_id}-rev{revision_number}"
    job_id = f"job-recovery-{revision_id}"
    try:
        commit, recovery, state = run_system_recovery(
            github=container.github, repository_url=repository_url,
            ref=body.ref, fallback_revision=source_ref.get("revision"),
            traceability=DEMO_TRACEABILITY,
        )
    except UnknownCommitError as exc:
        raise validation(str(exc)) from exc

    container.persistence.insert_system_revision(
        system_id=system_id, revision_id=revision_id,
        revision=revision_number,
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
        evidence_id=f"ev-recovery-{revision_id}",
        timestamp=now_iso(),
    )
    container.persistence.insert_evidence(
        workspace_id=workspace_id,
        evidence_id=f"ev-recovery-{revision_id}",
        payload=evidence_domain_to_wire(
            evidence, evidence_id=f"ev-recovery-{revision_id}",
            workspace_id=workspace_id, system_id=system_id,
            created_at=now_iso(),
        ),
    )
    job = container.persistence.insert_job(
        workspace_id=workspace_id, job_id=job_id,
        payload={
            "type": "system_recovery",
            "requestedBy": session.user_id,
            "authoritySnapshot": {
                "principal": session.display,
                "workspaceRole": "member",
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
            "idempotencyKey": None,
            "createdAt": now_iso(),
        },
    )
    audit(
        tenant_id=workspace_id, actor=session.display,
        action="system.recovered", target=f"system-revision/{revision_id}",
        meta={"sourceRevision": commit.sha, "jobId": job_id},
        ts=now_iso(),
    )
    return {"job": job, "systemRevisionId": revision_id}


@router.get("/systems/{system_id}/recovery")
def recovery_status(
    system_id: str,
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> dict:
    system = container.persistence.get_system(scope, system_id)
    if system is None:
        raise not_found("system not found")
    workspace_id = str(system["workspace_id"])
    jobs = container.persistence.list_jobs(
        scope, workspace_id=workspace_id, type_="system_recovery",
        cursor=cursor, limit=limit,
    )
    current = None
    if system.get("current_revision_id"):
        current = container.persistence.get_system_revision(
            scope, str(system["current_revision_id"])
        )
    return {
        "systemId": system_id,
        "currentRevisionId": system.get("current_revision_id"),
        "recovery": (current or {}).get("recovery"),
        "jobs": {"items": list(jobs.items), "nextCursor": jobs.next_cursor},
    }


# -- helpers -----------------------------------------------------------------


def _onboard_brownfield(
    *,
    container: ApiContainer,
    scope: TenantScope,
    workspace_id: str,
    system_id: str,
    name: str,
    repository_url: str,
    ref: str | None,
    actor: str,
) -> dict:
    commit, recovery, state = run_system_recovery(
        github=container.github, repository_url=repository_url, ref=ref,
        fallback_revision=None, traceability=DEMO_TRACEABILITY,
    )
    revision_id = f"{system_id}-rev1"
    job_id = f"job-recovery-{revision_id}"
    row = container.persistence.insert_system(
        workspace_id=workspace_id, system_id=system_id, name=name,
        mode="brownfield", current_revision_id=None, created_at=now_iso(),
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
            "system state recovered from the pinned commit at onboarding",
        ),
        provenance=EvidenceProvenance(
            source="architecture-recovery",
            observed_subject=system_id,
            timestamp=now_iso(),
            environment=None,
            implementation_revision=commit.sha,
        ),
        traceability=DEMO_TRACEABILITY,
        evidence_id=f"ev-recovery-{revision_id}",
        timestamp=now_iso(),
    )
    container.persistence.insert_evidence(
        workspace_id=workspace_id,
        evidence_id=f"ev-recovery-{revision_id}",
        payload=evidence_domain_to_wire(
            evidence, evidence_id=f"ev-recovery-{revision_id}",
            workspace_id=workspace_id, system_id=system_id,
            created_at=now_iso(),
        ),
    )
    container.persistence.insert_job(
        workspace_id=workspace_id, job_id=job_id,
        payload={
            "type": "system_recovery",
            "requestedBy": actor,
            "authoritySnapshot": {"principal": actor, "workspaceRole": "member"},
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
            "idempotencyKey": None,
            "createdAt": now_iso(),
        },
    )
    fresh = container.persistence.get_system(scope, system_id)
    return _with_current_revision(container, scope, dict(fresh or row))


def _with_current_revision(
    container: ApiContainer, scope: TenantScope, row: dict
) -> dict:
    revision = None
    if row.get("current_revision_id"):
        revision = container.persistence.get_system_revision(
            scope, str(row["current_revision_id"])
        )
    return {**row, "currentRevision": revision}


def _next_revision_number(
    container: ApiContainer, scope: TenantScope, system_id: str
) -> int:
    """Revisions append monotonically: current + 1 (the recovery flows only
    ever append and set-current)."""
    row = container.persistence.get_system(scope, system_id)
    current_id = (row or {}).get("current_revision_id")
    if not current_id:
        return 1
    current = container.persistence.get_system_revision(scope, str(current_id))
    return int(current["revision"]) + 1 if current else 1


def _graph_wire(graph) -> dict:
    return {
        "id": graph.id,
        "version": graph.version,
        "nodes": [
            {
                "id": n.id, "type": n.type.value, "name": n.name,
                "attributes": dict(n.attributes),
                "uncertainty": {
                    "state": n.uncertainty.state.value,
                    "reason": n.uncertainty.reason,
                    "confidence": n.uncertainty.confidence,
                },
            }
            for n in graph.nodes
        ],
        "edges": [
            {
                "id": e.id, "type": e.type.value, "sourceId": e.source_id,
                "targetId": e.target_id, "attributes": dict(e.attributes),
                "uncertainty": {
                    "state": e.uncertainty.state.value,
                    "reason": e.uncertainty.reason,
                    "confidence": e.uncertainty.confidence,
                },
            }
            for e in graph.edges
        ],
        "boundaryContracts": [
            {
                "id": b.id, "interfaceNodeId": b.interface_node_id,
                "contract": b.contract, "invariants": list(b.invariants),
            }
            for b in graph.boundary_contracts
        ],
    }


def _slugish(name: str) -> str:
    import re as _re

    slug = _re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (slug or "system")[:48]
