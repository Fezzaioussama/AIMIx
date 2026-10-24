"""Scanned PDFs and images, read through the OCR port. A fake engine stands in for
Tesseract; the PDFs and images are made with Pillow and pypdf, so the real parsers,
PDF renderer and image decoders run."""

from __future__ import annotations

import struct
import zlib
from dataclasses import replace
from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, TiffImagePlugin
from pypdf import PdfReader, PdfWriter

from api.deps import document_ocr
from api.exceptions import DocumentUnreadable, OcrTimedOut
from api.services.documents import pdf
from api.services.documents.extraction import TRUNCATION_NOTE, extract_document
from api.services.documents.images import IMAGE_SUFFIXES
from tests.test_documents import LIMITS, make_pdf, upload

#: Room for a few scanned pages; LIMITS reads at most 3.
ROOMY = replace(LIMITS, max_pages=10, max_ocr_pages=10)
#: The Pillow encoder behind each image extension.
ENCODERS = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP", ".tif": "TIFF"}
ENCODERS |= {".tiff": "TIFF", ".bmp": "BMP", ".gif": "GIF"}


class FakeOcr:
    """Implements the OcrEngine port: numbers what it reads and keeps each image."""

    def __init__(self, time_out_on: int | None = None) -> None:
        self.images: list[Image.Image] = []
        self.time_out_on = time_out_on

    def read(self, image: Image.Image) -> str:
        self.images.append(image)
        if len(self.images) == self.time_out_on:
            raise OcrTimedOut("Too slow.")
        return f"Recognised text {len(self.images)}"


def page(size: tuple[int, int] = (200, 100), mode: str = "RGB") -> Image.Image:
    return Image.new(mode, size, "white")


def encoded(image: Image.Image, encoder: str, **options: object) -> bytes:
    buffer = BytesIO()
    image.save(buffer, encoder, **options)
    return buffer.getvalue()


def frames(encoder: str, count: int) -> bytes:
    """A multi-frame file: the pages of a TIFF, or the frames of an animated GIF."""
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


def png_header(width: int, height: int) -> bytes:
    """A PNG that declares its size but holds almost no pixels: decoding it would fail."""

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    pixels = zlib.compress(b"\x00" * 10)
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")
    )


