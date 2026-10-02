"""Rate limiting middleware (directive §13 buckets) behind the coordination
seam — LOCAL in-process limiter now; the PUB-06 Upstash adapter carries the
identical semantics.

Buckets (per directive §13 + infra/environment.example):
- ``ip``: a coarse per-IP per-minute ceiling over ALL requests;
- ``anonymous``: per-IP per-minute for anonymous (demo-reads-only) traffic;
- ``user``: per-authenticated-user per-minute for normal reads;
- ``write``: per-user per-minute for mutations (checked by mutation routes);
- ``job``/``recovery``: per-workspace per-hour expensive-job quotas (checked
  at job creation);
- provider concurrency: the execution dispatch semaphore (PUB-06/PUB-08).
"""
from __future__ import annotations

from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..auth.session import resolve_session
from ..errors import error_body, CODE_RATE_LIMITED

_BODY_MAX_DEFAULT = 1 * 1024 * 1024


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Checks the per-IP and per-identity buckets before the route runs, and
    enforces the request-body size cap (SECURITY S16)."""

    def __init__(self, app: Any, container: Any) -> None:
        super().__init__(app)
        self._container = container

    async def dispatch(self, request: Request, call_next: Any):
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

        # Per-IP bucket (all traffic).
        ip_limit = settings.rate_anon_per_min + settings.rate_user_per_min
        decision = coordination.rate_limit(
            "ip", ip, limit=ip_limit, window_seconds=60
        )
        if not decision.allowed:
            return self._too_many(decision.retry_after_seconds)

        # Identity bucket: anonymous vs authenticated.
        session = resolve_session(request, self._container.persistence)
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
        if not decision.allowed:
            return self._too_many(decision.retry_after_seconds)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(decision.limit)
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        return response

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
