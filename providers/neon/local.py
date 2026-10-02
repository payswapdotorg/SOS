"""LOCAL persistence adapter: SQLite via the ``db/``-managed schema (PUB-01).

Truth rules enforced here:

- tenant scoping in EVERY query (SECURITY S5) — the ``TenantScope`` allowlist
  is applied inside this adapter, so a cross-tenant id yields zero rows;
- stored ``status`` truth states are passed through verbatim (six-state
  vocabulary; no conversion anywhere in the seam);
- cursor pagination is deterministic (``ORDER BY created_at, id``).
"""
from __future__ import annotations

import base64
import json
import sqlite3
import sys
import threading
from pathlib import Path
from typing import Any

from .seam import Page, SeamHealth, TenantScope

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from db.runner import migrate_down, migrate_up  # noqa: E402

_JSON_COLUMNS: dict[str, frozenset[str]] = {
    "mission_revisions": frozenset({
        "goals", "outcomes", "stakeholders", "measures", "constraints",
        "preferences", "approval",
    }),
    "system_revisions": frozenset({
        "uncertainty", "source_ref", "recovery", "graph",
    }),
    "evidence": frozenset({"provenance", "result"}),
    "hypotheses": frozenset({"causal", "evidence_refs"}),
    "candidates": frozenset({
        "subgraph_replacement", "effects", "costs", "risks", "constraints",
        "evidence_refs", "reversibility", "evaluation",
    }),
    "assurance_runs": frozenset({"checks"}),
    "decisions": frozenset({
        "evidence_refs", "authority_snapshot", "expected_impact",
        "reversibility", "required_approvals", "ask_payload",
    }),
    "experiments": frozenset({"events"}),
    "executions": frozenset({"receipt", "artifact_refs"}),
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
}

# Tables whose rows carry a tenant (workspace) column — scope-filtered reads.
_TENANT_TABLES: dict[str, str] = {
    "workspaces": "id",
    "missions": "workspace_id",
    "mission_revisions": "mission_id",
    "systems": "workspace_id",
    "system_revisions": "system_id",
    "evidence": "workspace_id",
    "hypotheses": "workspace_id",
    "candidates": "workspace_id",
    "assurance_runs": "workspace_id",
    "decisions": "workspace_id",
    "authorizations": "workspace_id",
    "experiments": "workspace_id",
    "executions": "workspace_id",
    "learning_records": "workspace_id",
    "memory_entries": "workspace_id",
    "jobs": "tenant_id",
}

# Child tables joined through their parent for scope resolution.
_PARENT_LINKS: dict[str, tuple[str, str, str]] = {
    "mission_revisions": ("missions", "mission_id", "workspace_id"),
    "system_revisions": ("systems", "system_id", "workspace_id"),
}


def encode_cursor(created_at: str, entity_id: str) -> str:
    raw = f"{created_at}|{entity_id}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, str] | None:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        created_at, _, entity_id = raw.partition("|")
        if not created_at or not entity_id:
            return None
        return created_at, entity_id
    except (ValueError, UnicodeDecodeError):
        return None


