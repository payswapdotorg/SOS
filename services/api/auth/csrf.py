"""Double-submit CSRF protection (PUB-04; SECURITY S6 mechanism).

Design (binding rules):

- Every REAL (non-stub) session carries a server-generated ``csrf_token``
  (stored on the ``auth_sessions`` row).
- At sign-in the token is ALSO issued as the non-httpOnly ``sos_csrf``
  cookie (path ``/`` so cockpit JS can read it — the browser must be able
  to echo it; it is not a secret).
- Mutations made with a real session must present the SAME value in the
  ``x-sos-csrf`` request header. Validation compares header == cookie ==
  the session's stored token (a DB-backed synchronizer value — a blind
  double-submit subdomain attack cannot forge the stored third leg).
- STUB sessions (the PUB-01 deterministic LOCAL test facility) are exempt:
  they are clearly labeled, LOCAL-only, and never enabled for
  ``SOS_ENV=public`` (their token is not a browser credential).

PUB-04 wires enforcement on the auth-surface mutations it owns (logout and
the OAuth consent step is additionally state-protected). The web client
already sends the header on EVERY mutation, so completing the per-mutation
check across the remaining routes is a pure wiring step in the lane that
owns ``services/api/dependencies`` (PUB-06/PUB-10 — disclosed in the PUB-04
checkpoint). SameSite=Lax session cookies provide the cross-site request
barrier meanwhile.
"""
from __future__ import annotations

from fastapi import Request, Response

CSRF_COOKIE = "sos_csrf"
CSRF_HEADER = "x-sos-csrf"


def issue_csrf_cookie(response: Response, token: str, *, secure: bool) -> None:
    """Attach the readable double-submit cookie (non-httpOnly BY DESIGN —
    the browser must echo it; secure outside LOCAL; SameSite=Lax)."""
    response.set_cookie(
        key=CSRF_COOKIE,
        value=token,
        httponly=False,
        samesite="lax",
        secure=secure,
        path="/",
    )


def csrf_failure_response() -> dict:
    """The honest 403 body for a failed mutation-CSRF check (S6)."""
    from ..errors import forbidden

    raise forbidden(
        "mutation rejected: missing or invalid CSRF token "
        f"(present the {CSRF_HEADER} header matching the {CSRF_COOKIE} cookie)"
    )


def enforce_mutation_csrf(request: Request, session) -> None:
    """Validate the double-submit pair for an unsafe-method request carrying
    a REAL session. Stub sessions (LOCAL test facility) are exempt.

    Raises the contract 403 FORBIDDEN envelope on mismatch — raised inside
    the route so the app-level error handler renders it correctly.
    """
    from providers.github.oauth import constant_time_equals

    if not session.authenticated or session.stub:
        return  # anonymous requests are rejected by authn; stubs are exempt
    header_value = request.headers.get(CSRF_HEADER, "")
    cookie_value = request.cookies.get(CSRF_COOKIE, "")
    expected = getattr(session, "csrf_token", "")
    if not expected or not header_value or not cookie_value:
        csrf_failure_response()
    if not (
        constant_time_equals(header_value, expected)
        and constant_time_equals(cookie_value, expected)
    ):
        csrf_failure_response()
