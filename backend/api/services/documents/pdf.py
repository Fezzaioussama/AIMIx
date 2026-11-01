"""PDF: the text layer through pypdf, OCR for the pages that are scans, and what a
page shows outside its text layer (filled form fields, comments; ``pdf_page``).

A page is a scan when it has no text layer, or when its text layer is thin (under
``ocr_min_page_chars``) and small print (a page number, a scanner app's footer, not
a slide's title) and pictures cover most of it; OCR's text then follows those few
words. A page is rendered (PDFium, through pypdfium2) only when OCR will read it,
so a page with a real text layer never reaches PDFium. PDFium is not
thread-safe and endpoints run in a thread pool, so every PDFium call in the process
takes one lock; a page that waits too long for it is skipped rather than holding
its reader up.

Pages are read from ``first_page`` and kept whole: reading stops before a page that
would take the text past ``max_chars``, so a later read can start there, and, for a
caller that reads on (``read_on``), before a page OCR's budget skipped. Only a first
page that is longer than that on its own is kept, for the service to cut.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Iterable
from contextlib import closing
from functools import partial
from io import BytesIO
from itertools import islice
from typing import Any

import pypdfium2 as pdfium  # type: ignore[import-untyped]
from PIL import Image
from pypdf import PageObject, PasswordType, PdfReader

from api.exceptions import DocumentUnreadable, OcrTimedOut
from api.services.documents.contracts import ExtractionLimits, ReadContext, ReadResult
from api.services.documents.pdf_page import PageMarks, largest_print, picture_share
from api.services.documents.scans import PageOcr, no_such_page

#: PDF canvas units per inch.
_POINTS_PER_INCH = 72
#: PDFium allows one call at a time in a process, whatever the document.
_PDFIUM = threading.Lock()
#: Between two pages in the text.
_PAGE_BREAK = "\n\n"
#: A thin text layer over pictures that cover more than this share of the page is a scan...
_MOST_OF_THE_PAGE = 0.5
#: ...when it is no larger than this, in points: a page number or a footer, not a title.
_SMALL_PRINT = 14.0


def page_count(data: bytes) -> int:
    """How many pages a PDF has, so an agent asked for one page can tell."""
    return len(PdfReader(BytesIO(data), strict=False).pages)


def read_pdf(data: bytes, context: ReadContext) -> ReadResult:
    reader = PdfReader(BytesIO(data), strict=False)
    if reader.is_encrypted and reader.decrypt("") == PasswordType.NOT_DECRYPTED:
        raise DocumentUnreadable("This PDF is password-protected. Remove the password first.")
    limits = context.limits
    total = len(reader.pages)
    first = context.first_page
    if first > max(total, 1):
        raise DocumentUnreadable(no_such_page("This PDF", total, first))
    window = islice(reader.pages, first - 1, first - 1 + limits.max_pages)
    with closing(_Renderer(data, limits)) as renderer:
        page_text = _PageText(context, renderer)
        parts = _whole_pages(window, first, page_text, limits.max_chars)
    last = first + len(parts) - 1
    return ReadResult(
        _PAGE_BREAK.join(parts),
        pages=total,
        cut_short=last < total,
        omissions=page_text.scans.omissions(last),
        ocr_pages=page_text.scans.pages_read,
        last_page=last,
    )


def _whole_pages(
    pages: Iterable[PageObject], first: int, page_text: _PageText, budget: int
) -> list[str]:
    """The text of each page from page ``first`` on, while they fit in ``budget``
    characters together (and OCR's budget, for a caller that reads on); the first is
    kept even when it alone is longer."""
    parts: list[str] = []
    size = 0
    for number, page in enumerate(pages, start=first):
        text = page_text(number, page)
        size += len(text) + (len(_PAGE_BREAK) if parts else 0)
        if parts and (size > budget or page_text.left_for_later):
            break  # left whole for a later read
        parts.append(text)
        if size >= budget:
            break  # no other page fits: do not parse pages nobody will see
    return parts


class _PageText:
    """One page's text: its text layer, or OCR's when the page is a scan, then its
    filled form fields and comments, one per line."""

    def __init__(self, context: ReadContext, renderer: _Renderer) -> None:
        self.scans = PageOcr(context)
        self._renderer = renderer
        self._min_chars = context.limits.ocr_min_page_chars
        self._read_on = context.read_on
        self._marks = PageMarks()

    @property
    def left_for_later(self) -> bool:
        """The caller reads on, and OCR's budget skipped the page just read: the next
        read, with a budget of its own, starts there."""
        return self._read_on and self.scans.budget_spent

    def __call__(self, number: int, page: PageObject) -> str:
        content = self._content(number, page).rstrip()
        return "\n".join(filter(None, (content, *self._marks.lines(page))))

    def _content(self, number: int, page: PageObject) -> str:
        text = page.extract_text() or ""
        render = partial(self._renderer.render, number - 1)
        found = text.strip()
        if not found:
            return self.scans.read(number, render)
        # A real text layer is never measured, rendered or OCR'd.
        if len(found) < self._min_chars and _stamped_scan(page):
            return self.scans.read(number, render, found=text)
        return text


def _stamped_scan(page: PageObject) -> bool:
    """Whether a page with little text is a scan a scanner stamped: pictures cover
    most of it, and its text is small print (a slide's title over a photo is not)."""
    return picture_share(page) > _MOST_OF_THE_PAGE and largest_print(page) <= _SMALL_PRINT


class _Renderer:
    """Renders pages of one PDF as gray images; opens it in PDFium only when asked."""

    def __init__(self, data: bytes, limits: ExtractionLimits) -> None:
        self._data = data
        self._limits = limits
        self._document: Any = None

    def render(self, index: int) -> Image.Image:
        """Page ``index`` as an image. Raises OcrTimedOut when another document
        keeps PDFium busy past ``wait_seconds``: the page is skipped, and named."""
        wait = self._limits.wait_seconds
        if not _PDFIUM.acquire(timeout=wait):
            raise OcrTimedOut(f"The PDF renderer stayed busy for {wait:g} seconds.")
        try:
            return self._render(index)
        finally:
            _PDFIUM.release()

    def close(self) -> None:
        # Closed here, under the lock: left to the garbage collector, PDFium would
        # be called from whichever thread happens to collect it. This waits as long
        # as it takes, for at most the one page being rendered (bounded in pixels).
        if self._document is not None:
            with _PDFIUM:
                self._document.close()

    def _render(self, index: int) -> Image.Image:
        """Page ``index`` rendered gray; the caller holds the PDFium lock."""
        if self._document is None:
            self._document = pdfium.PdfDocument(self._data)
        page = self._document[index]
        try:
            bitmap = page.render(scale=self._scale(*page.get_size()), grayscale=True)
            try:
                # A native bitmap's buffer outlives close(): the image keeps it alive.
                image: Image.Image = bitmap.to_pil()
                return image
            finally:
                bitmap.close()
        finally:
            page.close()

    def _scale(self, width: float, height: float) -> float:
        """ocr_dpi, or less when the page would otherwise exceed max_image_pixels."""
        area = max(width * height, 1.0)
        return min(
            self._limits.ocr_dpi / _POINTS_PER_INCH,
            math.sqrt(self._limits.max_image_pixels / area),
        )
