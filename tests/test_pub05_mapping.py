"""PUB-05 — the domain-object ↔ row mapping (db/mapping.py): round-trip
properties for every decomposed entity, registry ↔ migration-DDL
consistency, deterministic row ids, and doc-column ↔ normalized-rows
equivalence over the full deterministic demo dataset (SQLite side; the
PostgreSQL side is proven by tests/test_pub05_postgres_parity.py).

Hermetic (stdlib only — no asyncpg, no network)."""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(REPO_ROOT / "src"), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from db.mapping import (  # noqa: E402
    JSON_COLUMNS,
    PARENT_LINKS,
    TENANT_TABLES,
    assurance_result_rows,
    candidate_evaluation_rows,
    causal_hypothesis_row,
    decode_row,
    derived_row_id,
    encode_row,
    evidence_artifact_row,
    execution_receipt_row,
    execution_request_row,
    experiment_event_rows,
    graph_boundary_contract_rows,
    graph_edge_rows,
    graph_node_rows,
    rows_to_evaluation,
    rows_to_events,
    rows_to_gates,
    rows_to_graph,
    rows_to_receipt,
    snake_case,
)
from db.runner import discover_migrations  # noqa: E402
from db.seeds.demo_seed import seed_demo  # noqa: E402
from providers.neon.local import LocalSqlitePersistence  # noqa: E402
from providers.neon.seam import TenantScope  # noqa: E402

# ---------------------------------------------------------------------------
# Representative wire documents (the seed's exact shapes)
# ---------------------------------------------------------------------------

DEMO_GRAPH = {
    "id": "graph:demo:1",
    "version": 2,
    "nodes": [
        {
            "id": "node:src/api.py",
            "type": "component",
            "name": "src/api.py",
            "attributes": {"kind": "module", "lines": 120},
            "uncertainty": {
                "state": "UNKNOWN", "reason": "static recovery", "confidence": None,
            },
        },
        {
            "id": "node:src/store.py",
            "type": "datastore",
            "name": "src/store.py",
            "attributes": {},
            "uncertainty": None,
        },
    ],
    "edges": [
        {
            "id": "edge:api->store",
            "type": "uses",
            "sourceId": "node:src/api.py",
            "targetId": "node:src/store.py",
            "attributes": {"protocol": "function-call"},
            "uncertainty": None,
        },
    ],
    "boundaryContracts": [
        {
            "id": "bc:query-path",
            "interfaceNodeId": "node:src/api.py",
            "contract": "read-only query surface",
            "invariants": ["staleness window bounded to 60s"],
        },
    ],
}

DEMO_EVALUATION = {
    "objectives": [
        {
            "name": "p95-latency-ms", "direction": "MINIMIZE",
            "predictedValue": 205.0,
            "uncertainty": {"state": "UNKNOWN", "detail": "extrapolation"},
        },
        {
            "name": "infra-cost-usd", "direction": "MINIMIZE",
            "predictedValue": 41.0, "uncertainty": None,
        },
    ],
    "paretoFront": [
        {
            "candidateId": "cand-demo-cache",
            "values": {"p95-latency-ms": 205.0, "infra-cost-usd": 41.0},
        },
        {
            "candidateId": "cand-demo-replica",
            "values": {"p95-latency-ms": 251.0, "infra-cost-usd": 118.0},
        },
    ],
}

DEMO_CHECKS_DOC = {
    "gates": [
        {"name": "impact-analysis", "status": "PASS",
         "evidenceIds": ["ev-demo-01"], "detail": "bounded subgraph"},
        {"name": "rollback-path", "status": "UNKNOWN",
         "evidenceIds": [], "detail": "rollback evidence pending"},
    ],
    "domain": {"impact": "…"},
}

DEMO_EVENTS_DOC = {
    "events": [
        {"at": "2026-05-20T09:30:00Z", "type": "created", "detail": "created"},
        {"at": "2026-05-21T10:00:00Z", "type": "started", "detail": "window open"},
        {"at": "2026-05-22T15:00:00Z", "type": "completed", "detail": "closed"},
    ],
    "domain": {"mode": "canary"},
}