class LocalSqlitePersistence:
    """The LOCAL persistence implementation of the provider-neutral seam."""

    mode = "local"
    implementation = "sqlite"

    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self._db_path), check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.commit()

    # -- helpers -----------------------------------------------------------

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _exec(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        with self._lock:
            self._conn.execute(sql, params)
            self._conn.commit()

    def _fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def _fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def _row_to_dict(self, table: str, row: sqlite3.Row) -> dict[str, Any]:
        item: dict[str, Any] = {}
        json_cols = _JSON_COLUMNS.get(table, frozenset())
        for key in row.keys():
            value = row[key]
            if key in json_cols and isinstance(value, str):
                item[key] = json.loads(value)
            else:
                item[key] = value
        return item

    def _scope_clause(self, table: str, scope: TenantScope) -> tuple[str, tuple[str, ...]]:
        """The tenant-scope WHERE fragment for a tenant table (S5)."""
        if table == "workspaces":
            marks = ",".join("?" for _ in scope.workspace_ids) or "''"
            clause = f"workspaces.id IN ({marks})"
            return clause, tuple(sorted(scope.workspace_ids))
        if table in _PARENT_LINKS:
            parent, fk, tenant_col = _PARENT_LINKS[table]
            marks = ",".join("?" for _ in scope.workspace_ids) or "''"
            clause = (
                f"{table}.{fk} IN (SELECT id FROM {parent} WHERE {tenant_col} "
                f"IN ({marks}))"
            )
            return clause, tuple(sorted(scope.workspace_ids))
        tenant_col = _TENANT_TABLES[table]
        marks = ",".join("?" for _ in scope.workspace_ids) or "''"
        clause = f"{table}.{tenant_col} IN ({marks})"
        return clause, tuple(sorted(scope.workspace_ids))

    def _paginate(
        self,
        table: str,
        scope: TenantScope,
        *,
        extra_where: str = "",
        extra_params: tuple[Any, ...] = (),
        cursor: str | None,
        limit: int,
    ) -> Page:
        scope_clause, scope_params = self._scope_clause(table, scope)
        where = [scope_clause]
        params: list[Any] = list(scope_params)
        if extra_where:
            where.append(extra_where)
            params.extend(extra_params)
        if cursor is not None:
            decoded = decode_cursor(cursor)
            if decoded is None:
                raise ValueError("invalid cursor")
            where.append("(created_at, id) > (?, ?)")
            params.extend(decoded)
        sql = (
            f"SELECT * FROM {table} WHERE "
            + " AND ".join(where)
            + " ORDER BY created_at ASC, id ASC LIMIT ?"
        )
        params.append(limit + 1)
        rows = self._fetchall(sql, tuple(params))
        items = tuple(self._row_to_dict(table, r) for r in rows[:limit])
        next_cursor = None
        if len(rows) > limit and items:
            last = items[-1]
            next_cursor = encode_cursor(str(last["created_at"]), str(last["id"]))
        return Page(items=items, next_cursor=next_cursor)

    # -- lifecycle ---------------------------------------------------------

    def health_check(self) -> SeamHealth:
        try:
            row = self._fetchone("SELECT COUNT(*) AS n FROM workspaces")
            detail = f"sqlite ok ({row['n'] if row else 0} workspaces) at {self._db_path.name}"
            return SeamHealth(status="SUCCESS", detail=detail)
        except sqlite3.Error as exc:  # truthful failure, never a fake ok
            return SeamHealth(status="FAILED", detail=f"sqlite check failed: {exc}")

    def migrate(self) -> list[str]:
        with self._lock:
            return migrate_up(self._conn)

    def migrate_down(self, target: int = 0) -> list[str]:
        with self._lock:
            return migrate_down(self._conn, target)

    def is_seeded(self) -> bool:
        row = self._fetchone("SELECT COUNT(*) AS n FROM workspaces WHERE is_demo = 1")
        return bool(row and row["n"] > 0)

    def seed_demo(self, seed_fn: Any) -> None:
        seed_fn(self)

    # -- users / membership -------------------------------------------------

    def upsert_user(self, *, user_id: str, github_id: str, login: str,
                    display_name: str, created_at: str) -> dict[str, Any]:
        existing = self._fetchone(
            "SELECT * FROM users WHERE id = ? OR github_id = ?", (user_id, github_id)
        )
        if existing is not None:
            self._exec(
                "UPDATE users SET login = ?, display_name = ? WHERE id = ?",
                (login, display_name, existing["id"]),
            )
            row = self._fetchone("SELECT * FROM users WHERE id = ?", (existing["id"],))
            assert row is not None
            return self._row_to_dict("users", row)
        self._exec(
            "INSERT INTO users (id, github_id, login, display_name, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, github_id, login, display_name, created_at),
        )
        row = self._fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
        assert row is not None
        return self._row_to_dict("users", row)

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        row = self._fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
        return self._row_to_dict("users", row) if row else None

    def workspaces_for_user(self, user_id: str) -> tuple[dict[str, Any], ...]:
        rows = self._fetchall(
            "SELECT w.* FROM workspaces w JOIN workspace_members m "
            "ON m.workspace_id = w.id WHERE m.user_id = ? ORDER BY w.created_at, w.id",
            (user_id,),
        )
        return tuple(self._row_to_dict("workspaces", r) for r in rows)

    def demo_workspace(self) -> dict[str, Any] | None:
        row = self._fetchone("SELECT * FROM workspaces WHERE is_demo = 1")
        return self._row_to_dict("workspaces", row) if row else None

    # -- workspaces ----------------------------------------------------------

    def list_workspaces(self, scope: TenantScope, *, cursor: str | None,
                        limit: int) -> Page:
        return self._paginate("workspaces", scope, cursor=cursor, limit=limit)

    def get_workspace(self, scope: TenantScope, workspace_id: str) -> dict[str, Any] | None:
        if not scope.allows(workspace_id):
            return None
        row = self._fetchone("SELECT * FROM workspaces WHERE id = ?", (workspace_id,))
        return self._row_to_dict("workspaces", row) if row else None

    def create_workspace(self, *, workspace_id: str, name: str, slug: str,
                         owner_user_id: str, is_demo: bool,
                         created_at: str) -> dict[str, Any]:
        clash = self._fetchone("SELECT id FROM workspaces WHERE slug = ?", (slug,))
        if clash is not None:
            raise ConflictError(f"workspace slug '{slug}' already exists")
        self._exec(
            "INSERT INTO workspaces (id, name, slug, is_demo, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (workspace_id, name, slug, 1 if is_demo else 0, created_at),
        )
        self._exec(
            "INSERT INTO workspace_members (workspace_id, user_id, role, created_at) "
            "VALUES (?, ?, 'owner', ?)",
            (workspace_id, owner_user_id, created_at),
        )
        row = self._fetchone("SELECT * FROM workspaces WHERE id = ?", (workspace_id,))
        assert row is not None
        return self._row_to_dict("workspaces", row)

    def list_workspace_activity(self, scope: TenantScope, workspace_id: str,
                                *, limit: int) -> tuple[dict[str, Any], ...]:
        if not scope.allows(workspace_id):
            return ()
        rows = self._fetchall(
            "SELECT * FROM audit_events WHERE tenant_id = ? "
            "ORDER BY ts DESC, id DESC LIMIT ?",
            (workspace_id, limit),
        )
        return tuple(self._row_to_dict("audit_events", r) for r in rows)

    # -- missions --------------------------------------------------------------

    def list_missions(self, scope: TenantScope, *, workspace_id: str | None,
                      cursor: str | None, limit: int) -> Page:
        extra, params = "", ()
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra, params = "missions.workspace_id = ?", (workspace_id,)
        return self._paginate("missions", scope, extra_where=extra,
                              extra_params=params, cursor=cursor, limit=limit)

    def get_mission(self, scope: TenantScope, mission_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT * FROM missions WHERE missions.id = ? AND " + self._scope_clause("missions", scope)[0],
            (mission_id,) + self._scope_clause("missions", scope)[1],
        )
        return self._row_to_dict("missions", row) if row else None

    def insert_mission(self, *, workspace_id: str, mission_id: str, title: str,
                       status: str, current_revision_id: str | None,
                       created_at: str) -> dict[str, Any]:
        self._exec(
            "INSERT INTO missions (id, workspace_id, title, status, "
            "current_revision_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (mission_id, workspace_id, title, status, current_revision_id, created_at),
        )
        row = self._fetchone("SELECT * FROM missions WHERE id = ?", (mission_id,))
        assert row is not None
        return self._row_to_dict("missions", row)

    def list_mission_revisions(self, scope: TenantScope, mission_id: str,
                               *, cursor: str | None, limit: int) -> Page:
        parent = self.get_mission(scope, mission_id)
        if parent is None:
            return Page(items=(), next_cursor=None)
        return self._paginate(
            "mission_revisions", scope,
            extra_where="mission_revisions.mission_id = ?",
            extra_params=(mission_id,), cursor=cursor, limit=limit,
        )

    def get_mission_revision(self, scope: TenantScope,
                             revision_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT * FROM mission_revisions WHERE mission_revisions.id = ? AND "
            + self._scope_clause("mission_revisions", scope)[0],
            (revision_id,) + self._scope_clause("mission_revisions", scope)[1],
        )
        return self._row_to_dict("mission_revisions", row) if row else None

    def insert_mission_revision(self, *, mission_id: str, revision_id: str,
                                revision: int, payload: dict[str, Any],
                                created_at: str, set_current: bool) -> dict[str, Any]:
        cols = _JSON_COLUMNS["mission_revisions"]
        stored = {k: json.dumps(v, sort_keys=True) if k in cols else v
                  for k, v in payload.items()}
        self._exec(
            "INSERT INTO mission_revisions (id, mission_id, revision, goals, "
            "outcomes, stakeholders, measures, constraints, preferences, "
            "approval, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (revision_id, mission_id, revision, stored["goals"],
             stored["outcomes"], stored["stakeholders"], stored["measures"],
             stored["constraints"], stored["preferences"], stored["approval"],
             created_at),
        )
        if set_current:
            self._exec(
                "UPDATE missions SET current_revision_id = ? WHERE id = ?",
                (revision_id, mission_id),
            )
        row = self._fetchone(
            "SELECT * FROM mission_revisions WHERE id = ?", (revision_id,)
        )
        assert row is not None
        return self._row_to_dict("mission_revisions", row)

    # -- systems ---------------------------------------------------------------

    def list_systems(self, scope: TenantScope, *, workspace_id: str | None,
                     cursor: str | None, limit: int) -> Page:
        extra, params = "", ()
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra, params = "systems.workspace_id = ?", (workspace_id,)
        return self._paginate("systems", scope, extra_where=extra,
                              extra_params=params, cursor=cursor, limit=limit)

    def get_system(self, scope: TenantScope, system_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT * FROM systems WHERE systems.id = ? AND "
            + self._scope_clause("systems", scope)[0],
            (system_id,) + self._scope_clause("systems", scope)[1],
        )
        return self._row_to_dict("systems", row) if row else None

    def get_system_revision(self, scope: TenantScope,
                            revision_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT * FROM system_revisions WHERE system_revisions.id = ? AND "
            + self._scope_clause("system_revisions", scope)[0],
            (revision_id,) + self._scope_clause("system_revisions", scope)[1],
        )
        return self._row_to_dict("system_revisions", row) if row else None

    def insert_system(self, *, workspace_id: str, system_id: str, name: str,
                      mode: str, current_revision_id: str | None,
                      created_at: str) -> dict[str, Any]:
        self._exec(
            "INSERT INTO systems (id, workspace_id, name, mode, "
            "current_revision_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (system_id, workspace_id, name, mode, current_revision_id, created_at),
        )
        row = self._fetchone("SELECT * FROM systems WHERE id = ?", (system_id,))
        assert row is not None
        return self._row_to_dict("systems", row)

    def insert_system_revision(self, *, system_id: str, revision_id: str,
                               revision: int, payload: dict[str, Any],
                               created_at: str, set_current: bool) -> dict[str, Any]:
        self._exec(
            "INSERT INTO system_revisions (id, system_id, revision, "
            "state_summary, uncertainty, source_ref, recovery, graph, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (revision_id, system_id, revision, payload["stateSummary"],
             json.dumps(payload["uncertainty"], sort_keys=True),
             json.dumps(payload["sourceRef"], sort_keys=True),
             json.dumps(payload["recovery"], sort_keys=True),
             json.dumps(payload["graph"], sort_keys=True),
             created_at),
        )
        if set_current:
            self._exec(
                "UPDATE systems SET current_revision_id = ? WHERE id = ?",
                (revision_id, system_id),
            )
        row = self._fetchone(
            "SELECT * FROM system_revisions WHERE id = ?", (revision_id,)
        )
        assert row is not None
        return self._row_to_dict("system_revisions", row)

    # -- evidence ----------------------------------------------------------------

    def list_evidence(self, scope: TenantScope, *, workspace_id: str | None,
                      system_id: str | None, kind: str | None,
                      status: str | None, cursor: str | None,
                      limit: int) -> Page:
        extra: list[str] = []
        params: list[Any] = []
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra.append("evidence.workspace_id = ?")
            params.append(workspace_id)
        if system_id is not None:
            extra.append("evidence.system_id = ?")
            params.append(system_id)
        if kind is not None:
            extra.append("evidence.kind = ?")
            params.append(kind)
        if status is not None:
            extra.append("evidence.status = ?")
            params.append(status)
        return self._paginate(
            "evidence", scope, extra_where=" AND ".join(extra),
            extra_params=tuple(params), cursor=cursor, limit=limit,
        )

    def insert_evidence(self, *, workspace_id: str, evidence_id: str,
                        payload: dict[str, Any]) -> dict[str, Any]:
        # Content-addressed evidence ids dedup identical ingestion (W4):
        # an identical record already present is returned unchanged —
        # identical evidence never duplicates.
        existing = self._fetchone(
            "SELECT * FROM evidence WHERE id = ?", (evidence_id,)
        )
        if existing is not None:
            return self._row_to_dict("evidence", existing)
        self._exec(
            "INSERT INTO evidence (id, workspace_id, system_id, kind, status, "
            "provenance, timestamp, source_revision, related_system_state, "
            "confidence, artifact_ref, created_at, result) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (evidence_id, workspace_id, payload.get("systemId"),
             payload["kind"], payload["status"],
             json.dumps(payload["provenance"], sort_keys=True),
             payload.get("timestamp"), payload.get("sourceRevision"),
             payload.get("relatedSystemState"), payload.get("confidence"),
             payload.get("artifactRef"), payload["createdAt"],
             json.dumps(payload["result"], sort_keys=True)
             if payload.get("result") is not None else None),
        )
        row = self._fetchone("SELECT * FROM evidence WHERE id = ?", (evidence_id,))
        assert row is not None
        return self._row_to_dict("evidence", row)

    # -- hypotheses / candidates / assurance --------------------------------------

    def list_hypotheses(self, scope: TenantScope, *, workspace_id: str | None,
                        cursor: str | None, limit: int) -> Page:
        extra, params = "", ()
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra, params = "hypotheses.workspace_id = ?", (workspace_id,)
        return self._paginate("hypotheses", scope, extra_where=extra,
                              extra_params=params, cursor=cursor, limit=limit)

    def insert_hypothesis(self, *, workspace_id: str, hypothesis_id: str,
                          payload: dict[str, Any]) -> dict[str, Any]:
        self._exec(
            "INSERT INTO hypotheses (id, workspace_id, statement, causal, "
            "evidence_refs, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (hypothesis_id, workspace_id, payload["statement"],
             json.dumps(payload["causal"], sort_keys=True),
             json.dumps(payload["evidenceRefs"], sort_keys=True),
             payload["status"], payload["createdAt"]),
        )
        row = self._fetchone("SELECT * FROM hypotheses WHERE id = ?", (hypothesis_id,))
        assert row is not None
        return self._row_to_dict("hypotheses", row)

    def list_candidates(self, scope: TenantScope, *, workspace_id: str | None,
                        cursor: str | None, limit: int) -> Page:
        extra, params = "", ()
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra, params = "candidates.workspace_id = ?", (workspace_id,)
        return self._paginate("candidates", scope, extra_where=extra,
                              extra_params=params, cursor=cursor, limit=limit)

    def insert_candidate(self, *, workspace_id: str, candidate_id: str,
                         payload: dict[str, Any]) -> dict[str, Any]:
        self._exec(
            "INSERT INTO candidates (id, workspace_id, name, "
            "subgraph_replacement, effects, costs, risks, constraints, "
            "evidence_refs, reversibility, evaluation, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (candidate_id, workspace_id, payload["name"],
             json.dumps(payload["subgraphReplacement"], sort_keys=True),
             json.dumps(payload["effects"], sort_keys=True),
             json.dumps(payload["costs"], sort_keys=True),
             json.dumps(payload["risks"], sort_keys=True),
             json.dumps(payload["constraints"], sort_keys=True),
             json.dumps(payload["evidenceRefs"], sort_keys=True),
             json.dumps(payload["reversibility"], sort_keys=True),
             json.dumps(payload["evaluation"], sort_keys=True),
             payload["createdAt"]),
        )
        row = self._fetchone("SELECT * FROM candidates WHERE id = ?", (candidate_id,))
        assert row is not None
        return self._row_to_dict("candidates", row)

    def get_candidate(self, scope: TenantScope,
                      candidate_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT * FROM candidates WHERE candidates.id = ? AND "
            + self._scope_clause("candidates", scope)[0],
            (candidate_id,) + self._scope_clause("candidates", scope)[1],
        )
        return self._row_to_dict("candidates", row) if row else None

    def list_assurance(self, scope: TenantScope, *, workspace_id: str | None,
                       candidate_id: str | None, cursor: str | None,
                       limit: int) -> Page:
        extra: list[str] = []
        params: list[Any] = []
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra.append("assurance_runs.workspace_id = ?")
            params.append(workspace_id)
        if candidate_id is not None:
            extra.append("assurance_runs.candidate_id = ?")
            params.append(candidate_id)
        return self._paginate(
            "assurance_runs", scope, extra_where=" AND ".join(extra),
            extra_params=tuple(params), cursor=cursor, limit=limit,
        )

    def insert_assurance(self, *, workspace_id: str, assurance_id: str,
                         payload: dict[str, Any]) -> dict[str, Any]:
        # The checks column carries the full assurance record: the wire gates
        # list under "gates" plus the domain reconstruction payload under
        # "domain" (impact/risk/reversibility/objectives/traceability) so the
        # W7→W8→W9 chain can be re-driven exactly from persisted rows.
        checks_doc = {
            "gates": payload["checks"],
            "domain": payload.get("domain", {}),
        }
        self._exec(
            "INSERT INTO assurance_runs (id, workspace_id, candidate_id, "
            "checks, verdict, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (assurance_id, workspace_id, payload["candidateId"],
             json.dumps(checks_doc, sort_keys=True),
             payload["verdict"], payload["createdAt"]),
        )
        row = self._fetchone("SELECT * FROM assurance_runs WHERE id = ?", (assurance_id,))
        assert row is not None
        return self._row_to_dict("assurance_runs", row)

    def get_assurance(self, scope: TenantScope,
                      assurance_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT * FROM assurance_runs WHERE assurance_runs.id = ? AND "
            + self._scope_clause("assurance_runs", scope)[0],
            (assurance_id,) + self._scope_clause("assurance_runs", scope)[1],
        )
        return self._row_to_dict("assurance_runs", row) if row else None

    # -- decisions / authorizations -------------------------------------------------

    def list_decisions(self, scope: TenantScope, *, workspace_id: str | None,
                       cursor: str | None, limit: int) -> Page:
        extra, params = "", ()
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra, params = "decisions.workspace_id = ?", (workspace_id,)
        return self._paginate("decisions", scope, extra_where=extra,
                              extra_params=params, cursor=cursor, limit=limit)

    def insert_decision(self, *, workspace_id: str, decision_id: str,
                        payload: dict[str, Any]) -> dict[str, Any]:
        self._exec(
            "INSERT INTO decisions (id, workspace_id, action, rationale, "
            "evidence_refs, authority_snapshot, expected_impact, risk, "
            "blast_radius, reversibility, required_approvals, ask_payload, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (decision_id, workspace_id, payload["action"], payload["rationale"],
             json.dumps(payload["evidenceRefs"], sort_keys=True),
             json.dumps(payload["authoritySnapshot"], sort_keys=True),
             json.dumps(payload["expectedImpact"], sort_keys=True),
             payload["risk"], payload["blastRadius"],
             json.dumps(payload["reversibility"], sort_keys=True),
             json.dumps(payload["requiredApprovals"], sort_keys=True),
             json.dumps(payload["askPayload"], sort_keys=True)
             if payload.get("askPayload") is not None else None,
             payload["createdAt"]),
        )
        row = self._fetchone("SELECT * FROM decisions WHERE id = ?", (decision_id,))
        assert row is not None
        return self._row_to_dict("decisions", row)

    def get_decision(self, scope: TenantScope,
                     decision_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT * FROM decisions WHERE decisions.id = ? AND "
            + self._scope_clause("decisions", scope)[0],
            (decision_id,) + self._scope_clause("decisions", scope)[1],
        )
        return self._row_to_dict("decisions", row) if row else None

    def list_authorizations(self, scope: TenantScope, *, workspace_id: str | None,
                            cursor: str | None, limit: int) -> Page:
        extra, params = "", ()
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra, params = "authorizations.workspace_id = ?", (workspace_id,)
        return self._paginate("authorizations", scope, extra_where=extra,
                              extra_params=params, cursor=cursor, limit=limit)

    def insert_authorization(self, *, workspace_id: str,
                             authorization_id: str,
                             payload: dict[str, Any]) -> dict[str, Any]:
        self._exec(
            "INSERT INTO authorizations (id, workspace_id, decision_id, "
            "principal, scope, decision, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (authorization_id, workspace_id, payload.get("decisionId"),
             payload["principal"], payload["scope"], payload["decision"],
             payload["createdAt"]),
        )
        row = self._fetchone(
            "SELECT * FROM authorizations WHERE id = ?", (authorization_id,)
        )
        assert row is not None
        return self._row_to_dict("authorizations", row)

    # -- experiments / executions ---------------------------------------------------

    def list_experiments(self, scope: TenantScope, *, workspace_id: str | None,
                         candidate_id: str | None, cursor: str | None,
                         limit: int) -> Page:
        extra: list[str] = []
        params: list[Any] = []
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra.append("experiments.workspace_id = ?")
            params.append(workspace_id)
        if candidate_id is not None:
            extra.append("experiments.candidate_id = ?")
            params.append(candidate_id)
        return self._paginate(
            "experiments", scope, extra_where=" AND ".join(extra),
            extra_params=tuple(params), cursor=cursor, limit=limit,
        )

    def insert_experiment(self, *, workspace_id: str, experiment_id: str,
                          payload: dict[str, Any]) -> dict[str, Any]:
        # The events column carries the wire event list under "events" plus
        # the domain reconstruction payload under "domain" (mode/scope/
        # observation window/stop conditions/rollback ref/traceability) so the
        # W8/W11 chain can be re-driven exactly from persisted rows.
        events_doc = {
            "events": payload["events"],
            "domain": payload.get("domain", {}),
        }
        self._exec(
            "INSERT INTO experiments (id, workspace_id, candidate_id, status, "
            "events, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (experiment_id, workspace_id, payload["candidateId"],
             payload["status"], json.dumps(events_doc, sort_keys=True),
             payload["createdAt"]),
        )
        row = self._fetchone("SELECT * FROM experiments WHERE id = ?", (experiment_id,))
        assert row is not None
        return self._row_to_dict("experiments", row)

    def get_experiment(self, scope: TenantScope,
                       experiment_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT * FROM experiments WHERE experiments.id = ? AND "
            + self._scope_clause("experiments", scope)[0],
            (experiment_id,) + self._scope_clause("experiments", scope)[1],
        )
        return self._row_to_dict("experiments", row) if row else None

    def list_executions(self, scope: TenantScope, *, workspace_id: str | None,
                        experiment_id: str | None, cursor: str | None,
                        limit: int) -> Page:
        extra: list[str] = []
        params: list[Any] = []
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra.append("executions.workspace_id = ?")
            params.append(workspace_id)
        if experiment_id is not None:
            extra.append("executions.experiment_id = ?")
            params.append(experiment_id)
        return self._paginate(
            "executions", scope, extra_where=" AND ".join(extra),
            extra_params=tuple(params), cursor=cursor, limit=limit,
        )

    def insert_execution(self, *, workspace_id: str, execution_id: str,
                         payload: dict[str, Any]) -> dict[str, Any]:
        # Content-addressed execution ids make re-dispatch of an IDENTICAL
        # governed request idempotent (directive §8: retries never duplicate
        # side effects): the existing row is returned unchanged.
        existing = self._fetchone(
            "SELECT * FROM executions WHERE id = ?", (execution_id,)
        )
        if existing is not None:
            return self._row_to_dict("executions", existing)
        self._exec(
            "INSERT INTO executions (id, workspace_id, experiment_id, "
            "provider, request_hash, receipt, artifact_refs, status, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (execution_id, workspace_id, payload.get("experimentId"),
             payload["provider"], payload["requestHash"],
             json.dumps(payload["receipt"], sort_keys=True)
             if payload.get("receipt") is not None else None,
             json.dumps(payload["artifactRefs"], sort_keys=True),
             payload["status"], payload["createdAt"]),
        )
        row = self._fetchone("SELECT * FROM executions WHERE id = ?", (execution_id,))
        assert row is not None
        return self._row_to_dict("executions", row)

    def get_execution(self, scope: TenantScope,
                      execution_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT * FROM executions WHERE executions.id = ? AND "
            + self._scope_clause("executions", scope)[0],
            (execution_id,) + self._scope_clause("executions", scope)[1],
        )
        return self._row_to_dict("executions", row) if row else None

    # -- learning / memory --------------------------------------------------------

    def list_learning(self, scope: TenantScope, *, workspace_id: str | None,
                      cursor: str | None, limit: int) -> Page:
        extra, params = "", ()
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra, params = "learning_records.workspace_id = ?", (workspace_id,)
        return self._paginate("learning_records", scope, extra_where=extra,
                              extra_params=params, cursor=cursor, limit=limit)

    def insert_learning(self, *, workspace_id: str, record_id: str,
                        payload: dict[str, Any]) -> dict[str, Any]:
        self._exec(
            "INSERT INTO learning_records (id, workspace_id, context, "
            "candidate, predicted_effects, actual_effects, uncertainty, "
            "verdict, lessons, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (record_id, workspace_id,
             json.dumps(payload["context"], sort_keys=True),
             payload["candidate"],
             json.dumps(payload["predictedEffects"], sort_keys=True),
             json.dumps(payload["actualEffects"], sort_keys=True),
             json.dumps(payload["uncertainty"], sort_keys=True),
             payload["verdict"],
             json.dumps(payload["lessons"], sort_keys=True),
             payload["createdAt"]),
        )
        row = self._fetchone(
            "SELECT * FROM learning_records WHERE id = ?", (record_id,)
        )
        assert row is not None
        return self._row_to_dict("learning_records", row)

    def list_memory(self, scope: TenantScope, *, workspace_id: str | None,
                    cursor: str | None, limit: int) -> Page:
        extra, params = "", ()
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra, params = "memory_entries.workspace_id = ?", (workspace_id,)
        return self._paginate("memory_entries", scope, extra_where=extra,
                              extra_params=params, cursor=cursor, limit=limit)

    def insert_memory(self, *, workspace_id: str, entry_id: str,
                      payload: dict[str, Any]) -> dict[str, Any]:
        self._exec(
            "INSERT INTO memory_entries (id, workspace_id, context, "
            "candidate, predicted_effects, actual_effects, uncertainty, "
            "verdict, lessons, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entry_id, workspace_id,
             json.dumps(payload["context"], sort_keys=True),
             payload["candidate"],
             json.dumps(payload["predictedEffects"], sort_keys=True),
             json.dumps(payload["actualEffects"], sort_keys=True),
             json.dumps(payload["uncertainty"], sort_keys=True),
             payload["verdict"],
             json.dumps(payload["lessons"], sort_keys=True),
             payload["createdAt"]),
        )
        row = self._fetchone("SELECT * FROM memory_entries WHERE id = ?", (entry_id,))
        assert row is not None
        return self._row_to_dict("memory_entries", row)

    # -- jobs ------------------------------------------------------------------------

    def list_jobs(self, scope: TenantScope, *, workspace_id: str | None,
                  type_: str | None, cursor: str | None, limit: int) -> Page:
        extra: list[str] = []
        params: list[Any] = []
        if workspace_id is not None:
            if not scope.allows(workspace_id):
                return Page(items=(), next_cursor=None)
            extra.append("jobs.tenant_id = ?")
            params.append(workspace_id)
        if type_ is not None:
            extra.append("jobs.type = ?")
            params.append(type_)
        return self._paginate(
            "jobs", scope, extra_where=" AND ".join(extra),
            extra_params=tuple(params), cursor=cursor, limit=limit,
        )

    def get_job(self, scope: TenantScope, job_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT * FROM jobs WHERE jobs.id = ? AND "
            + self._scope_clause("jobs", scope)[0],
            (job_id,) + self._scope_clause("jobs", scope)[1],
        )
        return self._row_to_dict("jobs", row) if row else None

    def get_job_by_idempotency_key(self, scope: TenantScope,
                                   key: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT * FROM jobs WHERE jobs.idempotency_key = ? AND "
            + self._scope_clause("jobs", scope)[0],
            (key,) + self._scope_clause("jobs", scope)[1],
        )
        return self._row_to_dict("jobs", row) if row else None

    def insert_job(self, *, workspace_id: str, job_id: str,
                   payload: dict[str, Any]) -> dict[str, Any]:
        self._exec(
            "INSERT INTO jobs (id, tenant_id, type, requested_by, "
            "authority_snapshot, input_hash, source_revision, provider, "
            "status, started_at, completed_at, receipt, artifact_refs, "
            "error_state, idempotency_key, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (job_id, workspace_id, payload["type"], payload["requestedBy"],
             json.dumps(payload["authoritySnapshot"], sort_keys=True),
             payload["inputHash"], payload["sourceRevision"],
             payload["provider"], payload["status"], payload.get("startedAt"),
             payload.get("completedAt"),
             json.dumps(payload["receipt"], sort_keys=True)
             if payload.get("receipt") is not None else None,
             json.dumps(payload["artifactRefs"], sort_keys=True),
             payload.get("errorState"), payload.get("idempotencyKey"),
             payload["createdAt"]),
        )
        row = self._fetchone("SELECT * FROM jobs WHERE id = ?", (job_id,))
        assert row is not None
        return self._row_to_dict("jobs", row)

    def update_job(self, scope: TenantScope, job_id: str,
                   *, payload_patch: dict[str, Any]) -> dict[str, Any] | None:
        current = self.get_job(scope, job_id)
        if current is None:
            return None
        cols = _JSON_COLUMNS["jobs"]
        assignments: list[str] = []
        params: list[Any] = []
        for key, value in payload_patch.items():
            snake = _snake(key)
            assignments.append(f"{snake} = ?")
            params.append(
                json.dumps(value, sort_keys=True) if snake in cols else value
            )
        if assignments:
            params.append(job_id)
            self._exec(
                f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ?",
                tuple(params),
            )
        row = self._fetchone("SELECT * FROM jobs WHERE id = ?", (job_id,))
        return self._row_to_dict("jobs", row) if row else None

    # -- audit ------------------------------------------------------------------------

    def append_audit(self, *, tenant_id: str, actor: str, action: str,
                     target: str, meta: dict[str, Any], ts: str,
                     audit_id: str) -> dict[str, Any]:
        # Audit events are append-only: repeated identical events are
        # distinct records, so a sequence suffix keeps the caller-supplied
        # content id unique per write.
        with self._lock:
            clash = self._fetchone(
                "SELECT id FROM audit_events WHERE id = ?", (audit_id,)
            )
            if clash is not None:
                seq = 0
                candidate = f"{audit_id}-{seq:04d}"
                while self._fetchone(
                    "SELECT id FROM audit_events WHERE id = ?", (candidate,)
                ) is not None:
                    seq += 1
                    candidate = f"{audit_id}-{seq:04d}"
                audit_id = candidate
        self._exec(
            "INSERT INTO audit_events (id, tenant_id, actor, action, target, "
            "meta, ts) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (audit_id, tenant_id, actor, action, target,
             json.dumps(meta, sort_keys=True), ts),
        )
        row = self._fetchone("SELECT * FROM audit_events WHERE id = ?", (audit_id,))
        assert row is not None
        return self._row_to_dict("audit_events", row)


class ConflictError(Exception):
    """Raised when an insert violates a uniqueness invariant (409 CONFLICT)."""


_SNAKE_OVERRIDES: dict[str, str] = {
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


def _snake(camel: str) -> str:
    if camel in _SNAKE_OVERRIDES:
        return _SNAKE_OVERRIDES[camel]
    out = "".join(("_" + ch.lower()) if ch.isupper() else ch for ch in camel)
    return out if out else camel
