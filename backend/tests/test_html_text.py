"""HTML read the same way by fetch_url, uploaded .html files and pages read from a
link: the charset a page declares in its own <meta> tag, and table cells kept apart.
"""

from __future__ import annotations

import asyncio
import codecs
from pathlib import Path

import httpx
import pytest

from api.services.documents.extraction import extract_document
from api.services.toolbox.config import toolbox_config
from api.services.toolbox.html_text import (
    PRESCAN_BYTES,
    declared_charset,
    decode_page,
    html_to_text,
)
from api.services.toolbox.web import WebGateway
from tests.conftest import TEST_SETTINGS
from tests.test_documents import LIMITS

JAPANESE = "吾輩は猫である。名前はまだ無い。"


def japanese_page(meta: str, charset: str = "shift_jis") -> bytes:
    return f"<html><head>{meta}</head><body><p>{JAPANESE}</p></body></html>".encode(charset)


@pytest.mark.parametrize(
    "meta",
    [
        '<meta charset="Shift_JIS">',
        "<meta charset=shift_jis>",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=Shift_JIS">',
        '<meta http-equiv="Content-Type" content="text/html;charset=Shift_JIS" />',
    ],
)
def test_a_page_names_its_charset_in_a_meta_tag(meta: str) -> None:
    charset = declared_charset(japanese_page(meta))
    assert charset is not None
    assert codecs.lookup(charset).name == "shift_jis"


def test_a_page_that_declares_nothing_names_no_charset() -> None:
    assert declared_charset(b"<html><body><p>Plain</p></body></html>") is None


def test_a_declaration_past_the_prescan_is_not_looked_for() -> None:
    late = b"<!--" + b"x" * PRESCAN_BYTES + b'--><meta charset="shift_jis">'
    assert declared_charset(late) is None


def test_decoding_drops_a_utf8_byte_order_mark() -> None:
    assert decode_page(codecs.BOM_UTF8 + "café".encode(), "utf-8") == "café"
    assert decode_page(codecs.BOM_UTF8 + "café".encode(), None) == "café"


def test_table_cells_stay_apart() -> None:
    markup = (
        "<table><tr><th>Country</th><th>Population</th><th>Share</th></tr>"
        "<tr><td>France</td><td>69,081,996</td><td>0.8%</td></tr></table>"
    )
    assert html_to_text(markup) == "Country | Population | Share\nFrance | 69,081,996 | 0.8%"


def test_a_cell_that_holds_blocks_leaves_no_line_of_separators() -> None:
    markup = (
        "<table><tr><th>Products</th><td><ul><li>Tea</li><li>Coffee</li></ul></td></tr></table>"
    )
    assert html_to_text(markup) == "Products\nTea\nCoffee"


def test_an_uploaded_page_is_read_in_the_charset_its_meta_tag_declares() -> None:
    page = japanese_page('<meta http-equiv="Content-Type" content="text/html; charset=Shift_JIS">')
    assert extract_document("neko.html", page, LIMITS).text == JAPANESE


def test_a_byte_order_mark_wins_over_the_meta_tag() -> None:
    # The HTML standard's order: a BOM, then what the page itself declares.
    page = codecs.BOM_UTF8 + japanese_page('<meta charset="shift_jis">', charset="utf-8")
    assert extract_document("neko.html", page, LIMITS).text == JAPANESE


def test_an_uploaded_table_keeps_its_cells_apart() -> None:
    page = b"<table><tr><td>Revenue</td><td>12</td><td>14</td></tr></table>"
    assert extract_document("report.html", page, LIMITS).text == "Revenue | 12 | 14"


def fetched(page: bytes, content_type: str = "text/html") -> str:
    """What fetch_url reads of ``page``, served as ``content_type``."""

    async def public(host: str) -> list[str]:
        return ["93.184.215.14"]

    site = httpx.MockTransport(
        lambda request: httpx.Response(200, content=page, headers={"content-type": content_type})
    )
    web = WebGateway(toolbox_config(TEST_SETTINGS, Path("unused")), site, public)
    return asyncio.run(web.fetch("https://site.test/page.html")).text


@pytest.mark.parametrize(
    ("page", "content_type"),
    [
        (codecs.BOM_UTF8 + japanese_page('<meta charset="shift_jis">', "utf-8"), "text/html"),
        (codecs.BOM_UTF8 + japanese_page("", "utf-8"), "text/html; charset=shift_jis"),
        ("\ufeff".encode("utf-16-le") + japanese_page("", "utf-16-le"), "text/html"),
    ],
    ids=["bom-over-meta", "bom-over-header", "utf-16-bom"],
)
def test_fetch_url_reads_a_page_as_an_upload_does(page: bytes, content_type: str) -> None:
    # A byte order mark wins over the header and the <meta> tag alike (the HTML standard).
    assert extract_document("neko.html", page, LIMITS).text == JAPANESE
    assert fetched(page, content_type) == JAPANESE
