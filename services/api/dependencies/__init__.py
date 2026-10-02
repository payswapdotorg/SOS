"""Request dependencies: session resolution, tenant scoping (ALWAYS from the
server-side session — directive §6/SECURITY S5), audit writing, pagination."""
from __future__ import annotations

import hashlib
from typing import Any, Callable

from fastapi import Depends, Request

from fastapi import Query

from ..auth.session import SessionIdentity, resolve_session
from ..container import ApiContainer
from ..errors import not_found, unauthenticated, validation
from providers.neon.seam import TenantScope  # noqa: E402  (repo-root import)


def get_container(request: Request) -> ApiContainer:
    return request.app.state.container


def get_session(
    request: Request, container: ApiContainer = Depends(get_container)
) -> SessionIdentity:
    return resolve_session(request, container.persistence)


def require_authenticated(
    session: SessionIdentity = Depends(get_session),
) -> SessionIdentity:
    """Mutations (outside the demo read surface) require a session identity
    (SECURITY S7 — fail-closed)."""
    if not session.authenticated:
        raise unauthenticated(
            "authentication required for mutations (anonymous access is "
            "read-only demo access)"
        )
    return session


def tenant_scope(
    session: SessionIdentity = Depends(get_session),
    container: ApiContainer = Depends(get_container),
) -> TenantScope:
    """The tenant allowlist, derived ONLY from the server-side session.

    Anonymous → the demo workspace (read-only, enforced per-route). A signed-in
    user → their member workspaces plus the demo workspace.
    """
    demo = container.persistence.demo_workspace()
    demo_id = str(demo["id"]) if demo else None
    if not session.authenticated:
        ids = {demo_id} if demo_id else set()
        return TenantScope(
            workspace_ids=frozenset(ids), anonymous=True, user_id=None
        )
    workspaces = container.persistence.workspaces_for_user(session.user_id)
    ids = {str(w["id"]) for w in workspaces}
    if demo_id:
        ids.add(demo_id)
    return TenantScope(
        workspace_ids=frozenset(ids), anonymous=False,
        user_id=session.user_id,
    )


def audit_writer(
    container: ApiContainer = Depends(get_container),
) -> Callable[..., Any]:
    """An append-only audit writer bound to the container's persistence."""

    def write(
        *, tenant_id: str, actor: str, action: str, target: str,
        meta: dict[str, Any] | None = None, ts: str,
    ) -> dict[str, Any]:
        import time

        if ts is None:
            ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        material = "|".join(
            [tenant_id, actor, action, target, ts, repr(meta or {})]
        )
        audit_id = "audit-" + hashlib.sha256(
            material.encode("utf-8")
        ).hexdigest()[:16]
        return container.persistence.append_audit(
            tenant_id=tenant_id, actor=actor, action=action, target=target,
            meta=meta or {}, ts=ts, audit_id=audit_id,
        )

    return write


def now_iso() -> str:
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def ensure_workspace_access(
    scope: TenantScope, workspace_id: str
) -> None:
    if not scope.allows(workspace_id):
        # Cross-tenant: 404 hides existence (zero rows already leaked none).
        raise not_found("workspace not found")


def cursor_param(
    cursor: str | None = Query(default=None),
) -> str | None:
    """Validate the opaque pagination cursor upfront (422 VALIDATION
    envelope for malformed cursors — never a raw 500)."""
    if cursor is None:
        return None
    from providers.neon.local import decode_cursor

    if decode_cursor(cursor) is None:
        raise validation(f"invalid pagination cursor {cursor!r}")
    return cursor


def require_workspace_membership(
    container: ApiContainer,
    session: SessionIdentity,
    workspace_id: str,
) -> None:
    """Mutations require MEMBERSHIP in the target workspace — the demo
    workspace is readable by authenticated users but mutable only by its
    members (SECURITY S21)."""
    member_ids = {
        str(w["id"])
        for w in container.persistence.workspaces_for_user(session.user_id)
    }
    if workspace_id not in member_ids:
        raise not_found("workspace not found")
