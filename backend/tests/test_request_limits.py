"""The request body caps: counted as the body arrives, so a body without a
Content-Length (chunked) is refused too, before authentication runs."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.types import Message

from api.main import create_app
from api.middleware import RequestSizeLimitMiddleware
from api.models import Base
from api.services.documents.extraction import megabytes
from config.settings import MULTIPART_OVERHEAD_BYTES, pin_settings
from tests.conftest import TEST_SETTINGS

DOCUMENT_MAX_BYTES = 100
JSON_MAX_BYTES = 1_000
MULTIPART_CAP = DOCUMENT_MAX_BYTES + MULTIPART_OVERHEAD_BYTES
UPLOAD_TOO_LARGE = (
    f"The upload is larger than the {megabytes(DOCUMENT_MAX_BYTES)} limit. "
    f"Send one file at a time, each up to {megabytes(DOCUMENT_MAX_BYTES)}."
)


@pytest.fixture
def capped() -> Iterator[TestClient]:
    """The real app, with small caps."""
    limits = {"document_max_bytes": DOCUMENT_MAX_BYTES, "request_max_json_bytes": JSON_MAX_BYTES}
    pin_settings(TEST_SETTINGS.model_copy(update=limits))
    try:
        application = create_app()
    finally:
        pin_settings(TEST_SETTINGS)
    Base.metadata.create_all(application.state.database.engine)
    with TestClient(application) as client:
        yield client


def chunked(data: bytes, size: int = 64 * 1024) -> Iterator[bytes]:
    """A body httpx sends with ``Transfer-Encoding: chunked`` and no Content-Length."""
    for start in range(0, len(data), size):
        yield data[start : start + size]


def multipart(file_bytes: int) -> tuple[bytes, dict[str, str]]:
    body = (
        b'--cut\r\nContent-Disposition: form-data; name="file"; filename="a.txt"\r\n'
        b"Content-Type: text/plain\r\n\r\n" + b"x" * file_bytes + b"\r\n--cut--\r\n"
    )
    return body, {"content-type": "multipart/form-data; boundary=cut"}


def assert_too_large(response: Response) -> None:
    assert response.status_code == 413
    assert response.json()["error"] == "request_too_large"
    assert set(response.json()) == {"error", "detail"}
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("path", ["/api/files", "/api/documents/extract"])
def test_a_chunked_upload_over_the_cap_is_refused_before_authentication(
    capped: TestClient, path: str
) -> None:
    body, headers = multipart(MULTIPART_CAP)

    response = capped.post(path, content=chunked(body), headers=headers)

    assert_too_large(response)


@pytest.mark.parametrize("chunks", [False, True])
def test_an_oversize_upload_is_refused_with_the_file_limit_people_know(
    capped: TestClient, chunks: bool
) -> None:
    """The cap has room for the multipart framing, but the refusal names the file limit."""
    body, headers = multipart(MULTIPART_CAP)

    response = capped.post(
        "/api/documents/extract", content=chunked(body) if chunks else body, headers=headers
    )

    assert_too_large(response)
    assert response.json()["detail"] == UPLOAD_TOO_LARGE


def test_several_small_files_are_not_told_one_of_them_is_too_large() -> None:
    """POST /api/files takes several files: two under the file limit can pass the cap."""
    guarded = RequestSizeLimitMiddleware(
        FastAPI(), max_bytes=2_000_000, max_json_bytes=10, max_file_bytes=1_500_000
    )
    two_parts = b"".join(multipart(1_200_000)[0] for _ in range(2))
    response = TestClient(guarded).post("/", content=two_parts, headers=multipart(0)[1])

    assert response.status_code == 413
    assert response.json()["detail"] == (
        "The upload is larger than the 1.5 MB limit. Send one file at a time, each up to 1.5 MB."
    )


def test_an_oversize_json_body_still_names_the_request_limit(capped: TestClient) -> None:
    response = capped.post("/api/login", json={"username": "u", "password": "p" * JSON_MAX_BYTES})
    detail = f"The request is larger than the {megabytes(JSON_MAX_BYTES)} limit."
    assert response.json()["detail"] == detail


def test_a_chunked_upload_under_the_cap_still_reaches_authentication(capped: TestClient) -> None:
    body, headers = multipart(10)
    response = capped.post("/api/documents/extract", content=chunked(body), headers=headers)
    assert response.status_code == 401


def test_a_chunked_json_body_over_the_json_cap_is_refused(capped: TestClient) -> None:
    body = b'{"username": "u", "password": "' + b"p" * JSON_MAX_BYTES + b'"}'

    response = capped.post(
        "/api/login", content=chunked(body, 100), headers={"content-type": "application/json"}
    )

    assert_too_large(response)


def test_a_declared_json_body_over_the_json_cap_is_refused(capped: TestClient) -> None:
    response = capped.post("/api/login", json={"username": "u", "password": "p" * JSON_MAX_BYTES})
    assert_too_large(response)


def test_a_json_body_under_the_cap_is_served(capped: TestClient) -> None:
    response = capped.post("/api/login", json={"username": "nobody", "password": "wrong"})
    assert response.status_code == 401


def test_the_json_cap_does_not_shrink_the_upload_cap(capped: TestClient) -> None:
    """An upload bigger than the JSON cap but within its own cap is not refused for size."""
    body, headers = multipart(DOCUMENT_MAX_BYTES * 20)
    assert len(body) > JSON_MAX_BYTES
    response = capped.post("/api/documents/extract", content=chunked(body), headers=headers)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_reading_stops_at_the_cap_without_draining_the_body() -> None:
    """Chunks past the cap are never pulled from the client."""

    async def echo(request: Request) -> PlainTextResponse:
        return PlainTextResponse(str(len(await request.body())))

    guarded = RequestSizeLimitMiddleware(
        Starlette(routes=[Route("/", echo, methods=["POST"])]),
        max_bytes=10,
        max_json_bytes=10,
        max_file_bytes=5,
    )
    chunks = [{"type": "http.request", "body": b"abcd", "more_body": True} for _ in range(10)]
    pulled: list[Message] = []
    sent: list[Message] = []

    async def receive() -> Message:
        pulled.append(chunks[len(pulled)])
        return pulled[-1]

    async def send(message: Message) -> None:
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/", "headers": [], "query_string": b""}
    await guarded(scope, receive, send)

    assert len(pulled) == 3  # 12 bytes: one chunk past the 10-byte cap
    assert sent[0]["type"] == "http.response.start" and sent[0]["status"] == 413
    assert b"request_too_large" in sent[1]["body"]


def test_the_real_app_uses_the_configured_caps(app: FastAPI) -> None:
    guard = next(m for m in app.user_middleware if m.cls is RequestSizeLimitMiddleware)
    assert guard.kwargs == {
        "max_bytes": TEST_SETTINGS.max_request_bytes,
        "max_json_bytes": TEST_SETTINGS.request_max_json_bytes,
        "max_file_bytes": TEST_SETTINGS.document_max_bytes,
    }
