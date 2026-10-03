"""The provider-neutral persistence seam (PUBLIC-DEPLOYMENT-CONTRACT §B/§C).

Design rules (binding):

- **Tenant scoping is enforced HERE, in the adapter — never per-route**
  (SECURITY S5): every read/write method takes a :class:`TenantScope`
  describing the workspaces the caller may touch, and the implementation
  adds the scope filter to every query. Cross-tenant requests return zero
  rows; the routes layer turns that into 404/403.
- Rows are plain ``dict`` payloads shaped for the wire DTOs (``services/api/
  schemas`` owns the wire shapes); mapping rows ↔ ``sos.*`` domain objects
  happens in ``services/api/orchestration.py`` (mapping only — semantics stay
  in ``src/sos``).
- Cursor pagination is deterministic: ordering by ``(created_at, id)`` with an
  opaque cursor; the adapter never leaks tenant-crossing rows into a page.
- Truth states on stored ``status`` columns are the frozen six-state
  vocabulary (``sos.model.TruthState``) and are NEVER rewritten by the seam.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class SeamHealth:
    """Truthful health of one provider seam (never a fake ok)."""

    status: str  # a sos.model.TruthState value, reported verbatim
    detail: str


@dataclass(frozen=True)
class TenantScope:
    """The set of workspaces a request may touch.

    Derived ALWAYS from the server-side session (never from the browser —
    SECURITY threat notes / directive §6). ``workspace_ids`` is the exact
    allowlist; ``anonymous`` marks the read-only demo scope.
    """

    workspace_ids: frozenset[str]
    anonymous: bool = False
    user_id: str | None = None

    def allows(self, workspace_id: str) -> bool:
        return workspace_id in self.workspace_ids


@dataclass(frozen=True)
class Page:
    """One cursor-paginated collection page (contract §C.2 envelope input)."""

    items: tuple[dict[str, Any], ...]
    next_cursor: str | None


class ConflictError(Exception):
    """Raised when an insert violates a uniqueness invariant (409 CONFLICT).

    Shared by BOTH persistence implementations (SQLite LOCAL / Neon
    PostgreSQL — PUB-05); re-exported from ``providers.neon.local`` for the
    existing import sites (routes wire it to the ``CONFLICT`` error code)."""


class PersistencePort(Protocol):
    """The provider-neutral persistence interface (LOCAL SQLite now, Neon in
    PUB-05 — same interface, tenant scoping enforced in the adapter)."""

    mode: str
    implementation: str

    def health_check(self) -> SeamHealth: ...

    # -- lifecycle ---------------------------------------------------------
    def migrate(self) -> list[str]: ...
    def is_seeded(self) -> bool: ...
    def seed_demo(self, seed_fn: Any) -> None: ...

    # -- users / membership (session-backed, LOCAL stub identities) -------
    def upsert_user(self, *, user_id: str, github_id: str, login: str,
                    display_name: str, created_at: str) -> dict[str, Any]: ...
    def get_user(self, user_id: str) -> dict[str, Any] | None: ...
    def workspaces_for_user(self, user_id: str) -> tuple[dict[str, Any], ...]: ...
    def demo_workspace(self) -> dict[str, Any] | None: ...

    # -- workspaces --------------------------------------------------------
    def list_workspaces(self, scope: TenantScope, *, cursor: str | None,
                        limit: int) -> Page: ...
    def get_workspace(self, scope: TenantScope, workspace_id: str) -> dict[str, Any] | None: ...
    def create_workspace(self, *, workspace_id: str, name: str, slug: str,
                         owner_user_id: str, is_demo: bool,
                         created_at: str) -> dict[str, Any]: ...
    def list_workspace_activity(self, scope: TenantScope, workspace_id: str,
                                *, limit: int) -> tuple[dict[str, Any], ...]: ...

    # -- missions ----------------------------------------------------------
    def list_missions(self, scope: TenantScope, *, workspace_id: str | None,
                      cursor: str | None, limit: int) -> Page: ...
    def get_mission(self, scope: TenantScope, mission_id: str) -> dict[str, Any] | None: ...
    def insert_mission(self, *, workspace_id: str, mission_id: str, title: str,
                       status: str, current_revision_id: str | None,
                       created_at: str) -> dict[str, Any]: ...
    def list_mission_revisions(self, scope: TenantScope, mission_id: str,
                               *, cursor: str | None, limit: int) -> Page: ...
    def get_mission_revision(self, scope: TenantScope,
                             revision_id: str) -> dict[str, Any] | None: ...
    def insert_mission_revision(self, *, mission_id: str, revision_id: str,
                                revision: int, payload: dict[str, Any],
                                created_at: str, set_current: bool) -> dict[str, Any]: ...

    # -- systems -----------------------------------------------------------
    def list_systems(self, scope: TenantScope, *, workspace_id: str | None,
                     cursor: str | None, limit: int) -> Page: ...
    def get_system(self, scope: TenantScope, system_id: str) -> dict[str, Any] | None: ...
    def get_system_revision(self, scope: TenantScope,
                            revision_id: str) -> dict[str, Any] | None: ...
    def insert_system(self, *, workspace_id: str, system_id: str, name: str,
                      mode: str, current_revision_id: str | None,
                      created_at: str) -> dict[str, Any]: ...
    def insert_system_revision(self, *, system_id: str, revision_id: str,
                               revision: int, payload: dict[str, Any],
                               created_at: str, set_current: bool) -> dict[str, Any]: ...

    # -- evidence ----------------------------------------------------------
    def list_evidence(self, scope: TenantScope, *, workspace_id: str | None,
                      system_id: str | None, kind: str | None,
                      status: str | None, cursor: str | None,
                      limit: int) -> Page: ...
    def insert_evidence(self, *, workspace_id: str, evidence_id: str,
                        payload: dict[str, Any]) -> dict[str, Any]: ...

    # -- hypotheses / candidates / assurance -------------------------------
    def list_hypotheses(self, scope: TenantScope, *, workspace_id: str | None,
                        cursor: str | None, limit: int) -> Page: ...
    def insert_hypothesis(self, *, workspace_id: str, hypothesis_id: str,
                          payload: dict[str, Any]) -> dict[str, Any]: ...
    def list_candidates(self, scope: TenantScope, *, workspace_id: str | None,
                        cursor: str | None, limit: int) -> Page: ...
    def insert_candidate(self, *, workspace_id: str, candidate_id: str,
                         payload: dict[str, Any]) -> dict[str, Any]: ...
    def get_candidate(self, scope: TenantScope,
                      candidate_id: str) -> dict[str, Any] | None: ...
    def list_assurance(self, scope: TenantScope, *, workspace_id: str | None,
                        candidate_id: str | None, cursor: str | None,
                        limit: int) -> Page: ...
    def insert_assurance(self, *, workspace_id: str, assurance_id: str,
                         payload: dict[str, Any]) -> dict[str, Any]: ...
    def get_assurance(self, scope: TenantScope,
                      assurance_id: str) -> dict[str, Any] | None: ...

    # -- decisions / authorizations ----------------------------------------
    def list_decisions(self, scope: TenantScope, *, workspace_id: str | None,
                       cursor: str | None, limit: int) -> Page: ...
    def insert_decision(self, *, workspace_id: str, decision_id: str,
                        payload: dict[str, Any]) -> dict[str, Any]: ...
    def get_decision(self, scope: TenantScope,
                     decision_id: str) -> dict[str, Any] | None: ...
    def list_authorizations(self, scope: TenantScope, *, workspace_id: str | None,
                            cursor: str | None, limit: int) -> Page: ...
    def insert_authorization(self, *, workspace_id: str,
                             authorization_id: str,
                             payload: dict[str, Any]) -> dict[str, Any]: ...

    # -- experiments / executions ------------------------------------------
    def list_experiments(self, scope: TenantScope, *, workspace_id: str | None,
                         candidate_id: str | None, cursor: str | None,
                         limit: int) -> Page: ...
    def insert_experiment(self, *, workspace_id: str, experiment_id: str,
                          payload: dict[str, Any]) -> dict[str, Any]: ...
    def get_experiment(self, scope: TenantScope,
                       experiment_id: str) -> dict[str, Any] | None: ...
    def list_executions(self, scope: TenantScope, *, workspace_id: str | None,
                        experiment_id: str | None, cursor: str | None,
                        limit: int) -> Page: ...
    def insert_execution(self, *, workspace_id: str, execution_id: str,
                         payload: dict[str, Any]) -> dict[str, Any]: ...
    def get_execution(self, scope: TenantScope,
                      execution_id: str) -> dict[str, Any] | None: ...

    # -- learning / memory --------------------------------------------------
    def list_learning(self, scope: TenantScope, *, workspace_id: str | None,
                      cursor: str | None, limit: int) -> Page: ...
    def insert_learning(self, *, workspace_id: str, record_id: str,
                        payload: dict[str, Any]) -> dict[str, Any]: ...
    def list_memory(self, scope: TenantScope, *, workspace_id: str | None,
                    cursor: str | None, limit: int) -> Page: ...
    def insert_memory(self, *, workspace_id: str, entry_id: str,
                      payload: dict[str, Any]) -> dict[str, Any]: ...

    # -- jobs ---------------------------------------------------------------
    def list_jobs(self, scope: TenantScope, *, workspace_id: str | None,
                  type_: str | None, cursor: str | None, limit: int) -> Page: ...
    def get_job(self, scope: TenantScope, job_id: str) -> dict[str, Any] | None: ...
    def get_job_by_idempotency_key(self, scope: TenantScope,
                                   key: str) -> dict[str, Any] | None: ...
    def insert_job(self, *, workspace_id: str, job_id: str,
                   payload: dict[str, Any]) -> dict[str, Any]: ...
    def update_job(self, scope: TenantScope, job_id: str,
                   *, payload_patch: dict[str, Any]) -> dict[str, Any] | None: ...

    # -- audit (append-only; every mutation writes one row — S17) -----------
    def append_audit(self, *, tenant_id: str, actor: str, action: str,
                     target: str, meta: dict[str, Any],
                     ts: str, audit_id: str) -> dict[str, Any]: ...
