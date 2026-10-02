"""Error envelope (contract §C.2): ``{"error": {"code", "message", "details"}}``.

Transport errors (HTTP 4xx/5xx) never masquerade as resource truth states.
The eight contract codes cover every semantic error the API raises; a
reserved ``INTERNAL`` code exists ONLY as the last-resort fault barrier for
unexpected exceptions (disclosed in the checkpoint/API reference — it never
carries resource semantics). Truth states on DTOs are a DIFFERENT axis and
are never converted into errors or vice versa.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# The contract's semantic error codes (binding).
CODE_UNAUTHENTICATED = "UNAUTHENTICATED"
CODE_FORBIDDEN = "FORBIDDEN"
CODE_NOT_FOUND = "NOT_FOUND"
CODE_VALIDATION = "VALIDATION"
CODE_CONFLICT = "CONFLICT"
CODE_RATE_LIMITED = "RATE_LIMITED"
CODE_PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
CODE_PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
# Last-resort fault barrier for unexpected exceptions (not a contract
# semantic code; disclosed — never used for resource semantics).
CODE_INTERNAL = "INTERNAL"


class ApiError(Exception):
    """A typed API error rendered through the contract envelope."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers


def unauthenticated(message: str = "authentication required") -> ApiError:
    return ApiError(status_code=401, code=CODE_UNAUTHENTICATED, message=message)


def forbidden(message: str = "forbidden for this tenant") -> ApiError:
    return ApiError(status_code=403, code=CODE_FORBIDDEN, message=message)


def not_found(message: str = "resource not found") -> ApiError:
    return ApiError(status_code=404, code=CODE_NOT_FOUND, message=message)


def validation(message: str, details: dict[str, Any] | None = None) -> ApiError:
    return ApiError(
        status_code=422, code=CODE_VALIDATION, message=message, details=details
    )


def conflict(message: str, details: dict[str, Any] | None = None) -> ApiError:
    return ApiError(
        status_code=409, code=CODE_CONFLICT, message=message, details=details
    )


def rate_limited(retry_after: int) -> ApiError:
    return ApiError(
        status_code=429,
        code=CODE_RATE_LIMITED,
        message="rate limit exceeded",
        details={"retryAfterSeconds": retry_after},
        headers={"Retry-After": str(retry_after)},
    )


def payload_too_large(limit_mb: int) -> ApiError:
    return ApiError(
        status_code=413,
        code=CODE_PAYLOAD_TOO_LARGE,
        message="request payload too large",
        details={"maxBodyMb": limit_mb},
    )


def provider_unavailable(detail: str) -> ApiError:
    return ApiError(
        status_code=503,
        code=CODE_PROVIDER_UNAVAILABLE,
        message="a required provider seam is unavailable",
        details={"reason": detail},
    )


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, exc.details),
            headers=exc.headers or None,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body(
                CODE_VALIDATION,
                "request validation failed",
                {"errors": _compact_errors(exc.errors())},
            ),
        )

    @app.exception_handler(Exception)
    async def _internal_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=error_body(
                CODE_INTERNAL,
                "unexpected internal error (fault barrier; no resource "
                "semantics)",
                {"type": type(exc).__name__},
            ),
        )


def _compact_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for err in errors:
        compact.append(
            {
                "loc": [str(p) for p in err.get("loc", ())],
                "msg": err.get("msg", ""),
                "type": err.get("type", ""),
            }
        )
    return compact
