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


class PermissionDenied(DomainError):
    code = "permission_denied"
    status_code = 403


class Throttled(DomainError):
    code = "throttled"
    status_code = 429

    def __init__(self, detail: str, retry_after: int) -> None:
        super().__init__(detail)
        self.headers = {"Retry-After": str(retry_after)}


class NotFound(DomainError):
    code = "not_found"
    status_code = 404


class Conflict(DomainError):
    """The request clashes with the resource's current state, e.g. deleting a
    run that is still running."""

    code = "conflict"
    status_code = 409


class BudgetExceeded(DomainError):
    """A run reached its spending limit: it stops, or cannot resume under that limit."""

    code = "budget_exceeded"
    status_code = 409


class TooManyRuns(DomainError):
    """The account already has as many runs active as it may (RUN_MAX_ACTIVE_PER_USER)."""

    code = "too_many_runs"
    status_code = 429

    def __init__(self, cap: int) -> None:
        super().__init__(
            f"You already have {cap} run{'' if cap == 1 else 's'} queued, running or "
            "waiting, the most one account may have at once. Wait for one to end, or stop one."
        )


class RunStillRunning(DomainError):
    """A caller waited RUN_WAIT_MAX_SECONDS for a run's end; the run goes on.
    Accepted, not failed: the client follows the run by its id."""

    code = "run_still_running"
    status_code = 202

    def __init__(self, run_id: int, waited_seconds: float) -> None:
        super().__init__(
            f"Run {run_id} is still going after {waited_seconds:g} s and continues in the "
            f"background. Follow it with GET /api/runs/{run_id}."
        )
        self.run_id = run_id


class ProviderNotConfigured(DomainError):
    code = "provider_not_configured"
    status_code = 503


class ProviderUnavailable(DomainError):
    code = "provider_unavailable"
    status_code = 502


class ToolUnavailable(DomainError):
    code = "tool_unavailable"
    status_code = 502


class ProviderTimedOut(DomainError):
    code = "provider_timeout"
    status_code = 504


class UpstreamResponseInvalid(DomainError):
    """The provider answered, but not with something we can use."""

    code = "upstream_response_invalid"
    status_code = 502


class DocumentTooLarge(DomainError):
    code = "document_too_large"
    status_code = 413


class UnsupportedDocument(DomainError):
    code = "unsupported_document"
    status_code = 415


class DocumentUnreadable(DomainError):
    """A supported file type whose content cannot be turned into text."""

    code = "document_unreadable"
    status_code = 422


class OcrTimedOut(DocumentUnreadable):
    """OCR gave up on one page. A multi-page reader skips that page; alone, it is a 422."""


class DocumentReadersBusy(DomainError):
    """Every document reader of the process stayed busy for as long as one may wait."""

    code = "documents_busy"
    status_code = 503

    def __init__(self, detail: str, retry_after: int) -> None:
        super().__init__(detail)
        self.headers = {"Retry-After": str(retry_after)}


class FileAlreadyExists(DomainError):
    """A write would replace a file that the caller did not ask to replace."""

    code = "file_exists"
    status_code = 409


class FileTooLarge(DomainError):
    code = "file_too_large"
    status_code = 413


class StorageQuotaExceeded(DomainError):
    """The write would take the user's files past WORKSPACE_MAX_TOTAL_BYTES."""

    code = "storage_quota_exceeded"
    status_code = 413


class UnsupportedFileType(DomainError):
    code = "unsupported_file_type"
    status_code = 415
