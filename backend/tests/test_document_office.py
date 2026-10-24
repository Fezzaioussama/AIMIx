"""Excel workbooks and PowerPoint decks: what text they give, the limits on them, and
the zip-bomb guard they share with Word. Files are built with openpyxl and
python-pptx, so the real parsers run."""

from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from pptx import Presentation
from pptx.util import Inches

from api.exceptions import DocumentUnreadable
from api.services.documents.extraction import TRUNCATION_NOTE, extract_document
from tests.test_documents import LIMITS, upload


def make_xlsx() -> bytes:
    workbook = Workbook()
    sales = workbook.active
    assert sales is not None
    sales.title = "Sales"
    sales.append(["Region", "Revenue", None, "Note"])
    sales.append(["North", 42, None, "two\nlines\tand a tab"])
    sales.append([])
    sales.append(["South", 3.5])
    workbook.create_sheet("Costs").append(["Rent", 1000])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def make_pptx() -> bytes:
    deck = Presentation()
    first = deck.slides.add_slide(deck.slide_layouts[1])  # title and content
    assert first.shapes.title is not None
    first.shapes.title.text = "Quarterly results"
    first.placeholders[1].text_frame.text = "Revenue grew\nCosts fell"
    first.notes_slide.notes_text_frame.text = "Mention the new region."
    second = deck.slides.add_slide(deck.slide_layouts[5])  # title only
    assert second.shapes.title is not None
    second.shapes.title.text = "By region"
    table = second.shapes.add_table(2, 2, Inches(1), Inches(2), Inches(4), Inches(1)).table
    for (row, column), text in {(0, 0): "Region", (0, 1): "Revenue", (1, 0): "North"}.items():
        table.cell(row, column).text = text
    table.cell(1, 1).text = "42"
    group = second.shapes.add_group_shape()
    group.shapes.add_textbox(Inches(1), Inches(4), Inches(2), Inches(1)).text = "Grouped words"
    deck.slides.add_slide(deck.slide_layouts[6])  # blank: no title, no text
    buffer = BytesIO()
    deck.save(buffer)
    return buffer.getvalue()


# --- Excel -------------------------------------------------------------------------


def test_a_workbook_gives_each_sheet_then_its_rows_as_tab_separated_values() -> None:
    result = extract_document("figures.xlsx", make_xlsx(), LIMITS)
    assert result.text.splitlines() == [
        "## Sheet: Sales",
        "Region\tRevenue\t\tNote",
        "North\t42\t\ttwo lines and a tab",
        "",
        "South\t3.5",
        "",
        "## Sheet: Costs",
        "Rent\t1000",
    ]
    assert (result.format, result.pages, result.truncated) == ("xlsx", None, False)


def test_rows_past_the_limit_are_cut_across_the_whole_workbook() -> None:
    result = extract_document("figures.xlsx", make_xlsx(), replace(LIMITS, max_spreadsheet_rows=5))
    assert "Rent" in result.text  # the fifth row read is the first of the second sheet
    assert result.truncated is False

    result = extract_document("figures.xlsx", make_xlsx(), replace(LIMITS, max_spreadsheet_rows=3))
    assert "South" not in result.text
    assert "Costs" not in result.text
    assert result.text.endswith(TRUNCATION_NOTE.strip())


def test_a_workbook_that_unpacks_too_large_is_refused() -> None:
    with pytest.raises(DocumentUnreadable, match="Excel file is too large once unpacked"):
        extract_document("bomb.xlsx", make_xlsx(), replace(LIMITS, max_unpacked_bytes=100))


def test_something_that_is_not_a_workbook_is_unreadable() -> None:
    with pytest.raises(DocumentUnreadable, match="Excel"):
        extract_document("fake.xlsx", b"just some words", LIMITS)


# --- PowerPoint --------------------------------------------------------------------


def test_a_deck_gives_each_slide_its_title_text_tables_groups_and_notes() -> None:
    result = extract_document("deck.pptx", make_pptx(), LIMITS)
    assert result.text.splitlines() == [
        "## Slide 1: Quarterly results",
        "Revenue grew",
        "Costs fell",
        "Speaker notes: Mention the new region.",
        "",
        "## Slide 2: By region",
        "Region | Revenue",
        "North | 42",
        "Grouped words",
        "",
        "## Slide 3",
    ]
    assert (result.format, result.pages, result.truncated) == ("pptx", 3, False)


def test_slides_past_the_page_limit_are_cut_and_say_so() -> None:
    result = extract_document("deck.pptx", make_pptx(), replace(LIMITS, max_pages=1))
    assert "Slide 2" not in result.text
    assert result.pages == 3
    assert result.text.endswith(TRUNCATION_NOTE.strip())


def test_a_deck_that_unpacks_too_large_is_refused() -> None:
    with pytest.raises(DocumentUnreadable, match="PowerPoint file is too large once unpacked"):
        extract_document("bomb.pptx", make_pptx(), replace(LIMITS, max_unpacked_bytes=100))


def test_something_that_is_not_a_deck_is_unreadable() -> None:
    with pytest.raises(DocumentUnreadable, match="PowerPoint"):
        extract_document("fake.pptx", b"just some words", LIMITS)


# --- HTTP ----------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "content"), [("a.xlsx", make_xlsx()), ("a.pptx", make_pptx())])
def test_upload_reads_office_files(auth_client: TestClient, name: str, content: bytes) -> None:
    response = upload(auth_client, name, content)
    assert response.status_code == 200
    assert response.json()["text"].startswith("## S")
