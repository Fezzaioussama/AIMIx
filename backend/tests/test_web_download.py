"""The download core fetch_url and page imports share (api/services/web_download.py):
every redirect hop is held to the rules the link itself is, so a site cannot
redirect around them, and an address httpx cannot open is refused, not a crash.

Sites are httpx.MockTransport handlers and DNS is a fake resolver: nothing leaves
the process.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.tools import ToolException

from api.services.documents.web_import import PUBLIC_ONLY
from api.services.toolbox.config import toolbox_config
from api.services.toolbox.web import WebGateway
from tests.conftest import TEST_SETTINGS, UNUSED_WORKSPACE
from tests.site_fakes import ARTICLE, Handler, read_link, refused, resolver, use_site

#: Where a site may redirect that a link could not lead itself.
BAD_HOPS = [
    "https://user:secret-token@site.test/headers",  # sent as Basic auth, kept as the name
    "https://user@site.test/headers",
    "https://xn--n3h.net/",  # resolves, but IDNA 2008 refuses U+2603 (httpx raised)
]
HOP_IDS = ["credentials", "user-name", "idna-2008-refuses"]


def redirecting_to(target: str, requests: list[httpx.Request]) -> Handler:
    """/start redirects to ``target``; any other page is ARTICLE."""

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": target})
        return httpx.Response(200, text=ARTICLE)

    return handler


def fetch(handler: Handler, url: str) -> str:
    web = WebGateway(
        toolbox_config(TEST_SETTINGS, UNUSED_WORKSPACE), httpx.MockTransport(handler), resolver({})
    )
    return asyncio.run(web.fetch(url)).text


@pytest.mark.parametrize("target", BAD_HOPS, ids=HOP_IDS)
def test_a_link_cannot_be_redirected_where_it_could_not_lead_itself(
    app: FastAPI, auth_client: TestClient, target: str
) -> None:
    requests: list[httpx.Request] = []
    use_site(app, redirecting_to(target, requests))

    refused(read_link(auth_client, "https://site.test/start"), 400, "validation_error", PUBLIC_ONLY)
    assert [request.url.path for request in requests] == ["/start"]
    assert all("authorization" not in request.headers for request in requests)


@pytest.mark.parametrize("target", BAD_HOPS, ids=HOP_IDS)
def test_fetch_url_cannot_be_redirected_there_either(target: str) -> None:
    requests: list[httpx.Request] = []

    with pytest.raises(ToolException):
        fetch(redirecting_to(target, requests), "https://site.test/start")
    assert [request.url.path for request in requests] == ["/start"]


@pytest.mark.parametrize("url", ["https://xn--n3h.net/", "https://user:pw@site.test/"])
def test_such_a_link_given_directly_is_refused_too(url: str) -> None:
    requests: list[httpx.Request] = []

    with pytest.raises(ToolException):
        fetch(redirecting_to("/", requests), url)
    assert requests == []


def test_an_international_domain_name_is_still_followed(
    app: FastAPI, auth_client: TestClient
) -> None:
    requests: list[httpx.Request] = []
    use_site(app, redirecting_to("https://xn--bcher-kva.de/katalog", requests))  # bücher.de

    response = read_link(auth_client, "https://site.test/start")

    assert response.status_code == 200
    assert response.json()["filename"] == "https://xn--bcher-kva.de/katalog"
    assert requests[-1].url.host == "bücher.de"
