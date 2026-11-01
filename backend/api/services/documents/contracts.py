"""Value objects shared by the document readers and the extraction service (§7 DTO),
and the OCR port they read images through (§5 D)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from PIL import Image


class SlotPool(Enum):
    """Whose turns a reading slot is (``gate``): each pool has slots of its own."""

    #: Uploads and links, read while a person waits for the answer.
    PEOPLE = "people"
    #: Agents reading workspace files: their OCR can hold a slot for minutes, so it
    #: never keeps a person's upload waiting.
    AGENTS = "agents"
    #: Links being downloaded and read: each holds a body of up to max_bytes.
    LINKS = "links"


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
    #: Documents read at once in the process by everyone of ``pool``.
    max_concurrent: int
    #: How long a document waits for its turn, or for the PDF renderer, before giving up.
    wait_seconds: float
    #: A PDF page with less text than this whose pictures cover most of it is read
    #: by OCR too (a scan with a page number on top); 0 never does.
    ocr_min_page_chars: int = 0
    pool: SlotPool = SlotPool.PEOPLE


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
    #: The page (from 1) a PDF is read from; the pages before it are not read at all.
    first_page: int = 1
    #: The caller reads on from where this read stops (an agent with start_page): a
    #: page OCR's page or time budget would skip ends the read instead of being named,
    #: so the next read, with a budget of its own, starts there.
    read_on: bool = False
    #: The charset the Content-Type header names, for what a link holds; else None.
    charset: str | None = None


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
    #: The last page in ``text``, for a reader that reads whole pages (PDF); else None.
    last_page: int | None = None


@dataclass(frozen=True)
class DocumentText:
    """A document's tidied text, and what was left out of it, before any note says
    so: the upload endpoint and the agents' workspace word those notes differently."""

    filename: str
    #: Lower-case extension without the dot, e.g. "pdf".
    format: str
    #: Cut at the character limit when longer (``clipped``).
    text: str
    pages: int | None
    #: The reader stopped before the end, e.g. after ``last_page`` or at a limit.
    cut_short: bool
    clipped: bool
    #: One sentence per gap inside the text, e.g. pages OCR skipped.
    omissions: tuple[str, ...]
    #: The last page in ``text``, for a PDF; else None.
    last_page: int | None = None


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
