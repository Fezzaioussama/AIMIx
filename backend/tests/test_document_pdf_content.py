"""What a PDF holds besides its text layer: filled form fields, comments, scans whose
text layer is only a page number, characters a model cannot use, and where a long
PDF is cut. The PDFs are made with ReportLab and pypdf, so the real parser runs."""

from __future__ import annotations

import codecs
from dataclasses import replace
from io import BytesIO

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import FreeText, Popup, Text
from pypdf.generic import NameObject, TextStringObject
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from api.services.documents import pdf
from api.services.documents.contracts import ReadContext
from api.services.documents.extraction import (
    TRUNCATION_NOTE,
    extract_document,
    extraction_limits,
    read_document,
)
from config.settings import Settings
from tests.test_document_scans import ROOMY, FakeOcr, scanned_pdf
from tests.test_documents import LIMITS, make_pdf

WIDTH, HEIGHT = A4
#: The page of a scan that holds only a page number, as scanner apps stamp it.
SCANS = replace(LIMITS, ocr_min_page_chars=50)


def form_pdf() -> bytes:
    """A filled form, saved as a viewer saves one: values in fields, comments in
    annotations, none of them in the page's text layer."""
    buffer = BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4)
    page.drawString(72, 760, "Application form")
    form = page.acroForm
    form.textfield(name="applicant", tooltip="Full name", value="Jean Dupont", x=120, y=700)
    form.textfield(name="notes", value="", x=120, y=660)
    form.checkbox(name="agree", checked=True, x=120, y=620)
    form.checkbox(name="newsletter", checked=False, x=160, y=620)
    # Two radio buttons of one field: the field is said once.
    form.radio(name="plan", value="basic", selected=False, x=120, y=580)
    form.radio(name="plan", value="pro", selected=True, x=160, y=580)
    page.showPage()
    page.save()
    writer = PdfWriter(clone_from=PdfReader(BytesIO(buffer.getvalue())))
    writer.add_annotation(
        0, FreeText(text="Approved by finance\n on 3 Oct", rect=(50, 500, 450, 530))
    )
    note = writer.add_annotation(0, Text(text="Check figure 3", rect=(400, 600, 420, 620)))
    popup = Popup(rect=(420, 600, 520, 650), parent=note)
    popup[NameObject("/Contents")] = TextStringObject("Check figure 3")  # repeats its parent
    writer.add_annotation(0, popup)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def picture_pdf(stamp: str, picture: tuple[float, float, float, float]) -> bytes:
    """One A4 page: a picture at ``picture`` (x, y, width, height), then ``stamp`` as text."""
    buffer = BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4)
    scan = Image.new("L", (200, 280), "white")
    page.drawImage(ImageReader(scan), *picture)
    page.drawString(WIDTH / 2, 20, stamp)
    page.showPage()
    page.save()
    return buffer.getvalue()


def scan_with_page_number() -> bytes:
    return picture_pdf("Page 1", (0, 0, WIDTH, HEIGHT))


def slides(*titles: str | None) -> bytes:
    """A 16:9 deck as PowerPoint or Canva export one: every slide on a full-bleed
    picture, with its title (40 pt) in the text layer; None is a slide that is only a
    picture (a scanned annex)."""
    buffer = BytesIO()
    deck = canvas.Canvas(buffer, pagesize=(960, 540))
    for title in titles:
        deck.drawImage(ImageReader(Image.new("RGB", (96, 54), (40, 60, 140))), 0, 0, 960, 540)
        if title:
            deck.setFont("Helvetica-Bold", 40)
            deck.drawString(60, 300, title)
        deck.showPage()
    deck.save()
    return buffer.getvalue()


class BlankOcr(FakeOcr):
    """Finds no text on any page, as OCR does on a blank or unreadable scan."""

    def read(self, image: Image.Image) -> str:
        super().read(image)
        return ""


def refuse_pdfium(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object) -> None:
        raise AssertionError("PDFium opened a PDF that needed no OCR")

    monkeypatch.setattr(pdf.pdfium, "PdfDocument", refuse)


# --- form fields and comments -------------------------------------------------------


def test_filled_fields_and_comments_follow_the_page_text_once_each() -> None:
    result = extract_document("form.pdf", form_pdf(), LIMITS)

    assert result.text.splitlines() == [
        "Application form",
        "[Form field Full name: Jean Dupont]",
        "[Form field agree: Yes]",
        "[Form field plan: pro]",
        "[Comment: Approved by finance on 3 Oct]",
        "[Comment: Check figure 3]",
    ]
    assert result.truncated is False


def test_a_form_field_value_is_read_on_its_own_page() -> None:
    form = PdfReader(BytesIO(form_pdf())).pages[0]
    writer = PdfWriter()
    writer.add_page(
        PdfReader(BytesIO(make_pdf(["Cover page with enough words to be text"]))).pages[0]
    )
    writer.add_page(form)
    buffer = BytesIO()
    writer.write(buffer)

    text = extract_document("two.pdf", buffer.getvalue(), LIMITS).text

    cover, second = text.split("\n\n")
    assert cover == "Cover page with enough words to be text"
    assert second.startswith("Application form\n[Form field Full name: Jean Dupont]")


# --- scans whose text layer is only a page number ---------------------------------------


