"""Domain-object ↔ row mapping for the persisted entity set (PUB-05).

This module is the SINGLE mapping authority shared by BOTH persistence
implementations of the provider-neutral seam
(:class:`providers.neon.local.LocalSqlitePersistence` and
:class:`providers.neon.cloud.NeonPostgresPersistence`):

- **Registries** (single source of truth, imported by both adapters and by
  the migration runner's Postgres dialect): the JSON-column registry (which
  ``TEXT`` columns carry JSON documents — ``JSONB`` on PostgreSQL), the
  tenant-table registry (which column scopes each table to a workspace) and
  the parent-link registry (child tables that resolve their tenant through
  a parent table).
- **Decomposition/reassembly** of the wire-shaped payload documents into
  the normalized §11 entity rows (architecture nodes/edges, evidence
  artifacts, causal hypotheses, candidate evaluations, assurance results,
  experiment events, execution requests/receipts) and back. Every
  ``rows_to_x(x_to_rows(doc)) == doc`` round-trip property is asserted by
  the PUB-05 parity suite against BOTH backends.

MAPPING ONLY — no semantic interpretation: values (including truth states)
pass through verbatim; the frozen ``src/sos`` engines stay the only
semantic authority. Rows are plain dicts; JSON columns are encoded/decoded
by :func:`encode_row` / :func:`decode_row` so both backends serialize
byte-identically (``json.dumps(..., sort_keys=True)``).

Derived row ids are DETERMINISTIC (content-addressed over their natural
identity parts), so re-projecting the same payload yields the same rows —
idempotent projection, no duplicate side effects.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Registries (single source of truth for adapters + the Postgres dialect)
# ---------------------------------------------------------------------------

# Tables with columns carrying JSON documents (TEXT on SQLite, JSONB on
# PostgreSQL). Column names are the SNAKE_CASE storage names.
JSON_COLUMNS: dict[str, frozenset[str]] = {
    "mission_revisions": frozenset({
        "goals", "outcomes", "stakeholders", "measures", "constraints",
        "preferences", "approval",
    }),
    "system_revisions": frozenset({
        "uncertainty", "source_ref", "recovery", "graph",
    }),
    "architecture_nodes": frozenset({"attributes", "uncertainty"}),
    "architecture_edges": frozenset({"attributes", "uncertainty"}),
    "architecture_boundary_contracts": frozenset({"invariants"}),
    "evidence": frozenset({"provenance", "result"}),
    "evidence_artifacts": frozenset(),
    "hypotheses": frozenset({"causal", "evidence_refs"}),
    "causal_hypotheses": frozenset({"uncertainty", "supporting_evidence"}),
    "candidates": frozenset({
        "subgraph_replacement", "effects", "costs", "risks", "constraints",
        "evidence_refs", "reversibility", "evaluation",
    }),
    "candidate_evaluations": frozenset({"uncertainty", "point_values"}),
    "assurance_runs": frozenset({"checks"}),
    "assurance_results": frozenset({"evidence_ids"}),
    "decisions": frozenset({
        "evidence_refs", "authority_snapshot", "expected_impact",
        "reversibility", "required_approvals", "ask_payload",
    }),
    "experiments": frozenset({"events"}),
    "experiment_events": frozenset(),
    "executions": frozenset({"receipt", "artifact_refs"}),
    "execution_requests": frozenset(),
    "execution_receipts": frozenset({
        "outcome_value", "side_effects", "changed_revisions",
        "rollback_reference",
    }),
    "learning_records": frozenset({
        "context", "predicted_effects", "actual_effects", "uncertainty",
        "lessons",
    }),
    "memory_entries": frozenset({
        "context", "predicted_effects", "actual_effects", "uncertainty",
        "lessons",
    }),
    "jobs": frozenset({
        "authority_snapshot", "receipt", "artifact_refs",
    }),
    "audit_events": frozenset({"meta"}),
    "value_model_revisions": frozenset({
        "objectives", "constraints", "tradeoffs", "signals",
    }),
    "contexts": frozenset({"conditions"}),
    "provider_events": frozenset({"payload"}),
}

# Tables whose rows carry a DIRECT tenant (workspace) column — the adapter
# applies the TenantScope allowlist to exactly these columns (SECURITY S5).
TENANT_TABLES: dict[str, str] = {
    "workspaces": "id",
    "missions": "workspace_id",
    "mission_revisions": "mission_id",
    "systems": "workspace_id",
    "system_revisions": "system_id",
    "architecture_nodes": "workspace_id",
    "architecture_edges": "workspace_id",
    "architecture_boundary_contracts": "workspace_id",
    "evidence": "workspace_id",
    "evidence_artifacts": "workspace_id",
    "hypotheses": "workspace_id",
    "causal_hypotheses": "workspace_id",
    "candidates": "workspace_id",
    "candidate_evaluations": "workspace_id",
    "assurance_runs": "workspace_id",
    "assurance_results": "workspace_id",
    "decisions": "workspace_id",
    "authorizations": "workspace_id",
    "experiments": "workspace_id",
    "experiment_events": "workspace_id",
    "executions": "workspace_id",
    "execution_requests": "workspace_id",
    "execution_receipts": "workspace_id",
    "learning_records": "workspace_id",
    "memory_entries": "workspace_id",
    "jobs": "tenant_id",
    "value_models": "workspace_id",
    "contexts": "workspace_id",
    "provider_events": "workspace_id",
}

# Child tables joined through their parent for scope resolution (tables
# WITHOUT a direct tenant column).
PARENT_LINKS: dict[str, tuple[str, str, str]] = {
    "mission_revisions": ("missions", "mission_id", "workspace_id"),
    "system_revisions": ("systems", "system_id", "workspace_id"),
    "value_model_revisions": (  # tenant via parent link only
        "value_models", "value_model_id", "workspace_id"
    ),
}


# ---------------------------------------------------------------------------
# Row encode/decode (identical serialization on BOTH backends)
# ---------------------------------------------------------------------------

def encode_row(table: str, row: dict[str, Any]) -> dict[str, Any]:
    """Serialize a mapping row for storage: JSON columns are
    ``json.dumps(value, sort_keys=True)`` — byte-identical on SQLite and
    PostgreSQL (JSONB round-trips the decoded value)."""
    json_cols = JSON_COLUMNS.get(table, frozenset())
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key in json_cols and value is not None:
            out[key] = json.dumps(value, sort_keys=True)
        else:
            out[key] = value
    return out


def decode_row(table: str, row: dict[str, Any]) -> dict[str, Any]:
    """Deserialize a stored row: JSON columns are ``json.loads``-ed back to
    their document values (None stays None)."""
    json_cols = JSON_COLUMNS.get(table, frozenset())
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key in json_cols and isinstance(value, str):
            out[key] = json.loads(value)
        else:
            out[key] = value
    return out


# ---------------------------------------------------------------------------
# Deterministic derived row ids (idempotent projection)
# ---------------------------------------------------------------------------

def derived_row_id(prefix: str, *parts: Any) -> str:
    """A deterministic row id: ``prefix-<16 hex>`` over the natural identity
    parts (sha256). Same inputs → same id → re-projection is idempotent."""
    basis = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


# ---------------------------------------------------------------------------
# Architecture graph (system_revisions.graph → architecture_nodes/edges)
# ---------------------------------------------------------------------------

def graph_node_rows(
    workspace_id: str, system_id: str, system_revision_id: str,
    graph: dict[str, Any], created_at: str,
) -> list[dict[str, Any]]:
    """Decompose the wire graph document into architecture_nodes rows
    (position = document order; node_key = the graph node id — ids repeat
    across revisions of the same system, so the row id is per-revision)."""
    rows: list[dict[str, Any]] = []
    for position, node in enumerate(graph.get("nodes") or []):
        rows.append({
            "id": derived_row_id(
                "archnode", system_revision_id, node["id"]
            ),
            "workspace_id": workspace_id,
            "system_id": system_id,
            "system_revision_id": system_revision_id,
            "graph_id": graph.get("id"),
            "graph_version": graph.get("version"),
            "node_key": node["id"],
            "node_type": node["type"],
            "name": node["name"],
            "position": position,
            "attributes": node.get("attributes"),
            "uncertainty": node.get("uncertainty"),
            "created_at": created_at,
        })
    return rows


def graph_edge_rows(
    workspace_id: str, system_id: str, system_revision_id: str,
    graph: dict[str, Any], created_at: str,
) -> list[dict[str, Any]]:
    """Decompose the wire graph document into architecture_edges rows."""
    rows: list[dict[str, Any]] = []
    for position, edge in enumerate(graph.get("edges") or []):
        rows.append({
            "id": derived_row_id(
                "archedge", system_revision_id, edge["id"]
            ),
            "workspace_id": workspace_id,
            "system_id": system_id,
            "system_revision_id": system_revision_id,
            "graph_id": graph.get("id"),
            "graph_version": graph.get("version"),
            "edge_key": edge["id"],
            "edge_type": edge["type"],
            "source_key": edge["sourceId"],
            "target_key": edge["targetId"],
            "position": position,
            "attributes": edge.get("attributes"),
            "uncertainty": edge.get("uncertainty"),
            "created_at": created_at,
        })
    return rows


def graph_boundary_contract_rows(
    workspace_id: str, system_id: str, system_revision_id: str,
    graph: dict[str, Any], created_at: str,
) -> list[dict[str, Any]]:
    """Decompose the wire graph document's boundaryContracts (the W2 frozen
    BoundaryContract model — interface node, contract text, invariants) into
    architecture_boundary_contracts rows."""
    rows: list[dict[str, Any]] = []
    for position, contract in enumerate(graph.get("boundaryContracts") or []):
        rows.append({
            "id": derived_row_id(
                "archbc", system_revision_id, contract["id"]
            ),
            "workspace_id": workspace_id,
            "system_id": system_id,
            "system_revision_id": system_revision_id,
            "graph_id": graph.get("id"),
            "graph_version": graph.get("version"),
            "contract_key": contract["id"],
            "interface_node_id": contract.get("interfaceNodeId"),
            "contract": contract.get("contract"),
            "invariants": contract.get("invariants"),
            "position": position,
            "created_at": created_at,
        })
    return rows


def rows_to_graph(
    node_rows: Iterable[dict[str, Any]],
    edge_rows: Iterable[dict[str, Any]],
    contract_rows: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Reassemble the wire graph document from architecture_nodes/edges/
    boundary_contracts rows (order by position). Inverse of the
    graph_*_rows decompositions — exact for the full wire document."""
    nodes = sorted(node_rows, key=lambda r: r["position"])
    edges = sorted(edge_rows, key=lambda r: r["position"])
    contracts = sorted(contract_rows, key=lambda r: r["position"])
    graph_id = nodes[0]["graph_id"] if nodes else (
        edges[0]["graph_id"] if edges else None
    )
    graph_version = nodes[0]["graph_version"] if nodes else (
        edges[0]["graph_version"] if edges else None
    )
    return {
        "id": graph_id,
        "version": graph_version,
        "nodes": [
            {
                "id": r["node_key"],
                "type": r["node_type"],
                "name": r["name"],
                "attributes": r["attributes"],
                "uncertainty": r["uncertainty"],
            }
            for r in nodes
        ],
        "edges": [
            {
                "id": r["edge_key"],
                "type": r["edge_type"],
                "sourceId": r["source_key"],
                "targetId": r["target_key"],
                "attributes": r["attributes"],
                "uncertainty": r["uncertainty"],
            }
            for r in edges
        ],
        "boundaryContracts": [
            {
                "id": r["contract_key"],
                "interfaceNodeId": r["interface_node_id"],
                "contract": r["contract"],
                "invariants": r["invariants"],
            }
            for r in contracts
        ],
    }


