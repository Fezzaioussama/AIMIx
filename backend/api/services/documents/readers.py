"""One reader per file format, found through READERS (§5 O / §7 Strategy + Registry).

Adding a format is a new function and a registry entry, never another ``if``. The
third-party parsers behind these (pypdf, python-docx) are fed untrusted files, so
every reader runs inside ``_guarded``, which re-raises whatever they throw as our
own ``DocumentUnreadable`` (the §8 "adapter around a third-party library" case).
"""

from __future__ import annotations

import codecs
import logging
import zipfile
from collections.abc import Callable
from io import BytesIO
from itertools import islice

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PasswordType, PdfReader

from api.exceptions import DocumentUnreadable
from api.services.documents.contracts import ExtractionLimits, ReadResult
from api.services.toolbox.html_text import html_to_text

logger = logging.getLogger(__name__)

Reader = Callable[[bytes, ExtractionLimits], ReadResult]

TEXT_SUFFIXES = (
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml", ".xml", ".log", ".rst",
)  # fmt: skip
_BINARY_SNIFF_BYTES = 8192
_UTF16_BOMS = (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)
_W_P = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"
_W_TBL = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tbl"


def _guarded(kind: str, parse: Callable[[], ReadResult]) -> ReadResult:
    try:
        return parse()
    except DocumentUnreadable:
        raise
    except Exception as cause:  # third-party parsers raise anything on a hostile file
        logger.info("documents.unreadable kind=%s error=%s", kind, type(cause).__name__)
        raise DocumentUnreadable(
            f"This {kind} file could not be read. It may be damaged or not really a {kind}."
        ) from cause


def _decode(data: bytes) -> str:
    """Text from bytes: UTF-16 by its BOM, else UTF-8, else Windows-1252."""
    if data.startswith(_UTF16_BOMS):
        return data.decode("utf-16")
    if b"\x00" in data[:_BINARY_SNIFF_BYTES]:
        raise DocumentUnreadable("This file looks binary, not text.")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def read_text(data: bytes, limits: ExtractionLimits) -> ReadResult:
    return ReadResult(_decode(data))


def read_html(data: bytes, limits: ExtractionLimits) -> ReadResult:
    return _guarded("HTML", lambda: ReadResult(html_to_text(_decode(data))))


def read_pdf(data: bytes, limits: ExtractionLimits) -> ReadResult:
    return _guarded("PDF", lambda: _read_pdf(data, limits))


def _read_pdf(data: bytes, limits: ExtractionLimits) -> ReadResult:
    reader = PdfReader(BytesIO(data), strict=False)
    if reader.is_encrypted and reader.decrypt("") == PasswordType.NOT_DECRYPTED:
        raise DocumentUnreadable("This PDF is password-protected. Remove the password first.")
    total = len(reader.pages)
    parts: list[str] = []
    length = 0
    for page in islice(reader.pages, limits.max_pages):
        text = page.extract_text() or ""
        parts.append(text)
        length += len(text)
        if length > limits.max_chars:
            break  # the service truncates anyway; do not parse pages nobody will see
    return ReadResult("\n\n".join(parts), pages=total, cut_short=len(parts) < total)


def read_docx(data: bytes, limits: ExtractionLimits) -> ReadResult:
    return _guarded("Word", lambda: _read_docx(data, limits))


def _check_unpacked_size(data: bytes, limit: int) -> None:
    """Refuse a zip bomb before any XML is parsed."""
    with zipfile.ZipFile(BytesIO(data)) as archive:
        if sum(member.file_size for member in archive.infolist()) > limit:
            raise DocumentUnreadable("This Word file is too large once unpacked.")


def _read_docx(data: bytes, limits: ExtractionLimits) -> ReadResult:
    _check_unpacked_size(data, limits.max_unpacked_bytes)
    document = Document(BytesIO(data))
    blocks: list[str] = []
    # Walk the body in order, so a table stays between the paragraphs around it.
    for child in document.element.body.iterchildren():
        if child.tag == _W_P:
            blocks.append(Paragraph(child, document).text)
        elif child.tag == _W_TBL:
            blocks.extend(_table_rows(Table(child, document)))
    return ReadResult("\n".join(blocks))


def _table_rows(table: Table) -> list[str]:
    rows: list[str] = []
    for row in table.rows:
        # A merged cell is reported once per column it spans; keep it once.
        cells = {id(cell._tc): cell.text.strip() for cell in row.cells}
        rows.append(" | ".join(cells.values()))
    return rows


READERS: dict[str, Reader] = {
    ".pdf": read_pdf,
    ".docx": read_docx,
    ".html": read_html,
    ".htm": read_html,
    **dict.fromkeys(TEXT_SUFFIXES, read_text),
}
