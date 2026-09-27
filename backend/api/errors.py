"""The single place that shapes error responses.

Every error the API returns has the form documented in AGENTS.md §6:

    {"error": "<code>", "detail": "<message>"}

FastAPI calls these handlers for any exception an endpoint or dependency
raises, so endpoints never build error responses by hand.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.exceptions import DomainError

logger = logging.getLogger(__name__)

#: HTTP status codes mapped to our stable error codes.
STATUS_CODES: dict[int, str] = {
    400: "validation_error",
    401: "not_authenticated",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    406: "not_acceptable",
    415: "unsupported_media_type",
    429: "throttled",
}

#: Where a validation error can sit; the location kind is dropped from messages.
_LOCATION_KINDS = {"body", "query", "path", "header", "cookie"}


def error_body(code: str, detail: str) -> dict[str, str]:
    """Build the canonical error payload."""
    return {"error": code, "detail": detail}


def _error(
    status: int, code: str, detail: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(error_body(code, detail), status_code=status, headers=headers)


def _describe(error: dict[str, Any]) -> str:
    """One validation problem as ``field: message``."""
    location = [str(part) for part in error.get("loc", ())]
    if location and location[0] in _LOCATION_KINDS:
        location = location[1:]
    message = str(error.get("msg", "Invalid value.")).removeprefix("Value error, ")
    return f"{'.'.join(location)}: {message}" if location else message


async def _domain_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    logger.info("api.domain_error code=%s status=%s", exc.code, exc.status_code)
    return _error(exc.status_code, exc.code, exc.detail, exc.headers)


async def _validation_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    detail = " ".join(_describe(error) for error in exc.errors()) or "Invalid request."
    return _error(400, "validation_error", detail)


async def _http_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = STATUS_CODES.get(exc.status_code, "error")
    return _error(exc.status_code, code, str(exc.detail), dict(exc.headers or {}) or None)


async def _unexpected_error(_request: Request, _exc: Exception) -> JSONResponse:
    # Still a 500 — an unexpected error is never turned into a success. The
    # server logs the traceback when the exception propagates.
    return _error(500, "server_error", "An unexpected error occurred.")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected_error)