# ---------------------------------------------------------------------------
# Evidence artifacts (evidence.artifactRef → evidence_artifacts)
# ---------------------------------------------------------------------------

def evidence_artifact_row(
    workspace_id: str, evidence_id: str, payload: dict[str, Any],
) -> dict[str, Any] | None:
    """The evidence_artifacts metadata row for an evidence payload's
    artifactRef (None when the evidence carries no artifact). Bytes live in
    the artifact store (LOCAL FS / R2 — PUB-07), never in the database."""
    artifact_ref = payload.get("artifactRef")
    if not artifact_ref:
        return None
    return {
        "id": derived_row_id("evart", workspace_id, evidence_id),
        "workspace_id": workspace_id,
        "evidence_id": evidence_id,
        "system_id": payload.get("systemId"),
        "artifact_ref": artifact_ref,
        "created_at": payload.get("createdAt"),
    }


# ---------------------------------------------------------------------------
# Causal hypotheses (hypotheses.causal → causal_hypotheses)
# ---------------------------------------------------------------------------

def causal_hypothesis_row(
    workspace_id: str, hypothesis_id: str, payload: dict[str, Any],
) -> dict[str, Any] | None:
    """The causal_hypotheses row for a hypothesis payload's causal claim
    (columnar mapping of the W5 causal document; None when absent)."""
    causal = payload.get("causal")
    if not isinstance(causal, dict):
        return None
    return {
        "id": derived_row_id("causal", workspace_id, hypothesis_id),
        "workspace_id": workspace_id,
        "hypothesis_id": hypothesis_id,
        "cause_subject": causal.get("causeSubject"),
        "effect_subject": causal.get("effectSubject"),
        "relation_type": causal.get("relationType"),
        "direction": causal.get("direction"),
        "rationale": causal.get("rationale"),
        "status": causal.get("status"),
        "uncertainty": causal.get("uncertainty"),
        "supporting_evidence": causal.get("supportingEvidence"),
        "created_at": payload.get("createdAt"),
    }


