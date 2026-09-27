"""Domain exceptions raised by services and translated to HTTP by api.errors.

Services never import the web framework (AGENTS.md §2), so they signal failure
with these instead of returning Response objects or status codes.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class. ``code`` is the stable machine-readable error code returned
    to clients; ``status_code`` is how api.errors maps it to HTTP."""

    code = "error"
    status_code = 400
    #: Extra response headers the HTTP layer should send with this error.
    headers: dict[str, str] | None = None

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class ValidationFailed(DomainError):
    code = "validation_error"
    status_code = 400


class NotAuthenticated(DomainError):
    code = "not_authenticated"
    status_code = 401
    headers = {"WWW-Authenticate": "Bearer"}  # noqa: RUF012 - read-only per class


class NotFound(DomainError):
    code = "not_found"
    status_code = 404


class ProviderNotConfigured(DomainError):
    code = "provider_not_configured"
    status_code = 503


class ProviderUnavailable(DomainError):
    code = "provider_unavailable"
    status_code = 502


class ProviderTimedOut(DomainError):
    code = "provider_timeout"
    status_code = 504


class UpstreamResponseInvalid(DomainError):
    """The provider answered, but not with something we can use."""

    code = "upstream_response_invalid"
    status_code = 502
