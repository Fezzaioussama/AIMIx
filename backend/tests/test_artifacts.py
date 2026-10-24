"""Agent deliverables in real formats: the Markdown model, the Word and PDF writers
and the registry that picks one by extension. Files are opened with the same
libraries a reader would use, never inspected as raw bytes."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document
from docx.oxml.ns import qn
from pypdf import PdfReader

from api.exceptions import UnsupportedFileType, ValidationFailed
from api.services.artifacts import pdf_writer, registry
from api.services.artifacts.contracts import RenderOptions
from api.services.artifacts.markdown import (
    CodeBlock,
    Heading,
    ListBlock,
    Paragraph,
    Quote,
    Rule,
    Span,
    Table,
    parse_markdown,
)
from api.services.artifacts.registry import RENDERERS, artifact_extensions, render_artifact
from config.settings import Settings

DEFAULTS = Settings(_env_file=None)
DEJAVU = RenderOptions(DEFAULTS.pdf_font_path, DEFAULTS.pdf_bold_font_path)
NO_FONT = RenderOptions(Path("/no/such/font.ttf"), Path("/no/such/font-bold.ttf"))
needs_dejavu = pytest.mark.skipif(
    not DEJAVU.pdf_font.is_file(), reason="DejaVu Sans is not installed here"
)
#: "Good morning" in Greek, escaped because its letters look like Latin ones.
GREEK = "Καλημέρα"

REPORT = """# Quarterly report

