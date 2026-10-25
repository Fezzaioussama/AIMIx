"""OCR across the pages of one document: which pages it may read, and what the text
says about the ones it skips. Shared by the PDF and image readers (§3)."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from enum import Enum
from typing import TYPE_CHECKING

from api.exceptions import DocumentUnreadable, OcrTimedOut
from api.services.documents.contracts import OcrEngine, ReadContext

if TYPE_CHECKING:
    from PIL import Image


class Skipped(Enum):
    """Why a page that needed OCR was not read. The value is said in the text."""

    UNAVAILABLE = "no text layer, and OCR is not available"
    OVER_LIMIT = "OCR reads at most {pages} pages per document"
    OUT_OF_TIME = "OCR spends at most {seconds:g} seconds per document"
    TIMED_OUT = "OCR took too long"
    FAILED = "OCR failed"


class PageOcr:
    """Sends pages to the OCR engine, up to the document's OCR page and time limits.

    A page is rendered only when it will really be read, so a skipped page costs
    nothing. One instance per document: it counts that document's pages and time.
    The time limit is checked before each page, so the last page read may end past
    it by at most one page's OCR timeout.
    """

    def __init__(self, context: ReadContext) -> None:
        self._engine = context.ocr
        self._pages = context.limits.max_ocr_pages
        self._seconds = context.limits.ocr_max_seconds
        self.pages_read = 0
        self._spent = 0.0
        self._skipped: dict[Skipped, list[int]] = {}

    def read(self, number: int, render: Callable[[], Image.Image]) -> str:
        """Page ``number``'s text, or "" when it is skipped (and remembered).

        One page OCR fails on is skipped, not the document. A page that cannot be
        rendered (e.g. over the pixel limit) refuses the document: that is the file.
        """
        engine = self._engine
        if engine is None:
            return self._skip(Skipped.UNAVAILABLE, number)
        if self.pages_read >= self._pages:
            return self._skip(Skipped.OVER_LIMIT, number)
        if self._spent >= self._seconds:
            return self._skip(Skipped.OUT_OF_TIME, number)
        self.pages_read += 1
        started = time.monotonic()
        try:
            return self._recognise(engine, number, render)
        finally:
            self._spent += time.monotonic() - started

    def omissions(self) -> tuple[str, ...]:
        """One sentence per reason pages were skipped, naming the pages."""
        return tuple(
            f"Not read: {_page_list(numbers)} "
            f"({reason.value.format(pages=self._pages, seconds=self._seconds)})."
            for reason, numbers in self._skipped.items()
        )

    def _recognise(self, engine: OcrEngine, number: int, render: Callable[[], Image.Image]) -> str:
        try:
            image = render()
        except OcrTimedOut:  # the PDF renderer stayed busy with another document
            return self._skip(Skipped.TIMED_OUT, number)
        try:
            return engine.read(image)
        except OcrTimedOut:
            return self._skip(Skipped.TIMED_OUT, number)
        except DocumentUnreadable:
            return self._skip(Skipped.FAILED, number)

    def _skip(self, reason: Skipped, number: int) -> str:
        self._skipped.setdefault(reason, []).append(number)
        return ""


def _page_list(numbers: Sequence[int]) -> str:
    """'page 4' or 'pages 1-3, 7', from ascending page numbers."""
    runs: list[tuple[int, int]] = []
    for number in numbers:
        if runs and number == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], number)
        else:
            runs.append((number, number))
    spans = ", ".join(str(first) if first == last else f"{first}-{last}" for first, last in runs)
    return f"{'page' if len(numbers) == 1 else 'pages'} {spans}"
