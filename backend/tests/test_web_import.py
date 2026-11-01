"""Reading a web page, or a file behind a link, into run-input text
(POST /api/documents/import-url): what a link can hold, and what cannot be read.
Site failures, the SSRF guard and the HTTP contract: test_web_import_guard.py.

Sites are httpx.MockTransport handlers (tests/site_fakes.py); nothing leaves the process.
"""

from __future__ import annotations

import codecs
import gzip
from collections.abc import AsyncIterator
from dataclasses import replace
from io import BytesIO

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter

from api.deps import app_settings, document_limits, document_ocr
from api.services.documents.web_import import BUILT_IN_BROWSER, UNSUPPORTED
from config.settings import Settings
from tests.conftest import TEST_SETTINGS
from tests.site_fakes import ARTICLE, read_link, refused, serving, use_site
from tests.test_document_scans import FakeOcr, encoded, page
from tests.test_documents import LIMITS, make_docx, make_pdf

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
NEKO = (
    "吾輩は猫である。名前はまだ無い。どこで生れたかとんと見当がつかぬ。"
    "何でも薄暗いじめじめした所でニャーニャー泣いていた事だけは記憶している。"
    "吾輩はここで始めて人間というものを見た。しかもあとで聞くとそれは書生という人間中で"
    "一番獰悪な種族であったそうだ。この書生というのは時々我々を捕えて煮て食うという話である。"
    "しかしその当時は何という考もなかったから別段恐しいとも思わなかった。"
    "ただ彼の掌に載せられてスーと持ち上げられた時何だかフワフワした感じがあったばかりである。"
)


# --- what a link can hold -----------------------------------------------------------


def test_a_web_page_reads_like_an_uploaded_document(app: FastAPI, auth_client: TestClient) -> None:
    markup = f"<html><head><title>RAG</title><script>track()</script></head><p>{ARTICLE}</p>"
    use_site(app, serving(markup, "text/html; charset=utf-8"))

    response = read_link(auth_client, "https://wiki.test/RAG")

    assert response.status_code == 200
    assert response.json() == {
        "filename": "https://wiki.test/RAG",
        "format": "html",
        "text": f"RAG\n{ARTICLE}",
        "characters": len(f"RAG\n{ARTICLE}"),
        "pages": None,
        "truncated": False,
    }


