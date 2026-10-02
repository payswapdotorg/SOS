"""``/api/v1/auth/*`` — STUB session endpoints (PUB-01).

Real GitHub OAuth (state + PKCE, httpOnly/secure/sameSite cookies, CSRF)
arrives with PUB-04 and is deliberately NOT built here. LOCAL mode exposes
deterministic test identities through clearly-labeled stub sessions; the
stub login is refused outside LOCAL mode (never enabled for public)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from ..auth.session import SESSION_COOKIE, STUB_PROVIDER, login_local_stub
from ..container import ApiContainer
from ..dependencies import get_container, get_session, now_iso
from ..errors import ApiError, CODE_VALIDATION, CODE_FORBIDDEN
from ..schemas.workspace import (
    LoginRequestDTO,
    LoginResponseDTO,
    SessionDTO,
)
from ..auth.session import SessionIdentity

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/session", response_model=SessionDTO)
def session_info(
    session: SessionIdentity = Depends(get_session),
) -> dict:
    return {
        "authenticated": session.authenticated,
        "user": session.user,
        "stub": session.stub,
        "provider": session.provider,
    }


@router.post("/login", response_model=LoginResponseDTO)
def login(
    body: LoginRequestDTO,
    response: Response,
    container: ApiContainer = Depends(get_container),
) -> dict:
    if container.settings.env != "local":
        raise ApiError(
            status_code=403,
            code=CODE_FORBIDDEN,
            message=(
                "stub login is a LOCAL-mode test facility and is never "
                "enabled outside SOS_ENV=local (real GitHub OAuth arrives "
                "with PUB-04)"
            ),
        )
    try:
        user, token = login_local_stub(
            container.persistence, login=body.login,
            created_at=now_iso(),
        )
    except KeyError:
        raise ApiError(
            status_code=422,
            code=CODE_VALIDATION,
            message=(
                f"unknown LOCAL test identity {body.login!r} "
                "(known: demo-owner, alice, bob)"
            ),
        ) from None
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=container.settings.env != "local",
    )
    return {"user": user, "stub": True, "provider": STUB_PROVIDER}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(key=SESSION_COOKIE)
    return {"ok": True}
