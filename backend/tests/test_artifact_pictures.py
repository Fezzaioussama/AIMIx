"""Pictures in saved documents: ``![alt](path)`` on a line of its own shows a PNG or
JPEG of the user's workspace in a .docx or .pdf; anything else stays its alt text."""

from __future__ import annotations

import zipfile
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader

from api.services.artifacts.docx_writer import render_docx
from api.services.artifacts.markdown import (
    ListBlock,
    Paragraph,
    Picture,
    Span,
    load_pictures,
    parse_markdown,
)
from api.services.artifacts.pdf_writer import render_pdf
from tests.test_toolbox import RENDER, WORKSPACE_LIMITS, local_workspace


def png(width: int = 40, height: int = 20) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), "teal").save(buffer, "PNG")
    return buffer.getvalue()


def pdf_images(data: bytes) -> int:
    return sum(len(page.images) for page in PdfReader(BytesIO(data)).pages)


def docx_media(data: bytes) -> list[str]:
    return [name for name in zipfile.ZipFile(BytesIO(data)).namelist() if "/media/" in name]


def test_an_image_on_its_own_line_is_a_picture() -> None:
    assert parse_markdown("![The *launch* hero](images/hero.png)") == (
        Picture("images/hero.png", "The launch hero"),
    )


def test_pictures_load_wherever_they_are_and_fall_back_to_their_alt_text() -> None:
    blocks = parse_markdown("![Found](a.png)\n\n- ![Missing](b.png)")

    loaded = load_pictures(blocks, {"a.png": b"bytes"}.get)

    assert loaded[0] == Picture("a.png", "Found", b"bytes")
    assert loaded[1] == ListBlock(False, 1, ((Paragraph((Span("Missing"),)),),))
    assert load_pictures(blocks, None)[0] == Paragraph((Span("Found"),))


def test_a_word_document_embeds_its_pictures() -> None:
    options = replace(RENDER, pictures={"hero.png": png()}.get)

    assert docx_media(render_docx("# Plan\n\n![Hero](hero.png)", options)) == [
        "word/media/image1.png"
    ]


def test_a_pdf_embeds_its_pictures_even_a_huge_one() -> None:
    options = replace(RENDER, pictures={"wide.png": png(4000, 400)}.get)

    assert pdf_images(render_pdf("# Plan\n\n![Wide](wide.png)", options)) == 1


@pytest.mark.parametrize(
    "src",
    ["../outside.png", "https://example.com/hero.png", "notes.txt", "missing.png"],
    ids=["outside", "web", "not-a-picture", "missing"],
)
def test_a_saved_document_shows_only_pictures_of_the_workspace(tmp_path: Path, src: str) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (tmp_path / "outside.png").write_bytes(png())
    (root / "notes.txt").write_text("not a picture")
    (root / "hero.png").write_bytes(png())
    limits = replace(WORKSPACE_LIMITS, max_file_bytes=500_000)
    workspace = local_workspace(root, limits, quota=1_000_000)

    workspace.save_artifact("shown.pdf", "![Hero](hero.png)")
    workspace.save_artifact("refused.pdf", f"![Alt text]({src})")

    assert pdf_images((root / "shown.pdf").read_bytes()) == 1
    refused = (root / "refused.pdf").read_bytes()
    assert pdf_images(refused) == 0
    assert "Alt text" in PdfReader(BytesIO(refused)).pages[0].extract_text()
