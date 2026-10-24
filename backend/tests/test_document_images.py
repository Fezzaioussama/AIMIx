"""Images, read through the OCR port: every type, multi-page TIFFs, what reaches the
engine, and the guards on decoding. Images are made with Pillow, so the real
decoders run; a fake engine stands in for Tesseract."""

from __future__ import annotations

import struct
import zlib
from dataclasses import replace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, TiffImagePlugin

from api.deps import document_ocr
from api.exceptions import DocumentUnreadable
from api.services.documents.extraction import TRUNCATION_NOTE, extract_document
from api.services.documents.images import IMAGE_SUFFIXES
from tests.test_document_scans import ROOMY, FakeOcr, encoded, frames, page
from tests.test_documents import LIMITS, upload

#: The Pillow encoder behind each image extension.
ENCODERS = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP", ".tif": "TIFF"}
ENCODERS |= {".tiff": "TIFF", ".bmp": "BMP", ".gif": "GIF"}
ORIENTATION = 0x0112  # the EXIF tag; 6 means "turn 90 degrees to display"


def png_header(width: int, height: int) -> bytes:
    """A PNG that declares its size but holds almost no pixels: decoding it would fail."""

    def chunk(kind: bytes, body: bytes) -> bytes:
        checksum = struct.pack(">I", zlib.crc32(kind + body))
        return struct.pack(">I", len(body)) + kind + body + checksum

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    pixels = zlib.compress(b"\x00" * 10)
    signature = b"\x89PNG\r\n\x1a\n"
    return signature + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")


# --- types and pages -------------------------------------------------------------------


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


def test_a_photo_saved_under_the_wrong_extension_still_reads() -> None:
    result = extract_document("photo.png", encoded(page(), "JPEG"), LIMITS, FakeOcr())
    assert result.text == "Recognised text 1"


# --- what the engine is given ---------------------------------------------------------


def test_a_transparent_image_is_read_on_white() -> None:
    ocr = FakeOcr()
    clear = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    extract_document("logo.png", encoded(clear, "PNG"), LIMITS, ocr)
    assert ocr.images[0].getpixel((0, 0)) == 255


def test_a_16_bit_scan_is_scaled_to_8_bits_not_clipped_to_white() -> None:
    ocr = FakeOcr()
    scan = Image.new("I;16", (2, 1))
    scan.putpixel((1, 0), 0x8000)  # mid-gray beside black
    extract_document("scan.tiff", encoded(scan, "TIFF"), LIMITS, ocr)
    assert [ocr.images[0].getpixel((x, 0)) for x in (0, 1)] == [0, 128]


def test_a_sideways_photo_is_turned_upright() -> None:
    ocr = FakeOcr()
    exif = Image.Exif()
    exif[ORIENTATION] = 6
    extract_document("photo.jpg", encoded(page((80, 40)), "JPEG", exif=exif.tobytes()), LIMITS, ocr)
    assert ocr.images[0].size == (40, 80)


def test_a_sideways_tiff_is_turned_upright() -> None:
    ocr = FakeOcr()
    tags = TiffImagePlugin.ImageFileDirectory_v2()
    tags[ORIENTATION] = 6
    extract_document("scan.tiff", encoded(page((80, 40)), "TIFF", tiffinfo=tags), LIMITS, ocr)
    assert ocr.images[0].size == (40, 80)


# --- refusals ---------------------------------------------------------------------------


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
    options = {"save_all": True, "append_images": pages[1:], "compression": "tiff_deflate"}
    ocr = FakeOcr()
    with pytest.raises(DocumentUnreadable, match="pixels"):
        extract_document("fax.tiff", encoded(pages[0], "TIFF", **options), LIMITS, ocr)
    assert len(ocr.images) == 1


def test_an_image_ocr_fails_on_is_a_refusal_that_says_so() -> None:
    ocr = FakeOcr({1: DocumentUnreadable("Text recognition (OCR) failed on this file.")})
    with pytest.raises(DocumentUnreadable, match=r"Not read: page 1 \(OCR failed\)"):
        extract_document("photo.png", encoded(page(), "PNG"), LIMITS, ocr)


def test_without_ocr_an_image_is_refused_and_says_why() -> None:
    with pytest.raises(DocumentUnreadable, match="OCR, which is not available"):
        extract_document("photo.png", encoded(page(), "PNG"), LIMITS)


def test_a_damaged_image_is_unreadable_not_a_server_error() -> None:
    with pytest.raises(DocumentUnreadable, match="image"):
        extract_document("photo.png", b"\x89PNG not really", LIMITS, FakeOcr())


# --- HTTP -------------------------------------------------------------------------------


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