Revenue grew by **12%** and *margins* held, see [the source](https://example.com/q3).

1. First
2. Second
   - nested

| Region | Revenue |
|---|---|
| North | 42 |

> Quoted words.

```
print("hi")
```

---

2. Again from two
"""


def pdf_text(data: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(BytesIO(data)).pages)


# --- the Markdown model --------------------------------------------------------


def test_markdown_becomes_typed_blocks() -> None:
    blocks = parse_markdown(REPORT)

    assert [type(block) for block in blocks] == [
        Heading,
        Paragraph,
        ListBlock,
        Table,
        Quote,
        CodeBlock,
        Rule,
        ListBlock,
    ]
    heading, paragraph, first_list, table, *_, last_list = blocks
    assert heading == Heading(1, (Span("Quarterly report"),))
    assert isinstance(paragraph, Paragraph)
    assert Span("12%", bold=True) in paragraph.spans
    assert Span("margins", italic=True) in paragraph.spans
    assert Span("the source", href="https://example.com/q3") in paragraph.spans
    assert isinstance(first_list, ListBlock) and isinstance(last_list, ListBlock)
    assert (first_list.ordered, first_list.start, len(first_list.items)) == (True, 1, 2)
    assert isinstance(first_list.items[1][1], ListBlock)  # the nested bullet list
    assert last_list.start == 2
    assert table == Table(
        header=((Span("Region"),), (Span("Revenue"),)), rows=(((Span("North"),), (Span("42"),)),)
    )


def test_raw_html_stays_text_and_images_keep_their_alt_text() -> None:
    (paragraph,) = parse_markdown("<script>alert(1)</script> ![a chart](c.png) `x < y`")

    assert paragraph == Paragraph(
        (
            Span("<script>alert(1)</script> "),
            Span("a chart"),
            Span(" "),
            Span("x < y", code=True),
        )
    )


# --- Word ----------------------------------------------------------------------


def test_a_word_document_uses_word_styles_for_the_markdown() -> None:
    document = Document(BytesIO(render_artifact(".docx", REPORT, DEJAVU)))
    styled = [(paragraph.style.name, paragraph.text) for paragraph in document.paragraphs]

    assert styled[:5] == [
        ("Heading 1", "Quarterly report"),
        ("Normal", "Revenue grew by 12% and margins held, see the source."),
        ("List Number", "First"),
        ("List Number", "Second"),
        ("List Bullet 2", "nested"),
    ]
    assert ("Quote", "Quoted words.") in styled
    assert ("List Number", "Again from two") in styled
    rows = [[cell.text for cell in row.cells] for row in document.tables[0].rows]
    assert rows == [["Region", "Revenue"], ["North", "42"]]
    header_run = document.tables[0].rows[0].cells[0].paragraphs[0].runs[0]
    assert header_run.bold is True


def test_a_word_document_keeps_bold_italic_and_links() -> None:
    document = Document(BytesIO(render_artifact(".docx", REPORT, DEJAVU)))
    paragraph = document.paragraphs[1]
    runs = {run.text: run for run in paragraph.runs}

    assert runs["12%"].bold is True
    assert runs["margins"].italic is True
    (hyperlink,) = paragraph._p.findall(qn("w:hyperlink"))
    relation = document.part.rels[hyperlink.get(qn("r:id"))]
    assert relation.target_ref == "https://example.com/q3"


def test_each_numbered_list_counts_from_its_own_start() -> None:
    document = Document(BytesIO(render_artifact(".docx", "1. a\n2. b\n\npara\n\n5. c", DEJAVU)))
    numbered = [p for p in document.paragraphs if p.style.name == "List Number"]
    ids = [p._p.pPr.numPr.numId.val for p in numbered]
    numbering = document.part.numbering_part.element

    assert ids[0] == ids[1] != ids[2]
    starts = [
        numbering.num_having_numId(num_id).find(qn("w:lvlOverride")).find(qn("w:startOverride"))
        for num_id in (ids[0], ids[2])
    ]
    assert [int(start.get(qn("w:val"))) for start in starts] == [1, 5]


# --- PDF -----------------------------------------------------------------------


@needs_dejavu
def test_a_pdf_prints_non_latin_text_in_the_configured_font() -> None:
    data = render_artifact(".pdf", f"# Отчёт\n\n{GREEK} and **bold** café", DEJAVU)
    reader = PdfReader(BytesIO(data))
    fonts = reader.pages[0]["/Resources"]["/Font"]

    text = pdf_text(data)
    assert "Отчёт" in text
    assert f"{GREEK} and bold café" in text
    embedded = [font.get_object() for font in fonts.values()]
    assert all(font["/Subtype"] == "/TrueType" for font in embedded)
    assert all("/FontFile2" in font["/FontDescriptor"] for font in embedded)
    assert reader.metadata is not None and reader.metadata.title == "Отчёт"


def test_without_the_font_a_pdf_still_prints_western_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    pdf_writer._fonts.cache_clear()  # fonts are looked up once per process
    with caplog.at_level(logging.WARNING):
        data = render_artifact(".pdf", REPORT, NO_FONT)

    text = pdf_text(data)
    assert "Quarterly report" in text
    assert "Revenue grew by 12% and margins held" in text
    assert "North" in text
    assert "artifacts.pdf_font_unavailable" in caplog.text


def test_a_pdf_link_is_clickable_and_only_for_web_addresses() -> None:
    markdown = "[site](https://example.com) and [mail](mailto:a@example.com)"
    reader = PdfReader(BytesIO(render_artifact(".pdf", markdown, NO_FONT)))
    targets = [link.get_object()["/A"]["/URI"] for link in reader.pages[0]["/Annots"]]

    assert targets == ["https://example.com", "mailto:a@example.com"]


def test_long_content_flows_onto_more_pages() -> None:
    markdown = "\n\n".join(f"Paragraph {number} " + "word " * 80 for number in range(60))
    data = render_artifact(".pdf", markdown, NO_FONT)

    assert len(PdfReader(BytesIO(data)).pages) > 3
    assert "Paragraph 59" in pdf_text(data)


def test_characters_no_document_can_hold_are_dropped() -> None:
    markdown = "bell\x07 form\x0cfeed half\udc80pair"

    document = Document(BytesIO(render_artifact(".docx", markdown, NO_FONT)))

    assert document.paragraphs[0].text == "bell formfeed halfpair"
    assert "bell formfeed halfpair" in pdf_text(render_artifact(".pdf", markdown, NO_FONT))


def test_empty_content_still_makes_valid_documents() -> None:
    assert len(PdfReader(BytesIO(render_artifact(".pdf", "", NO_FONT))).pages) == 1
    assert Document(BytesIO(render_artifact(".docx", "", NO_FONT))).paragraphs == []


# --- the registry --------------------------------------------------------------


def test_the_registry_lists_every_format_an_agent_can_save() -> None:
    assert artifact_extensions() == [".csv", ".docx", ".html", ".json", ".md", ".pdf", ".txt"]


@pytest.mark.parametrize("extension", [".txt", ".md", ".json", ".csv", ".html"])
def test_text_formats_are_saved_as_written(extension: str) -> None:
    assert render_artifact(extension, "Grüße <b>", NO_FONT) == "Grüße <b>".encode()


def test_an_unknown_format_names_the_ones_that_exist() -> None:
    with pytest.raises(UnsupportedFileType, match=r"'\.exe' files cannot be saved.*\.pdf"):
        render_artifact(".exe", "x", NO_FONT)


def test_a_renderer_failure_is_a_validation_error_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(content: str, options: RenderOptions) -> bytes:
        raise RuntimeError("layout failed")

    monkeypatch.setitem(registry.RENDERERS, ".pdf", broken)

    with pytest.raises(ValidationFailed, match="could not be laid out"):
        render_artifact(".pdf", "x", NO_FONT)
    assert RENDERERS[".pdf"] is broken
