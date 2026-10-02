"""Common wire shapes (contract §C.2): collection envelope, error envelope,
cursor pagination, truth states.

Truth-state and decision-action enums are IMPORTED from ``sos.model`` — the
frozen single authority — so the six-state vocabulary survives every layer
unchanged (DB → API → UI; contract §A.6)."""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from sos.model import DecisionAction, TruthState

TruthStateWire = TruthState  # the six-state vocabulary, verbatim
DecisionActionWire = DecisionAction  # ACT|EXPERIMENT|GATHER_EVIDENCE|ASK|REJECT|ROLLBACK


def _to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


class CamelModel(BaseModel):
    """Wire DTO base: camelCase serialization, snake_case construction."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )


ItemT = TypeVar("ItemT")


class CollectionEnvelope(CamelModel, Generic[ItemT]):
    """``{"items": [...], "nextCursor": string|null}`` (§C.2)."""

    items: list[ItemT]
    next_cursor: str | None = None


class ErrorBody(CamelModel):
    code: str
    message: str
    details: dict | list | None = None


class ErrorEnvelope(CamelModel):
    error: ErrorBody


class PaginationParams(CamelModel):
    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = None