def test_a_scan_with_only_a_page_number_is_read_by_ocr_after_it() -> None:
    ocr = FakeOcr()

    result = extract_document("scan.pdf", scan_with_page_number(), SCANS, ocr)

    assert result.text == "Page 1\nRecognised text 1"
    assert (len(ocr.images), result.truncated) == (1, False)


def test_when_ocr_finds_nothing_the_page_number_is_kept() -> None:
    ocr = BlankOcr()
    result = extract_document("scan.pdf", scan_with_page_number(), SCANS, ocr)
    assert (result.text, len(ocr.images)) == ("Page 1", 1)


def test_without_ocr_such_a_scan_is_flagged_so_the_user_is_warned() -> None:
    result = extract_document("scan.pdf", scan_with_page_number(), SCANS)

    assert result.text == (
        "Page 1\n\n[Not read: page 1 (looks scanned: under 50 characters of text, "
        "and OCR is not available).]"
    )
    assert result.truncated is True


def test_a_title_slide_over_a_photo_is_not_a_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    refuse_pdfium(monkeypatch)
    ocr = FakeOcr()

    with_ocr = extract_document("deck.pdf", slides("Quarterly Review 2026"), SCANS, ocr)
    without = extract_document("deck.pdf", slides("Quarterly Review 2026"), SCANS)

    assert (with_ocr.text, with_ocr.truncated, ocr.images) == ("Quarterly Review 2026", False, [])
    assert (without.text, without.truncated) == ("Quarterly Review 2026", False)


def test_title_slides_leave_ocr_s_budget_to_the_scans_after_them() -> None:
    ocr = FakeOcr()
    one_page = replace(SCANS, max_ocr_pages=1)

    result = extract_document("deck.pdf", slides("Agenda", "Thank you!", None), one_page, ocr)

    assert result.text == "Agenda\n\nThank you!\n\nRecognised text 1"
    assert (len(ocr.images), result.truncated) == (1, False)


def test_a_short_page_with_a_small_picture_is_not_a_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    refuse_pdfium(monkeypatch)
    ocr = FakeOcr()
    logo = picture_pdf("Annual report", (40, HEIGHT - 120, 100, 80))

    result = extract_document("cover.pdf", logo, SCANS, ocr)

    assert (result.text, ocr.images, result.truncated) == ("Annual report", [], False)


def test_a_short_page_without_pictures_never_reaches_pdfium(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refuse_pdfium(monkeypatch)
    assert extract_document("title.pdf", make_pdf(["Chapter 1"]), SCANS, FakeOcr()).text == (
        "Chapter 1"
    )


def test_a_page_with_a_real_text_layer_over_a_picture_is_not_sent_to_ocr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refuse_pdfium(monkeypatch)
    caption = "A brochure page whose words are printed over a photo of the whole page."
    ocr = FakeOcr()

    result = extract_document(
        "brochure.pdf", picture_pdf(caption, (0, 0, WIDTH, HEIGHT)), SCANS, ocr
    )

    assert (result.text, ocr.images) == (caption, [])


@pytest.mark.parametrize(
    ("part", "damaged"),
    [
        (b"/MediaBox [ 0 0 595.2756 841.8898 ]", b""),
        (b"/MediaBox [ 0 0 595.2756 841.8898 ]", b"/MediaBox [ 0 0 (wide) 841.8898 ]"),
        (b"/ProcSet", b"/Annots [ 99 0 R ] /ProcSet"),  # a comment that is not there
        (b" 3 0 R\n>>", b" 98 0 R\n>>"),  # nor is the picture
    ],
)
def test_a_damaged_short_page_keeps_its_text(part: bytes, damaged: bytes) -> None:
    """The scan check reads what pypdf's text extraction never needed: damage there
    must not cost the document."""
    data = scan_with_page_number()
    assert part in data

    result = extract_document("damaged.pdf", data.replace(part, damaged, 1), SCANS)

    assert result.text.startswith("Page 1")


def test_the_scan_threshold_is_a_setting_that_reaches_the_limits() -> None:
    settings = Settings(_env_file=None)
    assert settings.document_ocr_min_page_chars == 50
    custom = Settings(_env_file=None, document_ocr_min_page_chars=10)
    assert extraction_limits(custom).ocr_min_page_chars == 10


# --- characters a model cannot use ---------------------------------------------------


def test_nul_characters_are_dropped() -> None:
    assert extract_document("nul.pdf", make_pdf(["Hello\x00World"]), LIMITS).text == "HelloWorld"


def test_a_leading_byte_order_mark_is_dropped() -> None:
    doubled = codecs.BOM_UTF16_LE + "﻿hello".encode("utf-16-le")
    assert extract_document("notes.txt", doubled, LIMITS).text == "hello"


# --- where a long PDF is cut ---------------------------------------------------------


def test_a_long_pdf_is_cut_after_the_last_whole_page_that_fits() -> None:
    long_pages = make_pdf(["a" * 600, "b" * 600])

    result = extract_document("long.pdf", long_pages, LIMITS)

    assert result.text == "a" * 600 + TRUNCATION_NOTE
    assert result.truncated is True


def test_reading_can_start_at_a_later_page_without_reading_the_earlier_ones() -> None:
    ocr = FakeOcr()

    document = read_document("scan.pdf", scanned_pdf(4), ReadContext(ROOMY, ocr, first_page=3))

    assert document.text == "Recognised text 1\n\nRecognised text 2"
    assert (len(ocr.images), document.pages, document.last_page) == (2, 4, 4)
    assert document.cut_short is False