# ---------------------------------------------------------------------------
# Candidate evaluations (candidates.evaluation → candidate_evaluations)
# ---------------------------------------------------------------------------

def candidate_evaluation_rows(
    workspace_id: str, candidate_id: str, evaluation: dict[str, Any],
) -> list[dict[str, Any]]:
    """Decompose a candidate evaluation document into candidate_evaluations
    rows: one ``objective`` row per objective, one ``pareto_point`` row per
    Pareto-front point (record_kind discriminates)."""
    rows: list[dict[str, Any]] = []
    for position, objective in enumerate(evaluation.get("objectives") or []):
        rows.append({
            "id": derived_row_id(
                "candev", workspace_id, candidate_id, "objective", position
            ),
            "workspace_id": workspace_id,
            "candidate_id": candidate_id,
            "record_kind": "objective",
            "position": position,
            "objective_name": objective.get("name"),
            "direction": objective.get("direction"),
            "predicted_value": objective.get("predictedValue"),
            "uncertainty": objective.get("uncertainty"),
            "candidate_ref": None,
            "point_values": None,
        })
    for position, point in enumerate(evaluation.get("paretoFront") or []):
        rows.append({
            "id": derived_row_id(
                "candev", workspace_id, candidate_id, "pareto", position
            ),
            "workspace_id": workspace_id,
            "candidate_id": candidate_id,
            "record_kind": "pareto_point",
            "position": position,
            "objective_name": None,
            "direction": None,
            "predicted_value": None,
            "uncertainty": None,
            "candidate_ref": point.get("candidateId"),
            "point_values": point.get("values"),
        })
    return rows


