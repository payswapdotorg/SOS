"""Wire DTOs: mission + revisions (§C.3; mission journey fields)."""
from __future__ import annotations

from typing import Literal

from .common import CamelModel


class MissionApprovalDTO(CamelModel):
    state: Literal["pending", "approved", "rejected"]
    requested_by: str | None = None
    decided_by: str | None = None
    decided_at: str | None = None


class MissionRevisionDTO(CamelModel):
    id: str
    mission_id: str
    revision: int
    goals: list[str]
    outcomes: list[str]
    stakeholders: list[str]
    measures: list[str]
    constraints: list[str]
    preferences: list[str]
    approval: MissionApprovalDTO
    created_at: str


class MissionDTO(CamelModel):
    id: str
    workspace_id: str
    title: str
    status: str  # sos.model.MissionStatus values (DRAFT..RETIRED)
    current_revision_id: str | None = None
    current_revision: MissionRevisionDTO | None = None


class CreateMissionRequestDTO(CamelModel):
    workspace_id: str
    title: str
    goals: list[str]
    outcomes: list[str]
    stakeholders: list[str]
    measures: list[str]
    constraints: list[str]
    preferences: list[str] = []


class ProposeMissionRevisionRequestDTO(CamelModel):
    goals: list[str]
    outcomes: list[str]
    stakeholders: list[str]
    measures: list[str]
    constraints: list[str]
    preferences: list[str] = []
    set_current: bool = False
