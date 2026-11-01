"""Extract plain text from an uploaded document (orchestration; formats live in readers.py).

Stateless on purpose (§6): the text goes back to the client, which sends it as an
ordinary run input. Nothing is stored, so there is no cleanup and no way for one
user to reach another's file. Never logs a file's name or content (§6).
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import PurePath

from api.exceptions import DocumentTooLarge, DocumentUnreadable, UnsupportedDocument
from api.services.documents.contracts import (
    DocumentText,
    ExtractedDocument,
    ExtractionLimits,
    OcrEngine,
    ReadContext,
)
from api.services.documents.gate import extraction_slot
from api.services.documents.readers import READERS, Reader
from config.settings import Settings

logger = logging.getLogger(__name__)

TRUNCATION_NOTE = "\n\n[Document truncated: the rest was not included.]"
NO_TEXT = "No text could be read from this file."
_BLANK_RUNS = re.compile(r"\n{3,}")


def supported_extensions() -> list[str]:
    return sorted(READERS)


def extraction_limits(settings: Settings) -> ExtractionLimits:
    """What one extraction may cost, from settings: for an uploaded run document
    and for a file an agent reads from the workspace alike (``toolbox_config`` gives
    agents reading slots of their own)."""
    return ExtractionLimits(
        max_bytes=settings.document_max_bytes,
        max_chars=settings.document_max_chars,
        max_pages=settings.document_max_pages,
        max_unpacked_bytes=settings.document_max_unpacked_bytes,
        max_xml_part_bytes=settings.document_max_xml_part_bytes,
        max_image_pixels=settings.document_max_image_pixels,
        max_spreadsheet_rows=settings.document_max_spreadsheet_rows,
        max_ocr_pages=settings.document_ocr_max_pages,
        ocr_max_seconds=settings.document_ocr_max_seconds,
        ocr_dpi=settings.document_ocr_dpi,
        max_concurrent=settings.document_max_concurrent_extractions,
        wait_seconds=settings.document_extraction_wait_seconds,
        ocr_min_page_chars=settings.document_ocr_min_page_chars,
    )


def megabytes(size: int) -> str:
    """A byte count as people read a limit, e.g. ``10 MB``."""
    return f"{size / 1_000_000:g} MB"


def _tidy(text: str) -> str:
    """Unix newlines, no trailing spaces, at most one blank line in a row, and no NUL
    or leading byte-order mark (some PDFs' text layers hold them; a model cannot use them)."""
    text = text.replace("\x00", "").removeprefix("\ufeff")
    lines = (line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    return _BLANK_RUNS.sub("\n\n", "\n".join(lines)).strip()


def omission_notes(omissions: tuple[str, ...]) -> str:
    """Each omission as a note of its own after the text, so the model knows."""
    return "".join(f"\n\n[{omission}]" for omission in omissions)


def _reader(name: str, suffix: str) -> Reader:
    reader = READERS.get(suffix)
    if reader is None:
        raise UnsupportedDocument(
            f"'{suffix or name}' files are not supported. "
            f"Use one of: {', '.join(supported_extensions())}."
        )
    return reader


def extract_document(
    filename: str, data: bytes, limits: ExtractionLimits, ocr: OcrEngine | None = None
) -> ExtractedDocument:
    """The text of ``data``, chosen by the extension of ``filename``, ending with a
    note on whatever was left out (TRUNCATION_NOTE, pages OCR skipped).

    ``ocr`` reads scanned pages and images; without it they are skipped, and said so.
    Raises what ``read_document`` raises.
    """
    return with_notes(read_document(filename, data, ReadContext(limits, ocr)))


def with_notes(document: DocumentText) -> ExtractedDocument:
    """``document`` as an upload returns it: its text ending with a note on whatever
    was left out (TRUNCATION_NOTE, pages OCR skipped)."""
    cut = document.cut_short or document.clipped
    text = document.text + (TRUNCATION_NOTE if cut else "") + omission_notes(document.omissions)
    truncated = cut or bool(document.omissions)
    return ExtractedDocument(
        document.filename, document.format, text, len(text), document.pages, truncated
    )


def read_document(filename: str, data: bytes, context: ReadContext) -> DocumentText:
    """The text of ``data``, chosen by the extension of ``filename``, from
    ``context.first_page`` on for a PDF, and what was left out; the caller words it.

    Raises UnsupportedDocument, DocumentTooLarge or DocumentUnreadable, and
    DocumentReadersBusy when the process is already reading as many documents as
    it may and none finishes in time.
    """
    name = PurePath(filename.replace("\\", "/")).name or "document"
    suffix = PurePath(name).suffix.lower()
    reader = _reader(name, suffix)
    limits = context.limits
    if not data:
        raise DocumentUnreadable("The file is empty.")
    if len(data) > limits.max_bytes:
        raise DocumentTooLarge(f"The file is larger than the {megabytes(limits.max_bytes)} limit.")

    with extraction_slot(limits.max_concurrent, limits.wait_seconds, limits.pool):
        started = time.monotonic()
        result = reader(data, context)
    text = _tidy(result.text)
    if not text:
        raise DocumentUnreadable(" ".join((NO_TEXT, *result.omissions)))
    clipped = len(text) > limits.max_chars
    logger.info(
        "documents.extracted format=%s bytes=%d chars=%d truncated=%s ocr_pages=%d duration_ms=%d",
        suffix.lstrip("."),
        len(data),
        min(len(text), limits.max_chars),
        clipped or result.cut_short or bool(result.omissions),
        result.ocr_pages,
        (time.monotonic() - started) * 1000,
    )
    shown = text[: limits.max_chars].rstrip() if clipped else text
    return DocumentText(
        name,
        suffix.lstrip("."),
        shown,
        result.pages,
        cut_short=result.cut_short,
        clipped=clipped,
        omissions=result.omissions,
        last_page=result.last_page,
    )
