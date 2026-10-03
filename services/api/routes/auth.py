"""``/api/v1/auth/*`` — session endpoints (PUB-01) + the GitHub OAuth
web flow, account surface and CSRF-protected logout (PUB-04).

Endpoint inventory:

- ``GET  /auth/session``      — the resolved session (SessionDTO; PUB-01).
- ``POST /auth/login``        — LOCAL stub login (PUB-01, LOCAL-only).
- ``POST /auth/logout``       — logout; REAL sessions are CSRF-protected
                                (double-submit) and revoked SERVER-side.
- ``GET  /auth/account``      — the signed-in user + their workspace
                                memberships with roles (owner/member) —
                                the tenant-aware navigation source.
- ``GET  /auth/github/start``  — begin the OAuth web flow (state + PKCE
                                 S256); redirects to github.com (live) or
                                 the LOCAL fake-GitHub consent surface.
- ``GET  /auth/github/callback`` — the OAuth redirect target: single-use
                                   state validation, code exchange,
                                   identity → user upsert, session issue.
- ``GET  /auth/github/fake/authorize`` + ``POST /auth/github/fake/consent``
  — the deterministic fake-GitHub provider surface (LOCAL ONLY, clearly
  labeled; refused for ``SOS_ENV != local``).

OpenAPI note (disclosed in the PUB-04 checkpoint): the PUB-04 additions are
``include_in_schema=False`` — the frozen PUB-01 OpenAPI snapshot (tests/
test_pub01_openapi_snapshot.py, frozen surface) pins the machine contract
byte-identically; the browser-flow endpoints are documented in
``docs/deployment/api-reference.md`` instead.

Security properties (SECURITY threat notes / directive §6):

- OAuth ``state`` (single-use, 10-minute TTL) + PKCE S256 with the verifier
  held server-side in ``oauth_states``;
- session cookie httpOnly + SameSite=Lax (+ Secure outside LOCAL), opaque
  server-side tokens (sha256-hashed at rest);
- the OAuth access token is used exactly once, server-side, to fetch the
  identity — never persisted, never sent to the browser;
- logout revokes the session row server-side;
- mutations with a real session require the double-submit CSRF pair
  (``x-sos-csrf`` header == ``sos_csrf`` cookie == the stored token);
- tenant context NEVER comes from the browser — the account surface
  derives memberships from the server-side session only.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from ..auth.csrf import (
    CSRF_COOKIE,
    enforce_mutation_csrf,
    issue_csrf_cookie,
)
from ..auth.session import (
    SESSION_COOKIE,
    STUB_PROVIDER,
    SessionIdentity,
    get_auth_store,
    login_local_stub,
    session_cookie_params,
)
from ..container import ApiContainer
from ..dependencies import get_container, get_session, now_iso
from ..errors import (
    ApiError,
    CODE_FORBIDDEN,
    CODE_VALIDATION,
    forbidden,
    rate_limited,
)
from ..schemas.common import CamelModel
from ..schemas.workspace import (
    LoginRequestDTO,
    LoginResponseDTO,
    SessionDTO,
    UserDTO,
)
from providers.github.oauth import (  # noqa: E402  (repo-root import)
    FAKE_CONSENT_PATH,
    FAKE_IDENTITIES,
    FakeGitHubOAuth,
    GitHubIdentityError,
    OAuthFlowError,
    build_github_oauth,
    code_challenge_s256,
)
from services.api.auth.store import (  # noqa: E402
    StateConsumedError,
    StateExpiredError,
    StateUnknownError,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# The web-cockpit callback page the API redirects the browser to after the
# flow completes (same-origin in the proxy topology; SOS_WEB_BASE_URL wins
# when explicitly configured).
WEB_CALLBACK_PATH = "/signin/callback"

_NEXT_PATH_RE = re.compile(r"^/[A-Za-z0-9\-._~!$&'()*+,;=:@%/?]*$")


# ---------------------------------------------------------------------------
# Route-local wire models (the §C.3 DTO minimums stay owned by
# services/api/schemas — outside PUB-04's allowed surface; these auth-flow
# shapes live with the auth routes that define them, following the PUB-01
# CreateWorkspaceRequest precedent).
# ---------------------------------------------------------------------------


class AccountWorkspaceDTO(CamelModel):
    id: str
    name: str
    slug: str
    is_demo: bool
    created_at: str
    role: str  # 'owner' | 'member' (DB-enforced, migration 0001)


class AccountDTO(CamelModel):
    authenticated: bool
    user: UserDTO | None = None
    stub: bool
    provider: str  # "none" | "local-stub" | "github" | "fake-github"
    workspaces: list[AccountWorkspaceDTO] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


def _auth_rate_limit(container: ApiContainer, request: Request) -> None:
    """The directive §13 auth bucket for the PUB-04 flow endpoints (the
    PUB-01 middleware already auth-buckets login/logout; these in-route
    checks cover start/callback/consent — the middleware list is outside
    PUB-04's allowed surface, so the check lives here, same seam)."""
    decision = container.coordination.rate_limit(
        "auth", _client_ip(request),
        limit=container.settings.rate_anon_per_min, window_seconds=60,
    )
    if not decision.allowed:
        raise rate_limited(decision.retry_after_seconds)


def _validate_next_path(next_path: str | None) -> str | None:
    """Open-redirect guard: a safe RELATIVE path only (starts with '/', no
    '//', no backslash, bounded length)."""
    if next_path is None:
        return None
    if (
        len(next_path) > 200
        or not _NEXT_PATH_RE.match(next_path)
        or next_path.startswith("//")
    ):
        raise ApiError(
            status_code=422,
            code=CODE_VALIDATION,
            message=(
                "invalid 'next' path: must be a relative path starting "
                "with '/' (open-redirect guard)"
            ),
        )
    return next_path


def _public_origin(request: Request) -> str:
    """The origin the BROWSER used to reach the API.

    Same-origin proxy topology (the PUB-04 web wiring): the web server
    forwards ``X-Forwarded-Host``/``X-Forwarded-Proto`` — those win (proto
    falling back to the ACTUAL connection scheme, never an assumed https).
    Direct API access (LOCAL, tests): the request's own base URL.
    """
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        forwarded_proto = request.headers.get("x-forwarded-proto")
        if forwarded_proto:
            proto = forwarded_proto.split(",")[0].strip()
        else:
            proto = request.url.scheme
        return f"{proto}://{forwarded_host.split(',')[0].strip()}"
    return str(request.base_url).rstrip("/")


def _web_base(request: Request, container: ApiContainer) -> str:
    """Where the cockpit lives (for post-flow redirects)."""
    web_base = (container.settings.web_base_url or "").strip()
    if web_base:
        return web_base.rstrip("/")
    return _public_origin(request)


def _flow_redirect(
    request: Request, container: ApiContainer, *, status: str,
    reason: str | None = None, next_path: str | None = None,
) -> RedirectResponse:
    """Redirect the browser to the cockpit's sign-in callback with an
    HONEST status (never a fake success)."""
    params: dict[str, str] = {"status": status}
    if reason:
        params["reason"] = reason
    if next_path:
        params["next"] = next_path
    url = f"{_web_base(request, container)}{WEB_CALLBACK_PATH}?{urlencode(params)}"
    return RedirectResponse(url, status_code=302)


def _audit_auth(
    container: ApiContainer, *, actor: str, action: str, target: str,
    meta: dict[str, Any] | None = None,
) -> None:
    """Append an auth audit event (tenant-less: auth precedes workspace
    context; append-only — S17)."""
    ts = now_iso()
    material = "|".join(["__auth__", actor, action, target, ts, repr(meta or {})])
    audit_id = "audit-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    container.persistence.append_audit(
        tenant_id=None, actor=actor, action=action, target=target,
        meta=meta or {}, ts=ts, audit_id=audit_id,
    )


