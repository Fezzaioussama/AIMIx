"""Image generation: the Muse Image adapter's request and failure contract, and the
generate_image tool (when it is offered: test_vision.py). Offline: the openai client
and the generator are fakes."""

from __future__ import annotations

import base64
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.tools import ToolException

from api.services.toolbox.images import ImageStudio
from llm.base import ProviderConfig
from llm.exceptions import ProviderRequestError, ProviderTimeout
from llm.images import GeneratedImage, MetaImageGenerator
from llm.retry import RetryPolicy
from tests.retry_fakes import INSTANT, openai_status, openai_timeout
from tests.test_toolbox import local_workspace

JPEG = b"\xff\xd8\xff\xe0fake"
NO_RETRIES = replace(INSTANT, retry=RetryPolicy(0, 0.0, 0.0))


def answer(encoded: str | None) -> SimpleNamespace:
    return SimpleNamespace(data=[SimpleNamespace(b64_json=encoded)] if encoded else [])


class _Images:
    """Stands in for ``client.images``: each ``generate`` plays the next answer."""

    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.calls: list[dict[str, Any]] = []

    def generate(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        result = self.answers.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def generator(
    monkeypatch: pytest.MonkeyPatch, images: _Images, config: ProviderConfig = INSTANT
) -> MetaImageGenerator:
    client = SimpleNamespace(images=images)
    monkeypatch.setattr("llm.providers.meta.OpenAI", lambda **kwargs: client)
    return MetaImageGenerator(replace(config, default_model="muse-image-1.0"))


def test_a_picture_is_asked_for_as_one_jpeg_in_the_chosen_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    images = _Images(answer(base64.b64encode(JPEG).decode()))

    assert generator(monkeypatch, images).generate("A red fox", "landscape").jpeg == JPEG
    assert images.calls == [
        {
            "model": "muse-image-1.0",
            "prompt": "A red fox",
            "size": "1792x1024",
            "n": 1,
            "response_format": "b64_json",
            "output_format": "jpeg",
        }
    ]


def test_a_busy_api_is_retried_under_the_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    images = _Images(openai_status(503), answer(base64.b64encode(JPEG).decode()))

    assert generator(monkeypatch, images).generate("A fox", "square").jpeg == JPEG
    assert len(images.calls) == 2


@pytest.mark.parametrize(
    ("result", "error"),
    [
        (openai_status(400), ProviderRequestError),  # e.g. content_policy_violation
        (openai_timeout(), ProviderTimeout),
        (answer(None), ProviderRequestError),
        (answer("not base64!"), ProviderRequestError),
    ],
    ids=["refused", "timeout", "no-image", "unreadable"],
)
def test_failures_keep_the_provider_contract(
    monkeypatch: pytest.MonkeyPatch, result: Any, error: type[Exception]
) -> None:
    with pytest.raises(error):
        generator(monkeypatch, _Images(result), NO_RETRIES).generate("A fox", "square")


class FakeGenerator:
    def __init__(self, result: GeneratedImage | Exception = GeneratedImage(JPEG)) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def generate(self, description: str, shape: str) -> GeneratedImage:
        self.calls.append((description, shape))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_the_tool_saves_a_new_jpeg_and_says_how_to_show_it(tmp_path: Path) -> None:
    fake = FakeGenerator()
    studio = ImageStudio(fake, local_workspace(tmp_path))

    reply = studio.create("A red fox in the snow", "images/fox", "portrait")

    assert (tmp_path / "images" / "fox.jpg").read_bytes() == JPEG
    assert "![a short description](images/fox.jpg)" in reply
    assert fake.calls == [("A red fox in the snow", "portrait")]


@pytest.mark.parametrize(
    ("description", "path", "shape"),
    [("A fox", "fox.jpg", "panorama"), ("  ", "fox.jpg", "square"), ("A fox", "", "square")],
    ids=["unknown-shape", "no-description", "no-file-name"],
)
def test_the_tool_refuses_a_request_it_cannot_draw(
    tmp_path: Path, description: str, path: str, shape: str
) -> None:
    fake = FakeGenerator()

    with pytest.raises(ToolException):
        ImageStudio(fake, local_workspace(tmp_path)).create(description, path, shape)
    assert fake.calls == []


def test_a_refused_picture_reaches_the_model_as_a_tool_error(tmp_path: Path) -> None:
    studio = ImageStudio(
        FakeGenerator(ProviderRequestError("meta could not answer the request.")),
        local_workspace(tmp_path),
    )

    with pytest.raises(ToolException, match="Describe it differently"):
        studio.create("A fox", "fox.jpg")


def test_the_tool_never_overwrites_a_file(tmp_path: Path) -> None:
    (tmp_path / "fox.jpg").write_bytes(b"the user's own")

    with pytest.raises(ToolException):
        ImageStudio(FakeGenerator(), local_workspace(tmp_path)).create("A fox", "fox.jpg")
    assert (tmp_path / "fox.jpg").read_bytes() == b"the user's own"
