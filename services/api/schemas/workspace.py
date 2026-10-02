"""Wire DTOs: user, auth session, workspace (§C.3 minimums, names binding)."""
from __future__ import annotations

from .common import CamelModel


class UserDTO(CamelModel):
    id: str
    github_id: str
    login: str
    display_name: str
    created_at: str


class SessionDTO(CamelModel):
    authenticated: bool
    user: UserDTO | None = None
    stub: bool  # LOCAL deterministic test identities (real OAuth is PUB-04)
    provider: str  # "local-stub" | "github" (PUB-04)


class LoginRequestDTO(CamelModel):
    login: str  # a known LOCAL test identity (demo-owner|alice|bob)


class LoginResponseDTO(CamelModel):
    user: UserDTO
    stub: bool
    provider: str


class WorkspaceDTO(CamelModel):
    id: str
    name: str
    slug: str
    created_at: str
    is_demo: bool = False


class AuditEventDTO(CamelModel):
    id: str
    tenant_id: str | None = None
    actor: str
    action: str
    target: str
    meta: dict | None = None
    ts: str


class WorkspaceDetailDTO(WorkspaceDTO):
    """GET /workspaces/{id}: the workspace plus its recent activity trail
    (audit events are append-only — S17)."""

    recent_activity: list[AuditEventDTO] = []
