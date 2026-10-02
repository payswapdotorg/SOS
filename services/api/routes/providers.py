"""``/api/v1/providers/*`` — provider status introspection (truthful)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..container import ApiContainer
from ..dependencies import get_container
from ..errors import not_found
from ..schemas.execution import ProviderStatusDTO
from ..schemas.common import CollectionEnvelope

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/status", response_model=CollectionEnvelope[ProviderStatusDTO])
def provider_status(
    container: ApiContainer = Depends(get_container),
) -> dict:
    return {"items": container.provider_statuses(), "nextCursor": None}


@router.get("/status/{name}", response_model=ProviderStatusDTO)
def provider_status_one(
    name: str,
    container: ApiContainer = Depends(get_container),
) -> dict:
    for status in container.provider_statuses():
        if status["name"] == name:
            return status
    raise not_found(f"provider '{name}' is not wired in this deployment")