def rows_to_evaluation(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Reassemble the evaluation document from candidate_evaluations rows."""
    ordered = sorted(rows, key=lambda r: (r["record_kind"], r["position"]))
    objectives = [
        {
            "name": r["objective_name"],
            "direction": r["direction"],
            "predictedValue": r["predicted_value"],
            "uncertainty": r["uncertainty"],
        }
        for r in ordered
        if r["record_kind"] == "objective"
    ]
    pareto = [
        {"candidateId": r["candidate_ref"], "values": r["point_values"]}
        for r in ordered
        if r["record_kind"] == "pareto_point"
    ]
    return {"objectives": objectives, "paretoFront": pareto}


# ---------------------------------------------------------------------------
# Assurance results (assurance_runs.checks gates → assurance_results)
# ---------------------------------------------------------------------------

def assurance_result_rows(
    workspace_id: str, assurance_run_id: str, candidate_id: str | None,
    checks_doc: dict[str, Any], created_at: str | None,
) -> list[dict[str, Any]]:
    """Decompose the assurance checks document ({gates, domain}) into
    assurance_results rows — one row per executed gate."""
    gates = checks_doc.get("gates") or []
    rows: list[dict[str, Any]] = []
    for position, gate in enumerate(gates):
        rows.append({
            "id": derived_row_id(
                "assur", workspace_id, assurance_run_id, position
            ),
            "workspace_id": workspace_id,
            "assurance_run_id": assurance_run_id,
            "candidate_id": candidate_id,
            "position": position,
            "gate_name": gate.get("name"),
            "gate_status": gate.get("status"),
            "evidence_ids": gate.get("evidenceIds"),
            "detail": gate.get("detail"),
            "created_at": created_at,
        })
    return rows


def rows_to_gates(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reassemble the gates list from assurance_results rows."""
    ordered = sorted(rows, key=lambda r: r["position"])
    return [
        {
            "name": r["gate_name"],
            "status": r["gate_status"],
            "evidenceIds": r["evidence_ids"],
            "detail": r["detail"],
        }
        for r in ordered
    ]


# ---------------------------------------------------------------------------
# Experiment events (experiments.events → experiment_events)
# ---------------------------------------------------------------------------

def experiment_event_rows(
    workspace_id: str, experiment_id: str, events_doc: dict[str, Any],
) -> list[dict[str, Any]]:
    """Decompose the experiment events document ({events, domain}) into
    experiment_events rows (the lifecycle event log)."""
    events = events_doc.get("events") or []
    rows: list[dict[str, Any]] = []
    for position, event in enumerate(events):
        rows.append({
            "id": derived_row_id(
                "expev", workspace_id, experiment_id, position
            ),
            "workspace_id": workspace_id,
            "experiment_id": experiment_id,
            "position": position,
            "occurred_at": event.get("at"),
            "event_type": event.get("type"),
            "detail": event.get("detail"),
        })
    return rows


def rows_to_events(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reassemble the events list from experiment_events rows."""
    ordered = sorted(rows, key=lambda r: r["position"])
    return [
        {"at": r["occurred_at"], "type": r["event_type"], "detail": r["detail"]}
        for r in ordered
    ]


# ---------------------------------------------------------------------------
# Execution request / receipt (executions → execution_requests/receipts)
# ---------------------------------------------------------------------------

def execution_request_row(
    workspace_id: str, execution_id: str, payload: dict[str, Any],
) -> dict[str, Any]:
    """The execution_requests row for an executions payload (the governed
    request identity: provider + request hash + experiment binding)."""
    return {
        "id": derived_row_id("execreq", workspace_id, execution_id),
        "workspace_id": workspace_id,
        "execution_id": execution_id,
        "experiment_id": payload.get("experimentId"),
        "provider": payload["provider"],
        "request_hash": payload["requestHash"],
        "created_at": payload["createdAt"],
    }


def execution_receipt_row(
    workspace_id: str, execution_id: str, payload: dict[str, Any],
) -> dict[str, Any] | None:
    """The execution_receipts row for an executions payload (the columnar
    W11 receipt: outcome truth state verbatim, demo flag, provenance and
    side-effect references). None when the payload carries no receipt."""
    receipt = payload.get("receipt")
    if not isinstance(receipt, dict):
        return None
    outcome = receipt.get("outcome") or {}
    rollback_reference = receipt.get("rollbackReference")
    demo_flag = receipt.get("demo")
    return {
        "id": derived_row_id("execrcpt", workspace_id, execution_id),
        "workspace_id": workspace_id,
        "execution_id": execution_id,
        "receipt_id": receipt.get("id"),
        "request_id": receipt.get("requestId"),
        "provider_id": receipt.get("providerId"),
        "action_scope": receipt.get("actionScope"),
        "lifecycle": receipt.get("lifecycle"),
        "outcome_state": outcome.get("state"),
        "outcome_value": outcome.get("value"),
        "outcome_detail": outcome.get("detail"),
        "w9_decision_id": receipt.get("w9DecisionId"),
        "w7_assurance_id": receipt.get("w7AssuranceId"),
        "source_revision": receipt.get("sourceRevision"),
        "provenance_revision": receipt.get("provenanceRevision"),
        "base_graph_id": receipt.get("baseGraphId"),
        "base_graph_revision": receipt.get("baseGraphRevision"),
        "environment": receipt.get("environment"),
        "started_at": receipt.get("startedAt"),
        "finished_at": receipt.get("finishedAt"),
        "side_effects": receipt.get("sideEffects"),
        "stdout_ref": receipt.get("stdoutRef"),
        "stderr_ref": receipt.get("stderrRef"),
        "log_ref": receipt.get("logRef"),
        "changed_revisions": receipt.get("changedRevisions"),
        "rollback_reference": rollback_reference,
        "demo": (
            None if demo_flag is None else (1 if demo_flag else 0)
        ),
        "created_at": payload.get("createdAt"),
    }


def rows_to_receipt(receipt_row: dict[str, Any]) -> dict[str, Any]:
    """Reassemble the wire receipt document from an execution_receipts row
    (the persisted columns → the receipt_to_payload shape)."""
    row = dict(receipt_row)
    return {
        "id": row.get("receipt_id"),
        "requestId": row.get("request_id"),
        "providerId": row.get("provider_id"),
        "actionScope": row.get("action_scope"),
        "lifecycle": row.get("lifecycle"),
        "outcome": {
            "state": row.get("outcome_state"),
            "value": row.get("outcome_value"),
            "detail": row.get("outcome_detail"),
        },
        "w9DecisionId": row.get("w9_decision_id"),
        "w7AssuranceId": row.get("w7_assurance_id"),
        "sourceRevision": row.get("source_revision"),
        "provenanceRevision": row.get("provenance_revision"),
        "baseGraphId": row.get("base_graph_id"),
        "baseGraphRevision": row.get("base_graph_revision"),
        "environment": row.get("environment"),
        "startedAt": row.get("started_at"),
        "finishedAt": row.get("finished_at"),
        "sideEffects": row.get("side_effects") or [],
        "stdoutRef": row.get("stdout_ref"),
        "stderrRef": row.get("stderr_ref"),
        "logRef": row.get("log_ref"),
        "changedRevisions": row.get("changed_revisions") or [],
        "rollbackReference": row.get("rollback_reference"),
        "demo": (
            None if row.get("demo") is None else bool(row.get("demo"))
        ),
    }


# ---------------------------------------------------------------------------
# Wire-key ↔ storage-column name mapping (shared by both adapters)
# ---------------------------------------------------------------------------

SNAKE_OVERRIDES: dict[str, str] = {
    "requestedBy": "requested_by",
    "authoritySnapshot": "authority_snapshot",
    "inputHash": "input_hash",
    "sourceRevision": "source_revision",
    "startedAt": "started_at",
    "completedAt": "completed_at",
    "artifactRefs": "artifact_refs",
    "errorState": "error_state",
    "idempotencyKey": "idempotency_key",
}


def snake_case(camel: str) -> str:
    """The storage column name for a wire (camelCase) key."""
    if camel in SNAKE_OVERRIDES:
        return SNAKE_OVERRIDES[camel]
    out = "".join(("_" + ch.lower()) if ch.isupper() else ch for ch in camel)
    return out if out else camel
