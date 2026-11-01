"""Contracts for turning an uploaded document, or what a link holds, into run-input text."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, StringConstraints

#: Longest link accepted, as browsers and most servers handle them.
PAGE_URL_MAX_LENGTH = 2048


class PageImportRequest(BaseModel):
    """Body of POST /api/documents/import-url."""

    url: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=PAGE_URL_MAX_LENGTH)
    ]


class DocumentOut(BaseModel):
    """Response of POST /api/documents/extract and POST /api/documents/import-url."""

    #: The uploaded file's name, or the address a link ended at after redirects.
    filename: str
    #: Lower-case extension without the dot, e.g. "pdf".
    format: str
    text: str
    characters: int
    #: Page count for paged formats (PDF pages, slides, TIFF pages), else null.
    pages: int | None
    #: True when part of the document was left out (a limit, or pages OCR skipped).
    truncated: bool
