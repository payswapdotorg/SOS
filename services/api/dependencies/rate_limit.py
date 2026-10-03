"""Rate limiting middleware (directive §13 buckets) behind the coordination
seam — the PUB-06 Upstash adapter carries the same epoch-aligned fixed-
window semantics as the LOCAL in-process limiter.

Buckets (per directive §13 + infra/environment.example):
- ``ip``: a coarse per-IP per-minute ceiling over ALL requests;
- ``anonymous``: per-IP per-minute for anonymous (demo-reads-only) traffic;
- ``user``: per-authenticated-user per-minute for normal reads;
- ``write``: per-user per-minute for mutations (checked by mutation routes);
- ``workspace``: per-workspace per-minute ceiling on requests that target
  an identifiable workspace (query ``workspaceId`` or a
  ``/workspaces/{id}`` path) — the shared-workspace abuse guard;
- ``job-type``/``recovery``: per-workspace per-hour expensive-job quotas
  (checked at job creation);
- ``provider``: per-provider per-minute dispatch quota (checked at job
  creation — PUB-06, directive §13 "provider" bucket); the Apify
  low-concurrency SEMAPHORE is PUB-08's ``apify_max_concurrent``.
"""
from __future__ import annotations

import re
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..auth.session import resolve_session
from ..errors import error_body, CODE_RATE_LIMITED

_BODY_MAX_DEFAULT = 1 * 1024 * 1024

# Workspace-target extraction: a ``/api/v1/workspaces/{id}`` path prefix
# (the first path segment pair under /api/v1).
_WORKSPACE_PATH_RE = re.compile(r"^/api/v1/workspaces/([^/?#]+)")


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


def _target_workspace_id(request: Request) -> str | None:
    """The workspace a request targets, when identifiable: the explicit
    ``workspaceId`` query parameter (collection narrowing) or a
    ``/workspaces/{id}`` path. Requests without an identifiable target are
    covered by the ip/identity buckets only (disclosed behavior)."""
    workspace_id = request.query_params.get("workspaceId")
    if workspace_id:
        return workspace_id
    match = _WORKSPACE_PATH_RE.match(request.url.path)
    if match:
        return match.group(1)
    return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Checks the per-IP and per-identity buckets before the route runs, and
    enforces the request-body size cap (SECURITY S16)."""

    def __init__(self, app: Any, container: Any) -> None:
        super().__init__(app)
        self._container = container

    async def dispatch(self, request: Request, call_next: Any):
        # The readiness probe is exempt: it must ALWAYS answer truthfully
        # (that is its purpose), even when the coordination plane is down.
        if request.url.path == "/api/v1/health":
            return await call_next(request)
        settings = self._container.settings
        coordination = self._container.coordination
        ip = _client_ip(request)

        # S16: request payload cap (Content-Length pre-check).
        max_bytes = settings.rate_body_max_mb * 1024 * 1024
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit():
            if int(content_length) > max_bytes:
                return JSONResponse(
                    status_code=413,
                    content=error_body(
                        "PAYLOAD_TOO_LARGE",
                        "request payload too large",
                        {"maxBodyMb": settings.rate_body_max_mb},
                    ),
                )

        # Per-IP bucket (all traffic). A coordination-plane failure fails
        # CLOSED for protected traffic (503 PROVIDER_UNAVAILABLE) — the
        # health endpoint above still reports the true seam state.
        try:
            ip_limit = settings.rate_anon_per_min + settings.rate_user_per_min
            decision = coordination.rate_limit(
                "ip", ip, limit=ip_limit, window_seconds=60
            )
        except Exception as exc:
            return self._coordination_down(str(exc))
        if not decision.allowed:
            return self._too_many(decision.retry_after_seconds)

        # Identity bucket: anonymous vs authenticated. The session-exchange
        # endpoints (login/logout) are exempt from the IDENTITY bucket —
        # they carry no session yet — but stay under the per-IP bucket.
        session_exchange = request.url.path in (
            "/api/v1/auth/login", "/api/v1/auth/logout",
        )
        try:
            if session_exchange:
                decision = coordination.rate_limit(
                    "auth", ip,
                    limit=settings.rate_anon_per_min, window_seconds=60,
                )
            else:
                session = resolve_session(
                    request, self._container.persistence
                )
                if session.authenticated:
                    decision = coordination.rate_limit(
                        "user", str(session.user_id),
                        limit=settings.rate_user_per_min, window_seconds=60,
                    )
                else:
                    decision = coordination.rate_limit(
                        "anonymous", ip,
                        limit=settings.rate_anon_per_min, window_seconds=60,
                    )
        except Exception as exc:
            return self._coordination_down(str(exc))
        if not decision.allowed:
            return self._too_many(decision.retry_after_seconds)

        # Directive §13 workspace bucket: per-workspace per-minute ceiling
        # on requests targeting an identifiable workspace (shared-workspace
        # abuse guard; anonymous demo traffic shares the demo workspace's
        # bucket — free-tier protection by design).
        target_workspace = _target_workspace_id(request)
        if target_workspace is not None:
            try:
                decision = coordination.rate_limit(
                    "workspace", target_workspace,
                    limit=settings.rate_workspace_per_min, window_seconds=60,
                )
            except Exception as exc:
                return self._coordination_down(str(exc))
            if not decision.allowed:
                return self._too_many(decision.retry_after_seconds)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(decision.limit)
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        return response

    @staticmethod
    def _coordination_down(reason: str) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content=error_body(
                "PROVIDER_UNAVAILABLE",
                "the coordination plane is unavailable; protected traffic "
                "fails closed",
                {"reason": reason},
            ),
        )

    @staticmethod
    def _too_many(retry_after: int) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content=error_body(
                CODE_RATE_LIMITED,
                "rate limit exceeded",
                {"retryAfterSeconds": retry_after},
            ),
            headers={"Retry-After": str(max(1, retry_after))},
        )


def check_write_quota(container: Any, session: Any) -> None:
    """The §13 bounded-writes bucket (per authenticated user per minute)."""
    if not session.authenticated:
        return  # anonymous mutations are rejected before this point (S7)
    decision = container.coordination.rate_limit(
        "write", str(session.user_id),
        limit=container.settings.rate_write_per_min, window_seconds=60,
    )
    if not decision.allowed:
        from ..errors import rate_limited

        raise rate_limited(decision.retry_after_seconds)


def check_job_quota(container: Any, workspace_id: str, job_type: str) -> None:
    """The §13 expensive-job quotas (per workspace per hour)."""
    settings = container.settings
    if job_type == "system_recovery":
        limit = settings.rate_recovery_per_hour
    else:
        limit = settings.rate_job_per_hour
    decision = container.coordination.rate_limit(
        "job-type", f"{workspace_id}:{job_type}",
        limit=limit, window_seconds=3600,
    )
    if not decision.allowed:
        from ..errors import rate_limited

        raise rate_limited(decision.retry_after_seconds)


def check_provider_quota(container: Any, provider: str) -> None:
    """The §13 provider bucket: per-provider per-minute dispatch quota
    (PUB-06 — checked at job creation; the execution provider's dispatches
    are bounded per provider id, LOCAL demo and PUBLIC Apify alike)."""
    decision = container.coordination.rate_limit(
        "provider", str(provider),
        limit=container.settings.rate_provider_per_min, window_seconds=60,
    )
    if not decision.allowed:
        from ..errors import rate_limited

        raise rate_limited(decision.retry_after_seconds)
