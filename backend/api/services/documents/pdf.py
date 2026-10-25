"""PDF: the text layer through pypdf, and OCR for the pages that have none.

A page is rendered (PDFium, through pypdfium2) only when OCR will read it, so a
PDF with a text layer never reaches PDFium. PDFium is not thread-safe and
endpoints run in a thread pool, so every PDFium call in the process takes one lock;
a page that waits too long for it is skipped rather than holding its reader up.
"""

from __future__ import annotations

import math
import threading
from contextlib import closing
from functools import partial
from io import BytesIO
from itertools import islice
from typing import Any

import pypdfium2 as pdfium  # type: ignore[import-untyped]
from PIL import Image
from pypdf import PasswordType, PdfReader

from api.exceptions import DocumentUnreadable, OcrTimedOut
from api.services.documents.contracts import ExtractionLimits, ReadContext, ReadResult
from api.services.documents.scans import PageOcr

#: PDF canvas units per inch.
_POINTS_PER_INCH = 72
#: PDFium allows one call at a time in a process, whatever the document.
_PDFIUM = threading.Lock()


def read_pdf(data: bytes, context: ReadContext) -> ReadResult:
    reader = PdfReader(BytesIO(data), strict=False)
    if reader.is_encrypted and reader.decrypt("") == PasswordType.NOT_DECRYPTED:
        raise DocumentUnreadable("This PDF is password-protected. Remove the password first.")
    limits = context.limits
    total = len(reader.pages)
    scans = PageOcr(context)
    parts: list[str] = []
    length = 0
    with closing(_Renderer(data, limits)) as renderer:
        for index, page in enumerate(islice(reader.pages, limits.max_pages)):
            text = page.extract_text() or ""
            if not text.strip():
                text = scans.read(index + 1, partial(renderer.render, index))
            parts.append(text)
            length += len(text)
            if length > limits.max_chars:
                break  # the service truncates anyway; do not parse pages nobody will see
    return ReadResult(
        "\n\n".join(parts),
        pages=total,
        cut_short=len(parts) < total,
        omissions=scans.omissions(),
        ocr_pages=scans.pages_read,
    )


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