# --- scanned and mixed PDFs ------------------------------------------------------


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
    result = extract_document("scan.pdf", scanned_pdf(3), ROOMY, FakeOcr(time_out_on=2))
    assert result.text == (
        "Recognised text 1\n\nRecognised text 3\n\n[Not read: page 2 (OCR took too long).]"
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


# --- images ------------------------------------------------------------------------


@pytest.mark.parametrize("suffix", IMAGE_SUFFIXES)
def test_every_image_type_is_read_by_ocr(suffix: str) -> None:
    ocr = FakeOcr()
    result = extract_document(f"photo{suffix}", encoded(page(), ENCODERS[suffix]), LIMITS, ocr)
    assert (result.text, result.format) == ("Recognised text 1", suffix.lstrip("."))
    assert result.pages == (1 if suffix in {".tif", ".tiff"} else None)
    assert ocr.images[0].mode == "L"


def test_every_page_of_a_tiff_is_read() -> None:
    ocr = FakeOcr()
    result = extract_document("fax.tiff", frames("TIFF", 3), LIMITS, ocr)
    assert len(ocr.images) == 3
    assert result.pages == 3


def test_tiff_pages_past_the_ocr_limit_are_named() -> None:
    limits = replace(ROOMY, max_ocr_pages=2)
    result = extract_document("fax.tiff", frames("TIFF", 4), limits, FakeOcr())
    assert result.text.endswith("[Not read: pages 3-4 (OCR reads at most 2 pages per document).]")


def test_tiff_pages_past_the_page_limit_are_cut_without_counting_them_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def count_all(_image: object) -> int:
        raise AssertionError("n_frames walks every page, in quadratic time")

    monkeypatch.setattr(TiffImagePlugin.TiffImageFile, "n_frames", property(count_all))
    ocr = FakeOcr()
    result = extract_document("fax.tiff", frames("TIFF", 5), LIMITS, ocr)
    assert len(ocr.images) == result.pages == LIMITS.max_pages
    assert result.text.endswith(TRUNCATION_NOTE.strip())


def test_an_animated_gif_is_read_once_not_frame_by_frame() -> None:
    ocr = FakeOcr()
    result = extract_document("loop.gif", frames("GIF", 3), LIMITS, ocr)
    assert len(ocr.images) == 1
    assert result.pages is None


def test_a_transparent_image_is_read_on_white() -> None:
    ocr = FakeOcr()
    clear = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    extract_document("logo.png", encoded(clear, "PNG"), LIMITS, ocr)
    assert ocr.images[0].getpixel((0, 0)) == 255


def test_a_sideways_photo_is_turned_upright() -> None:
    ocr = FakeOcr()
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90 degrees to display
    photo = encoded(page((80, 40)), "JPEG", exif=exif.tobytes())
    extract_document("photo.jpg", photo, LIMITS, ocr)
    assert ocr.images[0].size == (40, 80)


def test_a_photo_saved_under_the_wrong_extension_still_reads() -> None:
    result = extract_document("photo.png", encoded(page(), "JPEG"), LIMITS, FakeOcr())
    assert result.text == "Recognised text 1"


def test_only_the_listed_image_decoders_run() -> None:
    icon = encoded(page((32, 32)), "ICO")  # Pillow reads .ico; we do not
    with pytest.raises(DocumentUnreadable, match="image"):
        extract_document("icon.png", icon, LIMITS, FakeOcr())


def test_an_image_over_the_pixel_limit_is_refused_before_it_is_decoded() -> None:
    ocr = FakeOcr()
    with pytest.raises(DocumentUnreadable, match="1,000,000 pixels"):
        extract_document("huge.png", png_header(5_000, 5_000), LIMITS, ocr)
    assert ocr.images == []


def test_a_decompression_bomb_is_refused_for_the_same_reason() -> None:
    with pytest.raises(DocumentUnreadable, match="pixels"):
        extract_document("bomb.png", png_header(100_000, 100_000), LIMITS, FakeOcr())


def test_each_tiff_page_is_checked_against_the_pixel_limit() -> None:
    pages = [page((10, 10)), page((2_000, 1_000))]
    tiff = encoded(
        pages[0], "TIFF", save_all=True, append_images=pages[1:], compression="tiff_deflate"
    )
    ocr = FakeOcr()
    with pytest.raises(DocumentUnreadable, match="pixels"):
        extract_document("fax.tiff", tiff, LIMITS, ocr)
    assert len(ocr.images) == 1


def test_without_ocr_an_image_is_refused_and_says_why() -> None:
    with pytest.raises(DocumentUnreadable, match="OCR, which is not available"):
        extract_document("photo.png", encoded(page(), "PNG"), LIMITS)


def test_a_damaged_image_is_unreadable_not_a_server_error() -> None:
    with pytest.raises(DocumentUnreadable, match="image"):
        extract_document("photo.png", b"\x89PNG not really", LIMITS, FakeOcr())


# --- HTTP ----------------------------------------------------------------------------


def test_upload_reads_an_image_with_the_apps_ocr_engine(
    app: FastAPI, auth_client: TestClient
) -> None:
    app.dependency_overrides[document_ocr] = lambda: FakeOcr()
    response = upload(auth_client, "whiteboard.png", encoded(page(), "PNG"))
    assert response.status_code == 200
    assert response.json()["text"] == "Recognised text 1"


def test_upload_of_an_image_without_ocr_is_a_422_that_says_why(auth_client: TestClient) -> None:
    response = upload(auth_client, "whiteboard.png", encoded(page(), "PNG"))
    assert response.status_code == 422
    assert response.json()["error"] == "document_unreadable"
    assert "OCR" in response.json()["detail"]