DEMO_RECEIPT = {
    "id": "receipt-demo-1",
    "requestId": "exec-demo-1",
    "providerId": "demo",
    "actionScope": "deploy",
    "lifecycle": "completed",
    "outcome": {"state": "SUCCESS", "value": {"p95Ms": 208.0}, "detail": "done"},
    "w9DecisionId": "dec-demo-act",
    "w7AssuranceId": "assurance-demo-cache",
    "sourceRevision": "abc123",
    "provenanceRevision": "abc123",
    "baseGraphId": "graph:demo:1",
    "baseGraphRevision": "rev-2",
    "environment": "staging",
    "startedAt": "2026-05-22T15:00:00Z",
    "finishedAt": "2026-05-22T15:05:00Z",
    "sideEffects": [{"kind": "config-change", "target": "query-path",
                     "detail": "cache enabled"}],
    "stdoutRef": "run/stdout.txt",
    "stderrRef": None,
    "logRef": "run/log.txt",
    "changedRevisions": ["rev-3"],
    "rollbackReference": {
        "reference": "rollback://demo/example-api/cache-v1",
        "evidenceIds": ["ev-demo-rollback"],
        "detail": "rehearsed on staging",
    },
    "demo": True,
}

DEMO_CAUSAL = {
    "causeSubject": "query-path cache",
    "effectSubject": "p95 latency",
    "relationType": "reduces",
    "direction": "positive",
    "rationale": "intervention evidence",
    "status": "confirmed",
    "uncertainty": {"state": "UNKNOWN", "value": None, "detail": "one window"},
    "supportingEvidence": [
        {"evidenceId": "ev-demo-12", "supportKind": "interventional"},
    ],
}


# ---------------------------------------------------------------------------
# Round-trip properties (decompose → reassemble == identity)
# ---------------------------------------------------------------------------

def test_graph_round_trip() -> None:
    nodes = graph_node_rows("ws-demo", "sys-1", "sysrev-1", DEMO_GRAPH, "2026-01-01T00:00:00Z")
    edges = graph_edge_rows("ws-demo", "sys-1", "sysrev-1", DEMO_GRAPH, "2026-01-01T00:00:00Z")
    contracts = graph_boundary_contract_rows(
        "ws-demo", "sys-1", "sysrev-1", DEMO_GRAPH, "2026-01-01T00:00:00Z"
    )
    assert len(nodes) == 2 and len(edges) == 1 and len(contracts) == 1
    assert rows_to_graph(nodes, edges, contracts) == DEMO_GRAPH


def test_graph_round_trip_empty_boundary_contracts() -> None:
    """A graph without boundary contracts reassembles with the empty list
    (the exact seed shape: boundaryContracts: [])."""
    graph = {k: v for k, v in DEMO_GRAPH.items() if k != "boundaryContracts"}
    graph["boundaryContracts"] = []
    nodes = graph_node_rows("ws", "sys", "rev", graph, "t")
    edges = graph_edge_rows("ws", "sys", "rev", graph, "t")
    assert rows_to_graph(nodes, edges) == graph


def test_graph_projection_carries_tenant_and_revision() -> None:
    nodes = graph_node_rows("ws-demo", "sys-1", "sysrev-1", DEMO_GRAPH, "t")
    for row in nodes:
        assert row["workspace_id"] == "ws-demo"
        assert row["system_id"] == "sys-1"
        assert row["system_revision_id"] == "sysrev-1"
        assert row["graph_id"] == DEMO_GRAPH["id"]
        assert row["graph_version"] == DEMO_GRAPH["version"]
    # node ids repeat across revisions → row ids are per-(revision, key)
    other = graph_node_rows("ws-demo", "sys-1", "sysrev-2", DEMO_GRAPH, "t")
    assert {r["id"] for r in nodes}.isdisjoint({r["id"] for r in other})
    assert [r["node_key"] for r in nodes] == [r["node_key"] for r in other]


def test_graph_positions_preserve_document_order() -> None:
    nodes = graph_node_rows("ws", "sys", "rev", DEMO_GRAPH, "t")
    assert [r["position"] for r in nodes] == [0, 1]
    edges = graph_edge_rows("ws", "sys", "rev", DEMO_GRAPH, "t")
    assert [r["position"] for r in edges] == [0]


def test_evaluation_round_trip() -> None:
    rows = candidate_evaluation_rows("ws-demo", "cand-1", DEMO_EVALUATION)
    kinds = [r["record_kind"] for r in rows]
    assert kinds.count("objective") == 2
    assert kinds.count("pareto_point") == 2
    assert rows_to_evaluation(rows) == DEMO_EVALUATION


