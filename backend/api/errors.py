"""The single place that shapes error responses.

Every error the API returns has the form documented in AGENTS.md §6:

    {"error": "<code>", "detail": "<message>"}

DRF calls ``exception_handler`` for any exception raised inside a view, so
endpoints do not build error responses by hand.
"""

from __future__ import annotations

import logging
from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from api.exceptions import DomainError

logger = logging.getLogger(__name__)

#: DRF status codes mapped to our stable error codes.
STATUS_CODES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "validation_error",
    status.HTTP_401_UNAUTHORIZED: "not_authenticated",
    status.HTTP_403_FORBIDDEN: "permission_denied",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_406_NOT_ACCEPTABLE: "not_acceptable",
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "unsupported_media_type",
    status.HTTP_429_TOO_MANY_REQUESTS: "throttled",
}


def error_body(code: str, detail: str) -> dict[str, str]:
    """Build the canonical error payload."""
    return {"error": code, "detail": detail}


def _flatten(detail: Any) -> str:
    """Turn a DRF error detail (string, list, or nested dict) into one sentence."""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        return " ".join(_flatten(item) for item in detail)
    if isinstance(detail, dict):
        return " ".join(f"{field}: {_flatten(value)}" for field, value in detail.items())
    return str(detail)


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """DRF exception hook. Returns None for anything DRF cannot handle, letting
    Django produce a 500 — we never convert an unexpected error into a 2xx."""
    if isinstance(exc, DomainError):
        logger.info("api.domain_error code=%s status=%s", exc.code, exc.status_code)
        return Response(error_body(exc.code, exc.detail), status=exc.status_code)

    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    code = STATUS_CODES.get(response.status_code, "error")
    detail = getattr(exc, "detail", None)
    response.data = error_body(code, _flatten(detail) if detail is not None else str(exc))
    return response