# ---------------------------------------------------------------------------
# Session surface (PUB-01, unchanged shapes)
# ---------------------------------------------------------------------------


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
                "enabled outside SOS_ENV=local (use the GitHub OAuth flow "
                "at /auth/github/start)"
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
    _audit_auth(
        container, actor=f"{user['login']}({user['id']})",
        action="auth.login", target=f"user/{user['id']}",
        meta={"provider": STUB_PROVIDER, "stub": True},
    )
    return {"user": user, "stub": True, "provider": STUB_PROVIDER}


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    session: SessionIdentity = Depends(get_session),
    container: ApiContainer = Depends(get_container),
) -> dict:
    if session.authenticated and not session.stub:
        # Real session: CSRF double-submit required + SERVER-side revocation
        # (SECURITY: logout invalidates server-side; the cookie deletion is
        # belt-and-braces).
        enforce_mutation_csrf(request, session)
        store = get_auth_store(request, container.settings)
        store.revoke_session(str(session.session_id))
        _audit_auth(
            container, actor=session.display, action="auth.logout",
            target=f"session/{session.session_id}",
            meta={"provider": session.provider},
        )
    elif session.authenticated:
        _audit_auth(
            container, actor=session.display, action="auth.logout",
            target=f"user/{session.user_id}",
            meta={"provider": STUB_PROVIDER, "stub": True},
        )
    response.delete_cookie(key=SESSION_COOKIE)
    response.delete_cookie(key=CSRF_COOKIE, path="/")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Account surface (PUB-04): user + memberships(roles) — tenant-aware nav
