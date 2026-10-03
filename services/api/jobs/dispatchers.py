"""The provider dispatcher's bounded local operations (PUB-06, directive §8
diagram: "Provider dispatcher ── local bounded operation └─ Apify execution").

One operation per job type, moved here from the PUB-01 route file so the
route stays a thin controller (contract §C.4) and the WORKER process runs
the exact same operations the LOCAL inline executor runs:

- ``system_recovery`` — a local bounded operation: pin the exact revision
  via the GitHub seam, run the REAL W3 recovery pipeline, persist the
  system revision + source-revision evidence. Never executes user
  repository code (directive §16-A).
- ``experiment_execution`` — handoff to the governed W11 execution seam
  (DemoProvider today; the Apify bounded execution provider lands with
  PUB-08 and reuses this same dispatcher slot).

Each operation returns a terminal payload patch (``status``, ``receipt``,
``artifactRefs``, ``errorState``, …) for the JobService to apply;
infrastructure failures raise (the service's bounded retry policy handles
them), while truthful non-SUCCESS provider outcomes are terminal RESULTS
(never retried into a fake success). Deterministic side effects (system/
revision/evidence ids derived from the job id, hence from the idempotency
key) make repeated execution converge on the same rows instead of
duplicating them.

Semantics stay in ``src/sos`` (imported, never edited): the recovery
pipeline, the evidence model and the execution contract all come from the
frozen core; these adapters only map, delegate and persist.
"""
from __future__ import annotations

from typing import Any

from ..errors import ApiError


def run_recovery_operation(
    container: Any,
    scope: Any,
    job_row: dict[str, Any],
    session: Any,
    job_input: dict[str, Any],
) -> dict[str, Any]:
    """``system_recovery``: local bounded operation over the W3 pipeline."""
    repository_url = str(job_input.get("repositoryUrl") or "")
    ref = job_input.get("ref")
    workspace_id = str(job_row["tenant_id"])
    job_id = str(job_row["id"])

    from ..dependencies import now_iso
    from ..orchestration import (
        DEMO_TRACEABILITY,
        build_evidence_record,
        evidence_domain_to_wire,
        run_system_recovery,
    )
    from ..routes.systems import _graph_wire
    from providers.github.local import (
        UnknownCommitError,
        UnknownRepositoryError,
    )
    from sos.evidence import EvidenceProvenance
    from sos.model import TruthState, TruthfulValue

    try:
        commit, recovery, state = run_system_recovery(
            github=container.github, repository_url=repository_url,
            ref=ref, fallback_revision=None,
            traceability=DEMO_TRACEABILITY,
        )
    except UnknownRepositoryError as exc:
        raise _permanent(str(exc)) from exc
    except UnknownCommitError as exc:
        raise _permanent(str(exc)) from exc

    system_id = "sys-" + _slugish(repository_url)
    revision_id = f"{system_id}-rev1"
    existing_system = container.persistence.get_system(scope, system_id)
    if existing_system is None:
        container.persistence.insert_system(
            workspace_id=workspace_id, system_id=system_id,
            name=repository_url.rsplit("/", 1)[-1] or system_id,
            mode="brownfield", current_revision_id=None,
            created_at=now_iso(),
        )
    existing_revision = container.persistence.get_system_revision(
        scope, revision_id
    )
    if existing_revision is None:
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
    _insert_evidence_once(
        container, workspace_id=workspace_id, evidence_id=f"ev-{job_id}",
        payload=evidence_domain_to_wire(
            evidence, evidence_id=f"ev-{job_id}",
            workspace_id=workspace_id, system_id=system_id,
            created_at=now_iso(),
        ),
    )
    return {
        "status": "succeeded",
        "startedAt": job_row.get("started_at"),
        "completedAt": now_iso(),
        "receipt": {
            "performedBy": "sos.recovery.recover_repository",
            "fixture": True,
            "revision": commit.sha,
            "systemRevisionId": revision_id,
            "filesClassified": len(recovery.inventory.files),
            "nodesRecovered": len(state.architecture.nodes),
            "jobId": job_id,
        },
        "artifactRefs": [],
        "errorState": None,
        "sourceRevision": commit.sha,
    }


