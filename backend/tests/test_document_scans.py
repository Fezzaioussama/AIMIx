"""Scanned and mixed PDFs, read through the OCR port. A fake engine stands in for
Tesseract; the PDFs are made with Pillow and pypdf, so the real parser and PDF
renderer run. The helpers here are shared with test_document_images.py."""

from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from api.exceptions import DocumentUnreadable, OcrTimedOut
from api.services.documents import pdf
from api.services.documents.extraction import TRUNCATION_NOTE, extract_document
from tests.test_documents import LIMITS, make_pdf

#: Room for a few scanned pages; LIMITS reads at most 3.
ROOMY = replace(LIMITS, max_pages=10, max_ocr_pages=10)


class FakeOcr:
    """Implements the OcrEngine port: numbers what it reads and keeps each image.

    ``errors`` maps a call number (from 1) to the error that call raises.
    """

    def __init__(self, errors: dict[int, DocumentUnreadable] | None = None) -> None:
        self.images: list[Image.Image] = []
        self.errors = errors or {}

    def read(self, image: Image.Image) -> str:
        self.images.append(image)
        if len(self.images) in self.errors:
            raise self.errors[len(self.images)]
        return f"Recognised text {len(self.images)}"


def page(size: tuple[int, int] = (200, 100), mode: str = "RGB") -> Image.Image:
    return Image.new(mode, size, "white")


def encoded(image: Image.Image, encoder: str, **options: object) -> bytes:
    buffer = BytesIO()
    image.save(buffer, encoder, **options)
    return buffer.getvalue()


def frames(encoder: str, count: int) -> bytes:
    """A multi-frame file: the pages of a TIFF or PDF, or the frames of a GIF."""
    images = [page() for _ in range(count)]
    return encoded(images[0], encoder, save_all=True, append_images=images[1:])


def scanned_pdf(pages: int) -> bytes:
    """A PDF whose pages are only pictures, as a scanner makes them: no text layer."""
    return frames("PDF", pages)


def mixed_pdf() -> bytes:
    """Typed page, scanned page, typed page."""
    typed = PdfReader(BytesIO(make_pdf(["Typed first page", "Typed last page"]))).pages
    writer = PdfWriter()
    writer.add_page(typed[0])
    writer.add_page(PdfReader(BytesIO(scanned_pdf(1))).pages[0])
    writer.add_page(typed[1])
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_a_scanned_pdf_is_read_by_ocr_page_by_page() -> None:
    ocr = FakeOcr()
    result = extract_document("scan.pdf", scanned_pdf(2), LIMITS, ocr)
    assert result.text == "Recognised text 1\n\nRecognised text 2"
    assert (result.pages, result.truncated) == (2, False)
    assert [image.mode for image in ocr.images] == ["L", "L"]


def test_a_mixed_pdf_keeps_its_text_layer_and_reads_only_the_scanned_page() -> None:
    ocr = FakeOcr()
    result = extract_document("mixed.pdf", mixed_pdf(), LIMITS, ocr)
    assert result.text.splitlines() == [
        "Typed first page",
        "",
        "Recognised text 1",
        "",
        "Typed last page",
    ]
    assert len(ocr.images) == 1


def test_a_pdf_with_a_text_layer_never_reaches_pdfium(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object) -> None:
        raise AssertionError("PDFium opened a PDF that needed no OCR")

    monkeypatch.setattr(pdf.pdfium, "PdfDocument", refuse)
    ocr = FakeOcr()
    assert extract_document("typed.pdf", make_pdf(["Typed"]), LIMITS, ocr).text == "Typed"
    assert ocr.images == []


def test_a_scanned_page_is_rendered_at_the_ocr_resolution() -> None:
    ocr = FakeOcr()
    # Pillow writes a 200 x 100 pixel picture as a 200 x 100 point page (72 dpi).
    extract_document("scan.pdf", scanned_pdf(1), replace(LIMITS, ocr_dpi=144), ocr)
    assert ocr.images[0].size == (400, 200)


def test_a_huge_page_is_rendered_within_the_pixel_limit() -> None:
    ocr = FakeOcr()
    limits = replace(LIMITS, ocr_dpi=300, max_image_pixels=10_000)
    extract_document("scan.pdf", scanned_pdf(1), limits, ocr)
    width, height = ocr.images[0].size
    # The renderer rounds each side up, so allow one pixel per row and column.
    assert width * height <= 10_000 + width + height + 1
    assert width == 2 * height


def test_ocr_stops_at_its_page_limit_and_names_the_pages_it_skipped() -> None:
    ocr = FakeOcr()
    result = extract_document("scan.pdf", scanned_pdf(5), replace(ROOMY, max_ocr_pages=2), ocr)
    assert len(ocr.images) == 2
    assert result.text.endswith(
        "Recognised text 2\n\n[Not read: pages 3-5 (OCR reads at most 2 pages per document).]"
    )
    assert result.truncated is True


def test_a_page_ocr_gives_up_on_is_skipped_and_named() -> None:
    ocr = FakeOcr({2: OcrTimedOut("Too slow.")})
    result = extract_document("scan.pdf", scanned_pdf(3), ROOMY, ocr)
    assert result.text == (
        "Recognised text 1\n\nRecognised text 3\n\n[Not read: page 2 (OCR took too long).]"
    )
    assert result.truncated is True


def test_a_page_ocr_fails_on_is_skipped_not_the_document() -> None:
    ocr = FakeOcr({1: DocumentUnreadable("Text recognition (OCR) failed on this file.")})
    result = extract_document("mixed.pdf", mixed_pdf(), LIMITS, ocr)
    assert result.text == (
        "Typed first page\n\nTyped last page\n\n[Not read: page 2 (OCR failed).]"
    )
    assert result.truncated is True


def test_without_ocr_a_scanned_pdf_is_refused_and_says_why() -> None:
    with pytest.raises(DocumentUnreadable) as refusal:
        extract_document("scan.pdf", scanned_pdf(2), LIMITS)
    assert refusal.value.detail == (
        "No text could be read from this file. "
        "Not read: pages 1-2 (no text layer, and OCR is not available)."
    )


def test_without_ocr_a_mixed_pdf_keeps_its_text_and_names_the_gap() -> None:
    result = extract_document("mixed.pdf", mixed_pdf(), LIMITS)
    assert result.text == (
        "Typed first page\n\nTyped last page\n\n"
        "[Not read: page 2 (no text layer, and OCR is not available).]"
    )
    assert result.truncated is True


def test_the_page_limit_still_applies_before_ocr() -> None:
    ocr = FakeOcr()
    result = extract_document("scan.pdf", scanned_pdf(5), LIMITS, ocr)
    assert len(ocr.images) == LIMITS.max_pages
    assert result.text.endswith(TRUNCATION_NOTE.strip())
