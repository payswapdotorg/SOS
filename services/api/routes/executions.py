"""``/api/v1/executions`` — thin routes over the governed W11 dispatch.

POST /executions walks the full authority chain (W9 decision resolution →
scope state → provider-not-authorizer → chain equality → W7 PASS → W8
experiment binding → rollback binding) BEFORE any provider call, then
persists the receipt and converts it to W4 evidence (observed, not
inferred). ExecutionContractError from the substrate maps to the error
envelope — the governed rejection is never reinterpreted."""
from __future__ import annotations

from typing import Any

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
from ..errors import not_found, provider_unavailable, validation
from ..orchestration import (
    DEMO_TRACEABILITY,
    content_hash,
    dispatch_experiment_execution,
    evidence_domain_to_wire,
    receipt_evidence_wire,
    receipt_to_payload,
)
from ..schemas.execution import (
    DispatchExecutionRequestDTO,
    ExecutionDTO,
)
from ..schemas.common import CollectionEnvelope
from providers.neon.seam import TenantScope  # noqa: E402
from sos.execution import ExecutionContractError  # noqa: E402

router = APIRouter(tags=["executions"])


@router.get("/executions", response_model=CollectionEnvelope[ExecutionDTO])
def list_executions(
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    experiment_id: str | None = Query(default=None, alias="experimentId"),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> dict:
    page = container.persistence.list_executions(
        scope, workspace_id=workspace_id, experiment_id=experiment_id,
        cursor=cursor, limit=limit,
    )
    items = [_execution_wire(row) for row in page.items]
    return {"items": items, "nextCursor": page.next_cursor}


@router.post("/executions", response_model=ExecutionDTO)
def dispatch_execution(
    body: DispatchExecutionRequestDTO,
    session: SessionIdentity = Depends(require_authenticated),
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
    audit=Depends(audit_writer),
) -> dict:
    from ..dependencies.rate_limit import check_write_quota

    experiment_row = container.persistence.get_experiment(
        scope, body.experiment_id
    )
    if experiment_row is None:
        raise not_found("experiment not found")
    workspace_id = str(experiment_row["workspace_id"])
    check_write_quota(container, session)

    decisions_rows = [
        r for r in container.persistence.list_decisions(
            scope, workspace_id=workspace_id, cursor=None, limit=100
        ).items
    ]
    assurance_rows = [
        r for r in container.persistence.list_assurance(
            scope, workspace_id=workspace_id, candidate_id=None,
            cursor=None, limit=100,
        ).items
    ]
    experiment_rows = [experiment_row]

    provider_id = (
        "demo" if container.settings.execution_mode == "demo"
        else container.settings.execution_mode
    )
    try:
        receipt, decision_row = dispatch_experiment_execution(
            providers=container.execution_providers,
            decisions_rows=decisions_rows,
            assurance_rows=assurance_rows,
            experiment_rows=experiment_rows,
            experiment_id=body.experiment_id,
            intent=body.intent,
            decision_id=None,
            provider_id=provider_id,
        )
    except LookupError as exc:
        raise validation(
            f"cannot dispatch execution: {exc}",
            details={"experimentId": body.experiment_id},
        ) from exc
    except ExecutionContractError as exc:
        # The governed chain rejected the request BEFORE any provider call.
        raise validation(
            f"execution contract rejected the request: {exc}",
            details={"experimentId": body.experiment_id},
        ) from exc
    except Exception as exc:  # provider truly unavailable
        raise provider_unavailable(str(exc)) from exc

    receipt_payload = receipt_to_payload(receipt)
    execution_id = (
        "exec-" + content_hash((receipt.id, body.experiment_id))
    )
    system_id = _resolve_system_for_experiment(
        container, scope, workspace_id, experiment_row
    )
    artifact_key = (
        _store_receipt_artifact(
            container, workspace_id=workspace_id, system_id=system_id,
            execution_id=execution_id, receipt_payload=receipt_payload,
        )
        if system_id is not None
        else None
    )
    row = container.persistence.insert_execution(
        workspace_id=workspace_id, execution_id=execution_id,
        payload={
            "experimentId": body.experiment_id,
            "provider": receipt.provider_id,
            "requestHash": receipt.request_id,
            "receipt": receipt_payload,
            "artifactRefs": [artifact_key] if artifact_key else [],
            "status": receipt_payload["outcome"]["state"],
            "createdAt": now_iso(),
        },
    )
    # Receipt → W4 evidence (observed, not inferred; truth state verbatim).
    evidence, wire_kind = receipt_evidence_wire(
        receipt, traceability=DEMO_TRACEABILITY
    )
    evidence_id = "ev-exec-" + content_hash((receipt.id,))
    container.persistence.insert_evidence(
        workspace_id=workspace_id, evidence_id=evidence_id,
        payload=evidence_domain_to_wire(
            evidence, evidence_id=evidence_id, workspace_id=workspace_id,
            system_id=None, created_at=now_iso(), wire_kind=wire_kind,
            artifact_ref=artifact_key,
        ),
    )
    audit(
        tenant_id=workspace_id, actor=session.display,
        action="execution.dispatched", target=f"execution/{execution_id}",
        meta={
            "experimentId": body.experiment_id,
            "provider": receipt.provider_id,
            "lifecycle": receipt.lifecycle.value,
            "demo": receipt.provider_id == "demo",
        },
        ts=now_iso(),
    )
    return _execution_wire(row)


@router.get("/executions/{execution_id}", response_model=ExecutionDTO)
def get_execution(
    execution_id: str,
    scope: TenantScope = Depends(tenant_scope),
    container: ApiContainer = Depends(get_container),
) -> dict:
    row = container.persistence.get_execution(scope, execution_id)
    if row is None:
        raise not_found("execution not found")
    return _execution_wire(row)


def _execution_wire(row: dict) -> dict:
    return {
        "id": row["id"],
        "workspaceId": row["workspace_id"],
        "experimentId": row["experiment_id"],
        "provider": row["provider"],
        "requestHash": row["request_hash"],
        "receipt": row["receipt"],
        "artifactRefs": row["artifact_refs"],
        "status": row["status"],
        "createdAt": row["created_at"],
    }


def _store_receipt_artifact(
    container: ApiContainer,
    *,
    workspace_id: str,
    system_id: str,
    execution_id: str,
    receipt_payload: dict[str, Any],
) -> str | None:
    """Persist the receipt bytes into the artifact store under the §12
    layout (tenants/{tenantId}/systems/{systemId}/executions/{executionId}/
    receipts/) — content-addressed."""
    import json

    content = json.dumps(receipt_payload, sort_keys=True).encode("utf-8")
    try:
        stored = container.artifacts.put(
            workspace_id,
            system_id,
            category="executions",
            context_id=execution_id,
            subcategory="receipts",
            content=content,
            content_type="application/json",
        )
        return stored.key
    except Exception:
        # The artifact store being unavailable must not fabricate a receipt
        # artifact reference; the execution row records truthfully without
        # one and health reports the seam's true state.
        return None


def _resolve_system_for_experiment(
    container: ApiContainer,
    scope: TenantScope,
    workspace_id: str,
    experiment_row: dict,
) -> str | None:
    """Resolve the system whose current revision carries the experiment's
    base graph (honest §12 keying)."""
    base_graph_id = experiment_row["events"]["domain"].get("baseGraphId")
    systems = container.persistence.list_systems(
        scope, workspace_id=workspace_id, cursor=None, limit=100
    ).items
    for system in systems:
        current_id = system.get("current_revision_id")
        if not current_id:
            continue
        revision = container.persistence.get_system_revision(
            scope, str(current_id)
        )
        if revision and revision["graph"].get("id") == base_graph_id:
            return str(system["id"])
    return None
