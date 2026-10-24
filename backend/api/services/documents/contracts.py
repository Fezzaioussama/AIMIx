"""Value objects shared by the document readers and the extraction service (§7 DTO)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractionLimits:
    """What one extraction may cost; every value comes from settings (§6)."""

    max_bytes: int
    max_chars: int
    max_pages: int
    max_unpacked_bytes: int


@dataclass(frozen=True)
class ReadResult:
    """What a reader found, before the service tidies and truncates it."""

    text: str
    #: Page count for paged formats, else None.
    pages: int | None = None
    #: True when the reader stopped early (e.g. at the page limit).
    cut_short: bool = False


@dataclass(frozen=True)
class ExtractedDocument:
    filename: str
    #: Lower-case extension without the dot, e.g. "pdf".
    format: str
    text: str
    characters: int
    pages: int | None
    #: True when part of the document was left out.
    truncated: bool