def run_execution_operation(
    container: Any,
    scope: Any,
    job_row: dict[str, Any],
    session: Any,
    job_input: dict[str, Any],
) -> dict[str, Any]:
    """``experiment_execution``: handoff to the governed W11 execution seam.

    Calls the SAME thin dispatch path the executions route uses (the
    authority chain — W9 decision → provider-not-authorizer → W7 PASS →
    W8 binding → rollback binding — is enforced BEFORE any provider call;
    governed rejections are permanent job failures, never retried).
    """
    experiment_id = job_input.get("experimentId")
    if not experiment_id:
        raise _permanent("experiment_execution jobs require experimentId")
    from ..routes.executions import dispatch_execution
    from ..schemas.execution import DispatchExecutionRequestDTO

    try:
        execution = dispatch_execution(
            DispatchExecutionRequestDTO(
                experiment_id=str(experiment_id), intent=""
            ),
            session=session, scope=scope, container=container,
            audit=_worker_audit(container),
        )
    except ApiError as exc:
        if exc.code == "RATE_LIMITED":
            # A quota trip is transient relative to the backoff schedule:
            # the bounded retry policy retries after the jittered backoff.
            from .service import JobRetryableError

            raise JobRetryableError(
                f"execution dispatch rate limited: {exc.message}"
            ) from exc
        raise _permanent(f"execution dispatch rejected: {exc.message}") from exc
    except LookupError as exc:
        raise _permanent(f"cannot dispatch execution: {exc}") from exc

    receipt = execution["receipt"] or {}
    outcome_state = receipt.get("outcome", {}).get("state")
    return {
        "status": "succeeded" if outcome_state == "SUCCESS" else "failed",
        "startedAt": receipt.get("startedAt") or job_row.get("started_at"),
        "completedAt": receipt.get("finishedAt"),
        "receipt": receipt,
        "artifactRefs": list(execution.get("artifactRefs") or []),
        "errorState": (
            None if outcome_state == "SUCCESS"
            else str(receipt.get("outcome", {}).get("detail") or "")
        ),
        "sourceRevision": receipt.get("sourceRevision", ""),
        "inputHash": str(execution["requestHash"]),
    }


# -- helpers -------------------------------------------------------------------


def _worker_audit(container: Any):
    """The audit writer for job-driven mutations (every mutation carries an
    audit event — contract §C.2)."""
    from ..dependencies import audit_writer

    return audit_writer(container=container)


def _permanent(message: str):
    from .service import JobPermanentError

    return JobPermanentError(message)


def _slugish(url: str) -> str:
    import re as _re

    tail = url.rstrip("/").rsplit("/", 1)[-1] or "repo"
    slug = _re.sub(r"[^a-z0-9]+", "-", tail.lower()).strip("-")
    return (slug or "repo")[:48]


def _insert_evidence_once(
    container: Any, *, workspace_id: str, evidence_id: str,
    payload: dict[str, Any],
) -> None:
    """Insert the evidence row once; a duplicate-key hit means a previous
    (crash-interrupted) attempt already recorded it — idempotent
    convergence, never a duplicate side effect and never a fabricated
    failure. Any OTHER insert error propagates (bounded retry)."""
    try:
        container.persistence.insert_evidence(
            workspace_id=workspace_id, evidence_id=evidence_id,
            payload=payload,
        )
    except Exception as exc:  # noqa: BLE001 - duplicate detection below
        message = str(exc).lower()
        if "unique" in message or "duplicate key" in message:
            return
        raise


BUILT_IN_OPERATIONS = {
    "system_recovery": run_recovery_operation,
    "experiment_execution": run_execution_operation,
}
