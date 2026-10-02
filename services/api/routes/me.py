"""GET /api/v1/me — the current session identity (anonymous included)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth.session import SessionIdentity
from ..dependencies import get_session
from ..schemas.workspace import SessionDTO

router = APIRouter(tags=["me"])


@router.get("/me", response_model=SessionDTO)
def me(session: SessionIdentity = Depends(get_session)) -> dict:
    return {
        "authenticated": session.authenticated,
        "user": session.user,
        "stub": session.stub,
        "provider": session.provider,
    }