def test_assurance_gates_round_trip() -> None:
    rows = assurance_result_rows(
        "ws-demo", "assurance-1", "cand-1", DEMO_CHECKS_DOC, "t"
    )
    assert len(rows) == 2
    assert rows_to_gates(rows) == DEMO_CHECKS_DOC["gates"]


def test_experiment_events_round_trip() -> None:
    rows = experiment_event_rows("ws-demo", "exp-1", DEMO_EVENTS_DOC)
    assert len(rows) == 3
    assert rows_to_events(rows) == DEMO_EVENTS_DOC["events"]


def test_execution_receipt_round_trip() -> None:
    payload = {
        "experimentId": "exp-1", "provider": "demo",
        "requestHash": "hash-1", "receipt": DEMO_RECEIPT,
        "artifactRefs": ["tenants/ws/artifacts/x.json"],
        "status": "SUCCESS", "createdAt": "t",
    }
    receipt_row = execution_receipt_row("ws-demo", "exec-1", payload)
    assert receipt_row is not None
    assert receipt_row["demo"] == 1  # INTEGER storage form (both backends)
    assert receipt_row["outcome_state"] == "SUCCESS"  # truth state verbatim
    reassembled = rows_to_receipt(receipt_row)
    assert reassembled == DEMO_RECEIPT
    # the governed request identity row
    request_row = execution_request_row("ws-demo", "exec-1", payload)
    assert request_row["provider"] == "demo"
    assert request_row["request_hash"] == "hash-1"


def test_causal_hypothesis_row_mapping() -> None:
    row = causal_hypothesis_row(
        "ws-demo", "hyp-1",
        {"causal": DEMO_CAUSAL, "createdAt": "t"},
    )
    assert row is not None
    assert row["cause_subject"] == DEMO_CAUSAL["causeSubject"]
    assert row["effect_subject"] == DEMO_CAUSAL["effectSubject"]
    assert row["relation_type"] == DEMO_CAUSAL["relationType"]
    assert row["supporting_evidence"] == DEMO_CAUSAL["supportingEvidence"]
    assert causal_hypothesis_row("ws", "hyp", {"createdAt": "t"}) is None


def test_evidence_artifact_row_mapping() -> None:
    payload = {
        "artifactRef": "tenants/ws/systems/sys/evidence/ev/artifact.json",
        "systemId": "sys-1", "createdAt": "t",
    }
    row = evidence_artifact_row("ws-demo", "ev-1", payload)
    assert row is not None
    assert row["artifact_ref"] == payload["artifactRef"]
    assert row["evidence_id"] == "ev-1"
    assert evidence_artifact_row("ws", "ev", {}) is None


def test_derived_row_ids_are_deterministic() -> None:
    assert derived_row_id("x", "a", 1) == derived_row_id("x", "a", 1)
    assert derived_row_id("x", "a", 1) != derived_row_id("x", "a", 2)
    assert derived_row_id("x", "a") != derived_row_id("y", "a")


def test_snake_case_overrides() -> None:
    assert snake_case("requestedBy") == "requested_by"
    assert snake_case("idempotencyKey") == "idempotency_key"
    assert snake_case("status") == "status"


def test_encode_decode_row_round_trip() -> None:
    row = {
        "id": "r1", "attributes": {"a": 1, "b": [2, 3]},
        "uncertainty": None, "name": "n",
    }
    encoded = encode_row("architecture_nodes", row)
    assert encoded["attributes"] == '{"a": 1, "b": [2, 3]}'
    assert encoded["uncertainty"] is None
    assert decode_row("architecture_nodes", encoded) == row


# ---------------------------------------------------------------------------
# Registry ↔ migration-DDL consistency (the Postgres dialect's contract)
# ---------------------------------------------------------------------------

def _ddl_columns() -> dict[str, dict[str, str]]:
    """Parse every migration's CREATE TABLE columns (SQLite dialect),
    including ALTER TABLE … ADD COLUMN additions."""
    tables: dict[str, dict[str, str]] = {}
    column_re = re.compile(r"^\s+([a-z_][a-z0-9_]*)\s+([A-Z]+)\b")
    alter_re = re.compile(
        r"^\s*ALTER TABLE ([a-z_][a-z0-9_]*) ADD COLUMN "
        r"([a-z_][a-z0-9_]*)\s+([A-Z]+)\b"
    )
    current: str | None = None
    for entry in discover_migrations().values():
        for line in entry["up"].read_text(encoding="utf-8").splitlines():
            alter = alter_re.match(line)
            if alter is not None:
                tables.setdefault(alter.group(1), {})[alter.group(2)] = (
                    alter.group(3)
                )
                continue
            create = re.match(
                r"^\s*CREATE TABLE (?:IF NOT EXISTS )?([a-z_][a-z0-9_]*)", line
            )
            if create is not None:
                current = create.group(1)
                tables.setdefault(current, {})
                continue
            if current is not None:
                if line.strip().startswith(")"):
                    current = None
                    continue
                column = column_re.match(line)
                if column is not None:
                    tables[current][column.group(1)] = column.group(2)
    return tables


