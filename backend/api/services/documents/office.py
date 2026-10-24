"""Office documents: Word (.docx), Excel (.xlsx) and PowerPoint (.pptx).

All three are zip packages of XML, so each is checked against the unpacked-size
limit before any of its XML is parsed (zip bombs).
"""

from __future__ import annotations

import zipfile
from functools import singledispatch
from io import BytesIO
from itertools import islice

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from openpyxl import load_workbook
from openpyxl.workbook.workbook import Workbook
from pptx import Presentation
from pptx.shapes.autoshape import Shape
from pptx.shapes.base import BaseShape
from pptx.shapes.graphfrm import GraphicFrame
from pptx.shapes.group import GroupShape
from pptx.slide import Slide
from pptx.text.text import TextFrame

from api.exceptions import DocumentUnreadable
from api.services.documents.contracts import ReadContext, ReadResult

#: Between the cells of a table row, in Word and PowerPoint alike.
CELL_SEPARATOR = " | "
_W_P = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"
_W_TBL = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tbl"


def _check_unpacked_size(data: bytes, limit: int, kind: str) -> None:
    """Refuse a zip bomb before any XML is parsed."""
    with zipfile.ZipFile(BytesIO(data)) as archive:
        if sum(member.file_size for member in archive.infolist()) > limit:
            raise DocumentUnreadable(f"This {kind} file is too large once unpacked.")


# --- Word ------------------------------------------------------------------------


def read_docx(data: bytes, context: ReadContext) -> ReadResult:
    _check_unpacked_size(data, context.limits.max_unpacked_bytes, "Word")
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
        rows.append(CELL_SEPARATOR.join(cells.values()))
    return rows


# --- Excel -----------------------------------------------------------------------


def read_xlsx(data: bytes, context: ReadContext) -> ReadResult:
    _check_unpacked_size(data, context.limits.max_unpacked_bytes, "Excel")
    # read_only streams the rows; data_only gives a formula's saved value, not its code.
    workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
    try:
        return _read_workbook(workbook, context.limits.max_spreadsheet_rows)
    finally:
        workbook.close()


def _read_workbook(workbook: Workbook, max_rows: int) -> ReadResult:
    """Each sheet as a heading, then its rows as tab-separated values.

    ``max_rows`` counts every row read, blank ones too, across the whole workbook,
    so a sheet padded with empty rows cannot make reading it endless.
    """
    lines: list[str] = []
    rows_read = 0
    for sheet in workbook.worksheets:
        lines.append(f"## Sheet: {sheet.title}")
        for row in sheet.iter_rows(values_only=True):
            if rows_read == max_rows:
                return ReadResult("\n".join(lines), cut_short=True)
            rows_read += 1
            lines.append(_row_text(row))
        lines.append("")
    return ReadResult("\n".join(lines))


def _row_text(row: tuple[object, ...]) -> str:
    """Tab-separated values; a cell's own tabs and line breaks become spaces."""
    cells = ("" if value is None else " ".join(str(value).split()) for value in row)
    return "\t".join(cells).rstrip()


# --- PowerPoint ------------------------------------------------------------------


def read_pptx(data: bytes, context: ReadContext) -> ReadResult:
    _check_unpacked_size(data, context.limits.max_unpacked_bytes, "PowerPoint")
    slides = Presentation(BytesIO(data)).slides
    total = len(slides)
    read = islice(slides, context.limits.max_pages)
    blocks = [_slide_text(number, slide) for number, slide in enumerate(read, start=1)]
    return ReadResult("\n\n".join(blocks), pages=total, cut_short=len(blocks) < total)


def _slide_text(number: int, slide: Slide) -> str:
    """'## Slide N: <title>', then the slide's other text, then its speaker notes."""
    title = slide.shapes.title
    heading = f"## Slide {number}"
    if title is not None and title.text.strip():
        heading += f": {' '.join(title.text.split())}"
    body = [line for shape in slide.shapes if shape != title for line in _shape_lines(shape)]
    return "\n".join([heading, *body, *_notes(slide)])


def _notes(slide: Slide) -> list[str]:
    # Reading notes_slide would create one, so ask first.
    frame = slide.notes_slide.notes_text_frame if slide.has_notes_slide else None
    text = _text(frame) if frame is not None else ""
    return [f"Speaker notes: {text}"] if text else []


def _text(frame: TextFrame) -> str:
    # python-pptx writes a line break inside a paragraph as a vertical tab.
    return frame.text.replace("\v", "\n").strip()


# The text a shape shows, by kind of shape (§7 Strategy, through singledispatch):
# a new kind of shape is one more registered function.
@singledispatch
def _shape_lines(shape: BaseShape) -> list[str]:
    """Pictures, charts, connectors and other shapes without text show none."""
    return []


@_shape_lines.register
def _group_lines(shape: GroupShape) -> list[str]:
    return [line for child in shape.shapes for line in _shape_lines(child)]


@_shape_lines.register
def _table_lines(shape: GraphicFrame) -> list[str]:
    if not shape.has_table:
        return []
    rows = shape.table.rows
    return [CELL_SEPARATOR.join(_text(cell.text_frame) for cell in row.cells) for row in rows]


@_shape_lines.register
def _text_lines(shape: Shape) -> list[str]:
    return [_text(shape.text_frame)] if shape.has_text_frame else []
