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
    ExtractedDocument,
    ExtractionLimits,
    OcrEngine,
    ReadContext,
    ReadResult,
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
    and for a file an agent reads from the workspace alike."""
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
    )


def megabytes(size: int) -> str:
    """A byte count as people read a limit, e.g. ``10 MB``."""
    return f"{size / 1_000_000:g} MB"


def _tidy(text: str) -> str:
    """Unix newlines, no trailing spaces, and at most one blank line in a row."""
    lines = (line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    return _BLANK_RUNS.sub("\n\n", "\n".join(lines)).strip()


def _reader(name: str, suffix: str) -> Reader:
    reader = READERS.get(suffix)
    if reader is None:
        raise UnsupportedDocument(
            f"'{suffix or name}' files are not supported. "
            f"Use one of: {', '.join(supported_extensions())}."
        )
    return reader


def _finish(result: ReadResult, max_chars: int) -> tuple[str, bool]:
    """The text to return, and whether part of the document was left out.

    Each omission (e.g. pages OCR skipped) is said in the text, so the model knows.
    """
    text = _tidy(result.text)
    if not text:
        raise DocumentUnreadable(" ".join((NO_TEXT, *result.omissions)))
    cut = result.cut_short or len(text) > max_chars
    if cut:
        text = text[:max_chars].rstrip() + TRUNCATION_NOTE
    text += "".join(f"\n\n[{omission}]" for omission in result.omissions)
    return text, cut or bool(result.omissions)


def extract_document(
    filename: str, data: bytes, limits: ExtractionLimits, ocr: OcrEngine | None = None
) -> ExtractedDocument:
    """The text of ``data``, chosen by the extension of ``filename``.

    ``ocr`` reads scanned pages and images; without it they are skipped, and said so.
    Raises UnsupportedDocument, DocumentTooLarge or DocumentUnreadable, and
    DocumentReadersBusy when the process is already reading as many documents as
    it may and none finishes in time.
    """
    name = PurePath(filename.replace("\\", "/")).name or "document"
    suffix = PurePath(name).suffix.lower()
    reader = _reader(name, suffix)
    if not data:
        raise DocumentUnreadable("The file is empty.")
    if len(data) > limits.max_bytes:
        raise DocumentTooLarge(f"The file is larger than the {megabytes(limits.max_bytes)} limit.")

    with extraction_slot(limits.max_concurrent, limits.wait_seconds):
        started = time.monotonic()
        result = reader(data, ReadContext(limits, ocr))
    text, truncated = _finish(result, limits.max_chars)
    logger.info(
        "documents.extracted format=%s bytes=%d chars=%d truncated=%s ocr_pages=%d duration_ms=%d",
        suffix.lstrip("."),
        len(data),
        len(text),
        truncated,
        result.ocr_pages,
        (time.monotonic() - started) * 1000,
    )
    return ExtractedDocument(name, suffix.lstrip("."), text, len(text), result.pages, truncated)