def test_json_registry_matches_migration_ddl() -> None:
    """Every registered JSON column is declared TEXT in the SQLite DDL (the
    exact contract the Postgres dialect translation relies on)."""
    ddl = _ddl_columns()
    for table, columns in JSON_COLUMNS.items():
        assert table in ddl, f"JSON registry table {table} not in migrations"
        for column in columns:
            declared = ddl[table].get(column)
            assert declared == "TEXT", (
                f"{table}.{column} registered as JSON but declared "
                f"{declared!r} (must be TEXT for the dialect translation)"
            )


def test_tenant_registry_matches_migration_ddl() -> None:
    """Every registered tenant table declares its tenant column; every
    parent-link child table exists with its FK column."""
    ddl = _ddl_columns()
    for table, tenant_col in TENANT_TABLES.items():
        assert table in ddl, f"tenant registry table {table} not in migrations"
        assert tenant_col in ddl[table], (
            f"{table} is tenant-scoped by {tenant_col} but the column is "
            "not in the DDL"
        )
    for table, (parent, fk, tenant_col) in PARENT_LINKS.items():
        assert table in ddl and fk in ddl[table]
        assert parent in ddl and tenant_col in ddl[parent]


def test_directive_section11_minimum_tables_exist() -> None:
    """The §11 minimum relational model exists as tables (the PUB-01/PUB-05
    name mapping: §11 'architecture_memory' is served by memory_entries —
    the §C.3 MemoryEntry wire DTO, PUB-01 reviewed naming)."""
    ddl = _ddl_columns()
    directive_section11 = {
        "users", "workspaces", "workspace_members",
        "missions", "mission_revisions",
        "value_models", "value_model_revisions",
        "contexts",
        "systems", "system_revisions",
        "architecture_nodes", "architecture_edges",
        "evidence", "evidence_artifacts",
        "hypotheses", "causal_hypotheses",
        "candidates", "candidate_evaluations",
        "assurance_runs", "assurance_results",
        "decisions", "authorizations",
        "experiments", "experiment_events",
        "execution_requests", "execution_receipts",
        "learning_records", "memory_entries",  # §11 architecture_memory
        "jobs", "audit_events", "provider_events",
    }
    missing = directive_section11 - set(ddl)
    assert not missing, f"§11 minimum tables missing: {sorted(missing)}"


# ---------------------------------------------------------------------------
# Doc-column ↔ normalized-rows equivalence over the FULL demo dataset
# (SQLite side; PostgreSQL side in test_pub05_postgres_parity.py)
# ---------------------------------------------------------------------------

def _seeded_sqlite() -> LocalSqlitePersistence:
    persistence = LocalSqlitePersistence(
        tempfile.mktemp(suffix=".sqlite3")
    )
    persistence.migrate()
    seed_demo(persistence)
    return persistence


