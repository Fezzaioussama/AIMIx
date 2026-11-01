"""``pdf_page`` on PDFs as producers really write them: filled values pypdf cannot read
as a text string (a C program's NUL terminator, a Windows-1252 soft hyphen), numbers,
PDF 2.0 UTF-8 strings and lists; a field tree that loops; a scan drawn as an inline
picture; and drawing instructions that are damaged. The PDFs are
tests/test_document_pdf_content.py's, with one entry rewritten through pypdf."""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO

import pytest
from PIL import Image
from pypdf import PageObject, PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    ByteStringObject,
    DictionaryObject,
    FloatObject,
    IndirectObject,
    NameObject,
    NumberObject,
    PdfObject,
    TextStringObject,
)
from reportlab.pdfgen import canvas

from api.services.documents.extraction import extract_document
from tests.test_document_pdf_content import HEIGHT, SCANS, WIDTH, form_pdf, scan_with_page_number
from tests.test_document_scans import FakeOcr
from tests.test_documents import LIMITS

Edit = Callable[[DictionaryObject, IndirectObject], None]


def edited_form(edit: Edit, field: str = "applicant") -> bytes:
    """form_pdf(), with ``edit`` applied to the widget of ``field`` (and its reference)."""
    writer = PdfWriter(clone_from=PdfReader(BytesIO(form_pdf())))
    for reference in writer.pages[0]["/Annots"]:
        widget = reference.get_object()
        if widget.get("/T") == field:
            edit(widget, reference)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def valued(value: PdfObject) -> bytes:
    def set_value(widget: DictionaryObject, _reference: IndirectObject) -> None:
        widget[NameObject("/V")] = value

    return edited_form(set_value)


def applicant_line(data: bytes) -> str | None:
    lines = extract_document("form.pdf", data, LIMITS).text.splitlines()
    return next((line for line in lines if line.startswith("[Form field Full name")), None)


@pytest.mark.parametrize(
    ("value", "said"),
    [
        (ByteStringObject(b"Jean Dupont\x00"), "Jean Dupont"),
        (ByteStringObject(b"Marie\xadLouise"), "Marie\xadLouise"),  # cp1252 soft hyphen
        (ByteStringObject("Doğan Öztürk".encode()), "Doğan Öztürk"),  # 0x9F: no PDFDoc char
        (ByteStringObject(b"\xef\xbb\xbfJos\xc3\xa9"), "José"),  # PDF 2.0 UTF-8
        (ByteStringObject("﻿José".encode("utf-16-be")), "José"),
        (NumberObject(1500), "1500"),
        (FloatObject(12.5), "12.5"),
        (ArrayObject([TextStringObject("Tea"), TextStringObject("Coffee")]), "Tea, Coffee"),
    ],
    ids=[
        "nul-terminated",
        "soft-hyphen",
        "utf-8",
        "utf-8-bom",
        "utf-16-bom",
        "integer",
        "real",
        "list-of-two",
    ],
)
def test_a_filled_value_is_said_however_it_was_written(value: PdfObject, said: str) -> None:
    assert applicant_line(valued(value)) == f"[Form field Full name: {said}]"


def test_a_widget_whose_parent_chain_loops_is_skipped_not_followed_forever() -> None:
    def loop(widget: DictionaryObject, reference: IndirectObject) -> None:
        del widget[NameObject("/T")]
        widget[NameObject("/Parent")] = reference

    text = extract_document("form.pdf", edited_form(loop), LIMITS).text

    assert text.splitlines()[:3] == [
        "Application form",
        "[Form field agree: Yes]",
        "[Form field plan: pro]",
    ]


# --- how much of a page pictures cover ----------------------------------------------


def inline_scan() -> bytes:
    """A scan drawn as an inline picture (BI ... ID ... EI), with a page number."""
    buffer = BytesIO()
    page = canvas.Canvas(buffer, pagesize=(WIDTH, HEIGHT))
    page.drawInlineImage(Image.new("L", (40, 56), "white"), 0, 0, WIDTH, HEIGHT)
    page.drawString(WIDTH / 2, 20, "Page 1")
    page.showPage()
    page.save()
    return buffer.getvalue()


def test_a_scan_drawn_as_an_inline_picture_is_read_by_ocr() -> None:
    ocr = FakeOcr()
    result = extract_document("scan.pdf", inline_scan(), SCANS, ocr)
    assert (result.text, len(ocr.images)) == ("Page 1\nRecognised text 1", 1)


def five_operand_cm(page: PageObject) -> None:
    content = page.get_contents()
    assert content is not None
    content.operations = [
        (operands[:5] if operator == b"cm" else operands, operator)
        for operands, operator in content.operations
    ]
    page.replace_contents(content)


def no_xobjects(page: PageObject) -> None:
    del page["/Resources"][NameObject("/XObject")]


@pytest.mark.parametrize("damage", [five_operand_cm, no_xobjects], ids=["cm", "no-xobject"])
def test_damaged_drawing_instructions_cost_the_page_nothing(
    damage: Callable[[PageObject], None],
) -> None:
    writer = PdfWriter(clone_from=PdfReader(BytesIO(scan_with_page_number())))
    damage(writer.pages[0])
    out = BytesIO()
    writer.write(out)
    ocr = FakeOcr()

    result = extract_document("scan.pdf", out.getvalue(), SCANS, ocr)

    # Taken for a page whose pictures cover nothing: its text, as it is, and no OCR.
    assert (result.text, ocr.images) == ("Page 1", [])
