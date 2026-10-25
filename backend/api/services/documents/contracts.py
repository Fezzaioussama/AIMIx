"""Value objects shared by the document readers and the extraction service (§7 DTO),
and the OCR port they read images through (§5 D)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from PIL import Image


@dataclass(frozen=True)
class ExtractionLimits:
    """What one extraction may cost, and how many may run at once; every value
    comes from settings (§6)."""

    max_bytes: int
    max_chars: int
    #: Pages of a PDF, slides of a deck or frames of a TIFF read before stopping.
    max_pages: int
    max_unpacked_bytes: int
    #: An Office part this large is refused unless it is a picture or other media.
    max_xml_part_bytes: int
    #: An image, or a PDF page rendered for OCR, never has more pixels than this.
    max_image_pixels: int
    #: Rows read from one workbook, across all its sheets.
    max_spreadsheet_rows: int
    #: Pages one document may send to OCR; the rest are skipped and named.
    max_ocr_pages: int
    #: Time all the OCR of one document may take; later pages are skipped and named.
    ocr_max_seconds: float
    #: Resolution a PDF page is rendered at for OCR (lower if over max_image_pixels).
    ocr_dpi: int
    #: Documents read at once in the process, whoever asks.
    max_concurrent: int
    #: How long a document waits for its turn, or for the PDF renderer, before giving up.
    wait_seconds: float


class OcrEngine(Protocol):
    """The text in one page image (§5 D: readers depend on this, not on Tesseract).

    Returns "" for a page with no text. Raises OcrTimedOut when the page takes too
    long, and DocumentUnreadable when the engine fails on it.
    """

    def read(self, image: Image.Image) -> str: ...


@dataclass(frozen=True)
class ReadContext:
    """What a reader is given besides the file."""

    limits: ExtractionLimits
    #: None when OCR is turned off or not installed: pages that need it are skipped.
    ocr: OcrEngine | None = None


@dataclass(frozen=True)
class ReadResult:
    """What a reader found, before the service tidies and truncates it."""

    text: str
    #: Page count for paged formats, else None.
    pages: int | None = None
    #: True when the reader stopped early (e.g. at the page limit).
    cut_short: bool = False
    #: One sentence per gap in the text, e.g. pages OCR skipped; the service adds them.
    omissions: tuple[str, ...] = ()
    #: Pages sent to OCR, for the log.
    ocr_pages: int = 0


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