def test_demo_dataset_doc_rows_equivalence_sqlite() -> None:
    persistence = _seeded_sqlite()
    try:
        scope = TenantScope(workspace_ids=frozenset({"ws-demo"}))
        # graph: doc column == reassembled from architecture rows
        for revision in (
            persistence.get_system_revision(scope, "sysrev-demo-1"),
            persistence.get_system_revision(scope, "sysrev-demo-2"),
        ):
            assert revision is not None
            node_rows = [
                decode_row("architecture_nodes", dict(r)) for r in
                persistence._fetchall(
                    "SELECT * FROM architecture_nodes WHERE "
                    "system_revision_id = ? ORDER BY position",
                    (revision["id"],),
                )
            ]
            edge_rows = [
                decode_row("architecture_edges", dict(r)) for r in
                persistence._fetchall(
                    "SELECT * FROM architecture_edges WHERE "
                    "system_revision_id = ? ORDER BY position",
                    (revision["id"],),
                )
            ]
            contract_rows = [
                decode_row("architecture_boundary_contracts", dict(r)) for r in
                persistence._fetchall(
                    "SELECT * FROM architecture_boundary_contracts WHERE "
                    "system_revision_id = ? ORDER BY position",
                    (revision["id"],),
                )
            ]
            assert rows_to_graph(node_rows, edge_rows, contract_rows) == (
                revision["graph"]
            )

        # candidate evaluations: doc column == reassembled from rows
        for candidate in persistence.list_candidates(
            scope, workspace_id=None, cursor=None, limit=50
        ).items:
            rows = [
                decode_row("candidate_evaluations", dict(r)) for r in
                persistence._fetchall(
                    "SELECT * FROM candidate_evaluations WHERE "
                    "candidate_id = ?", (candidate["id"],),
                )
            ]
            assert rows_to_evaluation(rows) == candidate["evaluation"]

        # assurance gates: checks doc gates == rows
        for run in persistence.list_assurance(
            scope, workspace_id=None, candidate_id=None, cursor=None, limit=50
        ).items:
            rows = [
                decode_row("assurance_results", dict(r)) for r in
                persistence._fetchall(
                    "SELECT * FROM assurance_results WHERE "
                    "assurance_run_id = ?", (run["id"],),
                )
            ]
            assert rows_to_gates(rows) == run["checks"]["gates"]

        # experiment events: events doc == rows
        experiment = persistence.get_experiment(scope, "exp-demo-cache")
        assert experiment is not None
        rows = [
            decode_row("experiment_events", dict(r)) for r in
            persistence._fetchall(
                "SELECT * FROM experiment_events WHERE experiment_id = ?",
                ("exp-demo-cache",),
            )
        ]
        assert rows_to_events(rows) == experiment["events"]["events"]

        # execution receipt: receipt doc == reassembled receipt row
        execution = persistence.get_execution(scope, "exec-demo-1")
        assert execution is not None
        receipt_rows = [
            decode_row("execution_receipts", dict(r)) for r in
            persistence._fetchall(
                "SELECT * FROM execution_receipts WHERE execution_id = ?",
                ("exec-demo-1",),
            )
        ]
        assert len(receipt_rows) == 1
        assert rows_to_receipt(receipt_rows[0]) == execution["receipt"]
        request_rows = persistence._fetchall(
            "SELECT * FROM execution_requests WHERE execution_id = ?",
            ("exec-demo-1",),
        )
        assert len(request_rows) == 1

        # evidence artifact: one row per evidence carrying an artifactRef
        evidence = persistence.list_evidence(
            scope, workspace_id=None, system_id=None, kind=None,
            status=None, cursor=None, limit=100,
        ).items
        with_ref = [e for e in evidence if e.get("artifact_ref")]
        artifact_rows = persistence._fetchall(
            "SELECT * FROM evidence_artifacts"
        )
        assert len(artifact_rows) == len(with_ref)

        # causal hypotheses: one row per hypothesis with a causal claim
        hypotheses = persistence.list_hypotheses(
            scope, workspace_id=None, cursor=None, limit=50
        ).items
        causal_rows = persistence._fetchall(
            "SELECT * FROM causal_hypotheses"
        )
        assert len(causal_rows) == len(hypotheses)
    finally:
        persistence.close()


def test_demo_dataset_normalized_projection_counts_sqlite() -> None:
    persistence = _seeded_sqlite()
    try:
        def count(sql: str) -> int:
            row = persistence._fetchone(sql)
            return int(row[0]) if row else 0

        # 2 recovered revisions of the demo system
        assert count(
            "SELECT COUNT(*) FROM architecture_nodes WHERE "
            "system_revision_id = 'sysrev-demo-1'"
        ) > 0
        assert count(
            "SELECT COUNT(*) FROM architecture_nodes WHERE "
            "system_revision_id = 'sysrev-demo-2'"
        ) > 0
        # 2 candidates × (3 objectives + 2 pareto points)
        assert count("SELECT COUNT(*) FROM candidate_evaluations") == 10
        # execution receipt row carries the demo flag + SUCCESS state
        row = persistence._fetchone(
            "SELECT outcome_state, demo FROM execution_receipts "
            "WHERE execution_id = 'exec-demo-1'"
        )
        assert row["outcome_state"] == "SUCCESS"
        assert row["demo"] == 1
    finally:
        persistence.close()