# ---------------------------------------------------------------------------


@router.get("/account", response_model=AccountDTO, include_in_schema=False)
def account(
    request: Request,
    session: SessionIdentity = Depends(get_session),
    container: ApiContainer = Depends(get_container),
) -> dict:
    """The signed-in user + their workspace memberships with roles.

    Tenant context derives ONLY from the server-side session (directive
    §6): the browser can neither add nor select a workspace here.
    """
    if not session.authenticated:
        return {
            "authenticated": False, "user": None, "stub": False,
            "provider": "none", "workspaces": [],
        }
    store = get_auth_store(request, container.settings)
    memberships = store.memberships_for_user(str(session.user_id))
    return {
        "authenticated": True,
        "user": session.user,
        "stub": session.stub,
        "provider": session.provider,
        "workspaces": [
            {
                "id": m.workspace_id, "name": m.name, "slug": m.slug,
                "isDemo": m.is_demo, "createdAt": m.created_at, "role": m.role,
            }
            for m in memberships
        ],
    }


# ---------------------------------------------------------------------------
# GitHub OAuth web flow (PUB-04): start → authorize → callback
# ---------------------------------------------------------------------------


@router.get("/github/start", include_in_schema=False)
def github_start(
    request: Request,
    container: ApiContainer = Depends(get_container),
    next_path: str | None = Query(default=None, alias="next"),
) -> Response:
    """Begin the OAuth web flow: create the single-use state (+ PKCE
    verifier, server-held) and redirect to the provider's authorize URL."""
    _auth_rate_limit(container, request)
    safe_next = _validate_next_path(next_path)
    try:
        provider = build_github_oauth(container.settings)
    except OAuthFlowError:
        return _flow_redirect(
            request, container, status="error", reason="provider_unconfigured"
        )
    try:
        store = get_auth_store(request, container.settings)
        record = store.create_oauth_state(next_path=safe_next)
    except RuntimeError:
        return _flow_redirect(
            request, container, status="error",
            reason="auth_store_unavailable",
        )
    challenge = code_challenge_s256(record.code_verifier)
    if isinstance(provider, FakeGitHubOAuth):
        # LOCAL: the fake consent surface (relative URL → resolved against
        # the browser's current origin, so the proxy topology stays
        # single-origin).
        url = provider.authorize_url(
            state=record.state, code_challenge=challenge, redirect_uri=""
        )
    else:
        # Live: redirect back to THIS origin's callback (the proxy forwards
        # X-Forwarded-Host, so the browser-visible origin is used).
        redirect_uri = (
            f"{_public_origin(request)}/api/v1/auth/github/callback"
        )
        url = provider.authorize_url(
            state=record.state, code_challenge=challenge,
            redirect_uri=redirect_uri,
        )
    return RedirectResponse(url, status_code=302)


