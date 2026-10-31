"""Finding objects: the SAM 3.1 adapter's request, parsing and failure contract, the
find_objects tool, and when the tools on the Meta key are offered. Offline: the
openai client and the models are fakes."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.tools import ToolException
from PIL import Image

from api.models import User
from api.services import agent_tools
from api.services.toolbox.config import MetaTools
from api.services.toolbox.registry import toolbox_tools
from api.services.toolbox.vision import ObjectSpotter
from llm.base import ProviderConfig
from llm.exceptions import ProviderRequestError, ProviderTimeout
from llm.retry import RetryPolicy
from llm.vision import OPTIONS, Box, Detection, MetaObjectFinder
from tests.retry_fakes import INSTANT, openai_status, openai_timeout
from tests.test_images import FakeGenerator
from tests.test_toolbox import CONFIG, WORKSPACE_LIMITS, local_workspace

NO_RETRIES = replace(INSTANT, retry=RetryPolicy(0, 0.0, 0.0))
TWO_LOAVES = (
    "<0f>0<|box;x1=10;y1=20;x2=30;y2=40;w=64;h=48;c=0.94|><|mask;x=0;y=0;data=1,2,!!|>,"
    "1<|box;x1=35;y1=5;x2=60;y2=25;w=64;h=48;c=0.53|><|mask;x=0;y=0;data=3,4,!!|>"
)
NOON = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)


class _Responses:
    """Stands in for ``client.responses``: each ``create`` plays the next answer."""

    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        result = self.answers.pop(0)
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(output_text=result)


def finder(
    monkeypatch: pytest.MonkeyPatch, responses: _Responses, config: ProviderConfig = INSTANT
) -> MetaObjectFinder:
    client = SimpleNamespace(responses=responses)
    monkeypatch.setattr("llm.providers.meta.OpenAI", lambda **kwargs: client)
    return MetaObjectFinder(replace(config, default_model="sam-3.1"))


def test_a_search_sends_the_phrase_and_the_picture_and_reads_every_box(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = _Responses(TWO_LOAVES)

    found = finder(monkeypatch, responses).find(b"\xff\xd8jpeg", "image/jpeg", "loaf of bread")

    assert found == Detection((Box(10, 20, 30, 40, 0.94), Box(35, 5, 60, 25, 0.53)))
    (call,) = responses.calls
    assert (call["model"], call["metadata"]) == ("sam-3.1", OPTIONS)
    (message,) = call["input"]
    assert message["content"] == [
        {"type": "input_text", "text": "loaf of bread"},
        {"type": "input_image", "image_url": "data:image/jpeg;base64,/9hqcGVn"},
    ]


def test_no_match_is_an_empty_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    assert finder(monkeypatch, _Responses("<0f>")).find(b"x", "image/png", "unicorn") == (
        Detection(())
    )


def test_a_busy_api_is_retried_under_the_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = _Responses(openai_status(503), TWO_LOAVES)

    assert len(finder(monkeypatch, responses).find(b"x", "image/png", "loaf").boxes) == 2
    assert len(responses.calls) == 2


@pytest.mark.parametrize(
    ("answer", "error"),
    [
        (openai_status(400), ProviderRequestError),
        (openai_timeout(), ProviderTimeout),
        ("<0f>0<|box;x1=1;y1=oops|>", ProviderRequestError),
    ],
    ids=["refused", "timeout", "unreadable-box"],
)
def test_failures_keep_the_provider_contract(
    monkeypatch: pytest.MonkeyPatch, answer: Any, error: type[Exception]
) -> None:
    with pytest.raises(error):
        finder(monkeypatch, _Responses(answer), NO_RETRIES).find(b"x", "image/png", "loaf")


class FakeFinder:
    def __init__(self, result: Detection | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def find(self, image: bytes, media_type: str, what: str) -> Detection:
        self.calls.append((media_type, what))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def spotter(tmp_path: Path, result: Detection | Exception) -> tuple[ObjectSpotter, FakeFinder]:
    picture = BytesIO()
    Image.new("RGB", (64, 48), "wheat").save(picture, "PNG")
    (tmp_path / "shelf.png").write_bytes(picture.getvalue())
    (tmp_path / "notes.txt").write_text("not a picture")
    workspace = local_workspace(tmp_path, replace(WORKSPACE_LIMITS, max_file_bytes=200_000))
    fake = FakeFinder(result)
    return ObjectSpotter(fake, workspace, clock=lambda: NOON), fake


def test_the_tool_counts_the_matches_and_saves_a_marked_copy(tmp_path: Path) -> None:
    tool, fake = spotter(tmp_path, Detection((Box(10, 20, 30, 40, 0.94), Box(35, 5, 60, 25, 0.5))))

    report = tool.find("shelf.png", " Loaf of bread ")

    marked = "shelf-loaf-of-bread-20261031-120000.jpg"
    assert fake.calls == [("image/png", "Loaf of bread")]
    assert report.startswith('Found 2 matches for "Loaf of bread" in shelf.png')
    assert "1. (10, 20) to (30, 40), confidence 94%" in report
    assert f"![a short description]({marked})" in report
    with Image.open(tmp_path / marked) as copy:
        assert (copy.format, copy.size) == ("JPEG", (64, 48))


def test_no_match_saves_nothing(tmp_path: Path) -> None:
    tool, _ = spotter(tmp_path, Detection(()))

    assert tool.find("shelf.png", "unicorn") == "No unicorn found in shelf.png."
    assert sorted(path.name for path in tmp_path.iterdir()) == ["notes.txt", "shelf.png"]


@pytest.mark.parametrize(
    ("path", "what"),
    [("shelf.png", "  "), ("notes.txt", "loaf"), ("missing.png", "loaf")],
    ids=["nothing-named", "not-a-picture", "missing"],
)
def test_the_tool_refuses_what_it_cannot_look_at(tmp_path: Path, path: str, what: str) -> None:
    tool, fake = spotter(tmp_path, Detection(()))

    with pytest.raises(ToolException):
        tool.find(path, what)
    assert fake.calls == []


def test_a_failed_search_reaches_the_model_as_a_tool_error(tmp_path: Path) -> None:
    tool, _ = spotter(tmp_path, ProviderRequestError("meta could not answer the request."))

    with pytest.raises(ToolException, match=r"SAM 3\.1"):
        tool.find("shelf.png", "loaf")


META_TOOLS = ("generate_image", "find_objects")


def test_the_meta_tools_are_offered_only_with_a_meta_key(tmp_path: Path) -> None:
    config = replace(CONFIG, enabled=META_TOOLS, workspace_dir=tmp_path)
    models = MetaTools(FakeGenerator(), FakeFinder(Detection(())))

    assert toolbox_tools(config) == []
    assert tuple(tool.name for tool in toolbox_tools(replace(config, meta=models))) == META_TOOLS


def test_an_account_with_a_saved_meta_key_gets_the_meta_tools(
    app: FastAPI, auth_client: TestClient, user: User, tmp_path: Path
) -> None:
    settings = agent_tools.get_settings().model_copy(
        update={"workspace_dir": tmp_path, "agent_builtin_tools": list(META_TOOLS)}
    )

    def names() -> tuple[str, ...]:
        tools = agent_tools.native_tools(app.state.database, user, settings)
        return tuple(tool.name for tool in tools if tool.name in META_TOOLS)

    assert names() == ()
    saved = auth_client.put(
        "/api/llm-settings",
        json={
            "provider": "openrouter",
            "providers": [
                {"name": "meta", "default_model": "muse-spark-1.3", "api_key": "meta-key"}
            ],
        },
    )
    assert saved.status_code == 200
    assert names() == META_TOOLS
