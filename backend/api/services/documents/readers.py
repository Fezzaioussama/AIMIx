"""One reader per file format, found through READERS (§5 O / §7 Strategy + Registry).

Adding a format is a new function and a registry entry, never another ``if``. The
third-party parsers behind these (pypdf, PDFium, Pillow, python-docx, openpyxl,
python-pptx) are fed untrusted files, so their readers are registered through
``guarded``, which re-raises whatever they throw as our own ``DocumentUnreadable``
(the §8 "adapter around a third-party library" case). The formats live in pdf.py,
images.py and office.py; plain text and HTML, which need no third-party parser,
live here.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from api.exceptions import DocumentUnreadable, DomainError
from api.services.documents.contracts import ReadContext, ReadResult
from api.services.documents.images import IMAGE_SUFFIXES, read_image
from api.services.documents.office import read_docx, read_pptx, read_xlsx
from api.services.documents.pdf import read_pdf
from api.services.toolbox.html_text import decode_page, html_to_text, page_charset, text_charset

logger = logging.getLogger(__name__)

Reader = Callable[[bytes, ReadContext], ReadResult]

TEXT_SUFFIXES = (
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml", ".xml", ".log", ".rst",
)  # fmt: skip
_BINARY_SNIFF_BYTES = 8192


def guarded(kind: str, read: Reader) -> Reader:
    """``read``, with anything its parser throws on a hostile file made a DocumentUnreadable."""

    def guarded_read(data: bytes, context: ReadContext) -> ReadResult:
        try:
            return read(data, context)
        except DomainError:
            raise
        except Exception as cause:  # third-party parsers raise anything on a hostile file
            logger.info("documents.unreadable kind=%s error=%s", kind, type(cause).__name__)
            raise DocumentUnreadable(
                f"This {kind} file could not be read. It may be damaged or in another format."
            ) from cause

    return guarded_read


def _decode(data: bytes, charset: str | None) -> str:
    """Text from bytes: in ``charset`` when something named one (``html_text``'s
    rules), else UTF-8, else Windows-1252. A damaged file in a named charset (a UTF-16
    file with an odd byte at the end) keeps its readable text, with U+FFFD where it is
    damaged, as Windows-1252 does for stray bytes."""
    if charset:
        return decode_page(data, charset)
    if b"\x00" in data[:_BINARY_SNIFF_BYTES]:
        raise DocumentUnreadable("This file looks binary, not text.")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def read_text(data: bytes, context: ReadContext) -> ReadResult:
    return ReadResult(_decode(data, text_charset(data, context.charset)))


def read_html(data: bytes, context: ReadContext) -> ReadResult:
    return ReadResult(html_to_text(_decode(data, page_charset(data, context.charset))))


READERS: dict[str, Reader] = {
    ".pdf": guarded("PDF", read_pdf),
    ".docx": guarded("Word", read_docx),
    ".xlsx": guarded("Excel", read_xlsx),
    ".pptx": guarded("PowerPoint", read_pptx),
    ".html": guarded("HTML", read_html),
    ".htm": guarded("HTML", read_html),
    **dict.fromkeys(IMAGE_SUFFIXES, guarded("image", read_image)),
    **dict.fromkeys(TEXT_SUFFIXES, read_text),
}