def test_the_document_is_named_after_the_page_redirected_to(
    app: FastAPI, auth_client: TestClient
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return httpx.Response(200, html=f"<p>{ARTICLE}</p>")

    use_site(app, handler)

    assert read_link(auth_client, "https://site.test/old").json()["filename"] == (
        "https://site.test/new"
    )


def test_a_shift_jis_page_declared_only_in_its_meta_tag(
    app: FastAPI, auth_client: TestClient
) -> None:
    meta = '<meta http-equiv="Content-Type" content="text/html;charset=Shift_JIS" />'
    markup = f"<html><head>{meta}</head><body><p>{NEKO}</p></body></html>"
    use_site(app, serving(markup.encode("shift_jis"), "text/html"))

    assert read_link(auth_client, "https://aozora.test/773.html").json()["text"] == NEKO


def test_the_charset_the_header_names_wins_over_the_meta_tag(
    app: FastAPI, auth_client: TestClient
) -> None:
    markup = f'<html><head><meta charset="shift_jis"></head><body><p>{NEKO}</p></body></html>'
    use_site(app, serving(markup.encode(), "text/html; charset=utf-8"))

    assert read_link(auth_client, "https://site.test/").json()["text"] == NEKO


def test_text_is_read_in_the_charset_the_header_names(
    app: FastAPI, auth_client: TestClient
) -> None:
    use_site(app, serving(NEKO.encode("shift_jis"), "text/plain; charset=Shift_JIS"))

    body = read_link(auth_client, "https://site.test/neko.txt").json()

    assert (body["format"], body["text"]) == ("txt", NEKO)


def test_a_byte_order_mark_wins_over_the_header(app: FastAPI, auth_client: TestClient) -> None:
    markup = f"<html><body><p>{NEKO}</p></body></html>"
    use_site(app, serving(codecs.BOM_UTF8 + markup.encode(), "text/html; charset=shift_jis"))

    assert read_link(auth_client, "https://site.test/").json()["text"] == NEKO


def test_a_two_byte_page_near_the_size_limit_is_not_refused(
    app: FastAPI, auth_client: TestClient
) -> None:
    page = NEKO.encode("shift_jis")  # as UTF-8 it would be half as long again
    app.dependency_overrides[document_limits] = lambda: replace(LIMITS, max_bytes=len(page))
    use_site(app, serving(page, "text/plain; charset=Shift_JIS"))

    assert read_link(auth_client, "https://site.test/neko.txt").json()["text"] == NEKO


def test_a_table_row_keeps_its_numbers_apart(app: FastAPI, auth_client: TestClient) -> None:
    row = "<tr><td>France</td><td>69,081,996</td><td>0.8%</td></tr>"
    use_site(app, serving(f"<p>{ARTICLE}</p><table>{row}</table>", "text/html"))

    lines = read_link(auth_client, "https://site.test/").json()["text"].splitlines()

    assert "France | 69,081,996 | 0.8%" in lines


def test_a_pdf_link_reads_its_pages(app: FastAPI, auth_client: TestClient) -> None:
    pdf = make_pdf(["Attention is all you need", "Second page"])
    use_site(app, serving(pdf, "application/pdf"))

    body = read_link(auth_client, "https://arxiv.test/pdf/1706.03762").json()

    assert (body["filename"], body["format"], body["pages"]) == (
        "https://arxiv.test/pdf/1706.03762",
        "pdf",
        2,
    )
    assert "Attention is all you need" in body["text"]


@pytest.mark.parametrize("content_type", ["application/octet-stream", ""])
def test_a_pdf_sent_as_bare_bytes_is_known_by_its_signature(
    app: FastAPI, auth_client: TestClient, content_type: str
) -> None:
    use_site(app, serving(make_pdf(["Signed contract"]), content_type))

    body = read_link(auth_client, "https://files.test/download?id=7").json()

    assert body["format"] == "pdf"
    assert "Signed contract" in body["text"]


def test_a_word_document_link_keeps_its_tables(app: FastAPI, auth_client: TestClient) -> None:
    use_site(app, serving(make_docx(), DOCX))

    body = read_link(auth_client, "https://files.test/report").json()

    assert body["format"] == "docx"
    assert body["text"].splitlines() == [
        "Quarterly report",
        "Region | Revenue",
        "North | 42",
        "End of report",
    ]


def test_bare_bytes_fall_back_to_the_extension_in_the_link(
    app: FastAPI, auth_client: TestClient
) -> None:
    use_site(app, serving(make_docx(), "application/octet-stream"))

    assert read_link(auth_client, "https://files.test/Report.DOCX").json()["format"] == "docx"


def test_a_picture_link_is_read_by_ocr(app: FastAPI, auth_client: TestClient) -> None:
    app.dependency_overrides[document_ocr] = lambda: FakeOcr()
    use_site(app, serving(encoded(page(), "PNG"), "image/png"))

    body = read_link(auth_client, "https://site.test/chart.png").json()

    assert (body["format"], body["text"]) == ("png", "Recognised text 1")


# --- what cannot be read --------------------------------------------------------------


class Unread(httpx.AsyncByteStream):
    """A body that must never be read."""

    async def __aiter__(self) -> AsyncIterator[bytes]:
        raise AssertionError("the body was read")
        yield b""  # pragma: no cover - unreachable, keeps this a generator


def test_a_type_no_reader_handles_is_refused_before_its_body_is_read(
    app: FastAPI, auth_client: TestClient
) -> None:
    video = httpx.Response(200, headers={"content-type": "video/mp4"}, stream=Unread())
    use_site(app, lambda request: video)

    response = read_link(auth_client, "https://site.test/clip")

    refused(response, 415, "unsupported_document", UNSUPPORTED)


@pytest.mark.parametrize("url", ["https://site.test/setup.exe", "https://site.test/download"])
def test_bare_bytes_with_no_readable_extension_are_refused(
    app: FastAPI, auth_client: TestClient, url: str
) -> None:
    use_site(app, serving(b"MZ\x90\x00", "application/octet-stream"))

    refused(read_link(auth_client, url), 415, "unsupported_document", UNSUPPORTED)


def test_a_file_over_the_size_limit_is_refused_not_cut(
    app: FastAPI, auth_client: TestClient
) -> None:
    app.dependency_overrides[document_limits] = lambda: replace(LIMITS, max_bytes=1_000)
    use_site(app, serving(b"%PDF-1.4\n" + b"%" * 2_000, "application/pdf"))

    response = read_link(auth_client, "https://site.test/big.pdf")

    assert response.status_code == 413
    assert response.json()["error"] == "document_too_large"


def test_a_compressed_bomb_stops_at_the_size_limit(app: FastAPI, auth_client: TestClient) -> None:
    app.dependency_overrides[document_limits] = lambda: LIMITS
    bomb = gzip.compress(b"a" * 30_000_000)  # about 30 KB on the wire
    headers = {"content-encoding": "gzip", "content-type": "text/plain"}
    use_site(
        app, lambda request: httpx.Response(200, stream=httpx.ByteStream(bomb), headers=headers)
    )

    assert read_link(auth_client, "https://site.test/bomb").status_code == 413


@pytest.mark.parametrize(
    "markup",
    [
        '<html><head><title>Excalidraw</title></head><body><div id="root"></div>'
        '<script src="/app.js"></script><noscript>Enable JavaScript.</noscript></body></html>',
        "<div id=root></div><script>render()</script>",
    ],
)
def test_a_page_built_by_javascript_is_refused_with_advice(
    app: FastAPI, auth_client: TestClient, markup: str
) -> None:
    use_site(app, serving(markup, "text/html"))

    refused(
        read_link(auth_client, "https://app.test/"), 422, "document_unreadable", BUILT_IN_BROWSER
    )


def test_a_short_text_file_is_not_taken_for_a_javascript_page(
    app: FastAPI, auth_client: TestClient
) -> None:
    use_site(app, serving("Short note.", "text/plain"))

    assert read_link(auth_client, "https://site.test/note.txt").json()["text"] == "Short note."


def test_the_javascript_check_can_be_turned_off(app: FastAPI, auth_client: TestClient) -> None:
    lenient = TEST_SETTINGS.model_copy(update={"document_url_min_text_chars": 0})
    app.dependency_overrides[app_settings] = lambda: lenient
    use_site(app, serving("<p>Hi</p>", "text/html"))

    assert read_link(auth_client, "https://site.test/").json()["text"] == "Hi"


def test_a_password_protected_pdf_keeps_its_message(app: FastAPI, auth_client: TestClient) -> None:
    writer = PdfWriter()
    for sheet in PdfReader(BytesIO(make_pdf(["secret"]))).pages:
        writer.add_page(sheet)
    writer.encrypt("hunter2")
    locked = BytesIO()
    writer.write(locked)
    use_site(app, serving(locked.getvalue(), "application/pdf"))

    response = read_link(auth_client, "https://site.test/locked.pdf")

    assert response.status_code == 422
    assert "password" in response.json()["detail"]


def test_reading_a_link_has_finite_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.document_url_max_seconds == 60.0
    assert settings.document_url_min_text_chars == 200