@router.get("/github/callback", include_in_schema=False)
def github_callback(
    request: Request,
    container: ApiContainer = Depends(get_container),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> Response:
    """The OAuth redirect target. Validates the single-use state (CSRF for
    the flow), exchanges the code with the server-held PKCE verifier,
    upserts the user, issues the session (+ CSRF cookie) and redirects the
    browser to the cockpit callback. Any failure redirects with an HONEST
    error reason — never a fake success, never a partial session."""
    _auth_rate_limit(container, request)
    if error:
        _audit_auth(
            container, actor="anonymous", action="auth.oauth.denied",
            target="auth/github", meta={"error": error[:200]},
        )
        return _flow_redirect(
            request, container, status="error",
            reason="authorization_denied",
        )
    if not code or not state:
        return _flow_redirect(
            request, container, status="error", reason="invalid_request"
        )
    store = get_auth_store(request, container.settings)
    try:
        record = store.take_oauth_state(state)  # single-use, expiring
    except StateUnknownError:
        return _flow_redirect(
            request, container, status="error", reason="invalid_state"
        )
    except StateConsumedError:
        return _flow_redirect(
            request, container, status="error", reason="replayed_state"
        )
    except StateExpiredError:
        return _flow_redirect(
            request, container, status="error", reason="expired_state"
        )

    try:
        provider = build_github_oauth(container.settings)
    except OAuthFlowError:
        return _flow_redirect(
            request, container, status="error", reason="provider_unconfigured"
        )
    redirect_uri = (
        f"{_public_origin(request)}/api/v1/auth/github/callback"
    )
    try:
        access_token = provider.exchange_code(
            code=code, code_verifier=record.code_verifier,
            redirect_uri=redirect_uri,
        )
        identity = provider.identity_for(access_token)
    except (OAuthFlowError, GitHubIdentityError) as exc:
        _audit_auth(
            container, actor="anonymous", action="auth.oauth.failed",
            target="auth/github", meta={"reason": str(exc)[:200]},
        )
        return _flow_redirect(
            request, container, status="error", reason="exchange_failed"
        )

    user = container.persistence.upsert_user(
        user_id=f"user-{identity.login}",
        github_id=identity.github_id,
        login=identity.login,
        display_name=identity.display_name,
        created_at=now_iso(),
    )
    provider_name = "fake-github" if identity.fixture else "github"
    raw_token, session_record = store.create_session(
        user_id=str(user["id"]), provider=provider_name
    )
    response = _flow_redirect(
        request, container, status="ok",
        next_path=record.next_path or "/workspace",
    )
    cookie_params = session_cookie_params(container.settings.env)
    response.set_cookie(value=raw_token, path="/", **cookie_params)
    issue_csrf_cookie(
        response, session_record.csrf_token,
        secure=container.settings.env != "local",
    )
    _audit_auth(
        container,
        actor=f"{user['login']}({user['id']})",
        action="auth.login",
        target=f"user/{user['id']}",
        meta={"provider": provider_name, "fixture": identity.fixture},
    )
    return response


# ---------------------------------------------------------------------------
# The LOCAL fake-GitHub consent surface (deterministic, clearly labeled,
# refused outside SOS_ENV=local — SECURITY threat notes)
# ---------------------------------------------------------------------------


@router.get(
    "/github/fake/authorize", response_class=HTMLResponse,
    include_in_schema=False,
)
def fake_authorize(
    request: Request,
    container: ApiContainer = Depends(get_container),
    state: str = Query(default=""),
) -> Response:
    """The fake-GitHub consent page (LOCAL ONLY, clearly labeled).

    Deterministic fixture identities; the form POSTs back to the consent
    endpoint with the pending state (the state parameter IS the CSRF
    protection for this flow)."""
    if container.settings.env != "local":
        raise forbidden(
            "the fake-GitHub consent surface is a LOCAL-mode test facility "
            "and is never enabled outside SOS_ENV=local (fail-closed)"
        )
    store = get_auth_store(request, container.settings)
    pending = store.peek_oauth_state(state) if state else None
    if pending is None:
        return HTMLResponse(
            _fake_page_shell(
                title="FAKE GITHUB — expired or unknown state",
                body="""
<p class="warn">This authorization link is expired, already used, or
unknown. Start again from the SOS sign-in page.</p>
<p><a href="/signin">Back to SOS sign-in</a></p>
""",
            ),
            status_code=200,
        )
    options = "".join(
        f"""
<form method="post" action="{FAKE_CONSENT_PATH}">
  <input type="hidden" name="state" value="{state}" />
  <input type="hidden" name="login" value="{identity['login']}" />
  <button type="submit" class="identity">
    <span class="login">{identity['login']}</span>
    <span class="meta">github_id {identity['github_id']} — {identity['display_name']}</span>
  </button>
</form>
"""
        for identity in FAKE_IDENTITIES
    )
    return HTMLResponse(
        _fake_page_shell(
            title="FAKE GITHUB — authorize SOS (LOCAL TEST MODE)",
            body=f"""
<p class="banner">This is <strong>NOT github.com</strong>. It is the
deterministic fake-GitHub provider of the SOS LOCAL test mode (SOS_ENV=local
only). It exists so the full authentication journey is testable with zero
secrets and zero network. It is refused for every non-LOCAL environment.</p>
<p>Choose a fixture identity to authorize. The authorization state is
single-use and expires 10 minutes after the flow started.</p>
<div class="identities">{options}</div>
<p class="meta">state {state[:10]}… · PKCE S256 · the browser never
receives any token</p>
""",
        )
    )


@router.post("/github/fake/consent", include_in_schema=False)
async def fake_consent(
    request: Request,
    container: ApiContainer = Depends(get_container),
) -> Response:
    """The fake authorization decision: validate the pending state, then
    redirect to the real callback with the deterministic code.

    Parses the browser form (``application/x-www-form-urlencoded`` — the
    HTML consent page's native encoding; no extra dependencies)."""
    if container.settings.env != "local":
        raise forbidden(
            "the fake-GitHub consent surface is a LOCAL-mode test facility "
            "and is never enabled outside SOS_ENV=local (fail-closed)"
        )
    _auth_rate_limit(container, request)
    form = await request.form()
    state = str(form.get("state") or "")
    login = str(form.get("login") or "")
    if not state or not login:
        raise ApiError(
            status_code=422,
            code=CODE_VALIDATION,
            message="fake consent requires 'state' and 'login' form fields",
        )
    if login not in {i["login"] for i in FAKE_IDENTITIES}:
        raise ApiError(
            status_code=422,
            code=CODE_VALIDATION,
            message=(
                f"unknown fake-GitHub fixture identity {login!r} (known: "
                + ", ".join(i["login"] for i in FAKE_IDENTITIES) + ")"
            ),
        )
    store = get_auth_store(request, container.settings)
    if store.peek_oauth_state(state) is None:
        return _flow_redirect(
            request, container, status="error", reason="invalid_state"
        )
    code = FakeGitHubOAuth.code_for(state, login)
    return RedirectResponse(
        f"/api/v1/auth/github/callback?{urlencode({'code': code, 'state': state})}",
        status_code=302,
    )


_FAKE_PAGE_STYLE = """
body{font-family:system-ui,sans-serif;max-width:640px;margin:3rem auto;
padding:0 1rem;color:#0f172a;background:#fff}
.banner{border:1px solid #f59e0b;background:#fffbeb;color:#92400e;
padding:.75rem 1rem;border-radius:.5rem;font-size:.95rem}
.warn{border:1px solid #ef4444;background:#fef2f2;color:#991b1b;
padding:.75rem 1rem;border-radius:.5rem}
.identities{display:flex;flex-direction:column;gap:.5rem;margin:1.25rem 0}
form{margin:0}
.identity{display:flex;flex-direction:column;align-items:flex-start;gap:.15rem;
width:100%;padding:.6rem .9rem;border:1px solid #cbd5e1;border-radius:.5rem;
background:#fff;cursor:pointer;text-align:left;font-size:1rem}
.identity:hover{background:#f8fafc}
.identity .login{font-weight:600}
.identity .meta,.meta{color:#64748b;font-size:.8rem}
h1{font-size:1.25rem}
"""


def _fake_page_shell(*, title: str, body: str) -> str:
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\" />"
        f"<title>{title}</title><style>{_FAKE_PAGE_STYLE}</style></head>"
        f"<body><h1>{title}</h1>{body}</body></html>"
    )
