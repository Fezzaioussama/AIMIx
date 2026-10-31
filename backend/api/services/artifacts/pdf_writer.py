"""Markdown blocks into a PDF with ReportLab's Platypus layout engine.

One writer per block type, chosen by ``functools.singledispatch`` (§7 Strategy +
Registry). Text is set in the TrueType font at PDF_FONT_PATH (DejaVu Sans in the
image), so Greek, Cyrillic and every other script that font covers prints. When
the file is missing, the built-in Helvetica keeps Western European text working
and prints other characters as boxes. The fonts have no italic face: italics
print upright, bold prints bold.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from functools import lru_cache, singledispatch
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFError, TTFont
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    Indenter,
    ListFlowable,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)
from reportlab.platypus import Paragraph as PdfParagraph
from reportlab.platypus import Table as PdfTable

from api.services.artifacts.contracts import AI_GENERATED_KEYWORD, AI_GENERATED_NOTE, RenderOptions
from api.services.artifacts.markdown import (
    Block,
    CodeBlock,
    Heading,
    ListBlock,
    Paragraph,
    Quote,
    Rule,
    Span,
    Spans,
    Table,
    parse_markdown,
    plain_text,
    web_link,
)

logger = logging.getLogger(__name__)

MARGIN = 20 * mm
BODY_SIZE = 10.5
INDENT = 18
#: Code lines longer than this wrap, so they never run off the page.
CODE_LINE_CHARS = 88
#: Courier, like Helvetica, encodes Windows-1252 text only.
CODE_FONT = "Courier"
BULLET = "•"
LINK_COLOR = "#1d4ed8"
LINE_COLOR = colors.HexColor("#cbd5e1")
SHADE_COLOR = colors.HexColor("#f1f5f9")


@dataclass(frozen=True)
class _Fonts:
    regular: str
    bold: str


BUILT_IN = _Fonts("Helvetica", "Helvetica-Bold")


@dataclass(frozen=True)
class _Styles:
    fonts: _Fonts
    body: ParagraphStyle
    headings: dict[int, ParagraphStyle]
    cell: ParagraphStyle
    header_cell: ParagraphStyle
    code: ParagraphStyle


def render_pdf(content: str, options: RenderOptions) -> bytes:
    """The Markdown ``content`` as an A4 PDF."""
    styles = _styles(_fonts(options.pdf_font, options.pdf_bold_font))
    blocks = parse_markdown(content)
    title = next((plain_text(block.spans) for block in blocks if isinstance(block, Heading)), "")
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=title,
        creator="AIMIx",
        subject=AI_GENERATED_NOTE,
        keywords=[AI_GENERATED_KEYWORD],
        initialFontName=styles.fonts.regular,
    )
    document.build(_flows(blocks, styles) or [Spacer(0, 0)])
    return buffer.getvalue()


@lru_cache(maxsize=8)
def _fonts(regular: Path, bold: Path) -> _Fonts:
    """Register the TrueType faces once per process, or fall back to Helvetica."""
    family = f"AIMIx-{hashlib.sha256(str(regular).encode()).hexdigest()[:12]}"
    if not _register(family, regular):
        return BUILT_IN
    bold_name = f"{family}-Bold" if _register(f"{family}-Bold", bold) else family
    pdfmetrics.registerFontFamily(
        family, normal=family, bold=bold_name, italic=family, boldItalic=bold_name
    )
    return _Fonts(family, bold_name)


def _register(name: str, path: Path) -> bool:
    try:
        pdfmetrics.registerFont(TTFont(name, str(path)))
    except TTFError:
        logger.warning("artifacts.pdf_font_unavailable path=%s", path)
        return False
    return True


def _styles(fonts: _Fonts) -> _Styles:
    sample = getSampleStyleSheet()
    body = ParagraphStyle(
        "Body",
        parent=sample["BodyText"],
        fontName=fonts.regular,
        fontSize=BODY_SIZE,
        leading=BODY_SIZE * 1.4,
        spaceAfter=6,
    )
    cell = ParagraphStyle("Cell", parent=body, fontSize=9.5, leading=12.5, spaceAfter=0)
    return _Styles(
        fonts=fonts,
        body=body,
        headings={
            level: ParagraphStyle(
                f"H{level}", parent=sample[f"Heading{level}"], fontName=fonts.bold
            )
            for level in range(1, 7)
        },
        cell=cell,
        header_cell=ParagraphStyle("HeaderCell", parent=cell, fontName=fonts.bold),
        code=ParagraphStyle(
            "Code", parent=sample["Code"], fontSize=9, leading=12, spaceBefore=4, spaceAfter=10
        ),
    )


def _flows(blocks: tuple[Block, ...], styles: _Styles) -> list[Flowable]:
    return [flowable for block in blocks for flowable in _flow(block, styles)]


@singledispatch
def _flow(block: Block, styles: _Styles) -> list[Flowable]:
    raise TypeError(f"No PDF writer for {type(block).__name__}.")


@_flow.register
def _heading(block: Heading, styles: _Styles) -> list[Flowable]:
    return [PdfParagraph(_markup(block.spans, styles.fonts), styles.headings[block.level])]


@_flow.register
def _paragraph(block: Paragraph, styles: _Styles) -> list[Flowable]:
    return [PdfParagraph(_markup(block.spans, styles.fonts), styles.body)]


@_flow.register
def _list(block: ListBlock, styles: _Styles) -> list[Flowable]:
    # Each item is a list of flowables: the first gets the bullet, the rest follow it.
    items = [_flows(item, styles) or [Spacer(0, 0)] for item in block.items]
    return [
        ListFlowable(
            items,
            bulletType="1" if block.ordered else "bullet",
            start=block.start if block.ordered else BULLET,
            bulletFormat="%s." if block.ordered else "%s",
            bulletFontName=styles.fonts.regular,
            bulletFontSize=BODY_SIZE,
            leftIndent=INDENT,
        )
    ]


@_flow.register
def _table(block: Table, styles: _Styles) -> list[Flowable]:
    columns = max((len(row) for row in (block.header, *block.rows)), default=0)
    if not columns:
        return []
    header = [_cells(block.header, columns, styles.header_cell, styles)] if block.header else []
    body = [_cells(row, columns, styles.cell, styles) for row in block.rows]
    widths = [f"{100 / columns}%"] * columns
    table = PdfTable([*header, *body], colWidths=widths, repeatRows=len(header))
    style = TableStyle(
        [("GRID", (0, 0), (-1, -1), 0.5, LINE_COLOR), ("VALIGN", (0, 0), (-1, -1), "TOP")]
    )
    if header:
        style.add("BACKGROUND", (0, 0), (-1, 0), SHADE_COLOR)
    table.setStyle(style)
    return [table, Spacer(0, 8)]


def _cells(
    row: tuple[Spans, ...], columns: int, style: ParagraphStyle, styles: _Styles
) -> list[Flowable]:
    """One table row, padded to ``columns`` cells."""
    padded = (*row, *(((),) * (columns - len(row))))
    return [PdfParagraph(_markup(cell, styles.fonts), style) for cell in padded]


@_flow.register
def _code(block: CodeBlock, styles: _Styles) -> list[Flowable]:
    face = _code_face(block.text, styles.fonts)
    style = ParagraphStyle("CodeBlock", parent=styles.code, fontName=face)
    return [Preformatted(block.text, style, maxLineLength=CODE_LINE_CHARS, newLineChars="")]


@_flow.register
def _quote(block: Quote, styles: _Styles) -> list[Flowable]:
    return [Indenter(left=INDENT), *_flows(block.blocks, styles), Indenter(left=-INDENT)]


@_flow.register
def _rule(block: Rule, styles: _Styles) -> list[Flowable]:
    return [HRFlowable(width="100%", thickness=0.6, color=LINE_COLOR, spaceBefore=4, spaceAfter=8)]


def _markup(spans: Spans, fonts: _Fonts) -> str:
    """ReportLab's paragraph markup for ``spans``; their text is escaped, so
    nothing an agent writes can become markup."""
    return "".join(_span_markup(span, fonts) for span in spans)


def _span_markup(span: Span, fonts: _Fonts) -> str:
    text = escape(span.text).replace("\n", "<br/>")
    if span.code:
        text = f'<font face="{_code_face(span.text, fonts)}">{text}</font>'
    if span.bold:
        text = f"<b>{text}</b>"
    if span.italic:
        text = f"<i>{text}</i>"
    target = web_link(span)
    return f'<a href={quoteattr(target)} color="{LINK_COLOR}">{text}</a>' if target else text


def _code_face(text: str, fonts: _Fonts) -> str:
    """Courier where it can show the text, else the body font."""
    try:
        text.encode("cp1252")
    except UnicodeEncodeError:
        return fonts.regular
    return CODE_FONT
