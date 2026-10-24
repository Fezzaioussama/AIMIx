"""Contract for turning an uploaded document into run-input text."""

from __future__ import annotations

from pydantic import BaseModel


class DocumentOut(BaseModel):
    """Response of POST /api/documents/extract."""

    filename: str
    #: Lower-case extension without the dot, e.g. "pdf".
    format: str
    text: str
    characters: int
    #: Page count for paged formats (PDF), else null.
    pages: int | None
    #: True when part of the document was left out (size or page limit).
    truncated: bool
