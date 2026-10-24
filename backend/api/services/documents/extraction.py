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
from api.services.documents.contracts import ExtractedDocument, ExtractionLimits
from api.services.documents.readers import READERS

logger = logging.getLogger(__name__)

TRUNCATION_NOTE = "\n\n[Document truncated: the rest was not included.]"
_BLANK_RUNS = re.compile(r"\n{3,}")


def supported_extensions() -> list[str]:
    return sorted(READERS)


def _megabytes(size: int) -> str:
    return f"{size / 1_000_000:g} MB"


def _tidy(text: str) -> str:
    """Unix newlines, no trailing spaces, and at most one blank line in a row."""
    lines = (line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    return _BLANK_RUNS.sub("\n\n", "\n".join(lines)).strip()


def extract_document(filename: str, data: bytes, limits: ExtractionLimits) -> ExtractedDocument:
    """The text of ``data``, chosen by the extension of ``filename``.

    Raises UnsupportedDocument, DocumentTooLarge or DocumentUnreadable.
    """
    name = PurePath(filename.replace("\\", "/")).name or "document"
    suffix = PurePath(name).suffix.lower()
    reader = READERS.get(suffix)
    if reader is None:
        raise UnsupportedDocument(
            f"'{suffix or name}' files are not supported. "
            f"Use one of: {', '.join(supported_extensions())}."
        )
    if not data:
        raise DocumentUnreadable("The file is empty.")
    if len(data) > limits.max_bytes:
        raise DocumentTooLarge(f"The file is larger than the {_megabytes(limits.max_bytes)} limit.")

    started = time.monotonic()
    result = reader(data, limits)
    text = _tidy(result.text)
    if not text:
        raise DocumentUnreadable(
            "No text could be read from this file. A scanned document or an image "
            "needs OCR, which is not supported yet."
        )
    truncated = result.cut_short or len(text) > limits.max_chars
    if truncated:
        text = text[: limits.max_chars].rstrip() + TRUNCATION_NOTE
    logger.info(
        "documents.extracted format=%s bytes=%d chars=%d truncated=%s duration_ms=%d",
        suffix.lstrip("."),
        len(data),
        len(text),
        truncated,
        (time.monotonic() - started) * 1000,
    )
    return ExtractedDocument(name, suffix.lstrip("."), text, len(text), result.pages, truncated)
